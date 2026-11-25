"""ユーザーコードを隔離して実行する。

多層防御 (docs/expansion/m3-design.md §2):
1. コンテナ: ネットワークなし (network_mode: none)、読み取り専用ルート FS、
   /tmp のみ tmpfs、最小ケーパビリティ、no-new-privileges、pids/メモリ/CPU 上限
2. プロセス: 実行ごとに専用 uid (スロット) へ setuid し、サーバープロセスや
   他の実行に触れられないようにする。setrlimit で CPU 時間・メモリ・プロセス数・
   ファイルサイズ・FD 数を制限。プロセスグループごと強制終了する
3. 出力: stdout/stderr はファイルに書かせ (RLIMIT_FSIZE で上限)、先頭だけ読む

本番では gVisor (runsc) などのサンドボックスランタイムと組み合わせること (ADR-7)。
"""
from __future__ import annotations

import os
import resource
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Language = Literal["python", "javascript", "typescript"]
Status = Literal["passed", "failed", "error", "timeout"]

OUTPUT_LIMIT_BYTES = 64 * 1024
FILE_SIZE_LIMIT_BYTES = 1024 * 1024
PYTHON_MEMORY_BYTES = 256 * 1024 * 1024
NODE_HEAP_MB = 128
MAX_PROCESSES = 32

SOURCE_FILE: dict[str, str] = {
    "python": "main.py",
    "javascript": "main.js",
    "typescript": "main.ts",
}


def _command(language: Language, path: str) -> list[str]:
    if language == "python":
        # -I: 環境変数・ユーザー site-packages を無視 / -B: .pyc を書かない
        return ["/usr/bin/python3", "-I", "-B", path]
    node = ["node", f"--max-old-space-size={NODE_HEAP_MB}", "--disallow-code-generation-from-strings"]
    if language == "typescript":
        # 型注釈のみ取り除いて実行する (enum / namespace など変換が必要な構文は非対応)
        node += ["--experimental-strip-types", "--no-warnings"]
    return [*node, path]


@dataclass(frozen=True)
class TestCase:
    stdin: str
    expected: str


@dataclass(frozen=True)
class TestResult:
    status: Status
    stdout: str
    stderr: str
    time_ms: int


def normalize(output: str) -> str:
    """行末空白と末尾の空行の違いは無視する。"""
    return "\n".join(line.rstrip() for line in output.strip("\n").splitlines()).strip()


class Sandbox:
    """実行スロット (uid) を管理する。スロットごとに 1 実行ずつ。

    uid を切り替えられない環境 (root 以外で起動したテストなど) では、
    現在の uid のまま実行する (`isolate_uid=False`)。
    """

    def __init__(self, base_uid: int = 20000, slots: int = 2):
        self.isolate_uid = os.geteuid() == 0
        self.uids = [base_uid + i for i in range(slots)]

    def run_tests(
        self,
        language: Language,
        code: str,
        tests: list[TestCase],
        uid: int,
        time_limit_s: float = 2.0,
    ) -> list[TestResult]:
        workdir = Path(tempfile.mkdtemp(prefix="run-", dir="/tmp"))
        try:
            os.chmod(workdir, 0o700)
            source = workdir / SOURCE_FILE[language]
            source.write_text(code, encoding="utf-8")
            if self.isolate_uid:
                for p in (workdir, source):
                    os.chown(p, uid, uid)
            return [
                self._run_one(language, str(source), workdir, t, uid, time_limit_s)
                for t in tests
            ]
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    def _run_one(
        self,
        language: Language,
        source: str,
        workdir: Path,
        test: TestCase,
        uid: int,
        time_limit_s: float,
    ) -> TestResult:
        out_path, err_path = workdir / "stdout.txt", workdir / "stderr.txt"
        isolate = self.isolate_uid
        cpu = max(1, int(time_limit_s + 0.999))
        is_python = language == "python"

        def preexec() -> None:  # 子プロセス側 (fork 後・exec 前) で実行される
            os.setsid()
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
            resource.setrlimit(resource.RLIMIT_FSIZE, (FILE_SIZE_LIMIT_BYTES,) * 2)
            resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            resource.setrlimit(resource.RLIMIT_NPROC, (MAX_PROCESSES, MAX_PROCESSES))
            if is_python:
                # V8 は大きな仮想アドレス空間を予約するため node には設定しない
                # (node は --max-old-space-size とコンテナのメモリ上限で制限)
                resource.setrlimit(resource.RLIMIT_AS, (PYTHON_MEMORY_BYTES,) * 2)
            if isolate:
                os.setgroups([])
                os.setgid(uid)
                os.setuid(uid)

        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(workdir), "LANG": "C.UTF-8"}
        with open(out_path, "wb") as out, open(err_path, "wb") as err:
            if isolate:
                os.chown(out_path, uid, uid)
                os.chown(err_path, uid, uid)
            started = time.monotonic()
            proc = subprocess.Popen(
                _command(language, source),
                stdin=subprocess.PIPE,
                stdout=out,
                stderr=err,
                cwd=workdir,
                env=env,
                preexec_fn=preexec,
                close_fds=True,
            )
            timed_out = False
            try:
                proc.communicate(test.stdin.encode("utf-8"), timeout=time_limit_s * 2)
            except subprocess.TimeoutExpired:
                timed_out = True
            finally:
                _kill_group(proc.pid)
                if isolate:
                    # setsid などでグループから抜けたプロセスも、スロット uid ごと掃除する
                    _kill_uid(uid)
                proc.wait()
            elapsed = int((time.monotonic() - started) * 1000)

        stdout = _read_head(out_path)
        stderr = _read_head(err_path)
        # CPU 時間超過 (SIGXCPU / SIGKILL) も時間切れとして扱う
        if timed_out or proc.returncode in (-signal.SIGXCPU, -signal.SIGKILL):
            return TestResult("timeout", stdout, stderr, elapsed)
        if proc.returncode != 0:
            return TestResult("error", stdout, stderr, elapsed)
        status: Status = "passed" if normalize(stdout) == normalize(test.expected) else "failed"
        return TestResult(status, stdout, stderr, elapsed)


def _kill_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _kill_uid(uid: int) -> None:
    for _ in range(3):  # fork し続けるプロセスに備えて数回繰り返す
        found = False
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            try:
                if os.stat(f"/proc/{entry}").st_uid == uid:
                    os.kill(int(entry), signal.SIGKILL)
                    found = True
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                continue
        if not found:
            return


def _read_head(path: Path) -> str:
    try:
        with open(path, "rb") as f:
            data = f.read(OUTPUT_LIMIT_BYTES + 1)
    except FileNotFoundError:
        return ""
    text = data[:OUTPUT_LIMIT_BYTES].decode("utf-8", errors="replace")
    return text + ("\n…(出力が長すぎるため省略)" if len(data) > OUTPUT_LIMIT_BYTES else "")
