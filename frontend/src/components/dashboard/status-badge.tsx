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
      "bg-sky-500/10 text-sky-700 border-sky-500/20 dark:text-sky-400",
  },
  solved: {
    label: "Solved",
    className:
      "bg-emerald-600/10 text-emerald-700 border-emerald-600/20 dark:text-emerald-400",
  },
  gave_up: {
    label: "Gave Up",
    className:
      "bg-amber-500/10 text-amber-700 border-amber-500/20 dark:text-amber-400",
  },
  cancelled: {
    label: "Cancelled",
    className:
      "bg-muted text-muted-foreground border-border",
  },
  failed: {
    label: "Failed",
    className:
      "bg-destructive/10 text-destructive border-destructive/20",
  },
  finished: {
    label: "Finished",
    className:
      "bg-muted text-muted-foreground border-border",
  },
  error: {
    label: "Error",
    className:
      "bg-destructive/10 text-destructive border-destructive/20",
  },
  unknown: {
    label: "Unknown",
    className:
      "bg-muted text-muted-foreground border-border",
  },
};

type StatusBadgeProps = {
  status: TraceStatus;
  className?: string;
};

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const config = statusStyles[status] ?? statusStyles.unknown;

  return (
    <Badge
      variant="outline"
      className={cn("px-2 py-0.5", config.className, className)}
    >
      {config.label}
    </Badge>
  );
}
