import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import type {
  AnswerRequest,
  CatalogQuestion,
  ChallengeResponse,
  ChallengeResultResponse,
} from "@learning-platform/shared-types";
import { getChallenge, submitChallenge } from "@/api/challenges";
import { ErrorState, LoadingState } from "@/components/common/LoadingState";
import { Mascot } from "@/components/mascot/Mascot";
import { getErrorMessage } from "@/lib/api";
import { queryKeys } from "@/lib/queryKeys";
import { useRewardStore } from "@/stores/rewards";

const MODE_LABEL = { placement: "実力テスト", boss: "ボス戦" } as const;

export function ChallengePage() {
  const { challengeId = "" } = useParams();
  const { data, isLoading, error } = useQuery({
    queryKey: queryKeys.challenge(challengeId),
    queryFn: () => getChallenge(challengeId),
    // 受験中に再取得して入力が消えないようにする
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });

  if (isLoading) return <LoadingState />;
  if (error) return <ErrorState message={getErrorMessage(error)} />;
  if (!data) return null;
  if (data.status !== "open") {
    return (
      <div className="mx-auto max-w-xl space-y-4 text-center">
        <Mascot mood="think" className="justify-center" message="このチャレンジは提出済みだよ" />
        <Link to={`/catalog/courses/${data.course_id}`} className="text-sm text-brand-600 hover:underline">
          コースに戻る
        </Link>
      </div>
    );
  }
  return <ChallengeRunner challenge={data} />;
}

function ChallengeRunner({ challenge }: { challenge: ChallengeResponse }) {
  const qc = useQueryClient();
  const pushReward = useRewardStore((s) => s.push);
  const [answers, setAnswers] = useState<Record<string, AnswerRequest>>({});
  const answersRef = useRef(answers);
  answersRef.current = answers;

  const submit = useMutation({
    mutationFn: () => submitChallenge(challenge.id, { answers: answersRef.current }),
    onSuccess: (res) => {
      qc.setQueryData(queryKeys.gamification, res.stats);
      void qc.invalidateQueries({ queryKey: ["catalog"] });
      void qc.invalidateQueries({ queryKey: queryKeys.badges });
      pushReward(res.reward);
    },
  });

  const onTimeUp = useCallback(() => {
    if (!submit.isPending && !submit.data) submit.mutate();
  }, [submit]);
  const remaining = useCountdown(challenge.expires_at, onTimeUp, !submit.data);

  if (submit.data) return <ChallengeResult challenge={challenge} result={submit.data} />;

  const isBoss = challenge.mode === "boss";
  const answered = challenge.questions.filter((q) => isAnswered(q, answers[q.id])).length;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header
        className={clsx(
          "sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 rounded-2xl p-4 text-white shadow",
          isBoss
            ? "bg-gradient-to-r from-rose-500 via-red-500 to-orange-500"
            : "bg-gradient-to-r from-sky-500 to-indigo-500",
        )}
      >
        <div>
          <div className="text-xs font-semibold uppercase tracking-wider text-white/80">
            {isBoss ? "⚔️ ボス戦" : "🚀 実力テスト"}
          </div>
          <h1 className="text-lg font-bold">{challenge.course_title}</h1>
          <p className="text-xs text-white/90">
            {challenge.pass_percent}% 以上正解で{isBoss ? "ボス撃破" : "合格 (飛び級)"}
          </p>
        </div>
        <div className="text-right">
          <div
            className={clsx("font-mono text-2xl font-bold", remaining <= 30 && "motion-safe:animate-pulse")}
            aria-live="off"
          >
            ⏱ {formatTime(remaining)}
          </div>
          <div className="text-xs text-white/90">
            回答済み {answered} / {challenge.questions.length}
          </div>
        </div>
      </header>

      <ol className="space-y-4">
        {challenge.questions.map((q, i) => (
          <li key={q.id} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="text-xs text-slate-500">
              Q{i + 1} / {challenge.questions.length}
            </div>
            <h2 className="mt-1 text-sm font-bold text-slate-900">{q.title}</h2>
            <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{q.description}</p>
            <div className="mt-3">
              <AnswerInput
                question={q}
                value={answers[q.id]}
                onChange={(v) => setAnswers((prev) => ({ ...prev, [q.id]: v }))}
              />
            </div>
          </li>
        ))}
      </ol>

      {submit.error && (
        <div role="alert" className="rounded-lg bg-rose-50 p-3 text-sm text-rose-800">
          {getErrorMessage(submit.error)}
        </div>
      )}
      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => submit.mutate()}
          disabled={submit.isPending}
          className={clsx(
            "rounded-full px-6 py-2 text-sm font-bold text-white shadow transition disabled:bg-slate-300",
            isBoss ? "bg-rose-500 hover:bg-rose-600" : "bg-indigo-500 hover:bg-indigo-600",
          )}
        >
          {submit.isPending ? "採点中…" : "提出する"}
        </button>
      </div>
    </div>
  );
}

