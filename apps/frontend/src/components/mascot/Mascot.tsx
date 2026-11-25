import clsx from "clsx";

export type MascotMood = "happy" | "cheer" | "think" | "sleepy" | "sad";

type Props = {
  mood?: MascotMood;
  size?: number;
  className?: string;
  /** 吹き出しのセリフ (スクリーンリーダーにも読み上げる) */
  message?: string;
};

/**
 * オリジナルマスコット「ピコ」。
 * 頭の新芽は「学ぶほど育つ」の象徴。表情 (mood) で学習状況に反応する。
 */
export function Mascot({ mood = "happy", size = 72, className, message }: Props) {
  return (
    <div className={clsx("flex items-end gap-2", className)}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 100 100"
        role="img"
        aria-label={`ピコ (${MOOD_LABEL[mood]})`}
        className={clsx(mood === "cheer" && "motion-safe:animate-pop")}
      >
        <defs>
          <linearGradient id="pico-body" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#8b7cf6" />
            <stop offset="100%" stopColor="#5b4bd6" />
          </linearGradient>
        </defs>
        {/* 新芽 */}
        <path d="M50 24 C50 16 50 12 50 8" stroke="#16a34a" strokeWidth="3" fill="none" />
        <path d="M50 14 C40 6 32 10 34 16 C40 18 46 17 50 14Z" fill="#4ade80" />
        <path d="M50 11 C58 2 68 5 66 12 C60 15 54 14 50 11Z" fill="#22c55e" />
        {mood === "cheer" && (
          <>
            <path d="M12 44 L4 30" stroke="#5b4bd6" strokeWidth="6" strokeLinecap="round" />
            <path d="M88 44 L96 30" stroke="#5b4bd6" strokeWidth="6" strokeLinecap="round" />
            <text x="2" y="24" fontSize="12">
              ✨
            </text>
            <text x="84" y="24" fontSize="12">
              ✨
            </text>
          </>
        )}
        {/* からだ */}
        <path
          d="M50 22 C76 22 90 40 90 62 C90 84 72 94 50 94 C28 94 10 84 10 62 C10 40 24 22 50 22Z"
          fill="url(#pico-body)"
        />
        <ellipse cx="50" cy="72" rx="24" ry="14" fill="#ffffff" opacity="0.18" />
        {/* ほっぺ */}
        <ellipse cx="26" cy="66" rx="6" ry="4" fill="#f9a8d4" opacity="0.8" />
        <ellipse cx="74" cy="66" rx="6" ry="4" fill="#f9a8d4" opacity="0.8" />
        <Eyes mood={mood} />
        <Mouth mood={mood} />
        {mood === "sleepy" && (
          <text x="74" y="30" fontSize="14" fill="#64748b" fontWeight="bold">
            z
          </text>
        )}
      </svg>
      {message && (
        <div className="relative mb-3 rounded-2xl bg-white px-3 py-2 text-sm text-slate-700 shadow-sm ring-1 ring-slate-200">
          {message}
        </div>
      )}
    </div>
  );
}

const MOOD_LABEL: Record<MascotMood, string> = {
  happy: "にこにこ",
  cheer: "大よろこび",
  think: "考え中",
  sleepy: "おねむ",
  sad: "しょんぼり",
};

function Eyes({ mood }: { mood: MascotMood }) {
  if (mood === "sleepy") {
    return (
      <g stroke="#1e1b4b" strokeWidth="3" strokeLinecap="round" fill="none">
        <path d="M30 54 Q36 58 42 54" />
        <path d="M58 54 Q64 58 70 54" />
      </g>
    );
  }
  if (mood === "cheer") {
    return (
      <g stroke="#1e1b4b" strokeWidth="3.5" strokeLinecap="round" fill="none">
        <path d="M30 56 Q36 48 42 56" />
        <path d="M58 56 Q64 48 70 56" />
      </g>
    );
  }
  const look = mood === "think" ? -3 : 0;
  return (
    <g>
      <ellipse cx="36" cy="54" rx="7" ry="8.5" fill="#ffffff" />
      <ellipse cx="64" cy="54" rx="7" ry="8.5" fill="#ffffff" />
      <circle cx="37" cy={56 + look} r="4" fill="#1e1b4b" />
      <circle cx="65" cy={56 + look} r="4" fill="#1e1b4b" />
      <circle cx="38.5" cy={54 + look} r="1.4" fill="#ffffff" />
      <circle cx="66.5" cy={54 + look} r="1.4" fill="#ffffff" />
    </g>
  );
}

function Mouth({ mood }: { mood: MascotMood }) {
  switch (mood) {
    case "cheer":
      return <path d="M40 68 Q50 82 60 68 Z" fill="#1e1b4b" />;
    case "sad":
      return (
        <path d="M42 76 Q50 70 58 76" stroke="#1e1b4b" strokeWidth="3" fill="none" strokeLinecap="round" />
      );
    case "think":
      return <circle cx="54" cy="72" r="2.5" fill="#1e1b4b" />;
    case "sleepy":
      return <ellipse cx="50" cy="72" rx="3" ry="2" fill="#1e1b4b" />;
    default:
      return (
        <path d="M42 69 Q50 77 58 69" stroke="#1e1b4b" strokeWidth="3" fill="none" strokeLinecap="round" />
      );
  }
}
