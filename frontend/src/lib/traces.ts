import type { TraceDetail, TraceSummary } from "@/lib/types";

const DEFAULT_BACKEND_URL = "http://127.0.0.1:8081";

export const BACKEND_CLIENT_URL =
  typeof window !== "undefined"
    ? (document.querySelector('meta[name="backend-url"]')?.getAttribute("content") ??
      process.env.NEXT_PUBLIC_BACKEND_URL?.trim() ??
      DEFAULT_BACKEND_URL)
    : DEFAULT_BACKEND_URL;

type BackendTraceSummary = {
  id: string;
  file_name: string;
  challenge_id: string;
  challenge_name: string;
  model_name: string;
  status: string;
  event_count: number;
  tool_calls: number;
  model_responses: number;
  last_step: number;
  preview: string;
  started_at: string | null;
  updated_at: string | null;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cost_usd: number;
  flag: string | null;
};

type BackendTraceListResponse = {
  traces: BackendTraceSummary[];
  available: boolean;
  generated_at: string;
};

type BackendTraceDetailResponse = {
  summary: BackendTraceSummary;
  events: Record<string, unknown>[];
  terminal_output: string;
};

function toTraceSummary(item: BackendTraceSummary): TraceSummary {
  return {
    id: item.id,
    fileName: item.file_name,
    challengeId: item.challenge_id,
    challengeName: item.challenge_name,
    modelName: item.model_name,
    status: item.status as TraceSummary["status"],
    eventCount: item.event_count,
    toolCalls: item.tool_calls,
    modelResponses: item.model_responses,
    lastStep: item.last_step,
    preview: item.preview,
    startedAt: item.started_at,
    updatedAt: item.updated_at,
    inputTokens: item.input_tokens,
    outputTokens: item.output_tokens,
    cacheReadTokens: item.cache_read_tokens,
    costUsd: item.cost_usd,
    flag: item.flag,
  };
}

async function clientFetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function getTraces(
  challengeId?: string,
): Promise<{ traces: TraceSummary[]; available: boolean; generatedAt: string }> {
  const params = challengeId ? `?challenge_id=${encodeURIComponent(challengeId)}` : "";
  const payload = await clientFetchJson<BackendTraceListResponse>(
    `${BACKEND_CLIENT_URL}/api/v1/traces${params}`,
  );
  return {
    traces: payload.traces.map(toTraceSummary),
    available: payload.available,
    generatedAt: payload.generated_at,
  };
}

export async function getTraceDetail(
  traceId: string,
  limit = 450,
): Promise<TraceDetail> {
  const payload = await clientFetchJson<BackendTraceDetailResponse>(
    `${BACKEND_CLIENT_URL}/api/v1/traces/${encodeURIComponent(traceId)}?limit=${limit}`,
  );
  return {
    summary: toTraceSummary(payload.summary),
    events: payload.events as TraceDetail["events"],
    terminalOutput: payload.terminal_output,
  };
}
