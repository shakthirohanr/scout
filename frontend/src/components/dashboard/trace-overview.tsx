import { StatusBadge } from "@/components/dashboard/status-badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { TraceDetail, TraceSummary } from "@/lib/types";

type TraceOverviewProps = {
  trace: TraceSummary | null;
  detail: TraceDetail | null;
};

function formatDate(date: string | null): string {
  if (!date) {
    return "Not available";
  }

  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(date));
}

function StatRow({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3 border border-border/60 bg-background/50 px-5 py-4">
      <span className="text-base text-muted-foreground">{label}</span>
      <span className="text-base font-medium text-foreground">{value}</span>
    </div>
  );
}

export function TraceOverview({ trace, detail }: TraceOverviewProps) {
  if (!trace) {
    return (
      <Card className="rounded-none border-border/60 bg-card shadow-none">
        <CardContent className="p-6 text-base text-muted-foreground">
          Select a trace to inspect the run summary and token usage.
        </CardContent>
      </Card>
    );
  }

  return (
    <Tabs defaultValue="summary" className="rounded-none border border-border/60 bg-card p-6 md:p-7 shadow-none">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <CardTitle className="text-xl font-semibold text-foreground">Trace details</CardTitle>
        </div>
        <StatusBadge status={trace.status} />
      </div>

      <TabsList className="mb-5 grid w-full grid-cols-2 rounded-none">
        <TabsTrigger value="summary" className="rounded-none text-base">Summary</TabsTrigger>
        <TabsTrigger value="usage" className="rounded-none text-base">Usage</TabsTrigger>
      </TabsList>

      <TabsContent value="summary" className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <StatRow label="Challenge" value={trace.challengeName} />
          <StatRow label="Model" value={trace.modelName} />
          <StatRow label="Started" value={formatDate(trace.startedAt)} />
          <StatRow label="Updated" value={formatDate(trace.updatedAt)} />
          <StatRow label="Steps" value={trace.lastStep.toString()} />
          <StatRow label="Events" value={trace.eventCount.toString()} />
        </div>

        <div className="grid gap-3 md:grid-cols-3">
          <div className="border border-border/60 bg-[#e7eddc] p-5 dark:bg-background/40">
            <p className="text-base text-muted-foreground">Trace file</p>
            <p className="mt-2 text-base font-medium break-all text-foreground">
              {trace.fileName}
            </p>
          </div>
          <div className="border border-border/60 bg-[#e7eddc] p-5 dark:bg-background/40">
            <p className="text-base text-muted-foreground">Latest preview</p>
            <p className="mt-2 text-base leading-7 break-all text-foreground">
              {trace.preview}
            </p>
          </div>
          <div className="border border-border/60 bg-[#e7eddc] p-5 dark:bg-background/40">
            <p className="text-base text-muted-foreground">Flag</p>
            <p className="mt-2 text-base font-medium break-all text-foreground">
              {trace.flag ?? "No confirmed flag recorded"}
            </p>
          </div>
        </div>
      </TabsContent>

      <TabsContent value="usage" className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <StatRow label="Input tokens" value={trace.inputTokens.toLocaleString("en-US")} />
          <StatRow label="Output tokens" value={trace.outputTokens.toLocaleString("en-US")} />
          <StatRow
            label="Cached tokens"
            value={trace.cacheReadTokens.toLocaleString("en-US")}
          />
          <StatRow label="Estimated cost" value={`$${trace.costUsd.toFixed(2)}`} />
        </div>

        <div className="border border-border/60 bg-[#e7eddc] p-5 dark:bg-background/40">
          <CardHeader className="p-0">
            <CardTitle className="text-base font-medium text-foreground">Runtime health</CardTitle>
          </CardHeader>
          {detail ? (
            <p className="mt-2 text-base leading-7 text-muted-foreground">
              {detail.events.length} parsed events
            </p>
          ) : null}
        </div>
      </TabsContent>
    </Tabs>
  );
}
