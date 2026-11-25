import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import type { GamificationStatsResponse, QuestProgress } from "@learning-platform/shared-types";
import { getMyStats } from "@/api/gamification";
import { queryKeys } from "@/lib/queryKeys";
import { LoadingState } from "@/components/common/LoadingState";
import { Mascot, type MascotMood } from "@/components/mascot/Mascot";

function mascotFor(stats: GamificationStatsResponse): { mood: MascotMood; message: string } {
  const dailyDone = stats.daily_quests.every((q) => q.completed);
  if (dailyDone) return { mood: "cheer", message: "今日のクエスト全部クリア! すごい!" };
  if (stats.studied_today) return { mood: "happy", message: "いい調子! この勢いでクエストも狙おう" };
  if (stats.current_streak > 0)
    return {
      mood: "think",
      message: `${stats.current_streak} 日連続中! 今日も 1 問解いてつなげよう`,
    };
  return { mood: "sleepy", message: "まずは 1 問だけ解いてみない?" };
}

/** ダッシュボード用: マスコット + レベル進捗 + デイリー / ウィークリークエスト */
export function DailyQuests() {
  const { data, isLoading } = useQuery({
    queryKey: queryKeys.gamification,
    queryFn: getMyStats,
  });
  if (isLoading) return <LoadingState />;
  if (!data) return null;

  const levelPct = Math.round((data.xp_into_level / Math.max(1, data.xp_for_next_level)) * 100);
  const mascot = mascotFor(data);

  return (
    <section className="space-y-3">
      <Mascot mood={mascot.mood} message={mascot.message} />
      <div className="grid gap-3 md:grid-cols-3">
        <div className="rounded-2xl bg-gradient-to-br from-violet-500 to-fuchsia-500 p-5 text-white shadow-sm">
          <div className="text-xs font-semibold uppercase tracking-wider text-white/80">
            レベル
          </div>
          <div className="mt-1 text-4xl font-black">Lv {data.level}</div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/30">
            <div
              className="h-full rounded-full bg-white transition-all duration-700"
              style={{ width: `${levelPct}%` }}
            />
          </div>
          <div className="mt-1 text-xs text-white/90">
            次のレベルまで あと {data.xp_for_next_level - data.xp_into_level} XP
          </div>
          <div className="mt-4 flex flex-wrap gap-4 text-sm font-semibold">
            <span>
              <span aria-hidden>🔥</span> {data.current_streak} 日連続
            </span>
            <span title="ストリークフリーズ: 学習を休んだ日のストリークを守る">
              <span aria-hidden>🧊</span> {data.streak_freezes}
            </span>
            <span>
              <span aria-hidden>🪙</span> {data.coins}
            </span>
          </div>
        </div>

        <div className="space-y-3 md:col-span-2">
          <QuestCard title="今日のクエスト" icon="🎯" quests={data.daily_quests} />
          <QuestCard title="今週のクエスト" icon="🗓️" quests={data.weekly_quests} />
        </div>
      </div>
    </section>
  );
}

function QuestCard({
  title,
  icon,
  quests,
}: {
  title: string;
  icon: string;
  quests: QuestProgress[];
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="text-lg font-semibold text-slate-900">
        <span aria-hidden>{icon}</span> {title}
      </h2>
      <ul className="mt-3 space-y-3">
        {quests.map((q) => {
          const pct = Math.round((q.progress / q.target) * 100);
          return (
            <li key={q.id}>
              <div className="flex items-center justify-between text-sm">
                <span
                  className={clsx(
                    "font-medium",
                    q.completed ? "text-emerald-700" : "text-slate-800",
                  )}
                >
                  {q.completed ? "✅ " : ""}
                  {q.title}
                </span>
                <span className="text-xs text-slate-500">
                  {q.progress} / {q.target}・+{q.reward_xp} XP 🪙{q.reward_coins}
                </span>
              </div>
              <div
                role="progressbar"
                aria-label={q.title}
                aria-valuenow={q.progress}
                aria-valuemin={0}
                aria-valuemax={q.target}
                className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100"
              >
                <div
                  className={clsx(
                    "h-full rounded-full transition-all duration-700",
                    q.completed ? "bg-emerald-500" : "bg-brand-500",
                  )}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
