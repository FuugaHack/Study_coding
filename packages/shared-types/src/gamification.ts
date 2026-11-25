// backend: app/schemas/gamification.py と対応

export interface QuestProgress {
  id: string;
  title: string;
  progress: number;
  target: number;
  reward_xp: number;
  reward_coins: number;
  completed: boolean;
}

export interface GamificationStatsResponse {
  total_xp: number;
  level: number;
  xp_into_level: number;
  xp_for_next_level: number;
  coins: number;
  current_streak: number;
  longest_streak: number;
  studied_today: boolean;
  daily_quests: QuestProgress[];
}

export interface CompletedQuest {
  id: string;
  title: string;
  reward_xp: number;
}

export interface RewardResponse {
  xp_gained: number;
  coins_gained: number;
  leveled_up: boolean;
  level: number;
  completed_quests: CompletedQuest[];
}
