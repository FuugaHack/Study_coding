import uuid
from datetime import UTC, datetime, timedelta

from app.content.loader import Catalog, Question
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
# ボス戦も同じコースは 1 日 3 回まで (正誤フィードバックからの総当たりを防ぐ)
BOSS_ATTEMPTS_PER_DAY = 3


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
            taken = await self.repo.count_challenges(user_id, course.id, "boss", today)
            if taken >= BOSS_ATTEMPTS_PER_DAY:
                raise ConflictError(
                    f"このコースのボス戦は 1 日 {BOSS_ATTEMPTS_PER_DAY} 回までです。"
                    "復習してから明日また挑もう!"
                )

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

        graded: list[tuple[Question, bool, list[bool]]] = []
        for qid in session.question_ids:
            found = self.catalog.find_question(qid)
            if found is None:  # コンテンツ更新で削除された問題は採点対象外
                continue
            question = found[1]
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
            graded.append((question, ok, blanks))

        correct = sum(1 for _, ok, _ in graded if ok)
        score = ch.ChallengeScore(correct=correct, total=len(graded))
        # 正解・解説は合格したときだけ返す。不合格・時間切れでは正誤のみ
        # (答えを見るためだけに受験 → 通常回答で満額 XP、という抜け道を防ぐ)
        results = [
            ChallengeQuestionResult(
                question_id=q.id,
                correct=ok,
                blank_results=blanks,
                correct_answer=q.answer if score.passed else None,
                explanation=q.explanation if score.passed else None,
            )
            for q, ok, blanks in graded
        ]
        session.status = "passed" if score.passed else "failed"
        session.correct_count = correct
        session.completed_at = now

        summary = await self.gamification.begin_summary(user_id)
        if score.passed:
            # 未解決の問題の答えを見せた場合は「表示済み」として初回正解キーを 0 XP で埋める。
            # 以後その問題に正解しても復習 XP のみ (M1 の正解表示ルールと同じ扱い)
            for q, ok, _ in graded:
                if not ok and not before.status.get(q.id):
                    await self.gamification.award(
                        user_id,
                        amount=0,
                        reason="revealed",
                        key=g.first_correct_key(q.id),
                        today=today,
                    )
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
        questions = [
            found[1]
            for qid in session.question_ids
            if (found := self.catalog.find_question(qid)) is not None
        ]
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
            server_now=datetime.now(UTC),
        )
