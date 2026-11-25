import type { Course } from "@/types/catalog";

export type MapNode = { course: Course; x: number; y: number; tier: number };
export type MapEdge = { from: MapNode; to: MapNode };
export type StageMapLayout = {
  nodes: MapNode[];
  edges: MapEdge[];
  width: number;
  height: number;
};

export const MAP_WIDTH = 1200;
export const TIER_HEIGHT = 170;
export const TOP_PADDING = 70;

/**
 * 前提コースの DAG を段 (tier) ごとに並べる。
 * tier = 前提コースからの最長距離。同じ段の中は親の平均 x 座標順 (交差を減らす)。
 */
export function layoutStageMap(courses: Course[]): StageMapLayout {
  const byId = new Map(courses.map((c) => [c.id, c]));
  const tierCache = new Map<string, number>();
  const tierOf = (c: Course): number => {
    const cached = tierCache.get(c.id);
    if (cached !== undefined) return cached;
    const parents = c.prerequisiteIds.map((id) => byId.get(id)).filter(Boolean) as Course[];
    const t = parents.length ? 1 + Math.max(...parents.map(tierOf)) : 0;
    tierCache.set(c.id, t);
    return t;
  };

  const tiers: Course[][] = [];
  courses.forEach((c) => {
    const t = tierOf(c);
    (tiers[t] ??= []).push(c);
  });

  const nodeById = new Map<string, MapNode>();
  tiers.forEach((row, t) => {
    const ordered =
      t === 0
        ? row
        : [...row].sort((a, b) => parentX(a, nodeById) - parentX(b, nodeById));
    ordered.forEach((course, i) => {
      nodeById.set(course.id, {
        course,
        tier: t,
        x: ((i + 0.5) / ordered.length) * MAP_WIDTH,
        y: TOP_PADDING + t * TIER_HEIGHT,
      });
    });
  });

  const nodes = [...nodeById.values()];
  const edges: MapEdge[] = nodes.flatMap((to) =>
    to.course.prerequisiteIds
      .map((id) => nodeById.get(id))
      .filter((from): from is MapNode => !!from)
      .map((from) => ({ from, to })),
  );
  return {
    nodes,
    edges,
    width: MAP_WIDTH,
    height: TOP_PADDING + (tiers.length - 1) * TIER_HEIGHT + 110,
  };
}

function parentX(c: Course, placed: Map<string, MapNode>): number {
  const xs: number[] = [];
  for (const id of c.prerequisiteIds) {
    const node = placed.get(id);
    if (node) xs.push(node.x);
  }
  return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0;
}

/** タイトルを最大 2 行に分割する (SVG text は自動改行しないため) */
export function splitTitle(title: string, perLine = 8): string[] {
  const t = title.replace(/ 入門$/, "");
  if (t.length <= perLine) return [t];
  return [t.slice(0, perLine), t.length > perLine * 2 ? `${t.slice(perLine, perLine * 2 - 1)}…` : t.slice(perLine)];
}
