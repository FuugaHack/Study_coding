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
  streak_freezes: number;
  daily_quests: QuestProgress[];
  weekly_quests: QuestProgress[];
}

export interface CompletedQuest {
  id: string;
  title: string;
  reward_xp: number;
}

export interface EarnedBadge {
  id: string;
  title: string;
  icon: string;
}

export interface RewardResponse {
  xp_gained: number;
  coins_gained: number;
  leveled_up: boolean;
  level: number;
  completed_quests: CompletedQuest[];
  new_badges: EarnedBadge[];
}

export interface Badge {
  id: string;
  title: string;
  description: string;
  icon: string;
  earned_at: string | null;
}

export interface BadgesResponse {
  badges: Badge[];
}

export interface ShopPurchaseResponse {
  coins: number;
  streak_freezes: number;
}
