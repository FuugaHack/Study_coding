import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { buyStreakFreeze, getMyBadges, getMyStats } from "@/api/gamification";
import { ErrorState, LoadingState } from "@/components/common/LoadingState";
import { Mascot } from "@/components/mascot/Mascot";
import { getErrorMessage } from "@/lib/api";
import { queryKeys } from "@/lib/queryKeys";

const STREAK_FREEZE_COST = 50;
const MAX_STREAK_FREEZES = 2;

export function AchievementsPage() {
  const badges = useQuery({ queryKey: queryKeys.badges, queryFn: getMyBadges });
  const stats = useQuery({ queryKey: queryKeys.gamification, queryFn: getMyStats });

  if (badges.isLoading || stats.isLoading) return <LoadingState />;
  if (badges.error) return <ErrorState message={getErrorMessage(badges.error)} />;

  const list = badges.data?.badges ?? [];
  const earned = list.filter((b) => b.earned_at).length;

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">実績</h1>
          <p className="mt-1 text-sm text-slate-600">
            バッジを集めるとコインがもらえます。コインはショップで使えます。
          </p>
        </div>
        <Mascot
          mood={earned > 0 ? "cheer" : "think"}
          size={56}
          message={`バッジ ${earned} / ${list.length} 獲得`}
        />
      </header>

      <section>
        <h2 className="mb-3 text-lg font-semibold text-slate-900">バッジ</h2>
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {list.map((b) => {
            const got = !!b.earned_at;
            return (
              <li
                key={b.id}
                className={clsx(
                  "rounded-2xl border p-4 text-center transition",
                  got
                    ? "border-violet-200 bg-gradient-to-br from-violet-50 to-fuchsia-50 shadow-sm"
                    : "border-slate-200 bg-white",
                )}
              >
                <div className={clsx("text-4xl", !got && "opacity-30 grayscale")} aria-hidden>
                  {b.icon}
                </div>
                <div className="mt-2 text-sm font-semibold text-slate-900">{b.title}</div>
                <div className="mt-1 text-xs text-slate-500">{b.description}</div>
                <div className="mt-2 text-[11px] font-medium">
                  {got ? (
                    <span className="text-violet-700">
                      {new Date(b.earned_at!).toLocaleDateString("ja-JP")} 獲得
                    </span>
                  ) : (
                    <span className="text-slate-400">未獲得</span>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      </section>

      {stats.data && <Shop coins={stats.data.coins} freezes={stats.data.streak_freezes} />}
    </div>
  );
}

function Shop({ coins, freezes }: { coins: number; freezes: number }) {
  const qc = useQueryClient();
  const buy = useMutation({
    mutationFn: buyStreakFreeze,
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.gamification }),
  });
  const full = freezes >= MAX_STREAK_FREEZES;
  const poor = coins < STREAK_FREEZE_COST;

  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold text-slate-900">
        ショップ <span className="text-sm font-normal text-amber-600">🪙 {coins}</span>
      </h2>
      <div className="flex flex-wrap items-center gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="text-4xl" aria-hidden>
          🧊
        </div>
        <div className="flex-1">
          <div className="font-semibold text-slate-900">ストリークフリーズ</div>
          <p className="text-sm text-slate-600">
            学習できなかった日があっても、連続記録を 1 日分守ります (最大 {MAX_STREAK_FREEZES}{" "}
            個まで所持)。所持数: {freezes}
          </p>
          {buy.error && (
            <p role="alert" className="mt-1 text-sm text-rose-700">
              {getErrorMessage(buy.error)}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={() => buy.mutate()}
          disabled={full || poor || buy.isPending}
          className="rounded-full bg-amber-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-amber-600 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {full ? "所持上限です" : poor ? `🪙 ${STREAK_FREEZE_COST} 必要` : `🪙 ${STREAK_FREEZE_COST} で購入`}
        </button>
      </div>
    </section>
  );
}
