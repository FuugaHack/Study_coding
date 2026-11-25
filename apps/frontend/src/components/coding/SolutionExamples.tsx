import clsx from "clsx";
import type { CodingSolution } from "@learning-platform/shared-types";

type Props = {
  solutions: CodingSolution[];
  onApply?: (code: string) => void;
};

export function SolutionExamples({ solutions, onApply }: Props) {
  if (solutions.length === 0) {
    return <div className="text-sm text-slate-400">解答例はまだありません。</div>;
  }
  const sorted = [...solutions].sort(
    (a, b) => Number(b.is_recommended) - Number(a.is_recommended),
  );
  return (
    <div className="space-y-3">
      {sorted.map((s) => (
        <article
          key={s.id}
          className={clsx(
            "rounded-md border p-3",
            s.is_recommended ? "border-emerald-400/50 bg-emerald-400/5" : "border-slate-700 bg-[#0d1117]",
          )}
        >
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="text-sm font-semibold text-slate-100">{s.title}</h4>
            {s.is_recommended && (
              <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] font-semibold text-emerald-300 ring-1 ring-emerald-400/40">
                ⭐ おすすめ
              </span>
            )}
            {onApply && (
              <button
                type="button"
                onClick={() => onApply(s.code)}
                className="ml-auto rounded-md bg-slate-700 px-2 py-1 text-[11px] font-medium text-slate-100 hover:bg-slate-600"
              >
                エディタに反映
              </button>
            )}
          </div>
          <pre className="mt-2 overflow-x-auto rounded bg-black/50 p-2 font-mono text-[12px] leading-snug text-slate-100">
            <code>{s.code}</code>
          </pre>
          {s.explanation && <p className="mt-2 text-[12px] text-slate-300">{s.explanation}</p>}
          {s.points.length > 0 && (
            <ul className="mt-1 list-inside list-disc space-y-0.5 text-[12px] text-slate-400">
              {s.points.map((p, k) => (
                <li key={k}>{p}</li>
              ))}
            </ul>
          )}
        </article>
      ))}
    </div>
  );
}
