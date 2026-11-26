import clsx from "clsx";
import { useThemeStore, type ThemePreference } from "@/stores/theme";

const OPTIONS: Array<{ value: ThemePreference; label: string; icon: string }> = [
  { value: "system", label: "OS の設定に合わせる", icon: "🖥️" },
  { value: "light", label: "ライト", icon: "☀️" },
  { value: "dark", label: "ダーク", icon: "🌙" },
];

export function ThemeToggle() {
  const preference = useThemeStore((s) => s.preference);
  const setPreference = useThemeStore((s) => s.setPreference);

  return (
    <div
      role="radiogroup"
      aria-label="表示テーマ"
      className="inline-flex items-center rounded-full border border-line bg-surface-subtle p-0.5"
    >
      {OPTIONS.map((o) => {
        const active = preference === o.value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={o.label}
            title={o.label}
            onClick={() => setPreference(o.value)}
            className={clsx(
              "flex h-7 w-7 items-center justify-center rounded-full text-sm transition",
              "focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500",
              active ? "bg-surface shadow-sm ring-1 ring-line" : "opacity-60 hover:opacity-100",
            )}
          >
            <span aria-hidden>{o.icon}</span>
          </button>
        );
      })}
    </div>
  );
}
