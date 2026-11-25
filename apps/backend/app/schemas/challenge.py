from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.catalog import AnswerRequest, CatalogQuestion
from app.schemas.gamification import GamificationStatsResponse, RewardResponse

ChallengeMode = Literal["placement", "boss"]


class StartChallengeRequest(BaseModel):
    course_id: str = Field(max_length=100)
    mode: ChallengeMode


class ChallengeResponse(BaseModel):
    id: str
    course_id: str
    course_title: str
    mode: ChallengeMode
    status: str
    questions: list[CatalogQuestion]
    time_limit_seconds: int
    expires_at: datetime
    pass_percent: int
    # クライアントの時計ずれを補正するためのサーバー時刻
    server_now: datetime


class SubmitChallengeRequest(BaseModel):
    # question_id -> 回答
    answers: dict[str, AnswerRequest] = Field(max_length=20)


class ChallengeQuestionResult(BaseModel):
    question_id: str
    correct: bool
    blank_results: list[bool] = Field(default_factory=list)
    # 合格時のみ返す
    correct_answer: str | list[str] | None = None
    explanation: str | None = None


class ChallengeResultResponse(BaseModel):
    id: str
    course_id: str
    mode: ChallengeMode
    passed: bool
    timed_out: bool
    correct: int
    total: int
    percent: int
    results: list[ChallengeQuestionResult]
    unlocked_courses: list[str]  # 今回の結果で新たに解放されたコースのタイトル
    reward: RewardResponse
    stats: GamificationStatsResponse
