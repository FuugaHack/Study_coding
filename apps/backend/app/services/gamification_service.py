from dataclasses import dataclass, field
from datetime import date

from app.domain import gamification as g
from app.repositories.gamification_repository import GamificationRepository
from app.schemas.gamification import (
    CompletedQuest,
    GamificationStatsResponse,
    QuestProgressResponse,
)


@dataclass
class RewardSummary:
    xp_gained: int = 0
    coins_gained: int = 0
    level_before: int = 1
    completed_quests: list[CompletedQuest] = field(default_factory=list)


class GamificationService:
    """XP・コイン・ストリーク・デイリークエストの付与と参照。

    XP は必ず `award()` 経由で付与する。`xp_events` の冪等キーにより、
    同じ行動に対する二重付与は起こらない (ADR-3)。
    """

    def __init__(self, repo: GamificationRepository):
        self.repo = repo

    async def award(
        self,
        user_id: str,
        *,
        amount: int,
        reason: str,
        key: str,
        today: date,
        coins: int = 0,
        summary: RewardSummary | None = None,
    ) -> bool:
        # ロック順を「user_stats → xp_events」に統一する。同一ユーザーの同時リクエストでも
        # 逆順ロックによるデッドロックが起きないよう、必ず先に stats 行をロックする。
        stats = await self.repo.lock_stats(user_id)
        inserted = await self.repo.insert_xp_event(
            user_id=user_id,
            amount=amount,
            coins=coins,
            reason=reason,
            idempotency_key=key,
            activity_date=today,
        )
        if not inserted:
            return False

        stats.total_xp += amount
        stats.coins += coins
        streak = g.advance_streak(
            g.StreakState(stats.current_streak, stats.longest_streak, stats.last_active_date),
            today,
        )
        stats.current_streak = streak.current
        stats.longest_streak = streak.longest
        stats.last_active_date = streak.last_active_date
        await self.repo.db.flush()

        if summary is not None:
            summary.xp_gained += amount
            summary.coins_gained += coins
        return True

    async def begin_summary(self, user_id: str) -> RewardSummary:
        stats = await self.repo.get_stats(user_id)
        return RewardSummary(level_before=g.level_for_xp(stats.total_xp if stats else 0))

    async def evaluate_daily_quests(
        self, user_id: str, today: date, summary: RewardSummary | None = None
    ) -> None:
        """達成済みで未報酬のクエストに報酬を付与する。"""
        activity = await self._today_activity(user_id, today)
        for quest in g.DAILY_QUESTS:
            if not quest.is_complete(activity):
                continue
            awarded = await self.award(
                user_id,
                amount=quest.reward_xp,
                coins=g.QUEST_COINS,
                reason=g.QUEST_REASON,
                key=g.quest_key(quest.id, today),
                today=today,
                summary=summary,
            )
            if awarded and summary is not None:
                summary.completed_quests.append(
                    CompletedQuest(id=quest.id, title=quest.title, reward_xp=quest.reward_xp)
                )

    async def get_stats(self, user_id: str, today: date | None = None) -> GamificationStatsResponse:
        today = today or g.local_today()
        stats = await self.repo.get_stats(user_id)
        total_xp = stats.total_xp if stats else 0
        state = g.StreakState(
            stats.current_streak if stats else 0,
            stats.longest_streak if stats else 0,
            stats.last_active_date if stats else None,
        )
        lp = g.level_progress(total_xp)

        activity = await self._today_activity(user_id, today)
        done = await self.repo.completed_quest_keys(
            user_id, [g.quest_key(q.id, today) for q in g.DAILY_QUESTS]
        )
        quests = [
            QuestProgressResponse(
                id=q.id,
                title=q.title,
                progress=q.progress(activity),
                target=q.target,
                reward_xp=q.reward_xp,
                reward_coins=g.QUEST_COINS,
                completed=g.quest_key(q.id, today) in done,
            )
            for q in g.DAILY_QUESTS
        ]

        return GamificationStatsResponse(
            total_xp=total_xp,
            level=lp.level,
            xp_into_level=lp.xp_into_level,
            xp_for_next_level=lp.xp_for_next_level,
            coins=stats.coins if stats else 0,
            current_streak=g.effective_streak(state, today),
            longest_streak=state.longest,
            studied_today=state.last_active_date == today,
            daily_quests=quests,
        )

    async def _today_activity(self, user_id: str, today: date) -> g.TodayActivity:
        correct, attempted = await self.repo.today_question_counts(user_id, today)
        xp = await self.repo.today_xp_excluding(user_id, today, g.QUEST_REASON)
        return g.TodayActivity(
            correct_questions=correct, attempted_questions=attempted, xp_earned=xp
        )
