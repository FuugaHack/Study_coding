"""AI の運用データ: 使用量 (費用) と問題品質レビュー。"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class AiUsage(UUIDPrimaryKeyMixin, Base):
    """LLM 呼び出し 1 回分の使用量。費用の集計と利用上限の判定に使う。"""

    __tablename__ = "ai_usage"
    __table_args__ = (
        Index("ix_ai_usage_created_at", "created_at"),
        Index("ix_ai_usage_user_created", "user_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class QuestionReview(UUIDPrimaryKeyMixin, Base):
    """問題の AI 品質レビュー (履歴として追記する)。

    問題の内容ハッシュと一緒に保存し、問題が修正されたら「古いレビュー」とみなす。
    """

    __tablename__ = "question_reviews"
    __table_args__ = (
        Index("ix_question_reviews_question", "question_id", "content_hash", "created_at"),
    )

    question_id: Mapped[str] = mapped_column(String(100), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    # passed | needs_fix | unverified
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # 人の判断: AI の指摘を確認して対応不要とした場合 "dismissed"
    resolution: Mapped[str | None] = mapped_column(String(20))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
