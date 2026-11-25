"""ゲーミフィケーションの純粋ロジック (DB に依存しない)。

ルールの根拠は docs/expansion/m1-design.md を参照。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from app.config import settings

# ---------------------------------------------------------------- 日付


def local_today(now: datetime | None = None) -> date:
    """APP_TIMEZONE 基準の「今日」。ストリーク・クエストの日付境界に使う。"""
    tz = ZoneInfo(settings.APP_TIMEZONE)
    return (now.astimezone(tz) if now else datetime.now(tz)).date()


# ---------------------------------------------------------------- レベル

MAX_LEVEL = 999


def xp_required_for_level(level: int) -> int:
    """レベル `level` に到達するのに必要な累計 XP。L1=0, L2=50, L3=150, L4=300 ..."""
    if level <= 1:
        return 0
    return 25 * level * (level - 1)


def level_for_xp(total_xp: int) -> int:
    level = 1
    while level < MAX_LEVEL and xp_required_for_level(level + 1) <= total_xp:
        level += 1
    return level


@dataclass(frozen=True)
class LevelProgress:
    level: int
    xp_into_level: int
    xp_for_next_level: int  # 現レベル→次レベルに必要な XP 幅


def level_progress(total_xp: int) -> LevelProgress:
    level = level_for_xp(total_xp)
    base = xp_required_for_level(level)
    nxt = xp_required_for_level(level + 1)
    return LevelProgress(level=level, xp_into_level=total_xp - base, xp_for_next_level=nxt - base)


# ---------------------------------------------------------------- ストリーク

STREAK_FREEZE_COST = 50  # コイン
MAX_STREAK_FREEZES = 2


@dataclass(frozen=True)
class StreakState:
    current: int
    longest: int
    last_active_date: date | None


def missed_days(last: date | None, today: date) -> int:
    """最後の学習日から今日までに、学習しなかった日数 (昨日学習していれば 0)。"""
    if last is None or last >= today:
        return 0
    return max(0, (today - last).days - 1)


def freezes_to_consume(state: StreakState, today: date, freezes: int) -> int:
    """今日学習したときに消費するストリークフリーズの数 (守り切れない場合は 0)。"""
    missed = missed_days(state.last_active_date, today)
    return missed if 0 < missed <= freezes else 0


def advance_streak(state: StreakState, today: date, freezes: int = 0) -> StreakState:
    """今日学習した (XP を得た) ときのストリーク更新。

    休んだ日数がストリークフリーズの所持数以内なら、ストリークは途切れない。
    """
    last = state.last_active_date
    if last == today:
        return state
    continued = last == today - timedelta(days=1) or freezes_to_consume(state, today, freezes) > 0
    current = state.current + 1 if continued else 1
    return StreakState(current=current, longest=max(state.longest, current), last_active_date=today)


def effective_streak(state: StreakState, today: date, freezes: int = 0) -> int:
    """表示用ストリーク。昨日まで続いていれば (またはフリーズで守れるなら) 継続中とみなす。"""
    last = state.last_active_date
    if last in (today, today - timedelta(days=1)):
        return state.current
    missed = missed_days(last, today)
    if 0 < missed <= freezes:
        return state.current
    return 0


# ---------------------------------------------------------------- 報酬

FIRST_CORRECT_XP = {"easy": 10, "normal": 15, "hard": 20}
REVIEW_XP = 2
SELF_CHECK_XP = 5
LESSON_FIRST_CORRECT_XP = 20
QUEST_COINS = 5
BADGE_COINS = 10


def first_correct_key(question_id: str) -> str:
    return f"q:{question_id}:first"


def review_key(question_id: str, today: date) -> str:
    return f"q:{question_id}:review:{today.isoformat()}"


def lesson_key(lesson_id: str) -> str:
    return f"lesson:{lesson_id}:first"


def quest_key(quest_id: str, period_start: date) -> str:
    return f"quest:{quest_id}:{period_start.isoformat()}"


def week_start(today: date) -> date:
    """週の始まり (月曜日)。"""
    return today - timedelta(days=today.weekday())


# ---------------------------------------------------------------- クエスト

QuestPeriod = Literal["daily", "weekly"]


@dataclass(frozen=True)
class QuestActivity:
    """期間 (今日 / 今週) 内の学習量。"""

    correct_questions: int = 0  # 正解した異なる問題数
    attempted_questions: int = 0  # 挑戦した異なる問題数
    xp_earned: int = 0  # 得た XP (クエスト報酬を除く)
    active_days: int = 0  # 学習した日数
    bosses_defeated: int = 0  # 倒したボスの数


# M1 互換の名前
TodayActivity = QuestActivity


@dataclass(frozen=True)
class QuestDefinition:
    id: str
    title: str
    target: int
    reward_xp: int
    metric: str  # QuestActivity のフィールド名
    period: QuestPeriod = "daily"
    reward_coins: int = QUEST_COINS

    def progress(self, activity: QuestActivity) -> int:
        return min(getattr(activity, self.metric), self.target)

    def is_complete(self, activity: QuestActivity) -> bool:
        return getattr(activity, self.metric) >= self.target

    def period_start(self, today: date) -> date:
        return week_start(today) if self.period == "weekly" else today


DAILY_QUESTS: tuple[QuestDefinition, ...] = (
    QuestDefinition("daily_correct_3", "今日 3 問正解する", 3, 15, "correct_questions"),
    QuestDefinition("daily_attempt_5", "今日 5 問に挑戦する", 5, 10, "attempted_questions"),
    QuestDefinition("daily_xp_50", "今日 50 XP 獲得する", 50, 20, "xp_earned"),
)

WEEKLY_QUESTS: tuple[QuestDefinition, ...] = (
    QuestDefinition(
        "weekly_correct_30", "今週 30 問正解する", 30, 50, "correct_questions", "weekly", 20
    ),
    QuestDefinition("weekly_days_5", "今週 5 日学習する", 5, 60, "active_days", "weekly", 20),
    QuestDefinition(
        "weekly_boss_1", "今週ボスを 1 体倒す", 1, 40, "bosses_defeated", "weekly", 15
    ),
)

ALL_QUESTS = DAILY_QUESTS + WEEKLY_QUESTS

QUEST_REASON = "quest"


# ---------------------------------------------------------------- バッジ


@dataclass(frozen=True)
class BadgeMetrics:
    solved_questions: int = 0
    current_streak: int = 0
    level: int = 1
    completed_courses: int = 0
    bosses_defeated: int = 0
    placements_passed: int = 0
    quests_completed: int = 0


@dataclass(frozen=True)
class BadgeDefinition:
    id: str
    title: str
    description: str
    icon: str
    metric: str  # BadgeMetrics のフィールド名
    threshold: int

    def is_earned(self, m: BadgeMetrics) -> bool:
        return getattr(m, self.metric) >= self.threshold


BADGES: tuple[BadgeDefinition, ...] = (
    BadgeDefinition("first_step", "はじめの一歩", "初めて問題に正解する", "🌱", "solved_questions", 1),
    BadgeDefinition("solver_10", "見習いソルバー", "10 問に正解する", "🧩", "solved_questions", 10),
    BadgeDefinition("solver_50", "熟練ソルバー", "50 問に正解する", "🧠", "solved_questions", 50),
    BadgeDefinition("solver_100", "百問斬り", "100 問に正解する", "⚔️", "solved_questions", 100),
    BadgeDefinition("streak_3", "三日坊主卒業", "3 日連続で学習する", "🔥", "current_streak", 3),
    BadgeDefinition("streak_7", "一週間の習慣", "7 日連続で学習する", "📅", "current_streak", 7),
    BadgeDefinition("streak_30", "継続は力なり", "30 日連続で学習する", "🏔️", "current_streak", 30),
    BadgeDefinition("level_5", "成長期", "レベル 5 に到達する", "⭐", "level", 5),
    BadgeDefinition("level_10", "一人前", "レベル 10 に到達する", "🌟", "level", 10),
    BadgeDefinition("course_1", "完走者", "コースを 1 つ完走する", "🏁", "completed_courses", 1),
    BadgeDefinition("course_5", "マルチスキル", "コースを 5 つ完走する", "🎓", "completed_courses", 5),
    BadgeDefinition("boss_1", "ボスハンター", "ボスを初めて倒す", "👑", "bosses_defeated", 1),
    BadgeDefinition("boss_5", "ボスマスター", "ボスを 5 体倒す", "🐉", "bosses_defeated", 5),
    BadgeDefinition("placement_1", "飛び級", "実力テストに合格する", "🚀", "placements_passed", 1),
    BadgeDefinition("quest_10", "クエスト職人", "クエストを 10 回達成する", "🎯", "quests_completed", 10),
)

BADGE_BY_ID = {b.id: b for b in BADGES}


def newly_earned_badges(metrics: BadgeMetrics, owned: set[str]) -> list[BadgeDefinition]:
    return [b for b in BADGES if b.id not in owned and b.is_earned(metrics)]
