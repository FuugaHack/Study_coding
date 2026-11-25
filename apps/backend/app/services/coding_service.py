import uuid
from datetime import UTC, datetime

from pydantic import ValidationError

from app.content.coding import CodingCatalog, CodingQuestion, CodingRepository
from app.core.exceptions import ConflictError, NotFoundError
from app.domain import code_review as cr
from app.domain import gamification as g
from app.domain.code_rules import find_forbidden_python
from app.models.gamification import CodingSubmission
from app.repositories.coding_repository import CodingRepository as CodingRepo
from app.schemas.coding import (
    CodingIssueDetail,
    CodingIssueListResponse,
    CodingIssueSummary,
    CodingRepositoryListResponse,
    CodingRepositorySummary,
    HintResponse,
    ReviewResponse,
    RunResponse,
    SolutionResponse,
    SolutionsResponse,
    SubmitResponse,
    TestResultResponse,
    VisibleTest,
)
from app.services.catalog_service import reward_response
from app.services.gamification_service import GamificationService
from app.services.llm import AIUnavailableError, LLMClient
from app.services.runner_client import RunnerClient, RunResult, RunTest

# 初回合格の XP (難易度別)。ヒント 1 つにつき 20% 減 (最大 60% 減)
CODING_XP = {"easy": 30, "normal": 45, "hard": 60}
HINT_PENALTY = 0.2
MAX_HINT_PENALTY = 0.6
# 解答例を見てから合格した場合
AFTER_SOLUTION_XP = 5


def coding_xp(difficulty: str, hints_used: int, solutions_viewed: bool) -> int:
    if solutions_viewed:
        return AFTER_SOLUTION_XP
    penalty = min(MAX_HINT_PENALTY, HINT_PENALTY * hints_used)
    return round(CODING_XP[difficulty] * (1 - penalty))


