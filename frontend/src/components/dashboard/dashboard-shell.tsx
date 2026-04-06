"use client";

import { useState } from "react";
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
    listPending,
    detailPending,
    error,
    lastSyncedAt,
    refreshNow,
    totals,
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

  const hasRunningTrace = filteredTraces.some((t) => t.status === "running");
  const hasTerminalTrace = filteredTraces.some((t) =>
    ["solved", "gave_up", "cancelled", "finished", "failed", "error"].includes(t.status)
  );
  
  // The agent is considered running if:
  // 1. We have a live trace explicitly saying it's running
  // 2. OR the challenge is starting/running and we haven't yet received a terminal state update
  const isAgentRunning =
    hasRunningTrace ||
    ((activeChallenge?.state === "starting" || activeChallenge?.state === "running") &&
      !hasTerminalTrace);

  return (
    <div className="flex h-full w-full flex-col overflow-hidden bg-background px-4 py-6 sm:px-6 lg:px-8 **:rounded-none">
      <main className="flex-1 min-h-0 pr-1">
        <div className="grid gap-7 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)] h-full min-h-0 items-start">
          <div className="space-y-7 xl:order-last h-full overflow-hidden pr-2 pb-6 flex flex-col">
            <section className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-2">
              <p className="text-sm uppercase tracking-[0.18em] text-muted-foreground">
                Challenge workspace
              </p>
              <h1 className="text-3xl font-semibold tracking-tight text-foreground">
                {activeChallenge?.name ?? activeChallengeName ?? "Challenge dashboard"}
              </h1>
              <p className="text-sm text-muted-foreground">
                Inspect trace output, steer the agent, and manage active sessions.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {activeChallengeId && isAgentRunning ? (
                <Button
                  type="button"
                  variant="destructive"
                  onClick={handleKillAgent}
                  disabled={killPending}
                >
                  {killPending ? "Killing..." : "Kill Agent"}
                </Button>
              ) : null}

              <Button
                type="button"
                variant="outline"
                className="gap-2"
                onClick={refreshNow}
              >
                Sync
              </Button>
            </div>
          </section>

            <Card className="rounded-none border-border/60 bg-[#f0f4e6] shadow-none dark:bg-card">
              <CardHeader className="px-6 py-6 pb-4">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      {selectedTrace ? <StatusBadge status={selectedTrace.status} /> : null}
                    </div>
                    <CardTitle className="text-xl font-semibold sm:text-2xl">
                      {selectedTrace
                        ? `${selectedTrace.challengeName} on ${selectedTrace.modelName}`
                        : activeChallenge?.name ?? activeChallengeName ?? "Challenge dashboard"}
                    </CardTitle>
                  </div>
                  <div className="grid gap-3 text-base text-muted-foreground sm:grid-cols-2">
                    <div className="border border-border/60 bg-[#e7eddc] px-5 py-4 dark:bg-background/40">
                      <span className="block text-sm uppercase tracking-[0.18em] text-muted-foreground">
                        Active file
                      </span>
                      <span className="mt-1.5 block text-base font-medium text-foreground">
                        {selectedTrace?.fileName ?? "No file selected"}
                      </span>
                    </div>
                    <div className="border border-border/60 bg-[#e7eddc] px-5 py-4 dark:bg-background/40">
                      <span className="block text-sm uppercase tracking-[0.18em] text-muted-foreground">
                        Refresh state
                      </span>
                      <span className="mt-1.5 block text-base font-medium text-foreground">
                        {formatLastSync(lastSyncedAt)}
                      </span>
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
              <Card className="rounded-none border-border/60 bg-card shadow-none">
                <CardHeader className="px-6 py-5 pb-3">
                  <CardTitle className="text-lg">Session Traces</CardTitle>
                </CardHeader>
                <CardContent className="p-6 pt-0">
                  <SessionList
                    traces={filteredTraces}
                    selectedId={selectedId}
                    onSelect={(traceId) => setSelectedId(traceId)}
                  />
                </CardContent>
              </Card>
            ) : null}

            <div className="flex flex-col">
              <TraceOverview trace={selectedTrace} detail={detail} />
            </div>
          </div>

          <div className="xl:order-first h-full flex flex-col min-h-0">
            {filteredTraces.length ? (
              <LogTerminal
                summary={selectedTrace}
                content={detail?.terminalOutput ?? ""}
                onRefresh={refreshNow}
                className="h-full"
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
        </div>
      </main>
    </div>
  );
}
