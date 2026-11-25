"""学習エンジン + ゲーミフィケーション (M1) のモデル。

- QuestionAttempt: カタログ問題への回答ログ (サーバー採点結果)
- UserStats: XP / コイン / ストリークの集計値 (xp_events から再計算可能)
- XpEvent: XP・コイン付与の追記型台帳。idempotency_key で二重付与を防ぐ
"""
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class QuestionAttempt(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "question_attempts"
    __table_args__ = (
        Index("ix_question_attempts_user_time", "user_id", "attempted_at"),
        Index("ix_question_attempts_user_question", "user_id", "question_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[str] = mapped_column(String(100), nullable=False)
    course_id: Mapped[str] = mapped_column(String(100), nullable=False)
    # text 型 (自己チェック) は正誤判定しないため NULL
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    answer: Mapped[dict | None] = mapped_column(JSONB)
    content_version: Mapped[str] = mapped_column(String(20), nullable=False)
    time_spent_seconds: Mapped[int | None] = mapped_column(Integer)
    activity_date: Mapped[date] = mapped_column(Date, nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserStats(Base):
    __tablename__ = "user_stats"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    total_xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    longest_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_active_date: Mapped[date | None] = mapped_column(Date)
    streak_freezes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class XpEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "xp_events"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_xp_events_user_key"),
        Index("ix_xp_events_user_date", "user_id", "activity_date"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reason: Mapped[str] = mapped_column(String(30), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(150), nullable=False)
    activity_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserBadge(Base):
    __tablename__ = "user_badges"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    badge_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    earned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CourseAchievement(Base):
    """コース単位の達成: placement_passed (飛び級でクリア扱い) / boss_defeated (👑)"""

    __tablename__ = "course_achievements"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    course_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    kind: Mapped[str] = mapped_column(String(30), primary_key=True)
    achieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ChallengeSession(UUIDPrimaryKeyMixin, Base):
    """実力テスト / ボス戦の受験セッション。出題はサーバーが決め、提出時に採点する。"""

    __tablename__ = "challenge_sessions"
    __table_args__ = (Index("ix_challenge_sessions_user_course", "user_id", "course_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[str] = mapped_column(String(100), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    question_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    correct_count: Mapped[int | None] = mapped_column(Integer)
    activity_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
