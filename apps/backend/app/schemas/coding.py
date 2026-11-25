from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.code_review import CodeReview
from app.schemas.gamification import GamificationStatsResponse, RewardResponse

IssueStatus = Literal["open", "in-progress", "solved"]


class CodingRepositorySummary(BaseModel):
    id: str
    name: str
    description: str
    language: str
    framework: str | None
    tags: list[str]
    difficulty_range: str
    status: str
    question_count: int
    executable_count: int
    solved_count: int


class CodingRepositoryListResponse(BaseModel):
    repositories: list[CodingRepositorySummary]


class CodingIssueSummary(BaseModel):
    id: str
    repository_id: str
    issue_number: int
    title: str
    description: str
    language: str
    framework: str | None
    difficulty: str
    type: str
    estimated_minutes: int
    tags: list[str]
    executable: bool
    status: IssueStatus


class CodingIssueListResponse(BaseModel):
    repository: CodingRepositorySummary
    issues: list[CodingIssueSummary]


class VisibleTest(BaseModel):
    name: str
    stdin: str
    expected: str


class HintResponse(BaseModel):
    level: int
    title: str
    content: str
    closeness: str


class CodingIssueDetail(CodingIssueSummary):
    initial_code: str
    explanation: str
    visible_tests: list[VisibleTest]
    hidden_test_count: int
    hints: list[HintResponse]  # 開いたヒントのみ
    hints_total: int
    can_view_solutions: bool


class CodeRequest(BaseModel):
    code: str = Field(max_length=20_000)


class TestResultResponse(BaseModel):
    name: str
    hidden: bool
    status: Literal["passed", "failed", "error", "timeout"]
    # 非公開テストでは入出力を返さない
    stdin: str | None = None
    expected: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    time_ms: int


class RunResponse(BaseModel):
    results: list[TestResultResponse]


class SubmitResponse(BaseModel):
    submission_id: str
    passed: bool | None
    passed_count: int
    total_count: int
    results: list[TestResultResponse]
    reward: RewardResponse
    stats: GamificationStatsResponse


class SolutionResponse(BaseModel):
    id: str
    title: str
    code: str
    explanation: str
    points: list[str]
    is_recommended: bool


class SolutionsResponse(BaseModel):
    solutions: list[SolutionResponse]


ReviewStatus = Literal["not_requested", "pending", "processing", "completed", "failed"]


class ReviewResponse(BaseModel):
    submission_id: str
    # AI レビューはワーカーで処理する。completed になるまでポーリングする
    status: ReviewStatus
    passed: bool | None
    review: CodeReview | None = None
    reviewed_at: datetime | None = None
    error_message: str | None = None
    aspect_labels: dict[str, str]


class DisputeRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)
