import { StatusBadge } from "@/components/dashboard/status-badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { TraceDetail, TraceSummary } from "@/lib/types";

type TraceOverviewProps = {
  trace: TraceSummary | null;
  detail: TraceDetail | null;
};

function formatDate(date: string | null): string {
  if (!date) return "N/A";
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(date));
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border border-border bg-background px-3 py-2">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-xs font-medium text-foreground">{value}</span>
    </div>
  );
}

export function TraceOverview({ trace, detail }: TraceOverviewProps) {
  if (!trace) {
    return (
      <Card>
        <CardContent className="p-4 text-sm text-muted-foreground">
          Select a trace to inspect the run summary and token usage.
        </CardContent>
      </Card>
    );
  }

  return (
    <Tabs
      defaultValue="summary"
      className="rounded-lg border border-border bg-card p-4"
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <CardTitle className="text-sm font-medium text-foreground">Trace details</CardTitle>
        <StatusBadge status={trace.status} />
      </div>

      <TabsList className="mb-3 grid w-full grid-cols-2">
        <TabsTrigger value="summary" className="text-sm">Summary</TabsTrigger>
        <TabsTrigger value="usage" className="text-sm">Usage</TabsTrigger>
      </TabsList>

      <TabsContent value="summary" className="space-y-2">
        <div className="grid gap-2 sm:grid-cols-2">
          <StatRow label="Challenge" value={trace.challengeName} />
          <StatRow label="Model" value={trace.modelName} />
          <StatRow label="Started" value={formatDate(trace.startedAt)} />
          <StatRow label="Updated" value={formatDate(trace.updatedAt)} />
          <StatRow label="Steps" value={trace.lastStep.toString()} />
          <StatRow label="Events" value={trace.eventCount.toString()} />
        </div>

        <div className="grid gap-2 md:grid-cols-3">
          <div className="border border-border bg-background p-3">
            <p className="text-xs text-muted-foreground">Trace file</p>
            <p className="mt-0.5 line-clamp-2 break-all text-xs font-medium text-foreground">
              {trace.fileName}
            </p>
          </div>
          <div className="border border-border bg-background p-3">
            <p className="text-xs text-muted-foreground">Latest preview</p>
            <p className="mt-0.5 line-clamp-3 break-all text-xs leading-5 text-foreground">
              {trace.preview}
            </p>
          </div>
          <div className="border border-border bg-background p-3">
            <p className="text-xs text-muted-foreground">Flag</p>
            <p className="mt-0.5 line-clamp-2 break-all text-xs font-medium text-foreground">
              {trace.flag ?? "No confirmed flag recorded"}
            </p>
          </div>
        </div>
      </TabsContent>

      <TabsContent value="usage" className="space-y-2">
        <div className="grid gap-2 sm:grid-cols-2">
          <StatRow label="Input tokens" value={trace.inputTokens.toLocaleString("en-US")} />
          <StatRow label="Output tokens" value={trace.outputTokens.toLocaleString("en-US")} />
          <StatRow
            label="Cached tokens"
            value={trace.cacheReadTokens.toLocaleString("en-US")}
          />
          <StatRow label="Estimated cost" value={`$${trace.costUsd.toFixed(2)}`} />
        </div>

        <div className="border border-border bg-background p-3">
          <CardHeader className="p-0">
            <CardTitle className="text-xs font-medium text-foreground">Runtime health</CardTitle>
          </CardHeader>
          {detail && (
            <p className="mt-1 text-xs text-muted-foreground">
              {detail.events.length} parsed events
            </p>
          )}
        </div>
      </TabsContent>
    </Tabs>
  );
}
