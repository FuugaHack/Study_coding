"""問題品質レビューの登録・集計・人の判断 (docs/expansion/m4-design.md §5)。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.content.loader import Catalog, get_catalog
from app.domain import question_quality as qq
from app.models.ai_ops import QuestionReview
from app.models.async_task import AsyncTask, TaskStatus
from app.services.ai_usage import check_budget
from app.services.llm import parse_json_output
from app.worker import queue

TASK_TYPE = "question_review"

STATUS_LABELS = {
    "unreviewed": "未レビュー",
    "stale": "要再レビュー (問題が更新された)",
    "passed": "合格",
    "needs_fix": "要修正",
    "unverified": "要確認 (公式の根拠なし)",
    "dismissed": "対応不要 (人が確認)",
}


@dataclass
class QuestionStatus:
    question_id: str
    course_id: str
    title: str
    content_hash: str
    status: str
    review: QuestionReview | None


async def _active_targets(db: AsyncSession) -> set[tuple[str, str]]:
    rows = await db.scalars(
        select(AsyncTask.input_data).where(
            AsyncTask.task_type == TASK_TYPE,
            AsyncTask.status.in_([TaskStatus.pending, TaskStatus.processing]),
        )
    )
    return {(d.get("question_id"), d.get("content_hash")) for d in rows}


async def question_statuses(
    db: AsyncSession, catalog: Catalog | None = None
) -> list[QuestionStatus]:
    catalog = catalog or get_catalog()
    reviews = (
        await db.scalars(select(QuestionReview).order_by(QuestionReview.created_at.desc()))
    ).all()
    latest_by_hash: dict[tuple[str, str], QuestionReview] = {}
    reviewed: set[str] = set()
    for r in reviews:
        latest_by_hash.setdefault((r.question_id, r.content_hash), r)
        reviewed.add(r.question_id)

    out = []
    for course in catalog.courses:
        for q in course.questions:
            h = q.content_hash()
            r = latest_by_hash.get((q.id, h))
            if r is not None:
                status = "dismissed" if r.resolution == "dismissed" else r.status
            elif q.id in reviewed:
                status = "stale"
            else:
                status = "unreviewed"
            out.append(QuestionStatus(q.id, course.id, q.title, h, status, r))
    return out


async def enqueue_reviews(
    db: AsyncSession,
    *,
    all_questions: bool = False,
    question_ids: list[str] | None = None,
    catalog: Catalog | None = None,
) -> list[str]:
    """レビューを登録し、登録した問題 ID を返す。

    既定は「未レビュー」と「要再レビュー」だけ。同じ内容に対して処理待ちのタスクがあれば登録しない。
    """
    catalog = catalog or get_catalog()
    statuses = await question_statuses(db, catalog)
    if question_ids:
        unknown = set(question_ids) - {s.question_id for s in statuses}
        if unknown:
            raise ValueError(f"未知の問題 ID: {sorted(unknown)}")
        targets = [s for s in statuses if s.question_id in set(question_ids)]
    elif all_questions:
        targets = statuses
    else:
        targets = [s for s in statuses if s.status in ("unreviewed", "stale")]

    await check_budget(db, None)
    active = await _active_targets(db)
    enqueued = []
    for s in targets:
        if (s.question_id, s.content_hash) in active:
            continue
        await queue.enqueue(
            db,
            task_type=TASK_TYPE,
            user_id=None,
            input_data={"question_id": s.question_id, "content_hash": s.content_hash},
        )
        enqueued.append(s.question_id)
    return enqueued


async def dismiss(db: AsyncSession, review_id: str, note: str) -> QuestionReview:
    """AI の指摘を人が確認し、対応不要と判断したことを記録する。"""
    if not note.strip():
        raise ValueError("理由 (note) を書いてください")
    review = await db.get(QuestionReview, uuid.UUID(review_id), with_for_update=True)
    if review is None:
        raise ValueError("レビューが見つかりません")
    if review.status == "passed":
        raise ValueError("合格したレビューは対象外です")
    review.resolution = "dismissed"
    review.resolution_note = note.strip()
    review.resolved_at = datetime.now(UTC)
    await db.flush()
    return review


# ------------------------------------------------------------------ ワーカー


async def run_question_review_task(ctx) -> dict:
    from app.worker.worker import PermanentTaskError

    data = ctx.task.input_data
    catalog = get_catalog()
    found = catalog.find_question(data.get("question_id", ""))
    if found is None or found[1].content_hash() != data.get("content_hash"):
        # 常駐ワーカーは起動時のカタログを持っている。CLI が新しい内容で登録した場合に備えて読み直す
        get_catalog.cache_clear()
        catalog = get_catalog()
        found = catalog.find_question(data.get("question_id", ""))
    if found is None:
        raise PermanentTaskError("問題が見つかりません")
    course, q = found
    if q.content_hash() != data.get("content_hash"):
        raise PermanentTaskError("問題が更新されたため、このレビューは中止しました")

    async with ctx.session_factory() as db:
        # 再試行のときに同じタスクの結果が既に保存されていれば二重に保存しない
        existing = await db.scalar(
            select(QuestionReview).where(QuestionReview.task_id == ctx.task.id)
        )
        if existing is not None:
            return {"review_id": str(existing.id), "status": existing.status}

    similar = []
    for sid in qq.similar_to(catalog, q.id):
        other = catalog.find_question(sid)
        if other is not None:
            similar.append(other[1])

    response = await ctx.complete(
        TASK_TYPE,
        qq.build_system_prompt(),
        qq.build_user_message(course, q, similar),
        temperature=0.2,
    )
    review = qq.QuestionQualityReview.model_validate(parse_json_output(response.text))
    status, result = qq.apply_quality_guard(review)

    async with ctx.session_factory() as db:
        row = QuestionReview(
            question_id=q.id,
            content_hash=q.content_hash(),
            status=status,
            result=result,
            model=response.model,
            task_id=ctx.task.id,
        )
        db.add(row)
        await db.commit()
    return {"review_id": str(row.id), "status": status}


def render_report(statuses: list[QuestionStatus], lint: list[qq.LintIssue]) -> str:
    """Markdown のレポート。"""
    counts: dict[str, int] = {}
    for s in statuses:
        counts[s.status] = counts.get(s.status, 0) + 1
    lint_by_q: dict[str, list[qq.LintIssue]] = {}
    for i in lint:
        lint_by_q.setdefault(i.question_id, []).append(i)

    lines = ["# 問題品質レポート", "", "## 集計", "", "| 状態 | 件数 |", "|---|---|"]
    for key, label in STATUS_LABELS.items():
        lines.append(f"| {label} | {counts.get(key, 0)} |")
    lines.append(f"| 合計 | {len(statuses)} |")

    attention = [s for s in statuses if s.status in ("needs_fix", "unverified")]
    lines += ["", "## 要対応 (AI レビュー)", ""]
    if not attention:
        lines.append("なし")
    for s in attention:
        r = s.review
        lines.append(f"### {s.question_id} ({s.course_id}) — {STATUS_LABELS[s.status]}")
        lines.append("")
        lines.append(f"- レビュー ID: `{r.id}`")
        lines.append(f"- 総評: {r.result.get('summary', '')}")
        for issue in r.result.get("issues", []):
            refs = ", ".join(issue.get("references", []))
            lines.append(
                f"- [{issue['severity']}] {qq.ASPECTS.get(issue['aspect'], issue['aspect'])}: "
                f"{issue['detail']} → {issue.get('suggestion', '')}"
                + (f" ({refs})" if refs else "")
            )
        if not r.result.get("official_references"):
            lines.append("- 公式ドキュメントの根拠がありません")
        lines.append("")

    lines += ["", "## 静的チェック", "", "| 問題 | 重要度 | ルール | 内容 |", "|---|---|---|---|"]
    for qid, items in lint_by_q.items():
        for i in items:
            lines.append(f"| {qid} | {i.severity} | {i.rule} | {i.message} |")
    return "\n".join(lines) + "\n"
