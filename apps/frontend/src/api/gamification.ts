import type {
  BadgesResponse,
  GamificationStatsResponse,
  ShopPurchaseResponse,
} from "@learning-platform/shared-types";
import { api } from "@/lib/api";

export async function getMyStats() {
  const { data } = await api.get<GamificationStatsResponse>("/gamification/me");
  return data;
}

export async function getMyBadges() {
  const { data } = await api.get<BadgesResponse>("/gamification/badges");
  return data;
}

export async function buyStreakFreeze() {
  const { data } = await api.post<ShopPurchaseResponse>("/gamification/shop/streak-freeze");
  return data;
}
