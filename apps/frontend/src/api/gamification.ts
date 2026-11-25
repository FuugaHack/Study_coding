import type { GamificationStatsResponse } from "@learning-platform/shared-types";
import { api } from "@/lib/api";

export async function getMyStats() {
  const { data } = await api.get<GamificationStatsResponse>("/gamification/me");
  return data;
}
