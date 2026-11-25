from dataclasses import dataclass

from app.content.loader import Catalog, Course, Question
from app.core.exceptions import ForbiddenError, NotFoundError, UnprocessableError
from app.domain import challenge as ch
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
from app.services.gamification_service import GamificationService, RewardSummary

# 前提コースを「クリア」とみなす正解率 (docs/expansion/m1-design.md §5)
CLEAR_RATIO = 0.7
# 同じ問題でこの回数以上間違えたら正解を表示する
REVEAL_AFTER_INCORRECT = 2


@dataclass(frozen=True)
class ProgressView:
    """あるユーザーのコース進捗 (解答状況 + コース単位の達成) から状態を判定する。"""

    catalog: Catalog
    status: dict[str, bool]  # question_id -> solved
    achievements: dict[str, set[str]]  # course_id -> {"placement_passed", "boss_defeated"}

    def solved_count(self, course: Course) -> int:
        return sum(1 for q in course.questions if self.status.get(q.id))

    def is_cleared(self, course: Course) -> bool:
        if self.has(course, "placement_passed"):
            return True
        total = len(course.questions)
        return total > 0 and self.solved_count(course) / total >= CLEAR_RATIO

    def is_unlocked(self, course: Course) -> bool:
        for pid in course.prerequisites:
            pre = self.catalog.get_course(pid)
            if pre is None or not self.is_cleared(pre):
                return False
        return True

    def has(self, course: Course, kind: str) -> bool:
        return kind in self.achievements.get(course.id, set())


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

    async def progress(self, user_id: str) -> ProgressView:
        return ProgressView(
            catalog=self.catalog,
            status=await self.repo.get_question_status(user_id),
            achievements=await self.repo.course_achievements(user_id),
        )

    async def list_courses(self, user_id: str) -> CatalogCourseListResponse:
        view = await self.progress(user_id)
        return CatalogCourseListResponse(
            courses=[self._summary(c, view) for c in self.catalog.courses],
            content_version=self.catalog.version,
        )

    async def get_course(self, user_id: str, course_id: str) -> CatalogCourseDetailResponse:
        course = self.catalog.get_course(course_id)
        if course is None:
            raise NotFoundError("コース")
        view = await self.progress(user_id)
        summary = self._summary(course, view)
        return CatalogCourseDetailResponse(
            **summary.model_dump(),
            questions=[
                self.public_question(q, view.status.get(q.id, False)) for q in course.questions
            ],
        )

    # ---------------------------------------------------------- 回答

    async def answer(self, user_id: str, question_id: str, req: AnswerRequest) -> AnswerResponse:
        found = self.catalog.find_question(question_id)
        if found is None:
            raise NotFoundError("問題")
        course, question = found

        if not (await self.progress(user_id)).is_unlocked(course):
            raise ForbiddenError("前提コースをクリアすると挑戦できます")

        answer = req.model_dump(exclude={"time_spent_seconds"}, exclude_none=True)
        try:
            result = grade(question, answer)
        except InvalidAnswerError as e:
            raise UnprocessableError(str(e)) from e

        # 同一ユーザーの回答処理を直列化する (クエスト判定・XP 付与の整合性のため)
        await self.repo.lock_stats(user_id)

        today = g.local_today()
        # 記述式を空欄のまま解答例だけ見た場合は「回答」として記録せず、XP も付与しない
        # (解決済み扱い・クエスト進捗の水増しを防ぐ)
        peek_only = result.outcome == "self_check" and not answer.get("text", "").strip()
        # この回答より前に正解が表示済みか (表示後の初回正解は満額にしない)
        was_revealed = (
            await self.repo.count_incorrect(user_id, question.id) >= REVEAL_AFTER_INCORRECT
        )
        if not peek_only:
            await self.repo.create_question_attempt(
                user_id=user_id,
                question_id=question.id,
                course_id=course.id,
                is_correct={"correct": True, "incorrect": False, "self_check": None}[
                    result.outcome
                ],
                answer=answer,
                content_version=self.catalog.version,
                activity_date=today,
                time_spent_seconds=req.time_spent_seconds,
            )

        summary = await self.gamification.begin_summary(user_id)
        if result.outcome == "correct":
            first = await self.gamification.award(
                user_id,
                amount=g.REVIEW_XP if was_revealed else g.FIRST_CORRECT_XP[question.difficulty],
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
        elif result.outcome == "self_check" and not peek_only:
            await self.gamification.award(
                user_id,
                amount=g.SELF_CHECK_XP,
                reason="question",
                key=g.first_correct_key(question.id),
                today=today,
                summary=summary,
            )
        await self.gamification.after_activity(user_id, today, summary)

        reveal = result.outcome != "incorrect" or (
            await self.repo.count_incorrect(user_id, question.id) >= REVEAL_AFTER_INCORRECT
        )
        stats = await self.gamification.get_stats(user_id, today)
        # レスポンス送信前に確定させる (get_db の yield 後の commit はレスポンス送信後に
        # 実行され得るため、commit 失敗時に「付与済み」と表示してしまうのを防ぐ)
        await self.repo.db.commit()
        return AnswerResponse(
            question_id=question.id,
            result=result.outcome,
            blank_results=result.blank_results,
            correct_answer=question.answer if reveal else None,
            explanation=question.explanation if reveal else None,
            reward=reward_response(summary, stats.level),
            stats=stats,
        )

    # ---------------------------------------------------------- helpers

    def _summary(self, course: Course, view: ProgressView) -> CatalogCourseSummary:
        total = len(course.questions)
        solved = view.solved_count(course)
        attempted = any(q.id in view.status for q in course.questions)
        locked = not view.is_unlocked(course)
        cleared = view.is_cleared(course)
        if locked:
            state = "locked"
        elif total and solved == total:
            state = "completed"
        elif attempted or cleared:
            state = "in-progress"
        else:
            state = "not-started"
        available = ch.is_available(course)
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
            is_cleared=cleared,
            skipped=view.has(course, "placement_passed"),
            boss_defeated=view.has(course, "boss_defeated"),
            can_take_placement=available and not cleared,
            can_challenge_boss=available and cleared and not locked,
        )

    @staticmethod
    def public_question(q: Question, solved: bool) -> CatalogQuestion:
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


def reward_response(summary: RewardSummary, level: int) -> RewardResponse:
    return RewardResponse(
        xp_gained=summary.xp_gained,
        coins_gained=summary.coins_gained,
        leveled_up=level > summary.level_before,
        level=level,
        completed_quests=summary.completed_quests,
        new_badges=summary.new_badges,
    )
