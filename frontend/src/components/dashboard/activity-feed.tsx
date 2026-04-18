import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import type { TraceEvent } from "@/lib/types";

type ActivityFeedProps = {
  events: TraceEvent[];
};

type ActivityDetails = {
  label: string;
  detail: string;
};

function describeEvent(event: TraceEvent): ActivityDetails {
  if (event.type === "tool_call") {
    return {
      label: `${event.tool ?? "Tool"} call`,
      detail: String(event.args ?? "").slice(0, 120) || "No arguments recorded.",
    };
  }

  if (event.type === "model_response") {
    return {
      label: "Model response",
      detail: String(event.text ?? "").slice(0, 140) || "No model text recorded.",
    };
  }

  if (event.type === "flag_confirmed" || (event.type === "finish" && event.flag)) {
    return {
      label: "Flag confirmation",
      detail: String(event.flag ?? "Flag recorded."),
    };
  }

  return {
    label: event.type.replace(/_/g, " "),
    detail: JSON.stringify(event).slice(0, 140),
  };
}

function formatEventTime(ts: number | undefined): string {
  if (!ts) return "--:--:--";
  return new Intl.DateTimeFormat("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(ts * 1000));
}

export function ActivityFeed({ events }: ActivityFeedProps) {
  const recentEvents = [...events].reverse().slice(0, 12);

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <h2 className="mb-4 text-sm font-medium text-foreground">Recent activity</h2>

      <ScrollArea className="h-80">
        <div className="space-y-3">
          {recentEvents.map((event, index) => {
            const details = describeEvent(event);

            return (
              <div key={`${event.ts}-${event.type}-${index}`} className="space-y-3">
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-medium capitalize text-foreground">
                      {details.label}
                    </p>
                    <span className="text-xs text-muted-foreground">
                      {formatEventTime(event.ts)}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {details.detail}
                  </p>
                </div>
                {index < recentEvents.length - 1 && <Separator />}
              </div>
            );
          })}

          {!recentEvents.length && (
            <p className="py-8 text-center text-sm text-muted-foreground">
              Start a solver run to populate the activity feed.
            </p>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
