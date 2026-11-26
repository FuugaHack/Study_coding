import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin


class TaskStatus(enum.StrEnum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class AsyncTask(UUIDPrimaryKeyMixin, Base):
    """AI 処理のキュー兼ステータス。ワーカーが FOR UPDATE SKIP LOCKED で取り出す。"""

    __tablename__ = "async_tasks"
    __table_args__ = (
        Index("ix_async_tasks_queue", "status", "run_after"),
        # 提出 ID からコードレビューのタスクを引く (coding_service._latest_review_task)
        Index(
            "ix_async_tasks_code_review_submission",
            text("(input_data->>'submission_id')"),
            postgresql_where=text("task_type = 'code_review'"),
        ),
    )

    # 問題レビューなどシステムのタスクは NULL
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status"), default=TaskStatus.pending, nullable=False
    )
    input_data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    result_data: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 取り出された回数。完了・失敗を書き込むときのフェンシングにも使う
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    # この時刻以降に実行する (再試行の待ち時間)
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # 処理中のタスクの期限。過ぎたら別のワーカーが取り直す
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    user = relationship("User")
