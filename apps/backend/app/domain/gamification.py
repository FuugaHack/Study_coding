"""ゲーミフィケーションの純粋ロジック (DB に依存しない)。

ルールの根拠は docs/expansion/m1-design.md を参照。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
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


@dataclass(frozen=True)
class StreakState:
    current: int
    longest: int
    last_active_date: date | None


def advance_streak(state: StreakState, today: date) -> StreakState:
    """今日学習した (XP を得た) ときのストリーク更新。"""
    last = state.last_active_date
    if last == today:
        return state
    current = state.current + 1 if last == today - timedelta(days=1) else 1
    return StreakState(current=current, longest=max(state.longest, current), last_active_date=today)


def effective_streak(state: StreakState, today: date) -> int:
    """表示用ストリーク。昨日まで続いていれば今日まだ学習していなくても継続中とみなす。"""
    if state.last_active_date in (today, today - timedelta(days=1)):
        return state.current
    return 0


# ---------------------------------------------------------------- 報酬

FIRST_CORRECT_XP = {"easy": 10, "normal": 15, "hard": 20}
REVIEW_XP = 2
SELF_CHECK_XP = 5
LESSON_FIRST_CORRECT_XP = 20
QUEST_COINS = 5


def first_correct_key(question_id: str) -> str:
    return f"q:{question_id}:first"


def review_key(question_id: str, today: date) -> str:
    return f"q:{question_id}:review:{today.isoformat()}"


def lesson_key(lesson_id: str) -> str:
    return f"lesson:{lesson_id}:first"


def quest_key(quest_id: str, today: date) -> str:
    return f"quest:{quest_id}:{today.isoformat()}"


# ---------------------------------------------------------------- デイリークエスト


@dataclass(frozen=True)
class TodayActivity:
    correct_questions: int  # 今日正解した異なる問題数
    attempted_questions: int  # 今日挑戦した異なる問題数
    xp_earned: int  # 今日得た XP (クエスト報酬を除く)


@dataclass(frozen=True)
class QuestDefinition:
    id: str
    title: str
    target: int
    reward_xp: int
    metric: str  # TodayActivity のフィールド名

    def progress(self, activity: TodayActivity) -> int:
        return min(getattr(activity, self.metric), self.target)

    def is_complete(self, activity: TodayActivity) -> bool:
        return getattr(activity, self.metric) >= self.target


DAILY_QUESTS: tuple[QuestDefinition, ...] = (
    QuestDefinition("daily_correct_3", "今日 3 問正解する", 3, 15, "correct_questions"),
    QuestDefinition("daily_attempt_5", "今日 5 問に挑戦する", 5, 10, "attempted_questions"),
    QuestDefinition("daily_xp_50", "今日 50 XP 獲得する", 50, 20, "xp_earned"),
)

QUEST_REASON = "quest"
