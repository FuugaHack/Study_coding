import { create } from "zustand";
import type { RewardResponse } from "@learning-platform/shared-types";

export type RewardToast = { id: number; reward: RewardResponse };

type RewardState = {
  toasts: RewardToast[];
  push: (reward: RewardResponse) => void;
  dismiss: (id: number) => void;
};

let nextId = 1;
const TOAST_MS = 3500;

/** 回答で得た報酬 (XP / コイン / レベルアップ / クエスト達成) の演出キュー */
export const useRewardStore = create<RewardState>((set, get) => ({
  toasts: [],
  push: (reward) => {
    const nothing =
      reward.xp_gained === 0 && reward.coins_gained === 0 && !reward.leveled_up;
    if (nothing) return;
    const id = nextId++;
    set({ toasts: [...get().toasts, { id, reward }] });
    setTimeout(() => get().dismiss(id), reward.leveled_up ? TOAST_MS * 1.5 : TOAST_MS);
  },
  dismiss: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) }),
}));
