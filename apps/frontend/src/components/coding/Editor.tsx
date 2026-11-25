import { useEffect, useMemo, useState } from "react";
import MonacoEditor from "@monaco-editor/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import type {
  CodingIssueDetail,
  CodingReviewResponse,
  CodingSolution,
} from "@learning-platform/shared-types";
import {
  getCodeReview,
  getCodingIssue,
  requestCodeReview,
  revealCodingHint,
  runCode,
  submitCode,
  viewCodingSolutions,
} from "@/api/coding";
import { ErrorState, LoadingState } from "@/components/common/LoadingState";
import { getErrorMessage } from "@/lib/api";
import {
  DIFFICULTY_LABEL,
  ISSUE_STATUS_LABEL,
  LANGUAGE_MONACO,
  frameworkLabel,
  languageIcon,
  languageLabel,
  questionTypeLabel,
} from "@/lib/codingLabels";
import { diffLines } from "@/lib/diffLines";
import { queryKeys } from "@/lib/queryKeys";
import { useRewardStore } from "@/stores/rewards";
import type { CodingDifficulty, IssueStatus, Language } from "@/types/coding";
import { BottomPanel, type BottomTabId, type ExecutionState } from "./BottomPanel";

type Props = {
  questionId: string;
  onBack: () => void;
};

const STATUS_PILL_CLASS: Record<IssueStatus, string> = {
  open: "border-emerald-400/40 bg-emerald-400/10 text-emerald-300",
  "in-progress": "border-amber-400/40 bg-amber-400/10 text-amber-300",
  solved: "border-violet-400/40 bg-violet-400/10 text-violet-300",
};

const DIFFICULTY_PILL_CLASS: Record<CodingDifficulty, string> = {
  easy: "bg-emerald-500/15 text-emerald-300",
  normal: "bg-amber-500/15 text-amber-300",
  hard: "bg-rose-500/15 text-rose-300",
};

const draftKey = (id: string) => `coding-draft:${id}`;

export function Editor({ questionId, onBack }: Props) {
  const issueKey = ["coding", "issue", questionId] as const;
  const { data, isLoading, error } = useQuery({
    queryKey: issueKey,
    queryFn: () => getCodingIssue(questionId),
  });

  if (isLoading) return <LoadingState />;
  if (error) return <ErrorState message={getErrorMessage(error)} />;
  if (!data) return null;
  return <EditorBody issue={data} onBack={onBack} />;
}

