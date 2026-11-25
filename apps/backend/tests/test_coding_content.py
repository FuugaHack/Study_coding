"""コーディング問題のコンテンツ検証 (本物のランナーを使う)。

- 模範解答がすべてのテスト (非公開を含む) に合格すること
- 初期コードのままでは合格しないこと (問題として成立しているか)

ランナーのソケットがない環境 (ランナー未起動) ではスキップする。
docker compose / CI ではランナーと一緒に実行される。
"""
import os

import pytest

from app.config import settings
from app.content.coding import get_coding_catalog
from app.services.runner_client import RunnerClient, RunTest

pytestmark = pytest.mark.skipif(
    not os.path.exists(settings.RUNNER_SOCKET), reason="ランナーが起動していない"
)

EXECUTABLE = [q for q in get_coding_catalog().questions if q.executable]


async def _run(question, code: str):
    tests = [RunTest(t.stdin, t.expected) for t in question.execution.tests]
    return await RunnerClient().run(
        question.language, code + question.execution.harness, tests, question.execution.time_limit_s
    )


@pytest.mark.parametrize("question", EXECUTABLE, ids=lambda q: q.id)
async def test_reference_solution_passes(question) -> None:
    results = await _run(question, question.execution.reference_solution)
    failures = [
        (t.name, r.status, r.stdout[:200], r.stderr[:300])
        for t, r in zip(question.execution.tests, results, strict=True)
        if r.status != "passed"
    ]
    assert not failures, failures


@pytest.mark.parametrize("question", EXECUTABLE, ids=lambda q: q.id)
async def test_initial_code_does_not_pass(question) -> None:
    results = await _run(question, question.initial_code)
    assert any(r.status != "passed" for r in results)


@pytest.mark.parametrize("question", EXECUTABLE, ids=lambda q: q.id)
async def test_recommended_solution_passes(question) -> None:
    recommended = [s for s in question.solutions if s.is_recommended] or question.solutions[:1]
    for s in recommended:
        results = await _run(question, s.code)
        assert all(r.status == "passed" for r in results), (s.id, [r.stderr for r in results])
