import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import type { AnswerRequest, AnswerResponse } from "@learning-platform/shared-types";
import { answerQuestion } from "@/api/catalog";
import { getErrorMessage } from "@/lib/api";
import { queryKeys } from "@/lib/queryKeys";
import { useRewardStore } from "@/stores/rewards";
import type { Question, QuestionType } from "@/types/catalog";

type Props = {
  index: number;
  total: number;
  question: Question;
  onAdvance: () => void;
};

const QUESTION_TYPE_LABEL: Record<QuestionType, string> = {
  choice: "選択式",
  "multiple-choice": "複数選択",
  text: "記述式",
  code: "コード穴埋め",
};

const QUESTION_TYPE_CLASS: Record<QuestionType, string> = {
  choice: "bg-blue-100 text-blue-700",
  "multiple-choice": "bg-purple-100 text-purple-700",
  text: "bg-amber-100 text-amber-700",
  code: "bg-emerald-100 text-emerald-700",
};

const DIFFICULTY_LABEL: Record<Question["difficulty"], string> = {
  easy: "易",
  normal: "中",
  hard: "難",
};

const DIFFICULTY_CLASS: Record<Question["difficulty"], string> = {
  easy: "bg-emerald-50 text-emerald-700",
  normal: "bg-slate-100 text-slate-600",
  hard: "bg-rose-50 text-rose-700",
};

export function QuestionItem({ index, total, question, onAdvance }: Props) {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <header className="flex items-start gap-3">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-50 text-xs font-semibold text-brand-700">
          {index + 1}
        </span>
        <div className="flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={clsx(
                "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium",
                QUESTION_TYPE_CLASS[question.type],
              )}
            >
              {QUESTION_TYPE_LABEL[question.type]}
            </span>
            <span
              className={clsx(
                "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium",
                DIFFICULTY_CLASS[question.difficulty],
              )}
            >
              難易度: {DIFFICULTY_LABEL[question.difficulty]}
            </span>
            {question.solved && (
              <span className="text-[11px] font-medium text-emerald-600">✓ 正解済み</span>
            )}
            <span className="text-[11px] text-slate-500">
              {index + 1} / {total}
            </span>
          </div>
          <h3 className="mt-1 text-sm font-bold text-slate-900">{question.title}</h3>
          <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">
            {question.description}
          </p>
        </div>
      </header>
      <div className="mt-4">{renderBody(question, onAdvance)}</div>
    </article>
  );
}

function renderBody(question: Question, onAdvance: () => void) {
  switch (question.type) {
    case "choice":
      return <ChoiceBody question={question} onAdvance={onAdvance} />;
    case "multiple-choice":
      return <MultipleChoiceBody question={question} onAdvance={onAdvance} />;
    case "text":
      return <TextBody question={question} onAdvance={onAdvance} />;
    case "code":
      return <CodeBody question={question} onAdvance={onAdvance} />;
  }
}

// -------- 回答送信 (採点はサーバー) --------

function useAnswer(questionId: string) {
  const qc = useQueryClient();
  const pushReward = useRewardStore((s) => s.push);
  const startedAt = useRef(Date.now());

  return useMutation({
    mutationFn: (body: AnswerRequest) =>
      answerQuestion(questionId, {
        ...body,
        time_spent_seconds: Math.round((Date.now() - startedAt.current) / 1000),
      }),
    onSuccess: (res) => {
      qc.setQueryData(queryKeys.gamification, res.stats);
      // 一覧 (["catalog","courses"]) と詳細 (["catalog","course",id]) の両方を無効化
      void qc.invalidateQueries({ queryKey: ["catalog"] });
      pushReward(res.reward);
    },
  });
}

function asList(value: string | string[] | null | undefined): string[] {
  if (value == null) return [];
  return Array.isArray(value) ? value : [value];
}

function Feedback({ result, error }: { result: AnswerResponse | undefined; error: unknown }) {
  if (error) {
    return (
      <div role="alert" className="mt-3 rounded-lg bg-rose-50 p-3 text-sm text-rose-800">
        {getErrorMessage(error)}
      </div>
    );
  }
  if (!result || result.result === "self_check") return null;
  const correct = result.result === "correct";
  return (
    <div
      role="status"
      className={clsx(
        "mt-3 rounded-lg p-3 text-sm motion-safe:animate-pop",
        correct
          ? "bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200"
          : "bg-rose-50 text-rose-800 ring-1 ring-rose-200",
      )}
    >
      <div className="font-semibold">
        {correct
          ? "正解 🎉"
          : result.correct_answer == null
            ? "惜しい! もう一度考えてみよう 💪"
            : "不正解 — 正解と解説を確認しよう"}
      </div>
      {!correct && result.correct_answer != null && (
        <div className="mt-1 text-slate-700">
          正解: <code className="font-mono">{asList(result.correct_answer).join(" / ")}</code>
        </div>
      )}
      {result.explanation && <div className="mt-1 text-slate-700">{result.explanation}</div>}
    </div>
  );
}

