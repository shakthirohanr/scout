"""Helpers for reading solver trace files for HTTP APIs."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


TRACE_ID_RE = re.compile(r"^[A-Za-z0-9._-]+\.jsonl$")
REPO_ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = REPO_ROOT / "logs"


@dataclass(slots=True)
class TraceSummary:
    id: str
    file_name: str
    challenge_name: str
    model_name: str
    status: str
    event_count: int
    tool_calls: int
    model_responses: int
    last_step: int
    preview: str
    started_at: str | None
    updated_at: str | None
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cost_usd: float
    flag: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TraceDetail:
    summary: TraceSummary
    events: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary.to_dict(),
            "events": self.events,
            "terminal_output": format_trace_for_terminal(self.summary, self.events),
        }


def logs_directory() -> Path:
    return LOGS_DIR


def has_logs_directory() -> bool:
    return LOGS_DIR.is_dir()


def _safe_trace_path(trace_id: str) -> Path | None:
    if not TRACE_ID_RE.fullmatch(trace_id):
        return None
    path = (LOGS_DIR / trace_id).resolve()
    if path.parent != LOGS_DIR.resolve():
        return None
    return path


def _parse_event_line(line: str) -> dict[str, Any] | None:
    try:
        return json.loads(line)
    except Exception:
        return None


def _parse_events(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        event = _parse_event_line(line)
        if event:
            events.append(event)
    return events


def _filename_fallback(file_name: str) -> tuple[str, str]:
    bare = re.sub(r"-\d{8}-\d{6}\.jsonl$", "", file_name.replace("trace-", "", 1))
    return (bare or "Unknown challenge", "agent")


def _build_preview(event: dict[str, Any] | None) -> str:
    if not event:
        return "No events recorded yet."
    if event.get("type") == "tool_call":
        return f"{event.get('tool', 'tool')} {str(event.get('args', ''))[:70]}".strip()
    if event.get("type") == "tool_result":
        return re.sub(r"\s+", " ", str(event.get("result", "")))[:90] or "Tool result recorded."
    if event.get("type") == "model_response":
        return re.sub(r"\s+", " ", str(event.get("text", "")))[:90] or "Model response recorded."
    if event.get("type") == "finish" and event.get("flag"):
        return f"Flag candidate: {event['flag']}"
    if event.get("type") == "error":
        return str(event.get("error", "Solver error"))
    return f"{event.get('type', 'unknown')} event"


def _infer_status(events: list[dict[str, Any]]) -> str:
    finish = next((event for event in reversed(events) if event.get("type") == "finish"), None)
    if finish:
        status = str(finish.get("status", "unknown"))
        if status == "flag_found":
            return "solved"
        if status in {"gave_up", "cancelled", "error"}:
            return status
    if any(event.get("type") == "error" for event in events):
        return "error"
    return "running" if events else "unknown"


def summarize_trace(file_name: str, events: list[dict[str, Any]]) -> TraceSummary:
    start_event = next((event for event in events if event.get("type") == "start"), None)
    usage_events = [event for event in events if event.get("type") == "usage"]
    latest_usage = usage_events[-1] if usage_events else {}
    last_event = events[-1] if events else None
    finish_event = next((event for event in reversed(events) if event.get("type") == "finish"), None)
    fallback_name, fallback_model = _filename_fallback(file_name)
    last_step = max(
        int(event.get("step", 0))
        for event in events
        if isinstance(event.get("step", 0), int | float)
    ) if events else 0

    return TraceSummary(
        id=file_name,
        file_name=file_name,
        challenge_name=str(start_event.get("challenge", fallback_name) if start_event else fallback_name),
        model_name=str(start_event.get("model", fallback_model) if start_event else fallback_model),
        status=_infer_status(events),
        event_count=len(events),
        tool_calls=sum(1 for event in events if event.get("type") == "tool_call"),
        model_responses=sum(1 for event in events if event.get("type") == "model_response"),
        last_step=last_step,
        preview=_build_preview(last_event),
        started_at=_event_time_iso(start_event),
        updated_at=_event_time_iso(last_event),
        input_tokens=int(latest_usage.get("input_tokens", 0) or 0),
        output_tokens=int(latest_usage.get("output_tokens", 0) or 0),
        cache_read_tokens=int(latest_usage.get("cache_read_tokens", 0) or 0),
        cost_usd=float(latest_usage.get("cost_usd", finish_event.get("cost_usd", 0.0) if finish_event else 0.0) or 0.0),
        flag=str(finish_event["flag"]) if finish_event and finish_event.get("flag") else None,
    )


def _event_time_iso(event: dict[str, Any] | None) -> str | None:
    if not event:
        return None
    ts = event.get("ts")
    if not isinstance(ts, int | float):
        return None
    return __import__("datetime").datetime.fromtimestamp(ts, tz=__import__("datetime").timezone.utc).isoformat()


def list_trace_summaries() -> list[TraceSummary]:
    if not has_logs_directory():
        return []

    summaries: list[TraceSummary] = []
    for path in LOGS_DIR.iterdir():
        if not path.is_file() or path.suffix != ".jsonl":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        summaries.append(summarize_trace(path.name, _parse_events(text)))

    return sorted(
        summaries,
        key=lambda summary: summary.updated_at or "",
        reverse=True,
    )


def get_trace_detail(trace_id: str, limit: int = 400) -> TraceDetail | None:
    path = _safe_trace_path(trace_id)
    if not path or not path.exists():
        return None

    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None

    events = _parse_events(text)
    visible_events = events[-max(limit, 1):]
    return TraceDetail(
        summary=summarize_trace(path.name, events),
        events=visible_events,
    )


def format_trace_for_terminal(summary: TraceSummary, events: list[dict[str, Any]]) -> str:
    reset = "\x1b[0m"
    dim = "\x1b[2m"
    bold = "\x1b[1m"
    green = "\x1b[32m"
    bright_green = "\x1b[92m"
    cyan = "\x1b[36m"
    blue = "\x1b[34m"
    yellow = "\x1b[33m"
    red = "\x1b[31m"
    magenta = "\x1b[35m"
    gray = "\x1b[90m"

    def _time_label(ts: Any) -> str:
        if not isinstance(ts, int | float):
            return "--:--:--"
        dt = __import__("datetime").datetime.fromtimestamp(ts)
        return dt.strftime("%H:%M:%S")

    def _single_line(value: Any, max_len: int = 180) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if len(text) <= max_len:
            return text
        return text[: max_len - 1] + "…"

    lines = [
        f"{bold}{bright_green}CTF Agent Trace{reset} {dim}{summary.challenge_name} / {summary.model_name}{reset}",
        (
            f"{dim}file={summary.file_name} status={summary.status} events={summary.event_count} "
            f"tool_calls={summary.tool_calls} model_responses={summary.model_responses}{reset}"
        ),
        f"{gray}{'-' * 96}{reset}",
    ]

    for event in events:
        stamp = f"{dim}[{_time_label(event.get('ts'))}]{reset}"
        kind = event.get("type")
        if kind == "start":
            lines.append(f"{stamp} {bold}{bright_green}BOOT{reset} challenge={event.get('challenge')} model={event.get('model')}")
        elif kind == "tool_call":
            lines.append(f"{stamp} {green}CALL{reset} step={event.get('step', '?')} {event.get('tool', 'tool')} {_single_line(event.get('args'))}")
        elif kind == "tool_result":
            lines.append(f"{stamp} {cyan}OUT {reset} step={event.get('step', '?')} {event.get('tool', 'tool')} {_single_line(event.get('result'), 220)}")
        elif kind == "model_response":
            lines.append(f"{stamp} {magenta}THINK{reset} step={event.get('step', '?')} {_single_line(event.get('text'), 220)}")
        elif kind == "usage":
            lines.append(
                f"{stamp} {yellow}TOKENS{reset} in={int(event.get('input_tokens', 0) or 0)} "
                f"out={int(event.get('output_tokens', 0) or 0)} "
                f"cached={int(event.get('cache_read_tokens', 0) or 0)} "
                f"cost=${float(event.get('cost_usd', 0) or 0):.4f}"
            )
        elif kind == "bump":
            lines.append(f"{stamp} {blue}BUMP{reset} {_single_line(event.get('insights'), 220)}")
        elif kind == "flag_confirmed":
            lines.append(f"{stamp} {bold}{bright_green}FLAG{reset} {event.get('flag', 'confirmed')}")
        elif kind in {"error", "turn_failed"}:
            lines.append(f"{stamp} {bold}{red}ERR {reset} {_single_line(event.get('error') or event.get('message'), 220)}")
        elif kind == "finish":
            color = bright_green if event.get("status") == "flag_found" else red if event.get("status") == "error" else yellow
            flag_suffix = f" flag={event['flag']}" if event.get("flag") else ""
            lines.append(f"{stamp} {bold}{color}DONE{reset} status={event.get('status', 'unknown')}{flag_suffix}")
        else:
            lines.append(f"{stamp} {gray}{str(kind or 'event').upper():<5}{reset} {_single_line(event, 220)}")

    return "\n".join(lines) + "\n"
