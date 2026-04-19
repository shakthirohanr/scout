"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type SseStatus = "connected" | "disconnected" | "connecting";
type EventHandler = (data: unknown) => void;
const MAX_BACKOFF_MS = 8000;
const INITIAL_BACKOFF_MS = 1000;
const KNOWN_EVENT_TYPES = [
  "connected",
  "run_started",
  "run_status_changed",
  "run_finished",
  "trace_event",
  "error",
];

export function useSseEvents(url: string | null) {
  const [status, setStatus] = useState<SseStatus>("disconnected");
  const subscribersRef = useRef<Map<string, Set<EventHandler>>>(new Map());
  const esRef = useRef<EventSource | null>(null);
  const backoffRef = useRef(INITIAL_BACKOFF_MS);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const subscribe = useCallback(
    (eventType: string, callback: EventHandler) => {
      if (!subscribersRef.current.has(eventType)) {
        subscribersRef.current.set(eventType, new Set());
      }
      subscribersRef.current.get(eventType)!.add(callback);

      return () => {
        subscribersRef.current.get(eventType)?.delete(callback);
      };
    },
    [],
  );

  function dispatch(eventType: string, rawData: string) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(rawData);
    } catch {
      parsed = rawData;
    }

    subscribersRef.current.get(eventType)?.forEach((handler) => {
      try {
        handler(parsed);
      } catch {}
    });

    subscribersRef.current.get("*")?.forEach((handler) => {
      try {
        handler({ type: eventType, data: parsed });
      } catch {}
    });
  }

  useEffect(() => {
    mountedRef.current = true;

    if (!url) {
      return;
    }

    function doConnect() {
      if (!mountedRef.current || !url) return;

      const es = new EventSource(url);
      esRef.current = es;
      setStatus("connecting");

      es.onopen = () => {
        if (!mountedRef.current) return;
        setStatus("connected");
        backoffRef.current = INITIAL_BACKOFF_MS;
      };

      es.onerror = () => {
        if (!mountedRef.current) return;
        es.close();
        esRef.current = null;
        setStatus("disconnected");

        const delay = backoffRef.current;
        backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS);

        reconnectTimerRef.current = setTimeout(() => {
          reconnectTimerRef.current = null;
          doConnect();
        }, delay);
      };

      es.onmessage = (event) => {
        dispatch("message", event.data);
      };

      for (const eventType of KNOWN_EVENT_TYPES) {
        es.addEventListener(eventType, (event: MessageEvent) => {
          dispatch(eventType, event.data);
        });
      }
    }

    doConnect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
      setStatus("disconnected");
    };
  }, [url]);

  return { status, subscribe };
}
