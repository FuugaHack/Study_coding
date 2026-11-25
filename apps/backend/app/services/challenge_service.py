import uuid
from datetime import UTC, datetime, timedelta

from app.content.loader import Catalog
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.domain import challenge as ch
from app.domain import gamification as g
from app.domain.grading import InvalidAnswerError, grade
from app.models.gamification import ChallengeSession
from app.repositories.gamification_repository import GamificationRepository
from app.schemas.challenge import (
    ChallengeQuestionResult,
    ChallengeResponse,
    ChallengeResultResponse,
    StartChallengeRequest,
    SubmitChallengeRequest,
)
from app.services.catalog_service import CatalogService, reward_response
from app.services.gamification_service import GamificationService

# 同じコースの実力テストは 1 日 1 回まで (答えを覚えて再受験する総当たりを防ぐ)
PLACEMENT_ATTEMPTS_PER_DAY = 1


class ChallengeService:
    def __init__(
        self,
        catalog: Catalog,
        repo: GamificationRepository,
        gamification: GamificationService,
        catalog_service: CatalogService,
    ):
        self.catalog = catalog
        self.repo = repo
        self.gamification = gamification
        self.catalog_service = catalog_service

    async def start(self, user_id: str, req: StartChallengeRequest) -> ChallengeResponse:
        course = self.catalog.get_course(req.course_id)
        if course is None:
            raise NotFoundError("コース")
        if not ch.is_available(course):
            raise ConflictError("このコースにはチャレンジがありません")

        await self.repo.lock_stats(user_id)
        view = await self.catalog_service.progress(user_id)
        today = g.local_today()

        if req.mode == "placement":
            if view.is_cleared(course):
                raise ConflictError("このコースはすでにクリアしています")
            taken = await self.repo.count_challenges(user_id, course.id, "placement", today)
            if taken >= PLACEMENT_ATTEMPTS_PER_DAY:
                raise ConflictError(
                    "このコースの実力テストは 1 日 1 回までです。また明日挑戦しよう!"
                )
        else:
            if not view.is_unlocked(course) or not view.is_cleared(course):
                raise ForbiddenError("ボスに挑戦するには、コースの 70% に正解しよう")

        questions = ch.select_questions(course, req.mode)
        limit = ch.time_limit_seconds(req.mode, len(questions))
        session = await self.repo.create_challenge(
            ChallengeSession(
                user_id=user_id,
                course_id=course.id,
                mode=req.mode,
                question_ids=[q.id for q in questions],
                status="open",
                activity_date=today,
                expires_at=datetime.now(UTC) + timedelta(seconds=limit),
            )
        )
        await self.repo.db.commit()
        return self._to_response(session, view.status)

    async def get(self, user_id: str, challenge_id: str) -> ChallengeResponse:
        session = await self._get_session(user_id, challenge_id)
        view = await self.catalog_service.progress(user_id)
        return self._to_response(session, view.status)

    async def submit(
        self, user_id: str, challenge_id: str, req: SubmitChallengeRequest
    ) -> ChallengeResultResponse:
        # ロック順: user_stats → challenge_sessions → xp_events
        await self.repo.lock_stats(user_id)
        session = await self._get_session(user_id, challenge_id)
        if session.status != "open":
            raise ConflictError("このチャレンジはすでに提出済みです")

        course = self.catalog.get_course(session.course_id)
        before = await self.catalog_service.progress(user_id)
        now = datetime.now(UTC)
        timed_out = now > session.expires_at + timedelta(seconds=ch.SUBMIT_GRACE_SECONDS)
        today = g.local_today()

        results: list[ChallengeQuestionResult] = []
        correct = 0
        for qid in session.question_ids:
            _, question = self.catalog.find_question(qid)
            submitted = req.answers.get(qid)
            answer = (
                submitted.model_dump(exclude={"time_spent_seconds"}, exclude_none=True)
                if submitted
                else None
            )
            ok, blanks = False, []
            if answer and not timed_out:
                try:
                    result = grade(question, answer)
                    ok, blanks = result.outcome == "correct", result.blank_results
                except InvalidAnswerError:
                    pass
                await self.repo.create_question_attempt(
                    user_id=user_id,
                    question_id=qid,
                    course_id=course.id,
                    is_correct=ok,
                    answer=answer,
                    content_version=self.catalog.version,
                    activity_date=today,
                    time_spent_seconds=None,
                )
            correct += ok
            results.append(
                ChallengeQuestionResult(
                    question_id=qid,
                    correct=ok,
                    blank_results=blanks,
                    correct_answer=question.answer,
                    explanation=question.explanation,
                )
            )

        score = ch.ChallengeScore(correct=correct, total=len(session.question_ids))
        session.status = "passed" if score.passed else "failed"
        session.correct_count = correct
        session.completed_at = now

        summary = await self.gamification.begin_summary(user_id)
        if score.passed:
            if session.mode == "placement":
                for cid in {course.id, *ch.ancestors(self.catalog, course.id)}:
                    await self.repo.insert_achievement(user_id, cid, "placement_passed")
                await self.gamification.award(
                    user_id,
                    amount=ch.PLACEMENT_XP,
                    reason="placement",
                    key=ch.placement_key(course.id),
                    today=today,
                    summary=summary,
                )
            else:
                await self.repo.insert_achievement(user_id, course.id, "boss_defeated")
                await self.gamification.award(
                    user_id,
                    amount=ch.BOSS_XP,
                    coins=ch.BOSS_COINS,
                    reason="boss",
                    key=ch.boss_key(course.id),
                    today=today,
                    summary=summary,
                )
        await self.repo.db.flush()
        await self.gamification.after_activity(user_id, today, summary)

        after = await self.catalog_service.progress(user_id)
        unlocked = [
            c.title
            for c in self.catalog.courses
            if not before.is_unlocked(c) and after.is_unlocked(c)
        ]
        stats = await self.gamification.get_stats(user_id, today)
        await self.repo.db.commit()
        return ChallengeResultResponse(
            id=str(session.id),
            course_id=course.id,
            mode=session.mode,
            passed=score.passed,
            timed_out=timed_out,
            correct=score.correct,
            total=score.total,
            percent=score.percent,
            results=results,
            unlocked_courses=unlocked,
            reward=reward_response(summary, stats.level),
            stats=stats,
        )

    # ------------------------------------------------------------------ 内部

    async def _get_session(self, user_id: str, challenge_id: str) -> ChallengeSession:
        try:
            uuid.UUID(challenge_id)
        except ValueError as e:
            raise NotFoundError("チャレンジ") from e
        session = await self.repo.get_challenge(challenge_id, user_id)
        if session is None:
            raise NotFoundError("チャレンジ")
        return session

    def _to_response(self, session: ChallengeSession, status: dict[str, bool]) -> ChallengeResponse:
        course = self.catalog.get_course(session.course_id)
        questions = [self.catalog.find_question(qid)[1] for qid in session.question_ids]
        return ChallengeResponse(
            id=str(session.id),
            course_id=course.id,
            course_title=course.title,
            mode=session.mode,
            status=session.status,
            questions=[
                CatalogService.public_question(q, status.get(q.id, False)) for q in questions
            ],
            time_limit_seconds=ch.time_limit_seconds(session.mode, len(questions)),
            expires_at=session.expires_at,
            pass_percent=round(ch.PASS_RATIO * 100),
        )
