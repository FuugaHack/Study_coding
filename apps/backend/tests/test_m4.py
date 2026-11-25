"""M4: AI ワーカー・コスト計測と利用上限・問題品質レビュー・構造化ログ。"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update

from app.config import settings
from app.content.loader import Question, get_catalog
from app.domain import question_quality as qq
from app.models import AiUsage, AsyncTask, QuestionReview, TaskStatus
from app.services import question_review_service as qrs
from app.services.ai_usage import check_budget, cost_usd, record_usage, usage_summary
from app.services.llm import LLMResponse
from app.worker import queue
from app.worker.worker import PermanentTaskError, Worker
from tests.fakes import FakeLLM, drain

GENERIC = "AI の処理に失敗しました。時間をおいてもう一度お試しください"


async def _user_id(client: AsyncClient) -> str:
    from jose import jwt

    token = client.headers["Authorization"].removeprefix("Bearer ")
    return jwt.get_unverified_claims(token)["sub"]


async def _add_task(session_factory, task_type="noop", user_id=None, **values) -> uuid.UUID:
    async with session_factory() as db:
        task = await queue.enqueue(db, task_type=task_type, user_id=user_id, input_data={})
        if values:
            await db.execute(update(AsyncTask).where(AsyncTask.id == task.id).values(**values))
        await db.commit()
        return task.id


async def _task(session_factory, task_id) -> AsyncTask:
    async with session_factory() as db:
        return await db.get(AsyncTask, task_id)


# ================================================================ キュー / ワーカー


async def test_claim_skips_locked_tasks(session_factory) -> None:
    a = await _add_task(session_factory)
    b = await _add_task(session_factory)
    async with session_factory() as db1, session_factory() as db2:
        t1 = await queue.claim(db1)  # db1 のトランザクションは開いたまま (行ロック中)
        t2 = await queue.claim(db2)
        assert {t1.id, t2.id} == {a, b}
        assert await queue.claim(db2) is None
        await db1.commit()
        await db2.commit()


async def test_retry_waits_and_fencing_rejects_stale_worker(session_factory) -> None:
    tid = await _add_task(session_factory)
    async with session_factory() as db:
        claimed = await queue.claim(db)
        assert claimed.attempts == 1
        assert await queue.mark_failed(db, claimed, "x", retryable=True) == "pending"
        await db.commit()
    t = await _task(session_factory, tid)
    assert t.status == TaskStatus.pending and t.run_after > datetime.now(UTC)
    async with session_factory() as db:
        assert await queue.claim(db) is None  # 待ち時間中は取り出さない
        # 古い取り出し (attempts が違う) からの完了報告は無視される
        stale = queue.ClaimedTask(tid, "noop", None, {}, attempts=0)
        assert await queue.mark_completed(db, stale, {}) is False


async def test_expired_task_is_reclaimed_then_failed(session_factory, monkeypatch) -> None:
    monkeypatch.setattr(settings, "AI_TASK_MAX_ATTEMPTS", 2)
    past = datetime.now(UTC) - timedelta(seconds=1)
    tid = await _add_task(
        session_factory, status=TaskStatus.processing, attempts=1, locked_until=past
    )
    async with session_factory() as db:  # ワーカーが落ちた: 期限切れなので取り直せる
        claimed = await queue.claim(db)
        assert claimed.id == tid and claimed.attempts == 2
        await db.execute(update(AsyncTask).where(AsyncTask.id == tid).values(locked_until=past))
        await db.commit()
    async with session_factory() as db:  # 上限に達したので失敗にする
        assert await queue.fail_exhausted(db) == 1
        await db.commit()
    t = await _task(session_factory, tid)
    assert t.status == TaskStatus.failed and t.error_message == queue.TIMEOUT_MESSAGE


async def test_worker_handler_outcomes(session_factory) -> None:
    async def ok(ctx):
        return {"ok": True}

    async def permanent(ctx):
        raise PermanentTaskError("対象がありません")

    async def crash(ctx):
        raise RuntimeError("secret internal detail")

    worker = Worker(
        session_factory, FakeLLM({}), handlers={"ok": ok, "perm": permanent, "crash": crash}
    )
    ids = {
        name: await _add_task(session_factory, task_type=name)
        for name in ("ok", "perm", "crash", "unknown")
    }
    while await worker.run_once():
        pass
    assert (await _task(session_factory, ids["ok"])).result_data == {"ok": True}
    perm = await _task(session_factory, ids["perm"])
    assert perm.status == TaskStatus.failed and perm.error_message == "対象がありません"
    crashed = await _task(session_factory, ids["crash"])
    assert crashed.status == TaskStatus.pending  # 再試行待ち
    unknown = await _task(session_factory, ids["unknown"])
    assert unknown.status == TaskStatus.failed and unknown.error_message == GENERIC


async def test_worker_runs_tasks_concurrently(session_factory) -> None:
    running = 0
    peak = 0

    async def slow(ctx):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.2)
        running -= 1
        return {}

    for _ in range(2):
        await _add_task(session_factory, task_type="slow")
    worker = Worker(session_factory, FakeLLM({}), handlers={"slow": slow})
    await asyncio.gather(worker.run_once(), worker.run_once())
    assert peak == 2


# ================================================================ 費用・利用上限


def test_cost_calculation(monkeypatch) -> None:
    monkeypatch.setattr(settings, "AI_PRICE_INPUT_PER_MTOK", 3.0)
    monkeypatch.setattr(settings, "AI_PRICE_OUTPUT_PER_MTOK", 15.0)
    assert cost_usd(1_000_000, 0) == Decimal("3")
    assert cost_usd(1000, 500) == Decimal("0.010500")


async def _record(session_factory, user_id, input_tokens, output_tokens, purpose="code_review"):
    async with session_factory() as db:
        await record_usage(
            db,
            user_id=user_id,
            task_id=None,
            purpose=purpose,
            response=LLMResponse("", input_tokens, output_tokens, "m"),
        )
        await db.commit()


async def test_user_budget_blocks_enqueue(
    auth_client: AsyncClient, session_factory, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "AI_USER_DAILY_TOKEN_LIMIT", 1000)
    uid = await _user_id(auth_client)
    body = {"code": "print(1)", "problem_description": "p", "language": "python"}
    assert (await auth_client.post("/api/v1/ai/review", json=body)).status_code == 202
    await _record(session_factory, uid, 600, 400)
    res = await auth_client.post("/api/v1/ai/review", json=body)
    assert res.status_code == 429 and "上限" in res.json()["detail"]


async def test_global_budget_blocks_enqueue_and_worker(
    auth_client: AsyncClient, session_factory, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "AI_GLOBAL_DAILY_COST_LIMIT_USD", 0.01)
    body = {"code": "print(1)", "problem_description": "p", "language": "python"}
    res = await auth_client.post("/api/v1/ai/review", json=body)
    assert res.status_code == 202
    task_id = res.json()["task_id"]
    # 登録後に別のユーザー (またはシステム) の利用で上限に達した
    await _record(session_factory, None, 0, 1000)  # 0.015 USD

    llm = FakeLLM("レビュー")
    await drain(session_factory, llm)
    assert llm.calls == 0
    status = (await auth_client.get(f"/api/v1/ai/review/{task_id}")).json()
    assert status["status"] == "failed" and "利用枠" in status["error_message"]
    assert (await auth_client.post("/api/v1/ai/review", json=body)).status_code == 429


async def test_usage_is_recorded_per_call(auth_client: AsyncClient, session_factory) -> None:
    uid = await _user_id(auth_client)
    body = {"code": "print(1)", "problem_description": "p", "language": "python"}
    await auth_client.post("/api/v1/ai/review", json=body)
    await drain(session_factory, FakeLLM("良いコードです", input_tokens=1200, output_tokens=300))
    async with session_factory() as db:
        rows = (await db.scalars(select(AiUsage))).all()
        assert len(rows) == 1
        row = rows[0]
        assert str(row.user_id) == uid and row.purpose == "ai_review"
        assert (row.input_tokens, row.output_tokens) == (1200, 300)
        assert row.cost_usd == cost_usd(1200, 300)
        summary = await usage_summary(db, days=1)
    assert summary[0]["calls"] == 1 and summary[0]["cost_usd"] == cost_usd(1200, 300)
    async with session_factory() as db:
        await check_budget(db, uid)  # 上限未満なら例外にならない


# ================================================================ 既存 AI API のワーカー化


async def test_legacy_ai_review_does_not_call_llm_in_request(
    auth_client: AsyncClient, session_factory
) -> None:
    llm = FakeLLM("## 講評\nよく書けています")
    body = {"code": "print(1)", "problem_description": "p", "language": "python"}
    res = await auth_client.post("/api/v1/ai/review", json=body)
    assert res.status_code == 202
    task_id = res.json()["task_id"]
    assert (await auth_client.get(f"/api/v1/ai/review/{task_id}")).json()["status"] == "pending"
    assert llm.calls == 0

    await drain(session_factory, llm)
    result = (await auth_client.get(f"/api/v1/ai/review/{task_id}")).json()
    assert result["status"] == "completed" and "よく書けています" in result["review"]


async def test_legacy_problem_generation_via_worker(
    auth_client: AsyncClient, session_factory
) -> None:
    quiz = {
        "question": "Python のリストに要素を追加するメソッドは?",
        "choices": ["append", "push", "add", "insert_last"],
        "correct_index": 0,
        "explanation": "list.append は末尾に 1 要素を追加する。",
        "tags": ["python"],
    }
    res = await auth_client.post(
        "/api/v1/practice/generate",
        json={"problem_type": "quiz", "difficulty": "easy", "tags": ["python"]},
    )
    assert res.status_code == 202, res.text
    task_id = res.json()["task_id"]
    await drain(session_factory, FakeLLM(quiz))
    status = (await auth_client.get(f"/api/v1/practice/status/{task_id}")).json()
    assert status["status"] == "completed"
    assert status["problem"]["content"]["question"] == quiz["question"]


# ================================================================ 問題品質: 静的チェック


def test_catalog_has_no_static_errors() -> None:
    """CI のゲート: 静的チェックの error がない。"""
    errors = [i for i in qq.lint_catalog(get_catalog()) if i.severity == "error"]
    assert errors == []


def _question(**kw) -> Question:
    base = {
        "id": "q-x",
        "type": "choice",
        "title": "t",
        "description": "d",
        "choices": ["a", "b"],
        "answer": "a",
        "explanation": "十分に長い解説の文章です。理由もここに書きます。",
    }
    return Question.model_validate(base | kw)


def test_lint_rules() -> None:
    rules = lambda q: {i.rule for i in qq.lint_question(q)}  # noqa: E731
    assert rules(_question()) == set()
    assert "explanation-empty" in rules(_question(explanation=" "))
    assert "explanation-short" in rules(_question(explanation="短い"))
    assert "choice-duplicate" in rules(_question(choices=["a", "Ａ "]))
    assert "answer-in-prompt" in rules(
        _question(
            description="append を使う。正しいのは?", choices=["append", "push"], answer="append"
        )
    )
    assert "multiple-choice-single-answer" in rules(_question(type="multiple-choice", answer=["a"]))


def test_similarity_ignores_template_phrases() -> None:
    pairs = {(a, b) for _, a, b in qq.similar_pairs(get_catalog())}
    # 「〜の役割を説明してください」という定型文だけが共通する組は類似としない
    assert ("q-sql-join", "q-aws-iam") not in pairs
    assert ("q-css-color", "q-css-bg") in pairs


def test_content_hash_changes_when_question_changes() -> None:
    q = _question()
    assert q.content_hash() == _question().content_hash()
    assert q.content_hash() != _question(explanation=q.explanation + "追記").content_hash()


# ================================================================ 問題品質: AI レビュー


def quality_json(
    issues: list | None = None, references: list | None = None, ok: bool = True
) -> dict:
    return {
        "summary": "概ね正確です",
        "checks": {k: {"ok": ok, "comment": "ok"} for k in qq.ASPECTS},
        "issues": issues or [],
        "suggested_difficulty": "easy",
        "references": references
        if references is not None
        else ["https://developer.mozilla.org/ja/docs/Web/HTML/Element/Heading_Elements"],
    }


def _guard(raw: dict) -> str:
    return qq.apply_quality_guard(qq.QuestionQualityReview.model_validate(raw))[0]


def test_quality_guard() -> None:
    assert _guard(quality_json()) == "passed"
    low = {"aspect": "wording", "severity": "low", "detail": "d"}
    assert _guard(quality_json(issues=[low])) == "passed"
    # LLM が checks で「問題なし」と言っても、medium 以上の指摘があれば要修正
    high = {"aspect": "answer_validity", "severity": "high", "detail": "正解が誤り"}
    assert _guard(quality_json(issues=[high], ok=True)) == "needs_fix"
    # 公式ドキュメントの根拠がなければ人の確認が必要
    assert _guard(quality_json(references=["https://example.com/blog"])) == "unverified"
    assert qq.is_official_url("https://docs.python.org/3/library/functions.html")
    assert not qq.is_official_url("http://docs.python.org/3/")  # https のみ
    assert not qq.is_official_url("https://python.org.evil.example/")


def test_quality_schema_requires_https_reference() -> None:
    from pydantic import ValidationError

    for refs in ([], ["javascript:alert(1)"], ["ftp://python.org"]):
        with pytest.raises(ValidationError):
            qq.QuestionQualityReview.model_validate(quality_json(references=refs))
    with pytest.raises(ValidationError):
        bad = quality_json()
        del bad["checks"]["duplication"]
        qq.QuestionQualityReview.model_validate(bad)


async def test_question_review_flow(session_factory) -> None:
    catalog = get_catalog()
    total = sum(len(c.questions) for c in catalog.courses)
    ids = ["q-html-heading", "q-css-color"]

    async with session_factory() as db:
        statuses = await qrs.question_statuses(db)
        assert len(statuses) == total and {s.status for s in statuses} == {"unreviewed"}
        assert await qrs.enqueue_reviews(db, question_ids=ids) == ids
        # 処理待ちの間は二重に登録しない
        assert await qrs.enqueue_reviews(db, question_ids=ids) == []
        await db.commit()

    high = {
        "aspect": "duplication",
        "severity": "medium",
        "detail": "q-css-bg と似ている",
        "suggestion": "統合する",
        "references": ["https://developer.mozilla.org/ja/docs/Web/CSS/color"],
    }
    llm = FakeLLM(quality_json(issues=[high]))
    assert await drain(session_factory, llm) == 2
    # 類似候補 (q-css-bg) を LLM に渡している
    assert any("q-css-bg" in m for m in llm.messages)

    async with session_factory() as db:
        by_id = {s.question_id: s for s in await qrs.question_statuses(db)}
        assert by_id["q-html-heading"].status == "needs_fix"
        review = by_id["q-html-heading"].review
        assert review.result["official_references"]
        usage = await db.scalar(select(func.count()).select_from(AiUsage))
        assert usage == 2  # システムのタスクも費用を記録する

        # 人が確認して対応不要にする
        with pytest.raises(ValueError):
            await qrs.dismiss(db, str(review.id), " ")
        await qrs.dismiss(db, str(review.id), "類似は意図的 (比較のため)")
        await db.commit()
        by_id = {s.question_id: s for s in await qrs.question_statuses(db)}
        assert by_id["q-html-heading"].status == "dismissed"

        # 問題が修正された (ハッシュが変わった) ら要再レビュー
        await db.execute(
            update(QuestionReview)
            .where(QuestionReview.question_id == "q-css-color")
            .values(content_hash="old")
        )
        await db.commit()
        by_id = {s.question_id: s for s in await qrs.question_statuses(db)}
        assert by_id["q-css-color"].status == "stale"
        # 既定の enqueue は 未レビュー + 要再レビュー
        enqueued = await qrs.enqueue_reviews(db)
        assert "q-css-color" in enqueued and "q-html-heading" not in enqueued
        assert len(enqueued) == total - 1
        report = qrs.render_report(await qrs.question_statuses(db), qq.lint_catalog(catalog))
        assert "# 問題品質レポート" in report


async def test_question_review_aborts_when_content_changed(session_factory) -> None:
    async with session_factory() as db:
        await queue.enqueue(
            db,
            task_type=qrs.TASK_TYPE,
            user_id=None,
            input_data={"question_id": "q-html-heading", "content_hash": "outdated"},
        )
        await db.commit()
    llm = FakeLLM(quality_json())
    await drain(session_factory, llm)
    assert llm.calls == 0
    async with session_factory() as db:
        task = await db.scalar(select(AsyncTask))
        assert task.status == TaskStatus.failed and "更新" in task.error_message


def test_cli_lint_exit_code(capsys) -> None:
    from app.cli import main

    assert main(["questions", "lint"]) == 0
    assert "error 0 件" in capsys.readouterr().out


# ================================================================ 構造化ログ


async def test_request_id_header(client: AsyncClient) -> None:
    res = await client.get("/health")
    generated = res.headers["X-Request-ID"]
    assert len(generated) == 32
    res = await client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert res.headers["X-Request-ID"] == "abc-123"
    # ログに不正な文字を入れられないよう、形式外の ID は採用しない
    for bad in ("x" * 100, "a b", 'a"b'):
        res = await client.get("/health", headers={"X-Request-ID": bad})
        assert res.headers["X-Request-ID"] != bad


# ================================================================ レビュー指摘の回帰テスト


async def test_usage_recorded_even_if_task_times_out(session_factory, monkeypatch) -> None:
    """時間切れで中断しても、課金された LLM 呼び出しの使用量は記録する (利用上限のすり抜け防止)。"""

    class SlowLLM(FakeLLM):
        async def complete(self, *a, **kw):
            await asyncio.sleep(0.3)
            return await super().complete(*a, **kw)

    monkeypatch.setattr(settings, "AI_TASK_TIMEOUT_S", 0.1)

    async def handler(ctx):
        await ctx.complete("test", "s", "u")
        return {}

    tid = await _add_task(session_factory, task_type="slow")
    worker = Worker(session_factory, SlowLLM("x"), handlers={"slow": handler})
    await worker.run_once()
    assert (await _task(session_factory, tid)).status == TaskStatus.pending  # 再試行待ち
    await asyncio.sleep(0.5)
    async with session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(AiUsage)) == 1


async def test_worker_reloads_catalog_for_updated_question(session_factory, monkeypatch) -> None:
    """CLI が修正後の内容で登録したとき、常駐ワーカーは古いカタログを読み直してレビューする。"""
    from app.content.loader import load_catalog

    current = load_catalog()
    stale = load_catalog()
    stale.find_question("q-html-heading")[1].explanation = "修正前の解説"

    class FakeGetCatalog:
        cleared = False

        def __call__(self):
            return current if self.cleared else stale

        def cache_clear(self):
            self.cleared = True

    monkeypatch.setattr(qrs, "get_catalog", FakeGetCatalog())
    async with session_factory() as db:
        await queue.enqueue(
            db,
            task_type=qrs.TASK_TYPE,
            user_id=None,
            input_data={
                "question_id": "q-html-heading",
                "content_hash": current.find_question("q-html-heading")[1].content_hash(),
            },
        )
        await db.commit()
    llm = FakeLLM(quality_json())
    await drain(session_factory, llm)
    assert llm.calls == 1
    async with session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(QuestionReview)) == 1
