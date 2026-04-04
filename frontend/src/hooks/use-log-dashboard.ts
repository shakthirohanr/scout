"use client";

import { startTransition, useEffect, useEffectEvent, useMemo, useState } from "react";

import { buildChallengeItems } from "@/lib/challenges";
import type {
  ChallengeCatalogItem,
  TraceDetail,
  TraceListResponse,
  TraceSummary,
} from "@/lib/types";

const TRACE_POLL_MS = 5000;
const DETAIL_POLL_MS = 3500;
const DETAIL_LIMIT = 450;

function getScopedTraces(
  traces: TraceSummary[],
  activeChallengeId: string | null,
  activeChallengeName: string | null,
  catalogChallenges: ChallengeCatalogItem[],
): TraceSummary[] {
  if (!activeChallengeId && !activeChallengeName) {
    return traces;
  }

  const challengeItems = buildChallengeItems(traces, catalogChallenges);
  if (activeChallengeId) {
    const byId = challengeItems.find((item) => item.id === activeChallengeId);
    if (byId) {
      return byId.traces;
    }
  }

  if (activeChallengeName) {
    return traces.filter((trace) => trace.challengeName === activeChallengeName);
  }

  return [];
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}

export function useLogDashboard(
  initialTraces: TraceSummary[],
  activeChallengeId: string | null = null,
  activeChallengeName: string | null = null,
  catalogChallenges: ChallengeCatalogItem[] = [],
) {
  const [traces, setTraces] = useState(initialTraces);
  const initialScope = getScopedTraces(
    initialTraces,
    activeChallengeId,
    activeChallengeName,
    catalogChallenges,
  );
  const [selectedId, setSelectedId] = useState<string | null>(
    initialScope[0]?.id ?? null,
  );
  const [detail, setDetail] = useState<TraceDetail | null>(null);
  const [listPending, setListPending] = useState(false);
  const [detailPending, setDetailPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null);

  const refreshTraceList = useEffectEvent(async () => {
    setListPending(true);

    try {
      const payload = await fetchJson<TraceListResponse>("/api/logs");

      startTransition(() => {
        setTraces(payload.traces);
        setLastSyncedAt(payload.generatedAt);
        setError(null);
      });

      startTransition(() => {
        const scopedTraces = getScopedTraces(
          payload.traces,
          activeChallengeId,
          activeChallengeName,
          catalogChallenges,
        );
        const scopedTraceIds = new Set(scopedTraces.map((trace) => trace.id));

        setSelectedId((current) => {
          if (!scopedTraceIds.size) {
            return null;
          }

          if (current && scopedTraceIds.has(current)) {
            return current;
          }

          return scopedTraces[0]?.id ?? null;
        });
      });
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to refresh trace list.",
      );
    } finally {
      setListPending(false);
    }
  });

  const refreshTraceDetail = useEffectEvent(async (traceId: string) => {
    setDetailPending(true);

    try {
      const payload = await fetchJson<TraceDetail>(
        `/api/logs/${encodeURIComponent(traceId)}?limit=${DETAIL_LIMIT}`,
      );

      startTransition(() => {
        setDetail(payload);
        setError(null);
      });
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to refresh trace detail.",
      );
    } finally {
      setDetailPending(false);
    }
  });

  async function refreshNow() {
    setListPending(true);
    setDetailPending(true);

    try {
      const payload = await fetchJson<TraceListResponse>("/api/logs");
      let nextSelectedId = selectedId;
      const scopedTraces = getScopedTraces(
        payload.traces,
        activeChallengeId,
        activeChallengeName,
        catalogChallenges,
      );
      const scopedTraceIds = new Set(scopedTraces.map((trace) => trace.id));

      startTransition(() => {
        setTraces(payload.traces);
        setLastSyncedAt(payload.generatedAt);
        setError(null);
      });

      if (!scopedTraceIds.size) {
        startTransition(() => {
          setSelectedId(null);
          setDetail(null);
        });
        return;
      }

      if (!nextSelectedId || !scopedTraceIds.has(nextSelectedId)) {
        nextSelectedId = scopedTraces[0]?.id ?? null;
      }

      startTransition(() => {
        setSelectedId(nextSelectedId);
      });

      if (nextSelectedId) {
        const detailPayload = await fetchJson<TraceDetail>(
          `/api/logs/${encodeURIComponent(nextSelectedId)}?limit=${DETAIL_LIMIT}`,
        );

        startTransition(() => {
          setDetail(detailPayload);
          setError(null);
        });
      }
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to refresh trace dashboard.",
      );
    } finally {
      setListPending(false);
      setDetailPending(false);
    }
  }

  useEffect(() => {
    void refreshTraceList();

    const intervalId = window.setInterval(() => {
      void refreshTraceList();
    }, TRACE_POLL_MS);

    return () => {
      window.clearInterval(intervalId);
    };
  }, []);

  useEffect(() => {
    setSelectedId((current) => {
      const scopedTraces = getScopedTraces(
        traces,
        activeChallengeId,
        activeChallengeName,
        catalogChallenges,
      );
      const ids = new Set(scopedTraces.map((trace) => trace.id));
      if (!ids.size) {
        return null;
      }
      if (current && ids.has(current)) {
        return current;
      }
      return scopedTraces[0]?.id ?? null;
    });
  }, [activeChallengeId, activeChallengeName, traces, catalogChallenges]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }

    void refreshTraceDetail(selectedId);

    const intervalId = window.setInterval(() => {
      void refreshTraceDetail(selectedId);
    }, DETAIL_POLL_MS);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [selectedId]);

  const challengeItems = useMemo(
    () => buildChallengeItems(traces, catalogChallenges),
    [traces, catalogChallenges],
  );
  const activeChallenge =
    challengeItems.find((item) => item.id === activeChallengeId)
    ?? (activeChallengeName
      ? challengeItems.find((item) => item.name === activeChallengeName)
      : null)
    ?? null;
  const filteredTraces = activeChallenge?.traces ?? getScopedTraces(
    traces,
    activeChallengeId,
    activeChallengeName,
    catalogChallenges,
  );
  const selectedTrace =
    detail?.summary ?? filteredTraces.find((trace) => trace.id === selectedId) ?? null;

  const totals = filteredTraces.reduce(
    (summary, trace) => {
      summary.sessions += 1;
      summary.toolCalls += trace.toolCalls;
      summary.costUsd += trace.costUsd;

      if (trace.status === "running") {
        summary.running += 1;
      }

      if (trace.status === "solved") {
        summary.solved += 1;
      }

      return summary;
    },
    {
      sessions: 0,
      running: 0,
      solved: 0,
      toolCalls: 0,
      costUsd: 0,
    },
  );

  return {
    challengeItems,
    activeChallenge,
    filteredTraces,
    traces,
    selectedId,
    setSelectedId,
    selectedTrace,
    detail,
    listPending,
    detailPending,
    error,
    lastSyncedAt,
    refreshNow,
    totals,
  };
}