function PrimaryButton({
  onClick,
  disabled,
  label,
}: {
  onClick: () => void;
  disabled?: boolean;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="rounded-full bg-brand-500 px-4 py-1.5 text-xs font-semibold text-white transition hover:bg-brand-600 disabled:cursor-not-allowed disabled:bg-slate-300"
    >
      {label}
    </button>
  );
}

function GhostButton({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-full bg-white px-4 py-1.5 text-xs font-semibold text-slate-600 ring-1 ring-slate-200 transition hover:bg-slate-50"
    >
      {label}
    </button>
  );
}

function AdvanceButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-full bg-emerald-500 px-4 py-1.5 text-xs font-semibold text-white transition hover:bg-emerald-600"
      autoFocus
    >
      次の問題へ →
    </button>
  );
}

function Actions({
  result,
  pending,
  canSubmit,
  onSubmit,
  onRetry,
  onAdvance,
}: {
  result: AnswerResponse | undefined;
  pending: boolean;
  canSubmit: boolean;
  onSubmit: () => void;
  onRetry: () => void;
  onAdvance: () => void;
}) {
  return (
    <div className="mt-3 flex gap-2">
      {!result && (
        <PrimaryButton
          onClick={onSubmit}
          disabled={!canSubmit || pending}
          label={pending ? "採点中…" : "回答する"}
        />
      )}
      {result?.result === "incorrect" && (
        <>
          <GhostButton onClick={onRetry} label="もう一度" />
          <AdvanceButton onClick={onAdvance} />
        </>
      )}
      {result && result.result !== "incorrect" && <AdvanceButton onClick={onAdvance} />}
    </div>
  );
}

// -------- choice (single) --------
function ChoiceBody({ question, onAdvance }: { question: Question; onAdvance: () => void }) {
  const [selected, setSelected] = useState<string | null>(null);
  const answer = useAnswer(question.id);
  const result = answer.data;
  const revealed = asList(result?.correct_answer);

  return (
    <div>
      <div role="radiogroup" className="space-y-2">
        {question.choices.map((label) => {
          const checked = selected === label;
          const isCorrect =
            (result?.result === "correct" && checked) || revealed.includes(label);
          const isWrong = result?.result === "incorrect" && checked;
          return (
            <label
              key={label}
              className={clsx(
                "flex cursor-pointer items-start gap-2 rounded-lg border px-3 py-2 text-sm transition",
                "border-slate-200 hover:bg-slate-50",
                checked && !result && "border-brand-400 bg-brand-50",
                isCorrect && "border-emerald-400 bg-emerald-50",
                isWrong && "border-rose-400 bg-rose-50",
              )}
            >
              <input
                type="radio"
                name={question.id}
                checked={checked}
                onChange={() => setSelected(label)}
                disabled={!!result || answer.isPending}
                className="mt-0.5"
              />
              <span className="flex-1 whitespace-pre-wrap">{label}</span>
            </label>
          );
        })}
      </div>
      <Actions
        result={result}
        pending={answer.isPending}
        canSubmit={selected !== null}
        onSubmit={() => selected !== null && answer.mutate({ selected })}
        onRetry={() => {
          setSelected(null);
          answer.reset();
        }}
        onAdvance={onAdvance}
      />
      <Feedback result={result} error={answer.error} />
    </div>
  );
}

// -------- multiple-choice --------
function MultipleChoiceBody({
  question,
  onAdvance,
}: {
  question: Question;
  onAdvance: () => void;
}) {
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const answer = useAnswer(question.id);
  const result = answer.data;
  const revealed = new Set(asList(result?.correct_answer));

  const toggle = (label: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  };

  return (
    <div>
      <div className="space-y-2">
        {question.choices.map((label) => {
          const checked = selected.has(label);
          const showCorrect = revealed.has(label);
          const showWrong = result?.result === "incorrect" && revealed.size > 0 && checked && !showCorrect;
          return (
            <label
              key={label}
              className={clsx(
                "flex cursor-pointer items-start gap-2 rounded-lg border px-3 py-2 text-sm transition",
                "border-slate-200 hover:bg-slate-50",
                checked && !result && "border-brand-400 bg-brand-50",
                showCorrect && "border-emerald-400 bg-emerald-50",
                showWrong && "border-rose-400 bg-rose-50",
              )}
            >
              <input
                type="checkbox"
                checked={checked}
                onChange={() => toggle(label)}
                disabled={!!result || answer.isPending}
                className="mt-0.5"
              />
              <span className="flex-1 whitespace-pre-wrap">{label}</span>
            </label>
          );
        })}
      </div>
      <Actions
        result={result}
        pending={answer.isPending}
        canSubmit={selected.size > 0}
        onSubmit={() => answer.mutate({ selected: [...selected] })}
        onRetry={() => {
          setSelected(new Set());
          answer.reset();
        }}
        onAdvance={onAdvance}
      />
      <Feedback result={result} error={answer.error} />
    </div>
  );
}

