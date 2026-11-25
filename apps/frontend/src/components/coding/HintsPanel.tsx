import clsx from "clsx";
import type { CodingHint } from "@learning-platform/shared-types";
import type { HintCloseness } from "@/types/coding";

const CLOSENESS_LABEL: Record<HintCloseness, string> = {
  concept: "考え方",
  focus: "着目",
  implementation: "実装",
  "near-answer": "ほぼ答え",
  "almost-answer": "答え直前",
};

const CLOSENESS_TONE: Record<HintCloseness, string> = {
  concept: "border-sky-400/40 bg-sky-400/10 text-sky-200",
  focus: "border-blue-400/40 bg-blue-400/10 text-blue-200",
  implementation: "border-indigo-400/40 bg-indigo-400/10 text-indigo-200",
  "near-answer": "border-amber-400/40 bg-amber-400/10 text-amber-200",
  "almost-answer": "border-rose-400/40 bg-rose-400/10 text-rose-200",
};

type Props = {
  hints: CodingHint[];
  total: number;
  onReveal: () => void;
  pending: boolean;
  error: string | null;
};

/** 段階ヒント。開いた数はサーバーに記録され、合格時の XP が 1 つにつき 20% 減る。 */
export function HintsPanel({ hints, total, onReveal, pending, error }: Props) {
  const allShown = hints.length >= total;
  return (
    <div className="space-y-3">
      {hints.length === 0 && (
        <p className="text-sm text-slate-300">
          行き詰まったらヒントを開こう。考え方 → 着目点 → ほぼ答え の順に、少しずつ答えに近づきます。
        </p>
      )}
      <ol className="space-y-2">
        {hints.map((h) => {
          const closeness = h.closeness as HintCloseness;
          return (
            <li
              key={h.level}
              className={clsx("rounded-md border p-3", CLOSENESS_TONE[closeness] ?? CLOSENESS_TONE.concept)}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-[10px] uppercase tracking-wider opacity-80">
                  Level {h.level}
                </span>
                <span className="rounded-full bg-black/30 px-1.5 py-0.5 text-[10px]">
                  {CLOSENESS_LABEL[closeness] ?? h.closeness}
                </span>
                <span className="text-xs font-semibold">{h.title}</span>
              </div>
              <p className="mt-1 whitespace-pre-wrap text-[12px] leading-relaxed text-slate-100/90">
                {h.content}
              </p>
            </li>
          );
        })}
      </ol>
      <div className="flex flex-wrap items-center gap-2">
        {allShown ? (
          <span className="rounded-md bg-emerald-500/15 px-3 py-1 text-xs font-semibold text-emerald-300 ring-1 ring-emerald-400/30">
            すべてのヒントを表示済み ({total} / {total})
          </span>
        ) : (
          <button
            type="button"
            onClick={onReveal}
            disabled={pending}
            className="rounded-md bg-indigo-500 px-3 py-1 text-xs font-semibold text-white hover:bg-indigo-600 disabled:opacity-50"
          >
            {hints.length === 0 ? "ヒントを見る" : "次のヒントを見る"} ({hints.length + 1} / {total})
          </button>
        )}
        <span className="text-[10px] text-slate-500">
          ヒント 1 つにつき、合格時の XP が 20% 減ります (最大 60%)。
        </span>
      </div>
      {error && <p role="alert" className="text-rose-300">{error}</p>}
    </div>
  );
}
