import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchCourseCatalog } from "@/api/catalog";
import { ErrorState, LoadingState } from "@/components/common/LoadingState";
import { Mascot } from "@/components/mascot/Mascot";
import { getErrorMessage } from "@/lib/api";
import { queryKeys } from "@/lib/queryKeys";
import { layoutStageMap, splitTitle, type MapNode } from "@/lib/stageMap";

const RADIUS = 36;
const RING = 2 * Math.PI * (RADIUS + 6);

function nodeColors(node: MapNode) {
  const c = node.course;
  if (c.isLocked) return { fill: "#e2e8f0", ring: "#cbd5e1", text: "#64748b" };
  if (c.status === "completed") return { fill: "#10b981", ring: "#059669", text: "#065f46" };
  if (c.isCleared) return { fill: "#34d399", ring: "#10b981", text: "#065f46" };
  if (c.status === "in-progress") return { fill: "#6366f1", ring: "#4f46e5", text: "#312e81" };
  return { fill: "#ffffff", ring: "#6366f1", text: "#1e293b" };
}

function statusText(node: MapNode): string {
  const c = node.course;
  if (c.isLocked) return `ロック中 (解放条件: ${c.prerequisiteTitles.join("・")})`;
  if (c.bossDefeated) return "ボス撃破済み";
  if (c.status === "completed") return "完走";
  if (c.skipped) return "飛び級でクリア";
  if (c.isCleared) return "クリア";
  return `進捗 ${c.progress}%`;
}

export function StageMapPage() {
  const navigate = useNavigate();
  const { data, isLoading, error } = useQuery({
    queryKey: queryKeys.catalog,
    queryFn: fetchCourseCatalog,
  });
  const layout = useMemo(() => (data ? layoutStageMap(data.courses) : null), [data]);

  if (isLoading) return <LoadingState />;
  if (error) return <ErrorState message={getErrorMessage(error)} />;
  if (!layout || !data) return null;

  const cleared = data.courses.filter((c) => c.isCleared).length;
  const open = (id: string) => navigate(`/catalog/courses/${id}`);

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">ステージマップ</h1>
          <p className="mt-1 text-sm text-slate-600">
            コースをクリア (70% 正解) すると、道の先のステージが解放されます。経験者は「実力テスト」で飛び級できます。
          </p>
        </div>
        <Mascot
          mood={cleared === 0 ? "happy" : "cheer"}
          size={56}
          message={`${data.courses.length} ステージ中 ${cleared} クリア!`}
        />
      </header>

      <Legend />

      <div className="overflow-x-auto rounded-3xl border border-slate-200 bg-gradient-to-b from-sky-50 via-white to-emerald-50 p-2 shadow-sm">
        <svg
          viewBox={`0 0 ${layout.width} ${layout.height}`}
          className="min-w-[900px]"
          role="group"
          aria-label="コースのステージマップ"
        >
          {layout.edges.map(({ from, to }) => {
            const done = from.course.isCleared;
            const midY = (from.y + to.y) / 2;
            return (
              <path
                key={`${from.course.id}-${to.course.id}`}
                d={`M${from.x},${from.y + RADIUS} C${from.x},${midY} ${to.x},${midY} ${to.x},${to.y - RADIUS}`}
                fill="none"
                stroke={done ? "#10b981" : "#cbd5e1"}
                strokeWidth={done ? 5 : 4}
                strokeDasharray={done ? undefined : "8 8"}
                strokeLinecap="round"
              />
            );
          })}

          {layout.nodes.map((node) => {
            const c = node.course;
            const colors = nodeColors(node);
            const label = `${c.title}: ${statusText(node)}`;
            return (
              <g
                key={c.id}
                transform={`translate(${node.x},${node.y})`}
                role="link"
                tabIndex={0}
                aria-label={label}
                className="cursor-pointer outline-none [&:focus-visible>circle:first-child]:stroke-amber-400"
                onClick={() => open(c.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    open(c.id);
                  }
                }}
              >
                <title>{label}</title>
                {/* 進捗リング */}
                <circle r={RADIUS + 6} fill="none" stroke="#e2e8f0" strokeWidth={5} />
                {!c.isLocked && c.progress > 0 && (
                  <circle
                    r={RADIUS + 6}
                    fill="none"
                    stroke={colors.ring}
                    strokeWidth={5}
                    strokeDasharray={`${(c.progress / 100) * RING} ${RING}`}
                    transform="rotate(-90)"
                    strokeLinecap="round"
                  />
                )}
                <circle r={RADIUS} fill={colors.fill} stroke={colors.ring} strokeWidth={3} />
                <text
                  textAnchor="middle"
                  dominantBaseline="central"
                  fontSize={30}
                  opacity={c.isLocked ? 0.45 : 1}
                >
                  {c.icon}
                </text>
                {c.isLocked && (
                  <text x={24} y={-22} fontSize={18} textAnchor="middle">
                    🔒
                  </text>
                )}
                {c.bossDefeated && (
                  <text x={0} y={-RADIUS - 14} fontSize={22} textAnchor="middle">
                    👑
                  </text>
                )}
                {c.skipped && !c.bossDefeated && (
                  <text x={26} y={-24} fontSize={18} textAnchor="middle">
                    🚀
                  </text>
                )}
                {splitTitle(c.title).map((line, i) => (
                  <text
                    key={i}
                    y={RADIUS + 26 + i * 16}
                    textAnchor="middle"
                    fontSize={14}
                    fontWeight={600}
                    fill={colors.text}
                  >
                    {line}
                  </text>
                ))}
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}

function Legend() {
  const items = [
    { color: "bg-white ring-2 ring-indigo-500", label: "挑戦できる" },
    { color: "bg-indigo-500", label: "学習中" },
    { color: "bg-emerald-400", label: "クリア (次が解放)" },
    { color: "bg-slate-200", label: "ロック中" },
  ];
  return (
    <ul className="flex flex-wrap gap-4 text-xs text-slate-600">
      {items.map((i) => (
        <li key={i.label} className="flex items-center gap-1.5">
          <span className={`inline-block h-3 w-3 rounded-full ${i.color}`} aria-hidden />
          {i.label}
        </li>
      ))}
      <li>👑 ボス撃破</li>
      <li>🚀 飛び級</li>
    </ul>
  );
}
