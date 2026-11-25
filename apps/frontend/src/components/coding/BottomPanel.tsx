import clsx from "clsx";
import type {
  CodingIssueDetail,
  CodingReviewResponse,
  CodingSolution,
  CodingTestResult,
} from "@learning-platform/shared-types";
import type { CodeDiffLine } from "@/types/coding";
import { Mascot } from "@/components/mascot/Mascot";
import { HintsPanel } from "./HintsPanel";
import { SolutionExamples } from "./SolutionExamples";
import { DiffViewer } from "./DiffViewer";
import { AIReviewPanel } from "./AIReviewPanel";

export type BottomTabId = "output" | "tests" | "hints" | "solutions" | "diff" | "ai-review";

const TABS: Array<{ id: BottomTabId; label: string; icon: string }> = [
  { id: "output", label: "実行結果", icon: "▶" },
  { id: "tests", label: "テストケース", icon: "🧪" },
  { id: "hints", label: "ヒント", icon: "💡" },
  { id: "solutions", label: "解答例", icon: "📘" },
  { id: "diff", label: "差分", icon: "↔" },
  { id: "ai-review", label: "AIレビュー", icon: "🤖" },
];

export type ExecutionState =
  | { kind: "run"; results: CodingTestResult[] }
  | {
      kind: "submit";
      results: CodingTestResult[];
      passed: boolean | null;
      passedCount: number;
      totalCount: number;
    };

type Props = {
  tab: BottomTabId;
  onTabChange: (t: BottomTabId) => void;
  issue: CodingIssueDetail;
  execution: ExecutionState | null;
  executionPending: boolean;
  executionError: string | null;
  onRevealHint: () => void;
  hintPending: boolean;
  hintError: string | null;
  solutions: CodingSolution[] | null;
  onShowSolutions: () => void;
  solutionsPending: boolean;
  solutionsError: string | null;
  onApplySolution: (code: string) => void;
  diff: CodeDiffLine[];
  submissionId: string | null;
  review: CodingReviewResponse | null;
  onRequestReview: () => void;
  reviewPending: boolean;
  reviewError: string | null;
};