function ChallengeResult({
  challenge,
  result,
}: {
  challenge: ChallengeResponse;
  result: ChallengeResultResponse;
}) {
  const label = MODE_LABEL[result.mode];
  const headline = result.passed
    ? result.mode === "boss"
      ? "ボス撃破! 👑"
      : "合格! 飛び級しました 🚀"
    : result.timed_out
      ? "時間切れ…"
      : "あと少し! また挑戦しよう";

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <section
        className={clsx(
          "rounded-3xl p-6 text-center shadow-sm motion-safe:animate-pop",
          result.passed
            ? "bg-gradient-to-br from-emerald-50 to-teal-50 ring-1 ring-emerald-200"
            : "bg-gradient-to-br from-slate-50 to-rose-50 ring-1 ring-rose-200",
        )}
      >
        <Mascot mood={result.passed ? "cheer" : "sad"} size={96} className="justify-center" />
        <h1 className="mt-2 text-2xl font-black text-slate-900">{headline}</h1>
        <p className="mt-1 text-sm text-slate-600">
          {challenge.course_title} の{label}: {result.correct} / {result.total} 問正解 ({result.percent}%)
        </p>
        {result.unlocked_courses.length > 0 && (
          <p className="mt-3 text-sm font-semibold text-emerald-700">
            🔓 新しく解放: {result.unlocked_courses.join("、")}
          </p>
        )}
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          <Link
            to={`/catalog/courses/${result.course_id}`}
            className="rounded-full bg-white px-4 py-1.5 text-sm font-semibold text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50"
          >
            コースに戻る
          </Link>
          <Link
            to="/map"
            className="rounded-full bg-brand-500 px-4 py-1.5 text-sm font-semibold text-white hover:bg-brand-600"
          >
            ステージマップへ
          </Link>
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold text-slate-900">答え合わせ</h2>
        <ol className="space-y-3">
          {result.results.map((r, i) => {
            const q = challenge.questions.find((x) => x.id === r.question_id);
            const answer = Array.isArray(r.correct_answer)
              ? r.correct_answer.join(" / ")
              : r.correct_answer;
            return (
              <li
                key={r.question_id}
                className={clsx(
                  "rounded-xl border p-4 text-sm",
                  r.correct ? "border-emerald-200 bg-emerald-50" : "border-rose-200 bg-rose-50",
                )}
              >
                <div className="font-semibold text-slate-900">
                  {r.correct ? "⭕" : "❌"} Q{i + 1}. {q?.title}
                </div>
                <div className="mt-1 text-slate-700">
                  正解: <code className="font-mono">{answer}</code>
                </div>
                {r.explanation && <div className="mt-1 text-slate-600">{r.explanation}</div>}
              </li>
            );
          })}
        </ol>
      </section>
    </div>
  );
}

// -------------------------------------------------------------- 回答入力

function isAnswered(q: CatalogQuestion, v: AnswerRequest | undefined): boolean {
  if (!v) return false;
  if (q.type === "code") return (v.blanks ?? []).every((b) => b.trim());
  if (q.type === "multiple-choice") return Array.isArray(v.selected) && v.selected.length > 0;
  return typeof v.selected === "string";
}

function AnswerInput({
  question,
  value,
  onChange,
}: {
  question: CatalogQuestion;
  value: AnswerRequest | undefined;
  onChange: (v: AnswerRequest) => void;
}) {
  const choices = question.choices ?? [];
  if (question.type === "choice") {
    return (
      <div role="radiogroup" className="space-y-2">
        {choices.map((label) => (
          <label
            key={label}
            className={clsx(
              "flex cursor-pointer items-start gap-2 rounded-lg border px-3 py-2 text-sm",
              value?.selected === label ? "border-brand-400 bg-brand-50" : "border-slate-200 hover:bg-slate-50",
            )}
          >
            <input
              type="radio"
              name={question.id}
              checked={value?.selected === label}
              onChange={() => onChange({ selected: label })}
              className="mt-0.5"
            />
            <span className="whitespace-pre-wrap">{label}</span>
          </label>
        ))}
      </div>
    );
  }
  if (question.type === "multiple-choice") {
    const selected = new Set(Array.isArray(value?.selected) ? value.selected : []);
    return (
      <div className="space-y-2">
        {choices.map((label) => (
          <label
            key={label}
            className={clsx(
              "flex cursor-pointer items-start gap-2 rounded-lg border px-3 py-2 text-sm",
              selected.has(label) ? "border-brand-400 bg-brand-50" : "border-slate-200 hover:bg-slate-50",
            )}
          >
            <input
              type="checkbox"
              checked={selected.has(label)}
              onChange={() => {
                const next = new Set(selected);
                if (next.has(label)) next.delete(label);
                else next.add(label);
                onChange({ selected: [...next] });
              }}
              className="mt-0.5"
            />
            <span className="whitespace-pre-wrap">{label}</span>
          </label>
        ))}
      </div>
    );
  }
  // code (穴埋め)
  const count = Math.max(1, question.blank_count ?? 1);
  const blanks = value?.blanks ?? Array<string>(count).fill("");
  return (
    <div>
      <pre className="overflow-x-auto rounded-lg bg-slate-900 p-3 text-xs leading-relaxed text-slate-100">
        <code className="font-mono">{question.code_template}</code>
      </pre>
      <div className="mt-2 space-y-2">
        {blanks.map((b, i) => (
          <div key={i} className="flex items-center gap-2 text-sm">
            <label className="w-16 text-xs text-slate-500" htmlFor={`${question.id}-c-${i}`}>
              穴 {i + 1}
            </label>
            <input
              id={`${question.id}-c-${i}`}
              value={b}
              maxLength={500}
              onChange={(e) => {
                const next = [...blanks];
                next[i] = e.target.value;
                onChange({ blanks: next });
              }}
              className="flex-1 rounded-md border border-slate-200 px-2 py-1 font-mono focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
        ))}
      </div>
    </div>
  );
}

// -------------------------------------------------------------- タイマー

function useCountdown(expiresAt: string, onExpire: () => void, active: boolean): number {
  const deadline = new Date(expiresAt).getTime();
  const [now, setNow] = useState(() => Date.now());
  const fired = useRef(false);
  const remaining = Math.max(0, Math.ceil((deadline - now) / 1000));

  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [active]);

  useEffect(() => {
    if (active && remaining === 0 && !fired.current) {
      fired.current = true;
      onExpire();
    }
  }, [active, remaining, onExpire]);

  return remaining;
}

function formatTime(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}