// -------- text (自己チェック) --------
function TextBody({ question, onAdvance }: { question: Question; onAdvance: () => void }) {
  const [value, setValue] = useState("");
  const answer = useAnswer(question.id);
  const result = answer.data;

  return (
    <div>
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        rows={3}
        maxLength={5000}
        disabled={!!result}
        placeholder="自分の言葉で答えてみましょう"
        className="w-full rounded-lg border border-slate-200 p-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
      />
      <div className="mt-3 flex gap-2">
        {!result ? (
          <PrimaryButton
            onClick={() => answer.mutate({ text: value })}
            disabled={answer.isPending}
            label={value.trim() ? "回答して解答例を見る" : "解答例を見る"}
          />
        ) : (
          <AdvanceButton onClick={onAdvance} />
        )}
      </div>
      {result && (
        <div className="mt-3 rounded-lg bg-slate-50 p-3 text-sm ring-1 ring-slate-200 motion-safe:animate-pop">
          <div className="text-xs font-semibold text-slate-500">
            解答例 — 自分の答えと比べてみよう
          </div>
          <p className="mt-1 whitespace-pre-wrap text-slate-800">
            {asList(result.correct_answer).join("\n")}
          </p>
          {result.explanation && (
            <p className="mt-2 text-xs text-slate-600">{result.explanation}</p>
          )}
        </div>
      )}
      <Feedback result={undefined} error={answer.error} />
    </div>
  );
}

// -------- code (blank fill) --------
function CodeBody({ question, onAdvance }: { question: Question; onAdvance: () => void }) {
  const blankCount = Math.max(1, question.blankCount);
  const [values, setValues] = useState<string[]>(() => Array(blankCount).fill(""));
  const answer = useAnswer(question.id);
  const result = answer.data;
  const expected = asList(result?.correct_answer);

  return (
    <div>
      <pre className="overflow-x-auto rounded-lg bg-slate-900 p-3 text-xs leading-relaxed text-slate-100">
        <code className="font-mono">{question.codeTemplate}</code>
      </pre>
      <div className="mt-3 space-y-2">
        {values.map((value, i) => {
          const blankOk = result?.blank_results[i];
          return (
            <div key={i} className="flex items-center gap-2 text-sm">
              <label className="w-16 text-xs text-slate-500" htmlFor={`${question.id}-blank-${i}`}>
                穴 {i + 1}
              </label>
              <input
                id={`${question.id}-blank-${i}`}
                type="text"
                value={value}
                maxLength={500}
                onChange={(e) =>
                  setValues((prev) => {
                    const next = [...prev];
                    next[i] = e.target.value;
                    return next;
                  })
                }
                disabled={!!result || answer.isPending}
                placeholder="答えを入力"
                className={clsx(
                  "flex-1 rounded-md border px-2 py-1 font-mono focus:outline-none focus:ring-2 focus:ring-brand-500",
                  blankOk === undefined && "border-slate-200",
                  blankOk === true && "border-emerald-400 bg-emerald-50",
                  blankOk === false && "border-rose-400 bg-rose-50",
                )}
              />
              {blankOk === false && expected[i] !== undefined && (
                <span className="text-xs text-slate-500">
                  正解: <code className="font-mono">{expected[i]}</code>
                </span>
              )}
            </div>
          );
        })}
      </div>
      <Actions
        result={result}
        pending={answer.isPending}
        canSubmit={values.every((v) => v.trim())}
        onSubmit={() => answer.mutate({ blanks: values })}
        onRetry={() => {
          // 正解した穴は残し、間違えた穴だけ空にする
          setValues((prev) => prev.map((v, i) => (result?.blank_results[i] ? v : "")));
          answer.reset();
        }}
        onAdvance={onAdvance}
      />
      <Feedback result={result} error={answer.error} />
    </div>
  );
}
