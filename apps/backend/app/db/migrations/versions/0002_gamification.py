"""gamification: question_attempts / user_stats / xp_events

Revision ID: 0002_gamification
Revises: 0001_init
Create Date: 2026-11-25

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_gamification"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "question_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question_id", sa.String(100), nullable=False),
        sa.Column("course_id", sa.String(100), nullable=False),
        sa.Column("is_correct", sa.Boolean, nullable=True),
        sa.Column("answer", postgresql.JSONB, nullable=True),
        sa.Column("content_version", sa.String(20), nullable=False),
        sa.Column("time_spent_seconds", sa.Integer, nullable=True),
        sa.Column("activity_date", sa.Date, nullable=False),
        sa.Column(
            "attempted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_question_attempts_user_time", "question_attempts", ["user_id", "attempted_at"]
    )
    op.create_index(
        "ix_question_attempts_user_question", "question_attempts", ["user_id", "question_id"]
    )

    op.create_table(
        "user_stats",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("total_xp", sa.Integer, nullable=False, server_default="0"),
        sa.Column("coins", sa.Integer, nullable=False, server_default="0"),
        sa.Column("current_streak", sa.Integer, nullable=False, server_default="0"),
        sa.Column("longest_streak", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_active_date", sa.Date, nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "xp_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Integer, nullable=False),
        sa.Column("coins", sa.Integer, nullable=False, server_default="0"),
        sa.Column("reason", sa.String(30), nullable=False),
        sa.Column("idempotency_key", sa.String(150), nullable=False),
        sa.Column("activity_date", sa.Date, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_xp_events_user_key"),
    )
    op.create_index("ix_xp_events_user_date", "xp_events", ["user_id", "activity_date"])


def downgrade() -> None:
    op.drop_index("ix_xp_events_user_date", table_name="xp_events")
    op.drop_table("xp_events")
    op.drop_table("user_stats")
    op.drop_index("ix_question_attempts_user_question", table_name="question_attempts")
    op.drop_index("ix_question_attempts_user_time", table_name="question_attempts")
    op.drop_table("question_attempts")
