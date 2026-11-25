"""ai ops: async_tasks をキューとして使うための列 / ai_usage / question_reviews

Revision ID: 0005_ai_ops
Revises: 0004_coding
Create Date: 2026-11-25

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_ai_ops"
down_revision = "0004_coding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("async_tasks", "user_id", nullable=True)
    op.add_column(
        "async_tasks", sa.Column("attempts", sa.Integer, nullable=False, server_default="0")
    )
    op.add_column(
        "async_tasks",
        sa.Column(
            "run_after", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.add_column("async_tasks", sa.Column("locked_until", sa.DateTime(timezone=True)))
    op.create_index("ix_async_tasks_queue", "async_tasks", ["status", "run_after"])
    op.create_index(
        "ix_async_tasks_code_review_submission",
        "async_tasks",
        [sa.text("(input_data->>'submission_id')")],
        postgresql_where=sa.text("task_type = 'code_review'"),
    )
    # 旧実装はリクエスト内で同期実行していたため、途中で止まったタスクが残っていれば失敗扱いにする
    op.execute(
        "UPDATE async_tasks SET status = 'failed', completed_at = now(), "
        "error_message = '処理が中断されました' WHERE status IN ('pending', 'processing')"
    )

    op.create_table(
        "ai_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("purpose", sa.String(50), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=False),
        sa.Column("output_tokens", sa.Integer, nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_ai_usage_created_at", "ai_usage", ["created_at"])
    op.create_index("ix_ai_usage_user_created", "ai_usage", ["user_id", "created_at"])

    op.create_table(
        "question_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("question_id", sa.String(100), nullable=False),
        sa.Column("content_hash", sa.String(32), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("result", postgresql.JSONB, nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolution", sa.String(20), nullable=True),
        sa.Column("resolution_note", sa.Text, nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_question_reviews_question",
        "question_reviews",
        ["question_id", "content_hash", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("question_reviews")
    op.drop_table("ai_usage")
    op.drop_index("ix_async_tasks_code_review_submission", table_name="async_tasks")
    op.drop_index("ix_async_tasks_queue", table_name="async_tasks")
    op.drop_column("async_tasks", "locked_until")
    op.drop_column("async_tasks", "run_after")
    op.drop_column("async_tasks", "attempts")
    # システムのタスク (user_id が NULL) は戻せないので削除する
    op.execute("DELETE FROM async_tasks WHERE user_id IS NULL")
    op.alter_column("async_tasks", "user_id", nullable=False)
