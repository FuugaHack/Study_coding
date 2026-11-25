import { useRewardStore } from "@/stores/rewards";

/** 画面右下に XP 獲得・クエスト達成・レベルアップを演出表示する */
export function RewardToaster() {
  const toasts = useRewardStore((s) => s.toasts);
  const dismiss = useRewardStore((s) => s.dismiss);

  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-72 flex-col gap-2"
    >
      {toasts.map(({ id, reward }) => (
        <button
          key={id}
          type="button"
          onClick={() => dismiss(id)}
          className="pointer-events-auto rounded-2xl bg-white p-4 text-left shadow-xl ring-1 ring-slate-200 motion-safe:animate-pop"
        >
          {reward.leveled_up && (
            <div className="mb-2 rounded-xl bg-gradient-to-r from-amber-400 via-orange-400 to-pink-500 px-3 py-2 text-center text-white">
              <div className="text-2xl" aria-hidden>
                🎉
              </div>
              <div className="text-sm font-bold">レベルアップ! Lv {reward.level}</div>
            </div>
          )}
          <div className="flex items-center gap-3 text-sm font-semibold">
            {reward.xp_gained > 0 && (
              <span className="text-violet-600">+{reward.xp_gained} XP</span>
            )}
            {reward.coins_gained > 0 && (
              <span className="text-amber-600">
                <span aria-hidden>🪙</span> +{reward.coins_gained}
              </span>
            )}
          </div>
          {reward.completed_quests.map((q) => (
            <div key={q.id} className="mt-1 text-xs text-emerald-700">
              <span aria-hidden>✅</span> クエスト達成: {q.title}
            </div>
          ))}
        </button>
      ))}
    </div>
  );
}