export function BottomPanel(props: Props) {
  const { tab, onTabChange, issue } = props;
  return (
    <section className="flex h-80 shrink-0 flex-col border-t border-slate-700 bg-[#0d1117]">
      <div
        role="tablist"
        className="flex shrink-0 items-center gap-1 overflow-x-auto border-b border-slate-700 bg-[#161b22] px-2 pt-1 text-xs"
      >
        {TABS.map((t) => {
          const active = t.id === tab;
          return (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => onTabChange(t.id)}
              className={clsx(
                "flex shrink-0 items-center gap-1 rounded-t px-3 py-1 transition",
                active ? "bg-[#0d1117] text-white" : "text-slate-400 hover:bg-[#22272e]",
              )}
            >
              <span aria-hidden>{t.icon}</span>
              <span>{t.label}</span>
            </button>
          );
        })}
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-3 text-xs">
        {tab === "output" && (
          <OutputTab
            execution={props.execution}
            pending={props.executionPending}
            error={props.executionError}
            executable={issue.executable}
          />
        )}
        {tab === "tests" && <TestsTab issue={issue} />}
        {tab === "hints" && (
          <HintsPanel
            hints={issue.hints}
            total={issue.hints_total}
            onReveal={props.onRevealHint}
            pending={props.hintPending}
            error={props.hintError}
          />
        )}
        {tab === "solutions" && (
          <SolutionsTab
            issue={issue}
            solutions={props.solutions}
            onShow={props.onShowSolutions}
            pending={props.solutionsPending}
            error={props.solutionsError}
            onApply={props.onApplySolution}
          />
        )}
        {tab === "diff" &&
          (props.solutions ? (
            <DiffViewer diff={props.diff} />
          ) : (
            <p className="text-slate-400">解答例を表示すると、あなたのコードとの差分を確認できます。</p>
          ))}
        {tab === "ai-review" && (
          <AIReviewPanel
            submissionId={props.submissionId}
            review={props.review}
            onRequest={props.onRequestReview}
            pending={props.reviewPending}
            error={props.reviewError}
          />
        )}
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ 実行結果

const STATUS_VIEW: Record<CodingTestResult["status"], { icon: string; label: string; cls: string }> = {
  passed: { icon: "✅", label: "合格", cls: "text-emerald-300" },
  failed: { icon: "❌", label: "出力が違います", cls: "text-rose-300" },
  error: { icon: "💥", label: "エラー", cls: "text-rose-300" },
  timeout: { icon: "⏱", label: "時間切れ", cls: "text-amber-300" },
};

function OutputTab({
  execution,
  pending,
  error,
  executable,
}: {
  execution: ExecutionState | null;
  pending: boolean;
  error: string | null;
  executable: boolean;
}) {
  if (pending) return <div className="text-slate-400">サンドボックスで実行中…</div>;
  if (error) return <div role="alert" className="text-rose-300">{error}</div>;
  if (!execution) {
    return (
      <div className="text-slate-400">
        {executable
          ? "「▶ 実行」で公開テスト、「✔ 提出」で非公開テストも含めて採点します。"
          : "この問題は自動実行に対応していません。「✔ 提出して AI レビューへ」でコードのレビューを受けられます。"}
      </div>
    );
  }

  const passed = execution.results.filter((r) => r.status === "passed").length;
  return (
    <div className="space-y-2">
      {execution.kind === "submit" && execution.passed !== null && (
        <div
          className={clsx(
            "flex items-center gap-3 rounded-md p-2 motion-safe:animate-pop",
            execution.passed ? "bg-emerald-500/15 ring-1 ring-emerald-400/40" : "bg-rose-500/10 ring-1 ring-rose-400/30",
          )}
        >
          <Mascot mood={execution.passed ? "cheer" : "think"} size={40} />
          <div className="text-sm font-semibold text-white">
            {execution.passed
              ? "すべてのテストに合格! 🎉 AI レビューで改善点も見てみよう"
              : `${execution.passedCount} / ${execution.totalCount} 件合格。落ちたテストを確認しよう`}
          </div>
        </div>
      )}
      <div className="text-slate-300">
        {execution.kind === "run" ? "公開テスト" : "全テスト"}: {passed} / {execution.results.length} 件合格
      </div>
      <ul className="space-y-1 font-mono text-[12px]">
        {execution.results.map((r, i) => {
          const view = STATUS_VIEW[r.status];
          return (
            <li key={i} className="rounded-md border border-slate-700 p-2">
              <div className={clsx("font-semibold", view.cls)}>
                {view.icon} {r.name} — {view.label}{" "}
                <span className="text-[10px] font-normal text-slate-500">{r.time_ms}ms</span>
              </div>
              {!r.hidden && r.status !== "passed" && (
                <div className="mt-1 space-y-0.5 text-slate-300">
                  <div>入力: {r.stdin}</div>
                  <div>期待値: {r.expected}</div>
                  <div>実際: {r.stdout || "(出力なし)"}</div>
                </div>
              )}
              {r.stderr && (
                <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap text-[11px] text-amber-200/80">
                  {r.stderr}
                </pre>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// ------------------------------------------------------------------ テストケース

function TestsTab({ issue }: { issue: CodingIssueDetail }) {
  if (!issue.executable) {
    return <p className="text-slate-400">この問題には自動テストがありません。</p>;
  }
  return (
    <div>
      <ul className="space-y-1">
        {issue.visible_tests.map((t, i) => (
          <li key={i} className="rounded-md border border-slate-700 p-2 text-[12px]">
            <div className="font-semibold text-slate-100">{t.name}</div>
            <div className="mt-0.5 text-slate-400">
              入力 (引数): <code className="font-mono text-slate-300">{t.stdin}</code>
            </div>
            <div className="text-slate-400">
              期待値: <code className="font-mono text-slate-300">{t.expected}</code>
            </div>
          </li>
        ))}
      </ul>
      {issue.hidden_test_count > 0 && (
        <p className="mt-2 text-[11px] text-slate-500">
          ほかに非公開テストが {issue.hidden_test_count} 件あります (提出時に実行されます)。
        </p>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ 解答例

function SolutionsTab({
  issue,
  solutions,
  onShow,
  pending,
  error,
  onApply,
}: {
  issue: CodingIssueDetail;
  solutions: CodingSolution[] | null;
  onShow: () => void;
  pending: boolean;
  error: string | null;
  onApply: (code: string) => void;
}) {
  if (solutions) return <SolutionExamples solutions={solutions} onApply={onApply} />;
  const solved = issue.status === "solved";
  return (
    <div className="space-y-2 text-slate-300">
      <p>
        {solved
          ? "合格おめでとう! ほかの書き方と比べてみよう。"
          : "解答例は一度提出すると見られます。合格前に見ると、その問題の XP が少なくなります。"}
      </p>
      <button
        type="button"
        onClick={onShow}
        disabled={pending || !issue.can_view_solutions}
        className="rounded-md bg-slate-700 px-3 py-1 text-xs font-semibold text-white hover:bg-slate-600 disabled:opacity-50"
      >
        {solved ? "解答例を見る" : "ギブアップして解答例を見る"}
      </button>
      {error && <p role="alert" className="text-rose-300">{error}</p>}
    </div>
  );
}
