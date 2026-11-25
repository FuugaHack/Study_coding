from pydantic import BaseModel


class QuestProgressResponse(BaseModel):
    id: str
    title: str
    progress: int
    target: int
    reward_xp: int
    reward_coins: int
    completed: bool


class GamificationStatsResponse(BaseModel):
    total_xp: int
    level: int
    xp_into_level: int
    xp_for_next_level: int
    coins: int
    current_streak: int
    longest_streak: int
    studied_today: bool
    daily_quests: list[QuestProgressResponse]


class CompletedQuest(BaseModel):
    id: str
    title: str
    reward_xp: int


class RewardResponse(BaseModel):
    xp_gained: int
    coins_gained: int
    leveled_up: bool
    level: int
    completed_quests: list[CompletedQuest]
