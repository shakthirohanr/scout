"use client";

import { useEffect, useState } from "react";
import { RefreshCw, Square } from "lucide-react";
import { useRouter } from "next/navigation";

import { LogTerminal } from "@/components/dashboard/log-terminal";
import { SessionList } from "@/components/dashboard/session-list";
import { SteeringPanel } from "@/components/dashboard/steering-panel";
import { StatusBadge } from "@/components/dashboard/status-badge";
import { TraceOverview } from "@/components/dashboard/trace-overview";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { useLogDashboard } from "@/hooks/use-log-dashboard";
import type { ChallengeCatalogItem, TraceSummary } from "@/lib/types";

type DashboardShellProps = {
  initialTraces: TraceSummary[];
  catalogChallenges?: ChallengeCatalogItem[];
  activeChallengeId?: string | null;
  activeChallengeName?: string | null;
};

function formatLastSync(date: string | null): string {
  if (!date) return "Waiting for trace refresh";
  return new Intl.DateTimeFormat("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(date));
}

export function DashboardShell({
  initialTraces,
  catalogChallenges = [],
  activeChallengeId = null,
  activeChallengeName = null,
}: DashboardShellProps) {
  const router = useRouter();
  const [killPending, setKillPending] = useState(false);
  const [killError, setKillError] = useState<string | null>(null);
  const {
    activeChallenge,
    filteredTraces,
    selectedId,
    setSelectedId,
    selectedTrace,
    detail,
    error,
    lastSyncedAt,
    refreshNow,
  } = useLogDashboard(
    initialTraces,
    activeChallengeId,
    activeChallengeName,
    catalogChallenges,
  );

  async function handleKillAgent() {
    if (!activeChallengeId || killPending) return;

    setKillPending(true);
    setKillError(null);
    try {
      const response = await fetch(`/api/challenges/${encodeURIComponent(activeChallengeId)}/kill`, {
        method: "POST",
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { error?: string } | null;
        throw new Error(payload?.error || `Failed to kill agent: ${response.status}`);
      }

      await refreshNow();
      router.push("/");
      router.refresh();
    } catch (caughtError) {
      setKillError(
        caughtError instanceof Error
          ? caughtError.message
          : "Failed to kill challenge agent.",
      );
    } finally {
      setKillPending(false);
    }
  }

  const hasRunningTrace = filteredTraces.some((trace) => trace.status === "running");
  const hasTerminalTrace = filteredTraces.some((trace) =>
    ["solved", "gave_up", "cancelled", "finished", "failed", "error"].includes(trace.status)
  );
  const isAgentRunning =
    hasRunningTrace ||
    ((activeChallenge?.state === "starting" || activeChallenge?.state === "running") &&
      !hasTerminalTrace);

  useEffect(() => {
    const challengeTitle = activeChallenge?.name ?? activeChallengeName;
    document.title = challengeTitle || "CryptoAgent";
  }, [activeChallenge?.name, activeChallengeName]);

  return (
    <div className="flex h-full flex-col overflow-hidden bg-background p-4 sm:p-6">
      <div className="grid h-full min-h-0 gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <div className="flex min-h-0 flex-col">
          {filteredTraces.length ? (
            <LogTerminal
              summary={selectedTrace}
              content={detail?.terminalOutput ?? ""}
              onRefresh={refreshNow}
              className="h-full min-h-0"
            />
          ) : (
            <Card className="h-full border-dashed">
              <CardContent className="flex h-full items-center justify-center p-8">
                <p className="text-sm text-muted-foreground">No active session selected</p>
              </CardContent>
            </Card>
          )}
        </div>

        <div className="flex min-h-0 flex-col gap-3 overflow-hidden">
          <Card>
            <CardHeader className="space-y-3">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div className="space-y-1">
                  <p className="text-xs text-muted-foreground">
                    Challenge workspace
                  </p>
                  <CardTitle className="text-base font-semibold text-foreground">
                    {selectedTrace
                      ? `${selectedTrace.challengeName} on ${selectedTrace.modelName}`
                      : activeChallenge?.name ?? activeChallengeName ?? "Challenge dashboard"}
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Inspect trace output, steer the agent, and manage active sessions.
                  </CardDescription>
                </div>

                <div className="flex flex-col items-stretch gap-2 sm:flex-row sm:items-center lg:justify-end">
                  {selectedTrace && <StatusBadge status={selectedTrace.status} className="shrink-0" />}

                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="gap-1.5"
                      onClick={refreshNow}
                    >
                      <RefreshCw className="size-3.5" />
                      Sync
                    </Button>

                    {activeChallengeId && isAgentRunning && (
                      <Button
                        type="button"
                        variant="destructive"
                        size="sm"
                        onClick={handleKillAgent}
                        disabled={killPending}
                        className="gap-1.5"
                      >
                        <Square className="size-3.5 fill-current" />
                        {killPending ? "Killing..." : "Kill Agent"}
                      </Button>
                    )}
                  </div>
                </div>
              </div>

              <div className="grid gap-2 lg:grid-cols-2">
                <div className="rounded-md border border-border bg-background px-3 py-2">
                  <span className="block text-xs text-muted-foreground">Active file</span>
                  <span className="mt-0.5 block text-sm font-medium text-foreground">
                    {selectedTrace?.fileName ?? "No file selected"}
                  </span>
                </div>
                <div className="rounded-md border border-border bg-background px-3 py-2">
                  <span className="block text-xs text-muted-foreground">Refresh state</span>
                  <span className="mt-0.5 block text-sm font-medium text-foreground">
                    {formatLastSync(lastSyncedAt)}
                  </span>
                </div>
              </div>
            </CardHeader>
            {error || killError ? (
              <CardContent className="pt-0">
                <Separator className="mb-3" />
                <p className="text-sm text-destructive">{killError ?? error}</p>
              </CardContent>
            ) : null}
          </Card>

          {activeChallengeId && <SteeringPanel challengeId={activeChallengeId} />}

          {filteredTraces.length > 1 && (
            <Card className="min-h-0 max-h-[22rem]">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Session Traces</CardTitle>
                <CardDescription className="text-xs">
                  Switch between challenge runs.
                </CardDescription>
              </CardHeader>
              <CardContent className="min-h-0 flex-1 pt-0">
                <SessionList
                  traces={filteredTraces}
                  selectedId={selectedId}
                  onSelect={(traceId) => setSelectedId(traceId)}
                  className="h-full"
                />
              </CardContent>
            </Card>
          )}

          <div className="min-h-0 flex-1 overflow-auto">
            <TraceOverview trace={selectedTrace} detail={detail} />
          </div>
        </div>
      </div>
    </div>
  );
}
