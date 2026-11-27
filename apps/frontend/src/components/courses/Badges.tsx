import clsx from "clsx";
import type { CourseCategory, CourseLevel, CourseStatus } from "@/types/catalog";
import {
  CATEGORY_BADGE_CLASS,
  CATEGORY_LABEL,
  LEVEL_BADGE_CLASS,
  LEVEL_LABEL,
  STATUS_BADGE_CLASS,
  STATUS_LABEL,
} from "./catalogStyles";

const BASE = "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium";

/**
 * onAccent: 有彩色のグラデーション (コース詳細のヒーロー等) の上に置く場合。
 * 背景はダークモードでも明るいままなので、dark: バリアントを外してライトの配色に固定する。
 */
type AccentProps = { onAccent?: boolean };
const lightOnly = (cls: string) =>
  cls
    .split(" ")
    .filter((c) => !c.startsWith("dark:"))
    .join(" ");
const pick = (cls: string, onAccent?: boolean) => (onAccent ? lightOnly(cls) : cls);

export function CategoryBadge({ category, onAccent }: { category: CourseCategory } & AccentProps) {
  return (
    <span className={clsx(BASE, pick(CATEGORY_BADGE_CLASS[category], onAccent))}>
      {CATEGORY_LABEL[category]}
    </span>
  );
}

export function LevelBadge({ level, onAccent }: { level: CourseLevel } & AccentProps) {
  return (
    <span className={clsx(BASE, pick(LEVEL_BADGE_CLASS[level], onAccent))}>{LEVEL_LABEL[level]}</span>
  );
}

export function StatusBadge({ status, onAccent }: { status: CourseStatus } & AccentProps) {
  if (status === "not-started") return null;
  const dot =
    status === "in-progress"
      ? "bg-blue-500 animate-pulse-soft"
      : status === "completed"
        ? "bg-emerald-500"
        : "bg-ink-400";
  return (
    <span className={clsx(BASE, pick(STATUS_BADGE_CLASS[status], onAccent), "gap-1.5")}>
      <span className={clsx("h-1.5 w-1.5 rounded-full", dot)} />
      {STATUS_LABEL[status]}
    </span>
  );
}

export function TagPill({ children, onAccent }: { children: React.ReactNode } & AccentProps) {
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-md px-1.5 py-0.5 text-[11px]",
        // ヒーロー上ではテーマに関係なく明るいチップにする
        onAccent ? "bg-slate-100 text-slate-600" : "bg-surface-muted text-ink-600",
      )}
    >
      #{children}
    </span>
  );
}
