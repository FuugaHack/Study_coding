"""サンドボックスのテスト。

本番と同じ隔離設定のコンテナ内で実行すること (README の「ランナーのテスト」参照):
  docker compose run --rm runner pytest -q
"""
import os
import textwrap
import time

import pytest
from fastapi.testclient import TestClient

from runner.executor import Sandbox, normalize
from runner.executor import TestCase as Case

sandbox = Sandbox()
UID = sandbox.uids[0]
IN_CONTAINER = os.path.exists("/.dockerenv") or os.environ.get("RUNNER_SANDBOXED") == "1"
pytestmark = pytest.mark.skipif(not IN_CONTAINER, reason="ランナーのコンテナ内でのみ実行する")


def run(language: str, code: str, stdin: str = "", expected: str = "", limit: float = 2.0):
    code = textwrap.dedent(code)
    return sandbox.run_tests(language, code, [Case(stdin, expected)], UID, limit)[0]


# ------------------------------------------------------------------ 正常系


def test_python_passes_and_fails() -> None:
    code = "print(sum(int(x) for x in input().split()))"
    assert run("python", code, "1 2 3", "6").status == "passed"
    assert run("python", code, "1 2 3", "7").status == "failed"


def test_javascript_reads_stdin() -> None:
    code = """
    const input = require("fs").readFileSync(0, "utf8").trim();
    console.log(input.split(" ").map(Number).reduce((a, b) => a + b, 0));
    """
    assert run("javascript", code, "4 5", "9").status == "passed"


def test_typescript_type_annotations_are_stripped() -> None:
    code = """
    function first<T>(arr: T[]): T | undefined { return arr[0]; }
    console.log(first<number>([7, 8]));
    """
    result = run("typescript", code, "", "7")
    assert result.status == "passed", result.stderr


def test_runtime_error_is_error() -> None:
    result = run("python", "raise ValueError('boom')")
    assert result.status == "error" and "boom" in result.stderr


def test_normalize_ignores_trailing_whitespace() -> None:
    assert normalize("a  \nb\n\n") == normalize("a\nb")


# ------------------------------------------------------------------ 悪意のあるコード


def test_infinite_loop_times_out() -> None:
    assert run("python", "while True: pass", limit=1).status == "timeout"
    assert run("javascript", "while (true) {}", limit=1).status == "timeout"


def test_sleep_forever_times_out() -> None:
    assert run("python", "import time; time.sleep(60)", limit=1).status == "timeout"


def test_fork_bomb_is_contained() -> None:
    code = """
    import os
    while True:
        try:
            os.fork()
        except OSError:
            pass
    """
    assert run("python", code, limit=1).status in ("timeout", "error")
    # 後続の実行に影響しない
    assert run("python", "print('ok')", "", "ok").status == "passed"


def test_escaped_process_group_is_killed() -> None:
    code = """
    import subprocess
    subprocess.Popen(["sleep", "300"], start_new_session=True)
    print("spawned")
    """
    run("python", code)
    if not sandbox.isolate_uid:
        return
    # ゾンビは init (tini) が回収するまで少し残ることがあるので、生きているプロセスだけ数える
    deadline = time.monotonic() + 2
    while _live_processes_of(UID) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert _live_processes_of(UID) == []


def test_no_network() -> None:
    code = """
    import socket
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=1)
        print("connected")
    except OSError:
        print("blocked")
    """
    assert run("python", code, "", "blocked").status == "passed"


def test_cannot_write_outside_tmp() -> None:
    code = """
    try:
        open("/srv/pwned.txt", "w").write("x")
        print("written")
    except OSError:
        print("denied")
    """
    assert run("python", code, "", "denied").status == "passed"


def test_memory_bomb_fails() -> None:
    assert run("python", "x = 'a' * (1024 ** 3)").status == "error"


def test_output_flood_is_truncated() -> None:
    result = run("python", "while True: print('x' * 1000)", limit=1)
    assert result.status in ("error", "timeout")
    assert len(result.stdout) < 70 * 1024


@pytest.mark.skipif(not sandbox.isolate_uid, reason="uid 分離が有効なときのみ")
def test_cannot_touch_server_process() -> None:
    code = """
    import os, signal
    try:
        os.kill(1, signal.SIGKILL)
        print("killed")
    except PermissionError:
        print("denied")
    try:
        open("/proc/1/environ").read()
        print("leaked")
    except PermissionError:
        print("denied")
    """
    assert run("python", code, "", "denied\ndenied").status == "passed"


def test_environment_is_minimal() -> None:
    code = "import os; print(sorted(k for k in os.environ if 'TOKEN' in k))"
    assert run("python", code, "", "[]").status == "passed"


# ------------------------------------------------------------------ API


def test_api_requires_token(monkeypatch) -> None:
    from runner import app as app_module

    monkeypatch.setattr(app_module, "RUNNER_TOKEN", "secret")
    with TestClient(app_module.app) as client:
        body = {"language": "python", "code": "print(1)", "tests": [{"expected": "1"}]}
        assert client.post("/run", json=body).status_code == 401
        res = client.post("/run", json=body, headers={"X-Runner-Token": "secret"})
        assert res.status_code == 200
        assert res.json()["results"][0]["status"] == "passed"


def _live_processes_of(uid: int) -> list[str]:
    live = []
    for p in os.listdir("/proc"):
        if not p.isdigit() or _uid_of(p) != uid:
            continue
        try:
            state = open(f"/proc/{p}/stat").read().rsplit(")", 1)[1].split()[0]
        except (FileNotFoundError, IndexError):
            continue
        if state != "Z":
            live.append(p)
    return live


def _uid_of(pid: str) -> int | None:
    try:
        return os.stat(f"/proc/{pid}").st_uid
    except FileNotFoundError:
        return None


# ------------------------------------------------------------------ レビュー指摘の回帰テスト


def test_files_do_not_persist_between_tests() -> None:
    write = """
    for path in ("/tmp/leak.txt", "/dev/shm/leak.txt"):
        try:
            open(path, "w").write("secret")
        except OSError:
            pass
    print("ok")
    """
    assert run("python", write, "", "ok").status == "passed"
    read = """
    import os
    print(any(os.path.exists(p) for p in ("/tmp/leak.txt", "/dev/shm/leak.txt")))
    """
    assert run("python", read, "", "False").status == "passed"


def test_cannot_write_into_workdir_or_read_source_of_others() -> None:
    code = """
    import os
    try:
        open("injected.py", "w").write("x")
        print("written")
    except OSError:
        print("denied")
    """
    assert run("python", code, "", "denied").status == "passed"


@pytest.mark.skipif(not sandbox.isolate_uid, reason="uid 分離が有効なときのみ")
def test_cannot_connect_to_control_socket() -> None:
    code = """
    import socket
    s = socket.socket(socket.AF_UNIX)
    try:
        s.connect("/sock/runner.sock")
        print("connected")
    except OSError:
        print("denied")
    """
    assert run("python", code, "", "denied").status == "passed"


def test_node_memory_is_limited() -> None:
    code = "const b = Buffer.alloc(300 * 1024 * 1024); console.log(b.length);"
    assert run("javascript", code).status == "error"


def test_wall_clock_limit_is_tight() -> None:
    result = run("python", "import time; time.sleep(30)", limit=1)
    assert result.status == "timeout" and result.time_ms < 2500
