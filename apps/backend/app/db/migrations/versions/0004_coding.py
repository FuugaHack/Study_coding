"""coding: coding_progress / coding_submissions

Revision ID: 0004_coding
Revises: 0003_gamification_m2
Create Date: 2026-11-25

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_coding"
down_revision = "0003_gamification_m2"
branch_labels = None
depends_on = None


def _user_fk() -> sa.Column:
    return sa.Column(
        "user_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "coding_progress",
        _user_fk(),
        sa.Column("question_id", sa.String(100), nullable=False),
        sa.Column("hints_revealed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("solutions_viewed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("solved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("user_id", "question_id"),
    )

    op.create_table(
        "coding_submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        _user_fk(),
        sa.Column("question_id", sa.String(100), nullable=False),
        sa.Column("code", sa.Text, nullable=False),
        sa.Column("passed", sa.Boolean, nullable=True),
        sa.Column("passed_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("hints_used", sa.Integer, nullable=False, server_default="0"),
        sa.Column("results", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("content_version", sa.String(20), nullable=False),
        sa.Column("ai_review", postgresql.JSONB, nullable=True),
        sa.Column("ai_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispute_reason", sa.Text, nullable=True),
        sa.Column("disputed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_coding_submissions_user_question", "coding_submissions", ["user_id", "question_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_coding_submissions_user_question", table_name="coding_submissions")
    op.drop_table("coding_submissions")
    op.drop_table("coding_progress")