function EditorBody({ issue, onBack }: { issue: CodingIssueDetail; onBack: () => void }) {
  const qc = useQueryClient();
  const pushReward = useRewardStore((s) => s.push);
  const issueKey = ["coding", "issue", issue.id];

  // 書きかけのコードはブラウザに保存しておき、戻ってきたときに復元する
  const [code, setCode] = useState<string>(
    () => localStorage.getItem(draftKey(issue.id)) ?? issue.initial_code,
  );
  useEffect(() => {
    localStorage.setItem(draftKey(issue.id), code);
  }, [issue.id, code]);

  const [tab, setTab] = useState<BottomTabId>("output");
  const [execution, setExecution] = useState<ExecutionState | null>(null);
  const [submissionId, setSubmissionId] = useState<string | null>(null);
  const [solutions, setSolutions] = useState<CodingSolution[] | null>(null);

  const run = useMutation({
    mutationFn: () => runCode(issue.id, code),
    onMutate: () => setTab("output"),
    onSuccess: (res) => setExecution({ kind: "run", results: res.results }),
  });

  const submit = useMutation({
    mutationFn: () => submitCode(issue.id, code),
    onMutate: () => setTab("output"),
    onSuccess: (res) => {
      setExecution({
        kind: "submit",
        results: res.results,
        passed: res.passed,
        passedCount: res.passed_count,
        totalCount: res.total_count,
      });
      setSubmissionId(res.submission_id);
      qc.setQueryData(queryKeys.gamification, res.stats);
      pushReward(res.reward);
      void qc.invalidateQueries({ queryKey: ["coding"] });
      if (res.passed === null) setTab("ai-review");
    },
  });

  const hint = useMutation({
    mutationFn: () => revealCodingHint(issue.id),
    onSuccess: (hints) => {
      qc.setQueryData<CodingIssueDetail>(issueKey, (prev) =>
        prev ? { ...prev, hints, status: prev.status === "open" ? "in-progress" : prev.status } : prev,
      );
    },
  });

  const showSolutions = useMutation({
    mutationFn: () => viewCodingSolutions(issue.id),
    onSuccess: (res) => setSolutions(res.solutions),
  });

  // AI レビューはワーカーで処理されるので、完了するまでポーリングする
  const reviewKey = ["coding", "review", submissionId] as const;
  const reviewQuery = useQuery({
    queryKey: reviewKey,
    queryFn: () => getCodeReview(submissionId!),
    enabled: submissionId !== null,
    refetchInterval: (q) => {
      const status = q.state.data?.status;
      return status === "pending" || status === "processing" ? 2000 : false;
    },
  });
  const aiReview = useMutation({
    mutationFn: () => requestCodeReview(submissionId!),
    onSuccess: (res) => qc.setQueryData<CodingReviewResponse>(reviewKey, res),
  });
  const reviewState = reviewQuery.data;
  const review = reviewState?.status === "completed" ? reviewState : null;
  const reviewWaiting =
    aiReview.isPending ||
    reviewState?.status === "pending" ||
    reviewState?.status === "processing";
  const reviewError = aiReview.error
    ? getErrorMessage(aiReview.error)
    : reviewState?.status === "failed"
      ? reviewState.error_message
      : null;

  const recommended = solutions?.find((s) => s.is_recommended) ?? solutions?.[0] ?? null;
  const diff = useMemo(
    () => (recommended ? diffLines(code, recommended.code) : []),
    [code, recommended],
  );

  const handleReset = () => {
    setCode(issue.initial_code);
    setExecution(null);
  };

  const busy = run.isPending || submit.isPending;
  const executionError = run.error ?? submit.error;

  return (
    <div className="-mx-4 -my-6 flex h-[calc(100vh-3.5rem)] flex-col bg-[#0d1117] text-slate-200">
      {/* Issue header */}
      <header className="shrink-0 border-b border-slate-700 bg-[#161b22] px-4 py-3 motion-safe:animate-fade-up">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <button
            type="button"
            onClick={onBack}
            className="rounded-md bg-slate-700/60 px-2 py-1 text-slate-200 hover:bg-slate-600"
          >
            ← Issues に戻る
          </button>
          <span className="font-mono text-[11px] text-slate-500">
            #{String(issue.issue_number).padStart(3, "0")}
          </span>
          <span className="text-sm font-semibold text-white">{issue.title}</span>
          <span
            className={clsx(
              "rounded-full border px-1.5 py-0.5 text-[10px]",
              STATUS_PILL_CLASS[issue.status],
            )}
          >
            {ISSUE_STATUS_LABEL[issue.status]}
          </span>
          <span
            className={clsx(
              "rounded-full px-1.5 py-0.5 text-[10px]",
              DIFFICULTY_PILL_CLASS[issue.difficulty],
            )}
          >
            {DIFFICULTY_LABEL[issue.difficulty]}
          </span>
          <span className="rounded-full bg-slate-700/60 px-1.5 py-0.5 text-[10px] text-slate-300">
            {questionTypeLabel(issue.type)}
          </span>
          <span
            className={clsx(
              "ml-auto rounded-full px-2 py-0.5 text-[10px] font-bold",
              issue.executable
                ? "bg-emerald-500/20 text-emerald-300"
                : "bg-slate-700 text-slate-300",
            )}
            title={
              issue.executable
                ? "コードを実際に実行してテストで採点します"
                : "この問題はまだ自動実行に対応していません。提出すると AI がレビューします"
            }
          >
            {issue.executable ? "▶ 自動採点" : "AI レビューのみ"}
          </span>
        </div>
        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-500">
          <span>
            {languageIcon(issue.language)} {languageLabel(issue.language)}
          </span>
          {issue.framework && <span>Framework: {frameworkLabel(issue.framework)}</span>}
          <span>Estimated: {issue.estimated_minutes} min</span>
          <span>Labels: {issue.tags.join(" / ")}</span>
        </div>
      </header>

      {/* Description */}
      <div className="shrink-0 border-b border-slate-700 bg-[#0d1117] px-4 py-3">
        <p className="whitespace-pre-wrap text-xs text-slate-300">{issue.description}</p>
        {issue.executable && (
          <p className="mt-1 text-[11px] text-slate-500">
            関数を実装して「▶ 実行」で公開テスト、「✔ 提出」で非公開テストも含めて採点します。テスト用の呼び出しコードは自動で追加されます
            (print / console.log でのデバッグ出力は判定に影響しません)。
          </p>
        )}
      </div>

      {/* Action bar */}
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-slate-700 bg-[#161b22] px-3 py-2 text-xs">
        <ActionButton
          onClick={() => run.mutate()}
          label={run.isPending ? "実行中…" : "▶ 実行"}
          tone="primary"
          disabled={!issue.executable || busy}
          title={issue.executable ? undefined : "この問題は自動実行に対応していません"}
        />
        <ActionButton
          onClick={() => submit.mutate()}
          label={submit.isPending ? "採点中…" : issue.executable ? "✔ 提出" : "✔ 提出して AI レビューへ"}
          tone="success"
          disabled={busy}
        />
        <ActionButton onClick={handleReset} label="↺ 初期コードに戻す" disabled={busy} />
        <span className="ml-auto text-[11px] text-slate-500">
          {languageLabel(issue.language)} · {code.split("\n").length} 行 / {code.length} 文字
        </span>
      </div>

      <div className="min-h-0 flex-1">
        <MonacoEditor
          height="100%"
          language={LANGUAGE_MONACO[issue.language as Language] ?? "plaintext"}
          theme="vs-dark"
          value={code}
          onChange={(v) => setCode(v ?? "")}
          options={{
            minimap: { enabled: false },
            fontSize: 13,
            tabSize: 2,
            scrollBeyondLastLine: false,
            automaticLayout: true,
            wordWrap: "on",
            lineNumbers: "on",
          }}
        />
      </div>

      <BottomPanel
        tab={tab}
        onTabChange={setTab}
        issue={issue}
        execution={execution}
        executionPending={busy}
        executionError={executionError ? getErrorMessage(executionError) : null}
        onRevealHint={() => hint.mutate()}
        hintPending={hint.isPending}
        hintError={hint.error ? getErrorMessage(hint.error) : null}
        solutions={solutions}
        onShowSolutions={() => showSolutions.mutate()}
        solutionsPending={showSolutions.isPending}
        solutionsError={showSolutions.error ? getErrorMessage(showSolutions.error) : null}
        onApplySolution={(c) => setCode(c)}
        diff={diff}
        submissionId={submissionId}
        review={review}
        onRequestReview={() => aiReview.mutate()}
        reviewPending={reviewWaiting}
        reviewError={reviewError}
      />
    </div>
  );
}

function ActionButton({
  onClick,
  label,
  tone = "default",
  disabled,
  title,
}: {
  onClick: () => void;
  label: string;
  tone?: "default" | "primary" | "success";
  disabled?: boolean;
  title?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={clsx(
        "rounded-md px-3 py-1 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-50",
        tone === "primary" && "bg-[#0e639c] text-white hover:bg-[#1177bb]",
        tone === "success" && "bg-emerald-500 text-white hover:bg-emerald-600",
        tone === "default" && "bg-slate-700 text-slate-100 hover:bg-slate-600",
      )}
    >
      {label}
    </button>
  );
}

