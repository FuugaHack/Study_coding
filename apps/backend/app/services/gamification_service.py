import uuid
from dataclasses import dataclass, field
from datetime import date

from app.content.loader import Catalog
from app.core.exceptions import ConflictError
from app.domain import gamification as g
from app.repositories.gamification_repository import GamificationRepository
from app.schemas.gamification import (
    BadgeResponse,
    BadgesResponse,
    CompletedQuest,
    EarnedBadge,
    GamificationStatsResponse,
    QuestProgressResponse,
    ShopPurchaseResponse,
)


@dataclass
class RewardSummary:
    xp_gained: int = 0
    coins_gained: int = 0
    level_before: int = 1
    completed_quests: list[CompletedQuest] = field(default_factory=list)
    new_badges: list[EarnedBadge] = field(default_factory=list)


class GamificationService:
    """XP・コイン・ストリーク・クエスト・バッジの付与と参照。

    XP / コインの付与は必ず `award()` 経由で行う。`xp_events` の冪等キーにより、
    同じ行動に対する二重付与は起こらない (ADR-3)。
    """

    def __init__(self, repo: GamificationRepository, catalog: Catalog):
        self.repo = repo
        self.catalog = catalog

    # ------------------------------------------------------------------ 付与

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
        state = g.StreakState(stats.current_streak, stats.longest_streak, stats.last_active_date)
        held = stats.streak_freezes
        streak = g.advance_streak(state, today, held)
        stats.streak_freezes = held - g.freezes_to_consume(state, today, held)
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

    async def after_activity(
        self, user_id: str, today: date, summary: RewardSummary | None = None
    ) -> None:
        """学習行動の後に呼ぶ: クエスト → バッジの順に判定して報酬を付与する。"""
        await self.evaluate_quests(user_id, today, summary)
        await self.evaluate_badges(user_id, today, summary)

    async def evaluate_quests(
        self, user_id: str, today: date, summary: RewardSummary | None = None
    ) -> None:
        """達成済みで未報酬のクエスト (デイリー / ウィークリー) に報酬を付与する。"""
        activity = {
            "daily": await self._activity(user_id, today, today),
            "weekly": await self._activity(user_id, g.week_start(today), today),
        }
        for quest in g.ALL_QUESTS:
            if not quest.is_complete(activity[quest.period]):
                continue
            awarded = await self.award(
                user_id,
                amount=quest.reward_xp,
                coins=quest.reward_coins,
                reason=g.QUEST_REASON,
                key=g.quest_key(quest.id, quest.period_start(today)),
                today=today,
                summary=summary,
            )
            if awarded and summary is not None:
                summary.completed_quests.append(
                    CompletedQuest(id=quest.id, title=quest.title, reward_xp=quest.reward_xp)
                )

    # 後方互換 (M1 の呼び出し名)
    evaluate_daily_quests = evaluate_quests

    async def evaluate_badges(
        self, user_id: str, today: date, summary: RewardSummary | None = None
    ) -> None:
        owned = await self.repo.owned_badges(user_id)
        metrics = await self._badge_metrics(user_id, today)
        for badge in g.newly_earned_badges(metrics, set(owned)):
            if not await self.repo.insert_badge(user_id, badge.id):
                continue
            await self.award(
                user_id,
                amount=0,
                coins=g.BADGE_COINS,
                reason="badge",
                key=f"badge:{badge.id}",
                today=today,
                summary=summary,
            )
            if summary is not None:
                summary.new_badges.append(
                    EarnedBadge(id=badge.id, title=badge.title, icon=badge.icon)
                )

    # ------------------------------------------------------------------ ショップ

    async def buy_streak_freeze(self, user_id: str) -> ShopPurchaseResponse:
        stats = await self.repo.lock_stats(user_id)
        if stats.streak_freezes >= g.MAX_STREAK_FREEZES:
            raise ConflictError(f"ストリークフリーズは最大 {g.MAX_STREAK_FREEZES} 個まで持てます")
        if stats.coins < g.STREAK_FREEZE_COST:
            raise ConflictError("コインが足りません")
        # フリーズは「休む前に備える」アイテム。休んだ後に買って途切れた記録を戻すことはできない
        if g.missed_days(stats.last_active_date, g.local_today()) > 0:
            raise ConflictError(
                "ストリークフリーズは休む前に準備するアイテムです。今日 1 問解いてから購入しよう"
            )
        # 台帳にも記録する (XP は 0、コインはマイナス)
        await self.repo.insert_xp_event(
            user_id=user_id,
            amount=0,
            coins=-g.STREAK_FREEZE_COST,
            reason="shop",
            idempotency_key=f"shop:streak_freeze:{uuid.uuid4()}",
            activity_date=g.local_today(),
        )
        stats.coins -= g.STREAK_FREEZE_COST
        stats.streak_freezes += 1
        await self.repo.db.flush()
        return ShopPurchaseResponse(coins=stats.coins, streak_freezes=stats.streak_freezes)

    # ------------------------------------------------------------------ 参照

    async def get_stats(self, user_id: str, today: date | None = None) -> GamificationStatsResponse:
        today = today or g.local_today()
        stats = await self.repo.get_stats(user_id)
        total_xp = stats.total_xp if stats else 0
        freezes = stats.streak_freezes if stats else 0
        state = g.StreakState(
            stats.current_streak if stats else 0,
            stats.longest_streak if stats else 0,
            stats.last_active_date if stats else None,
        )
        lp = g.level_progress(total_xp)

        activity = {
            "daily": await self._activity(user_id, today, today),
            "weekly": await self._activity(user_id, g.week_start(today), today),
        }
        done = await self.repo.completed_quest_keys(
            user_id, [g.quest_key(q.id, q.period_start(today)) for q in g.ALL_QUESTS]
        )

        def progress(quests: tuple[g.QuestDefinition, ...]) -> list[QuestProgressResponse]:
            return [
                QuestProgressResponse(
                    id=q.id,
                    title=q.title,
                    progress=q.progress(activity[q.period]),
                    target=q.target,
                    reward_xp=q.reward_xp,
                    reward_coins=q.reward_coins,
                    completed=g.quest_key(q.id, q.period_start(today)) in done,
                )
                for q in quests
            ]

        return GamificationStatsResponse(
            total_xp=total_xp,
            level=lp.level,
            xp_into_level=lp.xp_into_level,
            xp_for_next_level=lp.xp_for_next_level,
            coins=stats.coins if stats else 0,
            current_streak=g.effective_streak(state, today, freezes),
            longest_streak=state.longest,
            studied_today=state.last_active_date == today,
            streak_freezes=freezes,
            daily_quests=progress(g.DAILY_QUESTS),
            weekly_quests=progress(g.WEEKLY_QUESTS),
        )

    async def get_badges(self, user_id: str) -> BadgesResponse:
        owned = await self.repo.owned_badges(user_id)
        return BadgesResponse(
            badges=[
                BadgeResponse(
                    id=b.id,
                    title=b.title,
                    description=b.description,
                    icon=b.icon,
                    earned_at=owned.get(b.id),
                )
                for b in g.BADGES
            ]
        )

    # ------------------------------------------------------------------ 内部

    async def _activity(self, user_id: str, start: date, end: date) -> g.QuestActivity:
        correct, attempted = await self.repo.period_question_counts(user_id, start, end)
        return g.QuestActivity(
            correct_questions=correct,
            attempted_questions=attempted,
            xp_earned=await self.repo.period_xp_excluding(user_id, start, end, g.QUEST_REASON),
            active_days=await self.repo.active_days(user_id, start, end),
            bosses_defeated=await self.repo.bosses_defeated(user_id, start, end),
        )

    async def _badge_metrics(self, user_id: str, today: date) -> g.BadgeMetrics:
        status = await self.repo.get_question_status(user_id)
        solved = {qid for qid, ok in status.items() if ok}
        completed_courses = sum(
            1
            for c in self.catalog.courses
            if c.questions and all(q.id in solved for q in c.questions)
        )
        achievements = await self.repo.course_achievements(user_id)
        stats = await self.repo.get_stats(user_id)
        state = g.StreakState(
            stats.current_streak if stats else 0,
            stats.longest_streak if stats else 0,
            stats.last_active_date if stats else None,
        )
        return g.BadgeMetrics(
            solved_questions=len(solved),
            current_streak=g.effective_streak(state, today, stats.streak_freezes if stats else 0),
            level=g.level_for_xp(stats.total_xp if stats else 0),
            completed_courses=completed_courses,
            bosses_defeated=sum(1 for kinds in achievements.values() if "boss_defeated" in kinds),
            placements_passed=sum(
                1 for kinds in achievements.values() if "placement_passed" in kinds
            ),
            quests_completed=await self.repo.count_xp_events(user_id, g.QUEST_REASON),
        )
