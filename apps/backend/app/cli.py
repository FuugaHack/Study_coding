"""運用 CLI (`python -m app.cli ...`)。管理画面ができるまでの問題レビュー・費用確認用。

python -m app.cli questions lint
python -m app.cli questions enqueue [--all | --ids q-a,q-b]
python -m app.cli questions report [--output report.md]
python -m app.cli questions dismiss <review_id> --note "理由"
python -m app.cli usage [--days 7]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.content.loader import get_catalog
from app.core.logging import configure_logging
from app.domain import question_quality as qq


def _print(text: str) -> None:
    sys.stdout.write(text if text.endswith("\n") else text + "\n")


def cmd_lint(_: argparse.Namespace) -> int:
    issues = qq.lint_catalog(get_catalog())
    errors = [i for i in issues if i.severity == "error"]
    for i in issues:
        _print(f"{i.severity:7} {i.question_id:32} {i.rule:30} {i.message}")
    _print(f"\nerror {len(errors)} 件 / warning {len(issues) - len(errors)} 件")
    return 1 if errors else 0


async def _with_session(fn):
    from app.db.session import async_session, engine

    try:
        async with async_session() as db:
            result = await fn(db)
            await db.commit()
            return result
    finally:
        await engine.dispose()


def cmd_enqueue(args: argparse.Namespace) -> int:
    from app.services import question_review_service as svc

    ids = [s.strip() for s in args.ids.split(",") if s.strip()] if args.ids else None

    async def run(db):
        return await svc.enqueue_reviews(db, all_questions=args.all, question_ids=ids)

    enqueued = asyncio.run(_with_session(run))
    _print(f"{len(enqueued)} 問のレビューを登録しました (ワーカーが順に処理します)")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    from app.services import question_review_service as svc

    catalog = get_catalog()
    statuses = asyncio.run(_with_session(lambda db: svc.question_statuses(db, catalog)))
    report = svc.render_report(statuses, qq.lint_catalog(catalog))
    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        _print(f"{args.output} に書き出しました")
    else:
        _print(report)
    return 0


def cmd_dismiss(args: argparse.Namespace) -> int:
    from app.services import question_review_service as svc

    async def run(db):
        return await svc.dismiss(db, args.review_id, args.note)

    review = asyncio.run(_with_session(run))
    _print(f"{review.question_id} のレビューを「対応不要」にしました")
    return 0


def cmd_usage(args: argparse.Namespace) -> int:
    from app.services.ai_usage import usage_summary

    rows = asyncio.run(_with_session(lambda db: usage_summary(db, args.days)))
    _print(f"{'日付':10} {'用途':20} {'回数':>6} {'入力':>10} {'出力':>10} {'USD':>10}")
    for r in rows:
        _print(
            f"{r['day']!s:10} {r['purpose']:20} {r['calls']:>6} {r['input_tokens']:>10} "
            f"{r['output_tokens']:>10} {r['cost_usd']:>10.4f}"
        )
    total = sum(r["cost_usd"] for r in rows)
    _print(f"合計 USD {total:.4f}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="group", required=True)

    questions = sub.add_parser("questions", help="問題の品質チェック")
    qsub = questions.add_subparsers(dest="command", required=True)
    qsub.add_parser("lint", help="静的チェック (error があれば終了コード 1)").set_defaults(
        func=cmd_lint
    )
    enqueue = qsub.add_parser("enqueue", help="AI レビューを登録 (既定: 未レビュー + 要再レビュー)")
    enqueue.add_argument("--all", action="store_true", help="全問題")
    enqueue.add_argument("--ids", help="カンマ区切りの問題 ID")
    enqueue.set_defaults(func=cmd_enqueue)
    report = qsub.add_parser("report", help="Markdown のレポート")
    report.add_argument("--output")
    report.set_defaults(func=cmd_report)
    dismiss = qsub.add_parser("dismiss", help="AI の指摘を「対応不要」にする")
    dismiss.add_argument("review_id")
    dismiss.add_argument("--note", required=True)
    dismiss.set_defaults(func=cmd_dismiss)

    usage = sub.add_parser("usage", help="AI の使用量と費用")
    usage.add_argument("--days", type=int, default=7)
    usage.set_defaults(func=cmd_usage)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    args = build_parser().parse_args(argv)
    from fastapi import HTTPException

    try:
        return args.func(args)
    except ValueError as e:
        _print(f"エラー: {e}")
        return 2
    except HTTPException as e:  # 利用上限の超過など
        _print(f"エラー: {e.detail}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
