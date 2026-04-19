"use client";

import { startTransition, useCallback, useEffect, useEffectEvent, useRef, useState } from "react";

import { getTraceDetail, getTraces } from "@/lib/traces";
import type {
  ChallengeCatalogItem,
  ChallengeRunState,
  TraceDetail,
  TraceEvent,
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

export function useLogDashboard(
  challengeId: string,
  challengeState: ChallengeRunState,
  _activeRunIds: string[],
  _catalogChallenges: ChallengeCatalogItem[],
) {
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<TraceDetail | null>(null);
  const [listPending, setListPending] = useState(false);
  const [detailPending, setDetailPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null);
  const listRequestInFlight = useRef(false);
  const detailRequestInFlight = useRef(false);
  const notifiedStatuses = useRef<Map<string, string>>(new Map());
  const sseConnectedRef = useRef(false);

  const isInitializing =
    (challengeState === "starting" || challengeState === "running") && traces.length === 0;

  const noTracesFound =
    !isInitializing &&
    traces.length === 0 &&
    challengeState !== "idle" &&
    challengeState !== "";

  const { status: runsSseStatus, subscribe: subscribeRuns } = useSseEvents(
    "/api/v1/events/runs",
  );

  const { status: traceSseStatus, subscribe: subscribeTrace } = useSseEvents(
    selectedId ? `/api/v1/events/traces/${encodeURIComponent(selectedId)}` : null,
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
      const payload = await getTraces(challengeId);

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
        const traceIds = new Set(payload.traces.map((t) => t.id));

        setSelectedId((current) => {
          if (!traceIds.size) {
            return null;
          }

          if (current && traceIds.has(current)) {
            return current;
          }

          return payload.traces[0]?.id ?? null;
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
      const payload = await getTraceDetail(traceId, DETAIL_LIMIT);

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
      const payload = await getTraces(challengeId);
      let nextSelectedId = selectedId;
      const traceIds = new Set(payload.traces.map((t) => t.id));

      startTransition(() => {
        setTraces(payload.traces);
        setLastSyncedAt(payload.generatedAt);
        setError(null);
      });

      if (!traceIds.size) {
        startTransition(() => {
          setSelectedId(null);
          setDetail(null);
        });
        return;
      }

      if (!nextSelectedId || !traceIds.has(nextSelectedId)) {
        nextSelectedId = payload.traces[0]?.id ?? null;
      }

      startTransition(() => {
        setSelectedId(nextSelectedId);
      });

      if (nextSelectedId) {
        const detailPayload = await getTraceDetail(nextSelectedId, DETAIL_LIMIT);

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
      const allTerminal =
        traces.length > 0 &&
        traces.every((t) => TERMINAL_STATES.has(t.status));
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
      const ids = new Set(traces.map((t) => t.id));
      if (!ids.size) {
        return null;
      }
      if (current && ids.has(current)) {
        return current;
      }
      return traces[0]?.id ?? null;
    });
  }, [traces]);

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

  const selectedTrace =
    detail?.summary ?? traces.find((trace) => trace.id === selectedId) ?? null;

  const totals = traces.reduce(
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
    traces,
    selectedId,
    setSelectedId,
    selectedTrace,
    detail,
    isInitializing,
    noTracesFound,
    listPending,
    detailPending,
    error,
    lastSyncedAt,
    refreshNow,
    totals,
  };
}