class CodingService:
    def __init__(
        self,
        catalog: CodingCatalog,
        repo: CodingRepo,
        gamification: GamificationService,
        runner: RunnerClient,
        llm: LLMClient,
    ):
        self.catalog = catalog
        self.repo = repo
        self.gamification = gamification
        self.runner = runner
        self.llm = llm

    # ------------------------------------------------------------------ 一覧

    async def list_repositories(self, user_id: str) -> CodingRepositoryListResponse:
        progress = await self.repo.all_progress(user_id)
        return CodingRepositoryListResponse(
            repositories=[self._repo_summary(r, progress) for r in self.catalog.repositories]
        )

    async def list_issues(self, user_id: str, repository_id: str) -> CodingIssueListResponse:
        repo = self.catalog.get_repository(repository_id)
        if repo is None:
            raise NotFoundError("リポジトリ")
        progress = await self.repo.all_progress(user_id)
        submitted = await self.repo.submission_counts(user_id)
        return CodingIssueListResponse(
            repository=self._repo_summary(repo, progress),
            issues=[
                self._issue_summary(q, progress, submitted)
                for q in self.catalog.questions_of(repository_id)
            ],
        )

    async def get_issue(self, user_id: str, question_id: str) -> CodingIssueDetail:
        q = self._question(question_id)
        progress = await self.repo.all_progress(user_id)
        submitted = await self.repo.submission_counts(user_id)
        p = progress.get(q.id)
        revealed = p.hints_revealed if p else 0
        tests = q.execution.tests if q.execution else []
        return CodingIssueDetail(
            **self._issue_summary(q, progress, submitted).model_dump(),
            initial_code=q.initial_code,
            explanation=q.explanation,
            visible_tests=[
                VisibleTest(name=t.name, stdin=t.stdin, expected=t.expected)
                for t in tests
                if not t.hidden
            ],
            hidden_test_count=sum(1 for t in tests if t.hidden),
            hints=[HintResponse(**h.model_dump()) for h in q.hints[:revealed]],
            hints_total=len(q.hints),
            can_view_solutions=bool(p and p.solved_at) or submitted.get(q.id, 0) > 0,
        )

    # ------------------------------------------------------------------ ヒント・解答例

    async def reveal_hint(self, user_id: str, question_id: str) -> list[HintResponse]:
        q = self._question(question_id)
        p = await self.repo.lock_progress(user_id, q.id)
        if p.hints_revealed >= len(q.hints):
            raise ConflictError("これ以上のヒントはありません")
        p.hints_revealed += 1
        await self.repo.db.commit()
        return [HintResponse(**h.model_dump()) for h in q.hints[: p.hints_revealed]]

    async def view_solutions(self, user_id: str, question_id: str) -> SolutionsResponse:
        """解答例は「合格後」または「1 回以上提出した後 (ギブアップ)」に見られる。"""
        q = self._question(question_id)
        submitted = (await self.repo.submission_counts(user_id)).get(q.id, 0)
        p = await self.repo.lock_progress(user_id, q.id)
        if not p.solved_at and submitted == 0:
            raise ConflictError("解答例は一度提出してから見られます。まずは挑戦してみよう!")
        if not p.solved_at:
            p.solutions_viewed = True  # 合格前に見た場合、以後の合格 XP は少なくなる
        await self.repo.db.commit()
        return SolutionsResponse(
            solutions=[SolutionResponse(**s.model_dump()) for s in q.solutions]
        )

    # ------------------------------------------------------------------ 実行・提出

    async def run(self, user_id: str, question_id: str, code: str) -> RunResponse:
        """公開テストだけを実行する (記録しない)。"""
        q = self._executable(question_id)
        visible = [(i, t) for i, t in enumerate(q.execution.tests) if not t.hidden]
        return RunResponse(results=await self._execute(q, code, visible))

    async def submit(self, user_id: str, question_id: str, code: str) -> SubmitResponse:
        q = self._question(question_id)
        # 実行は数秒かかるため、DB の行ロックを取る前に済ませる
        if q.execution:
            results = await self._execute(q, code, list(enumerate(q.execution.tests)))
            passed_count = sum(1 for r in results if r.status == "passed")
            passed: bool | None = passed_count == len(results)
        else:
            results, passed_count, passed = [], 0, None

        today = g.local_today()
        # ロック順: user_stats → coding_progress → xp_events
        await self.gamification.repo.lock_stats(user_id)
        progress = await self.repo.lock_progress(user_id, q.id)

        submission = await self.repo.add_submission(
            CodingSubmission(
                user_id=user_id,
                question_id=q.id,
                code=code,
                passed=passed,
                passed_count=passed_count,
                total_count=len(results),
                hints_used=progress.hints_revealed,
                results=[r.model_dump() for r in results],
                content_version=self.catalog.version,
            )
        )

        summary = await self.gamification.begin_summary(user_id)
        if passed:
            if not progress.solved_at:
                progress.solved_at = datetime.now(UTC)
            await self.gamification.award(
                user_id,
                amount=coding_xp(q.difficulty, progress.hints_revealed, progress.solutions_viewed),
                reason="coding",
                key=f"coding:{q.id}:first",
                today=today,
                summary=summary,
            )
        await self.gamification.after_activity(user_id, today, summary)
        stats = await self.gamification.get_stats(user_id, today)
        await self.repo.db.commit()
        return SubmitResponse(
            submission_id=str(submission.id),
            passed=passed,
            passed_count=passed_count,
            total_count=len(results),
            results=results,
            reward=reward_response(summary, stats.level),
            stats=stats,
        )

    # ------------------------------------------------------------------ AI レビュー

    async def review(self, user_id: str, submission_id: str) -> ReviewResponse:
        submission = await self._submission(user_id, submission_id)
        q = self._question(submission.question_id)
        if submission.ai_review is None:
            # LLM の呼び出し (数秒〜数十秒) の間は DB のロックを持たない
            await self.repo.db.commit()
            raw = await self.llm.complete_json(
                cr.build_system_prompt(),
                cr.build_user_message(
                    title=q.title,
                    description=q.description,
                    language=q.language,
                    code=submission.code,
                    passed=submission.passed,
                    passed_count=submission.passed_count,
                    total_count=submission.total_count,
                    hints_used=submission.hints_used,
                ),
            )
            try:
                review = cr.CodeReview.model_validate(raw)
            except ValidationError as e:
                raise AIUnavailableError(
                    "AI レビューの形式が不正でした。もう一度お試しください"
                ) from e
            review = cr.apply_objective_guard(review, submission.passed)
            submission = await self._submission(user_id, submission_id, for_update=True)
            if submission.ai_review is None:  # 同時リクエストで先に保存されていたらそちらを使う
                submission.ai_review = review.model_dump()
                submission.ai_reviewed_at = datetime.now(UTC)
            await self.repo.db.commit()
        return ReviewResponse(
            submission_id=str(submission.id),
            passed=submission.passed,
            review=cr.CodeReview.model_validate(submission.ai_review),
            reviewed_at=submission.ai_reviewed_at,
            aspect_labels=cr.ASPECTS,
        )

    async def dispute(self, user_id: str, submission_id: str, reason: str) -> None:
        submission = await self._submission(user_id, submission_id, for_update=True)
        if submission.disputed_at is not None:
            raise ConflictError("この提出はすでに報告済みです")
        submission.dispute_reason = reason
        submission.disputed_at = datetime.now(UTC)
        await self.repo.db.commit()

    # ------------------------------------------------------------------ 内部

    async def _execute(
        self, q: CodingQuestion, code: str, tests: list[tuple[int, object]]
    ) -> list[TestResultResponse]:
        execution = q.execution
        banned = (
            find_forbidden_python(code, execution.forbidden_names) if q.language == "python" else []
        )
        if banned:
            message = f"この問題では次の名前は使えません: {', '.join(banned)}"
            raw = [RunResult("error", "", message, 0) for _ in tests]
        else:
            raw = await self.runner.run(
                q.language,
                code + execution.harness,
                [RunTest(stdin=t.stdin, expected=t.expected) for _, t in tests],
                execution.time_limit_s,
            )
        hidden_no = 0
        out: list[TestResultResponse] = []
        for (_, t), r in zip(tests, raw, strict=True):
            if t.hidden:
                hidden_no += 1
                out.append(
                    TestResultResponse(
                        name=f"非公開テスト {hidden_no}",
                        hidden=True,
                        status=r.status,
                        time_ms=r.time_ms,
                    )
                )
            else:
                out.append(
                    TestResultResponse(
                        name=t.name,
                        hidden=False,
                        status=r.status,
                        stdin=t.stdin,
                        expected=t.expected,
                        stdout=r.stdout,
                        stderr=r.stderr,
                        time_ms=r.time_ms,
                    )
                )
        return out

    def _question(self, question_id: str) -> CodingQuestion:
        q = self.catalog.get_question(question_id)
        if q is None:
            raise NotFoundError("問題")
        return q

    def _executable(self, question_id: str) -> CodingQuestion:
        q = self._question(question_id)
        if not q.execution:
            raise ConflictError(
                "この問題はまだ自動実行に対応していません (AI レビューは利用できます)"
            )
        return q

    async def _submission(
        self, user_id: str, submission_id: str, *, for_update: bool = False
    ) -> CodingSubmission:
        try:
            uuid.UUID(submission_id)
        except ValueError as e:
            raise NotFoundError("提出") from e
        s = await self.repo.get_submission(submission_id, user_id, for_update=for_update)
        if s is None:
            raise NotFoundError("提出")
        return s

    def _repo_summary(self, r: CodingRepository, progress: dict) -> CodingRepositorySummary:
        qs = self.catalog.questions_of(r.id)
        return CodingRepositorySummary(
            **r.model_dump(),
            question_count=len(qs),
            executable_count=sum(1 for q in qs if q.executable),
            solved_count=sum(1 for q in qs if (p := progress.get(q.id)) and p.solved_at),
        )

    @staticmethod
    def _issue_summary(q: CodingQuestion, progress: dict, submitted: dict) -> CodingIssueSummary:
        p = progress.get(q.id)
        if p and p.solved_at:
            status = "solved"
        elif submitted.get(q.id) or (p and p.hints_revealed):
            status = "in-progress"
        else:
            status = "open"
        return CodingIssueSummary(
            id=q.id,
            repository_id=q.repository_id,
            issue_number=q.issue_number,
            title=q.title,
            description=q.description,
            language=q.language,
            framework=q.framework,
            difficulty=q.difficulty,
            type=q.type,
            estimated_minutes=q.estimated_minutes,
            tags=q.tags,
            executable=q.executable,
            status=status,
        )
