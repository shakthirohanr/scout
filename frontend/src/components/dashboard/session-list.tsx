"use client";

import { useDeferredValue, useState } from "react";

import { StatusBadge } from "@/components/dashboard/status-badge";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { TraceSummary } from "@/lib/types";

type SessionListProps = {
  traces: TraceSummary[];
  selectedId: string | null;
  onSelect: (traceId: string) => void;
  className?: string;
};

function formatUpdatedAt(updatedAt: string | null): string {
  if (!updatedAt) {
    return "Awaiting events";
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(updatedAt));
}

export function SessionList({
  traces,
  selectedId,
  onSelect,
  className,
}: SessionListProps) {
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const normalizedQuery = deferredQuery.trim().toLowerCase();
  const filteredTraces = traces.filter((trace) => {
    if (!normalizedQuery) {
      return true;
    }

    return (
      trace.challengeName.toLowerCase().includes(normalizedQuery) ||
      trace.modelName.toLowerCase().includes(normalizedQuery) ||
      trace.fileName.toLowerCase().includes(normalizedQuery)
    );
  });

  return (
    <div className={cn("flex min-h-0 flex-col", className)}>
      <Input
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Filter traces"
        aria-label="Filter traces"
      />

      <ScrollArea className="mt-4 min-h-0 flex-1 pr-3">
        <div className="space-y-3">
          {filteredTraces.map((trace) => {
            const isActive = selectedId === trace.id;

            return (
              <button
                key={trace.id}
                type="button"
                aria-pressed={isActive}
                onClick={() => onSelect(trace.id)}
                className={cn(
                  "group w-full border p-4 text-left transition-all",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70",
                  isActive
                    ? "border-primary/35 bg-[#dfe7d2]"
                    : "border-border/60 bg-[#eef3e6] hover:border-primary/25 hover:bg-[#e7eddc] dark:bg-card/70 dark:hover:bg-card",
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1">
                    <p className="text-sm font-semibold leading-tight text-foreground">
                      {trace.challengeName}
                    </p>
                    <p className="text-xs uppercase tracking-[0.22em] text-muted-foreground">
                      {trace.modelName}
                    </p>
                  </div>
                  <StatusBadge status={trace.status} className="shrink-0" />
                </div>

                <p className="mt-3 text-sm leading-6 text-muted-foreground">
                  {trace.preview}
                </p>

                <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
                  <span>{trace.eventCount} events</span>
                  <span>{formatUpdatedAt(trace.updatedAt)}</span>
                </div>
              </button>
            );
          })}

          {!filteredTraces.length ? (
            <div className="border border-dashed border-border/70 bg-card/60 px-4 py-8 text-center text-sm text-muted-foreground">
              No traces match this filter yet.
            </div>
          ) : null}
        </div>
      </ScrollArea>
    </div>
  );
}
