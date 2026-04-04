import type {
  ChallengeCatalogItem,
  ChallengeItem,
  TraceSummary,
} from "@/lib/types";

function slugify(value: string): string {
  const base = value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
  return base || "challenge";
}

function timestampOrZero(value: string | null): number {
  if (!value) {
    return 0;
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

export function buildChallengeItems(
  traces: TraceSummary[],
  catalog: ChallengeCatalogItem[] = [],
): ChallengeItem[] {
  const tracesByName = new Map<string, TraceSummary[]>();
  for (const trace of traces) {
    const current = tracesByName.get(trace.challengeName);
    if (current) {
      current.push(trace);
    } else {
      tracesByName.set(trace.challengeName, [trace]);
    }
  }

  for (const [name, list] of tracesByName) {
    tracesByName.set(
      name,
      [...list].sort(
        (left, right) => timestampOrZero(right.updatedAt) - timestampOrZero(left.updatedAt),
      ),
    );
  }

  const items: ChallengeItem[] = [];
  const consumedNames = new Set<string>();

  for (const catalogItem of catalog) {
    const challengeTraces = tracesByName.get(catalogItem.name) ?? [];
    consumedNames.add(catalogItem.name);
    const traceUpdatedAt = challengeTraces[0]?.updatedAt ?? null;
    items.push({
      id: catalogItem.id,
      name: catalogItem.name,
      traceCount: challengeTraces.length,
      startedAt: catalogItem.startedAt,
      updatedAt:
        timestampOrZero(traceUpdatedAt) > timestampOrZero(catalogItem.updatedAt)
          ? traceUpdatedAt
          : catalogItem.updatedAt,
      traces: challengeTraces,
    });
  }

  for (const [name, challengeTraces] of tracesByName) {
    if (consumedNames.has(name)) {
      continue;
    }
    items.push({
      id: challengeTraces[0]?.challengeId || slugify(name),
      name,
      traceCount: challengeTraces.length,
      startedAt: challengeTraces[0]?.startedAt ?? null,
      updatedAt: challengeTraces[0]?.updatedAt ?? null,
      traces: challengeTraces,
    });
  }

  return items.sort((left, right) => {
    const diff = timestampOrZero(right.updatedAt) - timestampOrZero(left.updatedAt);
    if (diff !== 0) {
      return diff;
    }
    return left.name.localeCompare(right.name, undefined, { sensitivity: "base" });
  });
}

export function findChallengeById(
  traces: TraceSummary[],
  challengeId: string,
  catalog: ChallengeCatalogItem[] = [],
): ChallengeItem | null {
  return buildChallengeItems(traces, catalog).find((item) => item.id === challengeId) ?? null;
}
