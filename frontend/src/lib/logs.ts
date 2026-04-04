import { promises as fs } from "fs";
import { unstable_cache } from "next/cache";
import path from "path";

import { formatTraceForTerminal } from "@/lib/terminal";
import type { TraceDetail, TraceEvent, TraceStatus, TraceSummary } from "@/lib/types";

const REPO_ROOT = path.resolve(process.cwd(), "..");
const LOGS_DIRECTORY = path.resolve(REPO_ROOT, "logs");
const TRACE_SUMMARIES_TAG = "trace-summaries";

function isSafeTraceId(traceId: string): boolean {
  return /^[a-zA-Z0-9._-]+\.jsonl$/.test(traceId);
}

function parseEventLine(line: string): TraceEvent | null {
  try {
    return JSON.parse(line) as TraceEvent;
  } catch {
    return null;
  }
}

function buildPreview(event: TraceEvent | undefined): string {
  if (!event) {
    return "No events recorded yet.";
  }

  if (event.type === "tool_call") {
    return `${event.tool ?? "tool"} ${String(event.args ?? "").slice(0, 70)}`.trim();
  }

  if (event.type === "tool_result") {
    return String(event.result ?? "").replace(/\s+/g, " ").slice(0, 90) || "Tool result recorded.";
  }

  if (event.type === "model_response") {
    return String(event.text ?? "").replace(/\s+/g, " ").slice(0, 90) || "Model response recorded.";
  }

  if (event.type === "finish" && event.flag) {
    return `Flag candidate: ${event.flag}`;
  }

  if (event.type === "error") {
    return String(event.error ?? "Solver error");
  }

  return `${event.type} event`;
}

function inferStatus(events: TraceEvent[]): TraceStatus {
  const finish = [...events].reverse().find((event) => event.type === "finish");
  if (finish?.status === "flag_found") {
    return "solved";
  }
  if (finish?.status === "gave_up") {
    return "gave_up";
  }
  if (finish?.status === "cancelled") {
    return "cancelled";
  }
  if (finish?.status === "error") {
    return "error";
  }
  if (events.some((event) => event.type === "error")) {
    return "error";
  }
  return events.length > 0 ? "running" : "unknown";
}

function filenameFallback(fileName: string): { challengeName: string; modelName: string } {
  const bare = fileName.replace(/^trace-/, "").replace(/-\d{8}-\d{6}\.jsonl$/, "");
  return {
    challengeName: bare || "Unknown challenge",
    modelName: "agent",
  };
}

function summarizeTrace(
  fileName: string,
  events: TraceEvent[],
): TraceSummary {
  const startEvent = events.find((event) => event.type === "start");
  const usageEvents = events.filter((event) => event.type === "usage");
  const latestUsage = usageEvents.at(-1);
  const lastEvent = events.at(-1);
  const fallback = filenameFallback(fileName);
  const challengeName = String(startEvent?.challenge ?? fallback.challengeName);
  const modelName = String(startEvent?.model ?? fallback.modelName);
  const lastStep = events.reduce((max, event) => {
    return typeof event.step === "number" ? Math.max(max, event.step) : max;
  }, 0);
  const finishEvent = [...events].reverse().find((event) => event.type === "finish");

  return {
    id: fileName,
    fileName,
    challengeId: challengeName,
    challengeName,
    modelName,
    status: inferStatus(events),
    eventCount: events.length,
    toolCalls: events.filter((event) => event.type === "tool_call").length,
    modelResponses: events.filter((event) => event.type === "model_response").length,
    lastStep,
    preview: buildPreview(lastEvent),
    startedAt: startEvent?.ts ? new Date(startEvent.ts * 1000).toISOString() : null,
    updatedAt: lastEvent?.ts ? new Date(lastEvent.ts * 1000).toISOString() : null,
    inputTokens: Number(latestUsage?.input_tokens ?? 0),
    outputTokens: Number(latestUsage?.output_tokens ?? 0),
    cacheReadTokens: Number(latestUsage?.cache_read_tokens ?? 0),
    costUsd: Number(latestUsage?.cost_usd ?? finishEvent?.cost_usd ?? 0),
    flag: finishEvent?.flag ? String(finishEvent.flag) : null,
  };
}

async function readTraceFile(fileName: string): Promise<string | null> {
  if (!isSafeTraceId(fileName)) {
    return null;
  }

  const fullPath = path.resolve(LOGS_DIRECTORY, fileName);
  if (!fullPath.startsWith(LOGS_DIRECTORY)) {
    return null;
  }

  try {
    return await fs.readFile(fullPath, "utf8");
  } catch {
    return null;
  }
}

function parseEvents(text: string): TraceEvent[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map(parseEventLine)
    .filter((event): event is TraceEvent => Boolean(event));
}

export function getLogsDirectory(): string {
  return LOGS_DIRECTORY;
}

export async function hasLogsDirectory(): Promise<boolean> {
  try {
    const stat = await fs.stat(LOGS_DIRECTORY);
    return stat.isDirectory();
  } catch {
    return false;
  }
}

export async function getTraceSummaries(): Promise<TraceSummary[]> {
  return getCachedTraceSummaries();
}

const getCachedTraceSummaries = unstable_cache(
  async (): Promise<TraceSummary[]> => {
  if (!(await hasLogsDirectory())) {
    return [];
  }

  const dirents = await fs.readdir(LOGS_DIRECTORY, { withFileTypes: true });
  const files = dirents
    .filter((dirent) => dirent.isFile() && dirent.name.endsWith(".jsonl"))
    .map((dirent) => dirent.name);

  const summaries = await Promise.all(
    files.map(async (fileName) => {
      const text = await readTraceFile(fileName);
      if (!text) {
        return null;
      }

      return summarizeTrace(fileName, parseEvents(text));
    }),
  );

  return summaries
    .filter((summary): summary is TraceSummary => Boolean(summary))
    .sort((left, right) => {
      return (Date.parse(right.updatedAt ?? "") || 0) - (Date.parse(left.updatedAt ?? "") || 0);
    });
  },
  ["trace-summaries"],
  { revalidate: 2, tags: [TRACE_SUMMARIES_TAG] },
);

export async function getTraceDetail(
  traceId: string,
  limit = 400,
): Promise<TraceDetail | null> {
  const text = await readTraceFile(traceId);
  if (!text) {
    return null;
  }

  const allEvents = parseEvents(text);
  const summary = summarizeTrace(traceId, allEvents);
  const visibleEvents = allEvents.slice(Math.max(0, allEvents.length - limit));

  return {
    summary,
    events: visibleEvents,
    terminalOutput: formatTraceForTerminal(summary, visibleEvents),
  };
}
