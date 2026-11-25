from app.content.loader import Catalog, Course, Question
from app.core.exceptions import ForbiddenError, NotFoundError, UnprocessableError
from app.domain import gamification as g
from app.domain.grading import InvalidAnswerError, grade
from app.repositories.gamification_repository import GamificationRepository
from app.schemas.catalog import (
    AnswerRequest,
    AnswerResponse,
    CatalogCourseDetailResponse,
    CatalogCourseListResponse,
    CatalogCourseSummary,
    CatalogQuestion,
)
from app.schemas.gamification import RewardResponse
from app.services.gamification_service import GamificationService

# 前提コースを「クリア」とみなす正解率 (docs/expansion/m1-design.md §5)
CLEAR_RATIO = 0.7
# 同じ問題でこの回数以上間違えたら正解を表示する
REVEAL_AFTER_INCORRECT = 2


class CatalogService:
    def __init__(
        self,
        catalog: Catalog,
        repo: GamificationRepository,
        gamification: GamificationService,
    ):
        self.catalog = catalog
        self.repo = repo
        self.gamification = gamification

    # ---------------------------------------------------------- 一覧・詳細

    async def list_courses(self, user_id: str) -> CatalogCourseListResponse:
        status = await self.repo.get_question_status(user_id)
        return CatalogCourseListResponse(
            courses=[self._summary(c, status) for c in self.catalog.courses],
            content_version=self.catalog.version,
        )

    async def get_course(self, user_id: str, course_id: str) -> CatalogCourseDetailResponse:
        course = self.catalog.get_course(course_id)
        if course is None:
            raise NotFoundError("コース")
        status = await self.repo.get_question_status(user_id)
        summary = self._summary(course, status)
        return CatalogCourseDetailResponse(
            **summary.model_dump(),
            questions=[self._public_question(q, status.get(q.id, False)) for q in course.questions],
        )

    # ---------------------------------------------------------- 回答

    async def answer(self, user_id: str, question_id: str, req: AnswerRequest) -> AnswerResponse:
        found = self.catalog.find_question(question_id)
        if found is None:
            raise NotFoundError("問題")
        course, question = found

        status = await self.repo.get_question_status(user_id)
        if not self._is_unlocked(course, status):
            raise ForbiddenError("前提コースをクリアすると挑戦できます")

        answer = req.model_dump(exclude={"time_spent_seconds"}, exclude_none=True)
        try:
            result = grade(question, answer)
        except InvalidAnswerError as e:
            raise UnprocessableError(str(e)) from e

        # 同一ユーザーの回答処理を直列化する (クエスト判定・XP 付与の整合性のため)
        await self.repo.lock_stats(user_id)

        today = g.local_today()
        is_correct = {"correct": True, "incorrect": False, "self_check": None}[result.outcome]
        # 記述式を空欄のまま解答例だけ見た場合は「未解決」として記録し、XP は付与しない
        gave_up = result.outcome == "self_check" and not answer.get("text", "").strip()
        if gave_up:
            is_correct = False
        await self.repo.create_question_attempt(
            user_id=user_id,
            question_id=question.id,
            course_id=course.id,
            is_correct=is_correct,
            answer=answer,
            content_version=self.catalog.version,
            activity_date=today,
            time_spent_seconds=req.time_spent_seconds,
        )

        summary = await self.gamification.begin_summary(user_id)
        if result.outcome == "correct":
            first = await self.gamification.award(
                user_id,
                amount=g.FIRST_CORRECT_XP[question.difficulty],
                reason="question",
                key=g.first_correct_key(question.id),
                today=today,
                summary=summary,
            )
            if not first:
                await self.gamification.award(
                    user_id,
                    amount=g.REVIEW_XP,
                    reason="review",
                    key=g.review_key(question.id, today),
                    today=today,
                    summary=summary,
                )
        elif result.outcome == "self_check" and not gave_up:
            await self.gamification.award(
                user_id,
                amount=g.SELF_CHECK_XP,
                reason="question",
                key=g.first_correct_key(question.id),
                today=today,
                summary=summary,
            )
        await self.gamification.evaluate_daily_quests(user_id, today, summary)

        reveal = result.outcome != "incorrect" or (
            await self.repo.count_incorrect(user_id, question.id) >= REVEAL_AFTER_INCORRECT
        )
        stats = await self.gamification.get_stats(user_id, today)
        return AnswerResponse(
            question_id=question.id,
            result=result.outcome,
            blank_results=result.blank_results,
            correct_answer=question.answer if reveal else None,
            explanation=question.explanation if reveal else None,
            reward=RewardResponse(
                xp_gained=summary.xp_gained,
                coins_gained=summary.coins_gained,
                leveled_up=stats.level > summary.level_before,
                level=stats.level,
                completed_quests=summary.completed_quests,
            ),
            stats=stats,
        )

    # ---------------------------------------------------------- helpers

    def _course_solved(self, course: Course, status: dict[str, bool]) -> int:
        return sum(1 for q in course.questions if status.get(q.id))

    def _is_cleared(self, course: Course, status: dict[str, bool]) -> bool:
        total = len(course.questions)
        return total > 0 and self._course_solved(course, status) / total >= CLEAR_RATIO

    def _is_unlocked(self, course: Course, status: dict[str, bool]) -> bool:
        for pid in course.prerequisites:
            pre = self.catalog.get_course(pid)
            if pre is None or not self._is_cleared(pre, status):
                return False
        return True

    def _summary(self, course: Course, status: dict[str, bool]) -> CatalogCourseSummary:
        total = len(course.questions)
        solved = self._course_solved(course, status)
        attempted = any(q.id in status for q in course.questions)
        locked = not self._is_unlocked(course, status)
        if locked:
            state = "locked"
        elif total and solved == total:
            state = "completed"
        elif attempted:
            state = "in-progress"
        else:
            state = "not-started"
        return CatalogCourseSummary(
            id=course.id,
            title=course.title,
            description=course.description,
            category=course.category,
            level=course.level,
            icon=course.icon,
            estimated_hours=course.estimated_hours,
            tags=course.tags,
            prerequisites=course.prerequisites,
            prerequisite_titles=[
                pre.title
                for pid in course.prerequisites
                if (pre := self.catalog.get_course(pid)) is not None
            ],
            question_count=total,
            solved_count=solved,
            progress=round(solved / total * 100) if total else 0,
            status=state,
            is_locked=locked,
        )

    @staticmethod
    def _public_question(q: Question, solved: bool) -> CatalogQuestion:
        return CatalogQuestion(
            id=q.id,
            type=q.type,
            title=q.title,
            description=q.description,
            difficulty=q.difficulty,
            choices=q.choices,
            code_template=q.code_template,
            blank_count=len(q.answers) if q.type == "code" else None,
            solved=solved,
        )
