"""コード実行ランナー (apps/runner) のクライアント。

ランナーはネットワークを持たないコンテナで動き、共有ボリューム上の UNIX ソケットで待ち受ける。
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import settings
from app.core.exceptions import AIServiceError, RateLimitError


class RunnerUnavailableError(AIServiceError):
    def __init__(self) -> None:
        super().__init__("コード実行環境に接続できません。しばらくしてからもう一度お試しください")


class RunnerBusyError(RateLimitError):
    def __init__(self) -> None:
        super().__init__("コード実行が混み合っています。少し待ってからもう一度お試しください")


@dataclass(frozen=True)
class RunTest:
    stdin: str
    expected: str


@dataclass(frozen=True)
class RunResult:
    status: str  # passed | failed | error | timeout
    stdout: str
    stderr: str
    time_ms: int


class RunnerClient:
    def __init__(self, socket_path: str | None = None, token: str | None = None):
        self.socket_path = socket_path or settings.RUNNER_SOCKET
        self.token = token or settings.RUNNER_TOKEN

    async def run(
        self, language: str, code: str, tests: list[RunTest], time_limit_s: float = 2.0
    ) -> list[RunResult]:
        transport = httpx.AsyncHTTPTransport(uds=self.socket_path)
        try:
            async with httpx.AsyncClient(
                transport=transport, base_url="http://runner", timeout=60
            ) as client:
                res = await client.post(
                    "/run",
                    headers={"X-Runner-Token": self.token},
                    json={
                        "language": language,
                        "code": code,
                        "tests": [{"stdin": t.stdin, "expected": t.expected} for t in tests],
                        "time_limit_s": time_limit_s,
                    },
                )
                if res.status_code == 429:
                    raise RunnerBusyError()
                res.raise_for_status()
        except (httpx.HTTPError, OSError) as e:
            raise RunnerUnavailableError() from e
        return [RunResult(**r) for r in res.json()["results"]]
