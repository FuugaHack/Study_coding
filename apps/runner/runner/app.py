"""コード実行ランナー API。

backend からのみ UNIX ソケット経由で呼ばれる。コンテナはネットワークを持たない。
"""
from __future__ import annotations

import asyncio
import hmac
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from runner.executor import Language, Sandbox, TestCase

RUNNER_TOKEN = os.environ.get("RUNNER_TOKEN", "")
SLOTS = int(os.environ.get("RUNNER_SLOTS", "2"))

sandbox = Sandbox(slots=SLOTS)
_free_uids: asyncio.Queue[int] | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _free_uids
    _free_uids = asyncio.Queue()
    for uid in sandbox.uids:
        _free_uids.put_nowait(uid)
    yield


app = FastAPI(title="Code Runner", lifespan=lifespan, docs_url=None, redoc_url=None)


def verify_token(x_runner_token: str = Header(default="")) -> None:
    if not RUNNER_TOKEN or not hmac.compare_digest(x_runner_token, RUNNER_TOKEN):
        raise HTTPException(status_code=401, detail="unauthorized")


class TestCaseIn(BaseModel):
    stdin: str = Field(default="", max_length=10_000)
    expected: str = Field(default="", max_length=10_000)


class RunRequest(BaseModel):
    language: Language
    code: str = Field(max_length=20_000)
    tests: list[TestCaseIn] = Field(min_length=1, max_length=20)
    time_limit_s: float = Field(default=2.0, gt=0, le=5)


class TestResultOut(BaseModel):
    status: str
    stdout: str
    stderr: str
    time_ms: int


class RunResponse(BaseModel):
    results: list[TestResultOut]


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/run", response_model=RunResponse, dependencies=[Depends(verify_token)])
async def run(req: RunRequest) -> RunResponse:
    assert _free_uids is not None
    uid = await _free_uids.get()  # 空きスロットが出るまで待つ (同時実行数の上限)
    try:
        results = await asyncio.to_thread(
            sandbox.run_tests,
            req.language,
            req.code,
            [TestCase(t.stdin, t.expected) for t in req.tests],
            uid,
            req.time_limit_s,
        )
    finally:
        _free_uids.put_nowait(uid)
    return RunResponse(results=[TestResultOut(**r.__dict__) for r in results])
