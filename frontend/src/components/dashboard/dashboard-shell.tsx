"use client";

import { useEffect, useState } from "react";
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
  if (!date) {
    return "Waiting for trace refresh";
  }

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
    if (!activeChallengeId || killPending) {
      return;
    }

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
    if (!challengeTitle) {
      document.title = "CryptoAgent";
      return;
    }

    document.title = challengeTitle;
  }, [activeChallenge?.name, activeChallengeName]);

  return (
    <div className="page-shell overflow-hidden **:rounded-none">
      <main className="min-h-0 flex-1 overflow-hidden pr-1 pb-6">
        <div className="grid h-full min-h-0 gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)] xl:items-stretch">
          <div className="flex min-h-0 flex-col">
            {filteredTraces.length ? (
              <LogTerminal
                summary={selectedTrace}
                content={detail?.terminalOutput ?? ""}
                onRefresh={refreshNow}
                className="h-full min-h-0"
              />
            ) : (
              <Card className="rounded-none border-dashed border-border/70 bg-card shadow-none">
                <CardContent className="p-12 text-center">
                  <h2 className="text-xl font-semibold text-foreground">
                    No active session selected
                  </h2>
                </CardContent>
              </Card>
            )}
          </div>

          <div className="flex min-h-0 flex-col gap-3 overflow-hidden">
            <Card className="rounded-none border-border/60 bg-[#f0f4e6] shadow-none dark:bg-card">
              <CardHeader className="px-4 py-4">
                <div className="flex flex-col gap-4">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div className="space-y-1.5">
                      <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                        Challenge workspace
                      </p>
                      <CardTitle className="text-lg font-semibold text-foreground sm:text-xl">
                        {selectedTrace
                          ? `${selectedTrace.challengeName} on ${selectedTrace.modelName}`
                          : activeChallenge?.name ?? activeChallengeName ?? "Challenge dashboard"}
                      </CardTitle>
                      <CardDescription className="text-xs text-muted-foreground sm:text-sm">
                        Inspect trace output, steer the agent, and manage active sessions.
                      </CardDescription>
                    </div>

                    {selectedTrace ? (
                      <StatusBadge status={selectedTrace.status} className="shrink-0" />
                    ) : null}
                  </div>

                  <div className="grid gap-2 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.8fr)_auto] lg:items-stretch">
                    <div className="border border-border/60 bg-[#e7eddc] px-4 py-3 dark:bg-background/40">
                      <span className="block text-xs uppercase tracking-[0.18em] text-muted-foreground">
                        Active file
                      </span>
                      <span className="mt-1 block text-sm font-medium text-foreground">
                        {selectedTrace?.fileName ?? "No file selected"}
                      </span>
                    </div>

                    <div className="border border-border/60 bg-[#e7eddc] px-4 py-3 dark:bg-background/40">
                      <span className="block text-xs uppercase tracking-[0.18em] text-muted-foreground">
                        Refresh state
                      </span>
                      <span className="mt-1 block text-sm font-medium text-foreground">
                        {formatLastSync(lastSyncedAt)}
                      </span>
                    </div>

                    <div className="flex flex-wrap items-center justify-end gap-2 border border-border/60 bg-[#e7eddc] px-3 py-3 dark:bg-background/40">
                      <Button
                        type="button"
                        variant="outline"
                        className="h-8 gap-2 px-3 text-xs"
                        onClick={refreshNow}
                      >
                        Sync
                      </Button>

                      {activeChallengeId && isAgentRunning ? (
                        <Button
                          type="button"
                          variant="destructive"
                          onClick={handleKillAgent}
                          disabled={killPending}
                          className="h-8 px-3 text-xs"
                        >
                          {killPending ? "Killing..." : "Kill Agent"}
                        </Button>
                      ) : null}
                    </div>
                  </div>
                </div>
              </CardHeader>
              {error || killError ? (
                <CardContent className="px-5 pb-5 pt-0">
                  <Separator className="mb-5" />
                  <p className="text-base text-rose-600 dark:text-rose-300">{killError ?? error}</p>
                </CardContent>
              ) : null}
            </Card>

            {activeChallengeId ? <SteeringPanel challengeId={activeChallengeId} /> : null}

            {filteredTraces.length > 1 ? (
              <Card className="min-h-0 max-h-[22rem] rounded-none border-border/60 bg-card shadow-none">
                <CardHeader className="px-4 py-3 pb-2">
                  <CardTitle className="text-base">Session Traces</CardTitle>
                  <CardDescription className="text-xs text-muted-foreground">
                    Switch between challenge runs without leaving the dashboard.
                  </CardDescription>
                </CardHeader>
                <CardContent className="min-h-0 flex-1 p-4 pt-0">
                  <SessionList
                    traces={filteredTraces}
                    selectedId={selectedId}
                    onSelect={(traceId) => setSelectedId(traceId)}
                    className="h-full"
                  />
                </CardContent>
              </Card>
            ) : null}

            <div className="min-h-0 flex-1 overflow-auto pr-1">
              <TraceOverview trace={selectedTrace} detail={detail} />
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
