import type { TraceEvent, TraceSummary } from "@/lib/types";

const RESET = "\u001b[0m";
const DIM = "\u001b[2m";
const BOLD = "\u001b[1m";
const BRIGHT = "\u001b[97m";
const CYAN = "\u001b[36m";
const BLUE = "\u001b[34m";
const YELLOW = "\u001b[33m";
const RED = "\u001b[31m";
const MAGENTA = "\u001b[35m";
const GRAY = "\u001b[90m";

export const terminalThemes = {
  dark: {
    background: "#111214",
    foreground: "#e6e7ea",
    cursor: "#c4c7cf",
    cursorAccent: "#111214",
    selectionBackground: "#3f434b99",
    black: "#111214",
    red: "#ff7782",
    green: "#c4c7cf",
    yellow: "#d6cf6d",
    blue: "#9eb6ff",
    magenta: "#e48fff",
    cyan: "#95c6d8",
    white: "#f4f4f5",
    brightBlack: "#5d6169",
    brightRed: "#ff9aa8",
    brightGreen: "#e5e7eb",
    brightYellow: "#f1e78a",
    brightBlue: "#c0d2ff",
    brightMagenta: "#efb5ff",
    brightCyan: "#c9e6ef",
    brightWhite: "#ffffff",
  },
  light: {
    background: "#f4f4f5",
    foreground: "#1f2328",
    cursor: "#4b5563",
    cursorAccent: "#f4f4f5",
    selectionBackground: "#cdd2d970",
    black: "#f4f4f5",
    red: "#c2334a",
    green: "#4b5563",
    yellow: "#877317",
    blue: "#3b5fb8",
    magenta: "#8e3bb4",
    cyan: "#37687f",
    white: "#1f2328",
    brightBlack: "#71717a",
    brightRed: "#eb5d71",
    brightGreen: "#111827",
    brightYellow: "#b99917",
    brightBlue: "#5b7be0",
    brightMagenta: "#b55fe0",
    brightCyan: "#5591a4",
    brightWhite: "#08160f",
  },
} as const;

function formatTime(ts: number | undefined): string {
  if (!ts) {
    return "--:--:--";
  }

  return new Intl.DateTimeFormat("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(ts * 1000));
}

function toSingleLine(value: unknown, max = 140): string {
  const text = String(value ?? "")
    .replace(/\s+/g, " ")
    .trim();

  if (!text) {
    return "";
  }

  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function header(summary: TraceSummary): string {
  const started = summary.startedAt
    ? new Intl.DateTimeFormat("en-US", {
        dateStyle: "medium",
        timeStyle: "medium",
      }).format(new Date(summary.startedAt))
    : "unknown";

  return [
    `${BOLD}${BRIGHT}CTF Agent Trace${RESET} ${DIM}${summary.challengeName} / ${summary.modelName}${RESET}`,
    `${DIM}file=${summary.fileName} status=${summary.status} events=${summary.eventCount} tool_calls=${summary.toolCalls} model_responses=${summary.modelResponses} started=${started}${RESET}`,
    `${GRAY}${"-".repeat(96)}${RESET}`,
  ].join("\n");
}

function formatEventLine(event: TraceEvent): string {
  const stamp = `${DIM}[${formatTime(event.ts)}]${RESET}`;

  switch (event.type) {
    case "start":
      return `${stamp} ${BOLD}${BRIGHT}BOOT${RESET} challenge=${event.challenge ?? "unknown"} model=${event.model ?? "unknown"}`;
    case "tool_call":
      return `${stamp} ${BLUE}CALL${RESET} step=${event.step ?? "?"} ${event.tool ?? "tool"} ${toSingleLine(event.args, 180)}`;
    case "tool_result":
      return `${stamp} ${CYAN}OUT ${RESET} step=${event.step ?? "?"} ${event.tool ?? "tool"} ${toSingleLine(event.result, 220)}`;
    case "model_response":
      return `${stamp} ${MAGENTA}THINK${RESET} step=${event.step ?? "?"} ${toSingleLine(event.text, 220)}`;
    case "usage":
      return `${stamp} ${YELLOW}TOKENS${RESET} in=${event.input_tokens ?? 0} out=${event.output_tokens ?? 0} cached=${event.cache_read_tokens ?? 0} cost=$${Number(event.cost_usd ?? 0).toFixed(4)}`;
    case "bump":
      return `${stamp} ${BLUE}BUMP${RESET} ${toSingleLine(event.insights, 220)}`;
    case "flag_confirmed":
      return `${stamp} ${BOLD}${BRIGHT}FLAG${RESET} ${event.flag ?? "confirmed"}`;
    case "loop_break":
      return `${stamp} ${YELLOW}LOOP${RESET} forced break on ${event.tool ?? "tool"}`;
    case "error":
    case "turn_failed":
      return `${stamp} ${BOLD}${RED}ERR ${RESET} ${toSingleLine(event.error ?? event.message, 220)}`;
    case "finish": {
      const status = String(event.status ?? "unknown");
      const color =
        status === "flag_found"
          ? `${BOLD}${CYAN}`
          : status === "error"
            ? `${BOLD}${RED}`
            : `${BOLD}${YELLOW}`;
      const flagSuffix = event.flag ? ` flag=${event.flag}` : "";
      return `${stamp} ${color}DONE${RESET} status=${status}${flagSuffix}`;
    }
    default:
      return `${stamp} ${GRAY}${String(event.type).toUpperCase().padEnd(5, " ")}${RESET} ${toSingleLine(JSON.stringify(event), 220)}`;
  }
}

export function formatTraceForTerminal(
  summary: TraceSummary,
  events: TraceEvent[],
): string {
  const lines = [header(summary), ...events.map(formatEventLine)];
  return `${lines.join("\n")}\n`;
}
