import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { TraceStatus } from "@/lib/types";

const statusStyles: Record<
  TraceStatus,
  { label: string; className: string }
> = {
  running: {
    label: "Live",
    className:
      "border-sky-500/25 bg-sky-500/10 text-sky-700 dark:text-sky-300",
  },
  solved: {
    label: "Solved",
    className:
      "border-slate-400/30 bg-slate-400/12 text-slate-700 dark:text-slate-200",
  },
  gave_up: {
    label: "Gave Up",
    className:
      "border-amber-500/30 bg-amber-500/15 text-amber-700 dark:text-amber-300",
  },
  cancelled: {
    label: "Cancelled",
    className:
      "border-slate-400/30 bg-slate-400/10 text-slate-600 dark:text-slate-300",
  },
  error: {
    label: "Error",
    className:
      "border-rose-500/30 bg-rose-500/15 text-rose-700 dark:text-rose-300",
  },
  unknown: {
    label: "Unknown",
    className:
      "border-border/70 bg-muted/50 text-muted-foreground",
  },
};

type StatusBadgeProps = {
  status: TraceStatus;
  className?: string;
};

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const config = statusStyles[status];

  return (
    <Badge
      variant="outline"
      className={cn("gap-1.5 rounded-none px-2.5 py-1", config.className, className)}
    >
      {config.label}
    </Badge>
  );
}
