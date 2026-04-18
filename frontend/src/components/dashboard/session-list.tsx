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
  if (!updatedAt) return "Awaiting events";
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
    if (!normalizedQuery) return true;
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
        className="h-8 text-sm"
      />

      <ScrollArea className="mt-3 min-h-0 flex-1">
        <div className="space-y-1">
          {filteredTraces.map((trace) => {
            const isActive = selectedId === trace.id;

            return (
              <button
                key={trace.id}
                type="button"
                aria-pressed={isActive}
                onClick={() => onSelect(trace.id)}
                className={cn(
                  "group w-full rounded-md border p-3 text-left transition-colors",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
                  isActive
                    ? "border-primary/25 bg-accent"
                    : "border-border bg-background hover:bg-muted/30",
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="space-y-0.5 min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">
                      {trace.challengeName}
                    </p>
                    <p className="text-xs text-muted-foreground uppercase tracking-wide">
                      {trace.modelName}
                    </p>
                  </div>
                  <StatusBadge status={trace.status} className="shrink-0" />
                </div>

                <p className="mt-2 text-xs text-muted-foreground line-clamp-2">
                  {trace.preview}
                </p>

                <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
                  <span>{trace.eventCount} events</span>
                  <span>{formatUpdatedAt(trace.updatedAt)}</span>
                </div>
              </button>
            );
          })}

          {!filteredTraces.length && (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No traces match this filter.
            </p>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
