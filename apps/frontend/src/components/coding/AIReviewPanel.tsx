import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import clsx from "clsx";
import type { CodingReviewResponse } from "@learning-platform/shared-types";
import { disputeReview } from "@/api/coding";
import { getErrorMessage } from "@/lib/api";

type Props = {
  submissionId: string | null;
  review: CodingReviewResponse | null;
  onRequest: () => void;
  pending: boolean;
  error: string | null;
};

/** AI による観点別コードレビュー。合否は自動テストで決まり、AI は補助として改善点を示す。 */
export function AIReviewPanel({ submissionId, review, onRequest, pending, error }: Props) {
  if (!submissionId) {
    return (
      <p className="text-slate-400">
        コードを「✔ 提出」すると、AI が正確性・可読性・効率・セキュリティなど 7 つの観点でレビューします。
      </p>
    );
  }
  if (!review || !review.review) {
    return (
      <div className="space-y-2 text-slate-300">
        <p>提出したコードを AI にレビューしてもらおう。</p>
        <button
          type="button"
          onClick={onRequest}
          disabled={pending}
          className="rounded-md bg-gradient-to-r from-indigo-500 to-fuchsia-500 px-3 py-1 text-xs font-semibold text-white disabled:opacity-50"
        >
          {pending ? "レビュー中…" : error ? "🤖 もう一度レビューを依頼する" : "🤖 AI レビューを受ける"}
        </button>
        {pending && (
          <p className="text-xs text-slate-400">
            AI がコードを読んでいます。数十秒かかることがあります (このまま待つか、他の作業を続けても大丈夫です)。
          </p>
        )}
        {error && (
          <p role="alert" className="text-rose-300">
            {error}
          </p>
        )}
      </div>
    );
  }

  const r = review.review;
  return (
    <div className="space-y-3 text-[12px]">
      <div className="rounded-md bg-gradient-to-r from-indigo-500/20 to-fuchsia-500/20 p-3 ring-1 ring-indigo-400/30">
        <div className="text-xs font-semibold text-white">
          {review.passed === null
            ? "AI レビュー (自動テスト非対応の問題)"
            : review.passed
              ? "✅ 自動テスト合格"
              : "🟡 自動テスト不合格"}
        </div>
        <p className="mt-1 text-slate-200">{r.summary}</p>
      </div>

      <ul className="grid gap-2 sm:grid-cols-2">
        {Object.entries(r.aspects).map(([key, a]) => (
          <li key={key} className="rounded-md border border-slate-700 p-2">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-slate-100">{review.aspect_labels[key] ?? key}</span>
              <span aria-label={`${a.score} / 5`} className="font-mono text-amber-300">
                {"★".repeat(a.score)}
                <span className="text-slate-600">{"★".repeat(5 - a.score)}</span>
              </span>
            </div>
            <p className="mt-1 text-slate-300">{a.comment}</p>
          </li>
        ))}
      </ul>

      <Section title="良かった点" tone="ok">
        <List items={r.good_points} />
      </Section>
      <Section title="改善点" tone="warn">
        {r.improvements.length === 0 ? (
          <p className="text-slate-500">(なし)</p>
        ) : (
          <ul className="space-y-2">
            {r.improvements.map((imp, i) => (
              <li key={i}>
                <div className="font-semibold text-slate-100">{imp.title}</div>
                <p className="text-slate-300">{imp.detail}</p>
                {imp.code_example && (
                  <pre className="mt-1 overflow-x-auto rounded bg-black/50 p-2 font-mono text-[11px] text-slate-100">
                    <code>{imp.code_example}</code>
                  </pre>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Section title="次に学ぶと良いこと" tone="info">
        <List items={r.next_topics} />
      </Section>

      <Dispute submissionId={review.submission_id} />
      <p className="text-[10px] text-slate-500">
        ※ 合否は自動テストで判定しています。AI の評価は参考情報で、誤ることがあります。
      </p>
    </div>
  );
}

function Dispute({ submissionId }: { submissionId: string }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const send = useMutation({ mutationFn: () => disputeReview(submissionId, reason) });

  if (send.isSuccess) {
    return <p className="text-emerald-300">報告ありがとうございます。内容を確認して改善に役立てます。</p>;
  }
  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="text-[11px] text-slate-400 underline">
        評価に異議がある / 間違いを報告する
      </button>
    );
  }
  return (
    <div className="space-y-1">
      <textarea
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        maxLength={2000}
        rows={2}
        placeholder="どの評価がおかしいと思いますか?"
        className="w-full rounded-md border border-slate-700 bg-[#0d1117] p-2 text-slate-200"
      />
      <button
        type="button"
        onClick={() => send.mutate()}
        disabled={!reason.trim() || send.isPending}
        className="rounded-md bg-slate-700 px-3 py-1 text-xs text-white disabled:opacity-50"
      >
        送信
      </button>
      {send.error && <p className="text-rose-300">{getErrorMessage(send.error)}</p>}
    </div>
  );
}

function Section({
  title,
  children,
  tone,
}: {
  title: string;
  children: React.ReactNode;
  tone: "ok" | "warn" | "info";
}) {
  return (
    <div>
      <div
        className={clsx(
          "text-[10px] font-semibold uppercase tracking-wider",
          tone === "ok" && "text-emerald-300",
          tone === "warn" && "text-amber-300",
          tone === "info" && "text-sky-300",
        )}
      >
        {title}
      </div>
      <div className="mt-1">{children}</div>
    </div>
  );
}

function List({ items }: { items: string[] }) {
  if (items.length === 0) return <p className="text-slate-500">(なし)</p>;
  return (
    <ul className="list-inside list-disc space-y-0.5 text-slate-300">
      {items.map((it, i) => (
        <li key={i}>{it}</li>
      ))}
    </ul>
  );
}
