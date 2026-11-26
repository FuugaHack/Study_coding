import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import type { ChallengeMode } from "@learning-platform/shared-types";
import { startChallenge } from "@/api/challenges";
import { getErrorMessage } from "@/lib/api";
import type { Course } from "@/types/catalog";

/** コース詳細の「実力テスト (飛び級)」「ボス戦」ボタン */
export function ChallengeActions({ course }: { course: Course }) {
  const navigate = useNavigate();
  const start = useMutation({
    mutationFn: (mode: ChallengeMode) => startChallenge(course.id, mode),
    onSuccess: (c) => navigate(`/challenges/${c.id}`),
  });

  if (!course.canTakePlacement && !course.canChallengeBoss && !course.bossDefeated) return null;

  return (
    <div className="rounded-2xl border border-line bg-surface p-4 shadow-sm">
      <div className="flex flex-wrap items-center gap-3">
        {course.canTakePlacement && (
          <div className="flex-1">
            <div className="text-sm font-semibold text-ink-900">🚀 実力テストで飛び級</div>
            <p className="text-xs text-ink-600">
              もう知っている内容なら、テストに合格 (80%) してこのコースと前提コースをまとめてクリアできます。1 日 1 回まで。
            </p>
          </div>
        )}
        {course.canTakePlacement && (
          <button
            type="button"
            onClick={() => start.mutate("placement")}
            disabled={start.isPending}
            className="rounded-full bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-600 disabled:bg-line-strong"
          >
            実力テストを受ける
          </button>
        )}
        {course.canChallengeBoss && (
          <div className="flex-1">
            <div className="text-sm font-semibold text-ink-900">
              {course.bossDefeated ? "👑 ボス撃破済み" : "⚔️ ボスが現れた!"}
            </div>
            <p className="text-xs text-ink-600">
              コースの総合問題に制限時間つきで挑戦。80% 以上で撃破
              {course.bossDefeated ? " (再挑戦できます)" : " して 👑 と報酬をゲット"}。
            </p>
          </div>
        )}
        {course.canChallengeBoss && (
          <button
            type="button"
            onClick={() => start.mutate("boss")}
            disabled={start.isPending}
            className="rounded-full bg-rose-500 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-600 disabled:bg-line-strong"
          >
            {course.bossDefeated ? "再挑戦" : "ボスに挑む"}
          </button>
        )}
      </div>
      {start.error && (
        <p role="alert" className="mt-2 text-sm text-rose-700 dark:text-rose-300">
          {getErrorMessage(start.error)}
        </p>
      )}
    </div>
  );
}
