"""gamification M2: badges / course achievements / challenge sessions / streak freezes

Revision ID: 0003_gamification_m2
Revises: 0002_gamification
Create Date: 2026-11-25

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_gamification_m2"
down_revision = "0002_gamification"
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
    op.add_column(
        "user_stats",
        sa.Column("streak_freezes", sa.Integer, nullable=False, server_default="0"),
    )

    op.create_table(
        "user_badges",
        _user_fk(),
        sa.Column("badge_id", sa.String(50), nullable=False),
        sa.Column(
            "earned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("user_id", "badge_id"),
    )

    op.create_table(
        "course_achievements",
        _user_fk(),
        sa.Column("course_id", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column(
            "achieved_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("user_id", "course_id", "kind"),
    )

    op.create_table(
        "challenge_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        _user_fk(),
        sa.Column("course_id", sa.String(100), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("question_ids", postgresql.JSONB, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("correct_count", sa.Integer, nullable=True),
        sa.Column("activity_date", sa.Date, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_challenge_sessions_user_course", "challenge_sessions", ["user_id", "course_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_challenge_sessions_user_course", table_name="challenge_sessions")
    op.drop_table("challenge_sessions")
    op.drop_table("course_achievements")
    op.drop_table("user_badges")
    op.drop_column("user_stats", "streak_freezes")
