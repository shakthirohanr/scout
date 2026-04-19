"use client";

import { startTransition, useCallback, useEffect, useEffectEvent, useMemo, useRef, useState } from "react";

import { buildChallengeItems } from "@/lib/challenges";
import type {
  ChallengeCatalogItem,
  TraceDetail,
  TraceEvent,
  TraceListResponse,
  TraceSummary,
} from "@/lib/types";
import { useSseEvents } from "@/hooks/use-sse-events";
import { toast } from "sonner";

const TRACE_POLL_MS = 5000;
const TRACE_POLL_SSE_MS = 15000;
const DETAIL_POLL_MS = 3500;
const DETAIL_POLL_SSE_MS = 15000;
const DETAIL_LIMIT = 450;
const TERMINAL_STATES = new Set(["solved", "gave_up", "cancelled", "failed", "finished"]);

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
  const listRequestInFlight = useRef(false);
  const detailRequestInFlight = useRef(false);
  const notifiedStatuses = useRef<Map<string, string>>(new Map());
  const sseConnectedRef = useRef(false);

  const { status: runsSseStatus, subscribe: subscribeRuns } = useSseEvents(
    "/api/events/runs",
  );

  const { status: traceSseStatus, subscribe: subscribeTrace } = useSseEvents(
    selectedId ? `/api/events/traces/${encodeURIComponent(selectedId)}` : null,
  );

  const sseConnected = runsSseStatus === "connected" || traceSseStatus === "connected";
  sseConnectedRef.current = sseConnected;

  const handleRunSseEvent = useCallback(
    (data: unknown) => {
      const payload = data as {
        run_id?: string;
        challenge_id?: string;
        status?: string;
        timestamp?: string;
      };

      if (payload.run_id && payload.status) {
        setTraces((prev) => {
          return prev.map((trace) => {
            if (trace.challengeId === payload.challenge_id || trace.id === payload.run_id) {
              const newStatus = payload.status as TraceSummary["status"];
              const prevStatus = notifiedStatuses.current.get(trace.id);
              if (prevStatus === "running" && prevStatus !== newStatus) {
                if (newStatus === "solved") {
                  toast.success("Challenge solved!", { description: trace.challengeName });
                } else if (newStatus === "error" || newStatus === "failed") {
                  toast.error("Agent failed", { description: trace.challengeName });
                } else if (newStatus === "gave_up") {
                  toast("Agent gave up", { description: trace.challengeName });
                }
              }
              notifiedStatuses.current.set(trace.id, newStatus);
              return { ...trace, status: newStatus };
            }
            return trace;
          });
        });
      }
    },
    [],
  );

  const handleTraceSseEvent = useCallback(
    (data: unknown) => {
      const payload = data as { trace_id?: string; event?: TraceEvent };
      if (!payload.event) return;

      setDetail((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          events: [...prev.events, payload.event!],
        };
      });
    },
    [],
  );

  useEffect(() => {
    const unsub1 = subscribeRuns("run_started", handleRunSseEvent);
    const unsub2 = subscribeRuns("run_status_changed", handleRunSseEvent);
    const unsub3 = subscribeRuns("run_finished", handleRunSseEvent);
    return () => {
      unsub1();
      unsub2();
      unsub3();
    };
  }, [subscribeRuns, handleRunSseEvent]);

  useEffect(() => {
    const unsub = subscribeTrace("trace_event", handleTraceSseEvent);
    return () => {
      unsub();
    };
  }, [subscribeTrace, handleTraceSseEvent]);

  const refreshTraceList = useEffectEvent(async () => {
    if (listRequestInFlight.current) {
      return;
    }

    listRequestInFlight.current = true;
    setListPending(true);

    try {
      const payload = await fetchJson<TraceListResponse>("/api/logs");

      startTransition(() => {
        setTraces(payload.traces);
        setLastSyncedAt(payload.generatedAt);
        setError(null);
      });

      for (const trace of payload.traces) {
        const prev = notifiedStatuses.current.get(trace.id);
        if (prev === "running" && prev !== trace.status) {
          if (trace.status === "solved") {
            toast.success("Challenge solved!", { description: trace.challengeName });
          } else if (trace.status === "error" || trace.status === "failed") {
            toast.error("Agent failed", { description: trace.challengeName });
          } else if (trace.status === "gave_up") {
            toast("Agent gave up", { description: trace.challengeName });
          }
        }
        notifiedStatuses.current.set(trace.id, trace.status);
      }

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
      listRequestInFlight.current = false;
      setListPending(false);
    }
  });

  const refreshTraceDetail = useEffectEvent(async (traceId: string) => {
    if (detailRequestInFlight.current) {
      return;
    }

    detailRequestInFlight.current = true;
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
      detailRequestInFlight.current = false;
      setDetailPending(false);
    }
  });

  async function refreshNow() {
    if (listRequestInFlight.current || detailRequestInFlight.current) {
      return;
    }

    listRequestInFlight.current = true;
    detailRequestInFlight.current = true;
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
      listRequestInFlight.current = false;
      detailRequestInFlight.current = false;
      setListPending(false);
      setDetailPending(false);
    }
  }

  useEffect(() => {
    void refreshTraceList();

    const pollMs = sseConnectedRef.current ? TRACE_POLL_SSE_MS : TRACE_POLL_MS;

    const intervalId = window.setInterval(() => {
      const scopedTraces = getScopedTraces(
        traces,
        activeChallengeId,
        activeChallengeName,
        catalogChallenges,
      );
      const allTerminal =
        scopedTraces.length > 0 &&
        scopedTraces.every((t) => TERMINAL_STATES.has(t.status));
      if (allTerminal) {
        return;
      }
      void refreshTraceList();
    }, pollMs);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [sseConnected]);

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

    const pollMs = sseConnectedRef.current ? DETAIL_POLL_SSE_MS : DETAIL_POLL_MS;

    const intervalId = window.setInterval(() => {
      const currentTrace = traces.find((t) => t.id === selectedId);
      if (currentTrace && TERMINAL_STATES.has(currentTrace.status)) {
        return;
      }
      void refreshTraceDetail(selectedId);
    }, pollMs);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [selectedId, sseConnected]);

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
