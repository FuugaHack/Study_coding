import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { getMyStats } from "@/api/gamification";
import { queryKeys } from "@/lib/queryKeys";

/** ヘッダー用: レベル / XP バー / ストリーク / コイン */
export function GamificationBar() {
  const { data } = useQuery({ queryKey: queryKeys.gamification, queryFn: getMyStats });
  if (!data) return null;

  const pct = Math.round((data.xp_into_level / Math.max(1, data.xp_for_next_level)) * 100);

  return (
    <div className="flex items-center gap-3 text-xs">
      <div
        className="flex items-center gap-2"
        title={`累計 ${data.total_xp} XP / 次のレベルまで ${data.xp_for_next_level - data.xp_into_level} XP`}
      >
        <span className="rounded-full bg-violet-100 dark:bg-violet-500/15 px-2 py-0.5 font-bold text-violet-700 dark:text-violet-300">
          Lv {data.level}
        </span>
        <div
          role="progressbar"
          aria-label="次のレベルまでの経験値"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          className="hidden h-2 w-20 overflow-hidden rounded-full bg-surface-muted sm:block"
        >
          <div
            className="h-full bg-gradient-to-r from-violet-400 to-fuchsia-500 transition-all duration-700"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
      <span
        className={clsx(
          "font-semibold",
          data.studied_today ? "text-orange-600 dark:text-orange-400" : "text-ink-400",
        )}
        title={
          data.studied_today
            ? `${data.current_streak} 日連続で学習中 (最長 ${data.longest_streak} 日)`
            : "今日はまだ学習していません。1 問解いてストリークを伸ばそう!"
        }
      >
        <span aria-hidden>🔥</span>
        <span className="sr-only">連続学習日数</span> {data.current_streak}
      </span>
      <span className="font-semibold text-amber-600 dark:text-amber-400" title="コイン">
        <span aria-hidden>🪙</span>
        <span className="sr-only">コイン</span> {data.coins}
      </span>
    </div>
  );
}
