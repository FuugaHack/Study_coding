from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.gamification import GamificationStatsResponse, RewardResponse

CourseStatus = Literal["locked", "not-started", "in-progress", "completed"]


class CatalogCourseSummary(BaseModel):
    id: str
    title: str
    description: str
    category: str
    level: str
    icon: str
    estimated_hours: float
    tags: list[str]
    prerequisites: list[str]
    prerequisite_titles: list[str]
    question_count: int
    solved_count: int
    progress: int  # 0-100
    status: CourseStatus
    is_locked: bool


class CatalogCourseListResponse(BaseModel):
    courses: list[CatalogCourseSummary]
    content_version: str


class CatalogQuestion(BaseModel):
    """クライアントに渡す問題。正解・解説・解答例は含めない。"""

    id: str
    type: str
    title: str
    description: str
    difficulty: str
    choices: list[str] | None = None
    code_template: str | None = None
    blank_count: int | None = None
    solved: bool


class CatalogCourseDetailResponse(CatalogCourseSummary):
    questions: list[CatalogQuestion]


class AnswerRequest(BaseModel):
    # choice: str / multiple-choice: list[str]
    selected: str | list[str] | None = Field(default=None)
    # code (穴埋め)
    blanks: list[str] | None = Field(default=None, max_length=20)
    # text (記述・自己チェック)
    text: str | None = Field(default=None, max_length=5000)
    time_spent_seconds: int | None = Field(default=None, ge=0, le=86400)

    @model_validator(mode="after")
    def _limit_sizes(self) -> "AnswerRequest":
        values = self.selected if isinstance(self.selected, list) else [self.selected or ""]
        values = [*values, *(self.blanks or [])]
        if len(values) > 20 or any(len(v) > 500 for v in values):
            raise ValueError("回答が長すぎます")
        return self


class AnswerResponse(BaseModel):
    question_id: str
    result: Literal["correct", "incorrect", "self_check"]
    blank_results: list[bool] = Field(default_factory=list)
    # 正解時・自己チェック時・同じ問題で 2 回以上間違えたときのみ返す
    correct_answer: str | list[str] | None = None
    explanation: str | None = None
    reward: RewardResponse
    stats: GamificationStatsResponse
