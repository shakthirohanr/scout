"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { ActivityFeed } from "@/components/dashboard/activity-feed";
import { ChallengeSidebar } from "@/components/dashboard/challenge-sidebar";
import { LogTerminal } from "@/components/dashboard/log-terminal";
import { OverviewCards } from "@/components/dashboard/overview-cards";
import { SessionList } from "@/components/dashboard/session-list";
import { SteeringPanel } from "@/components/dashboard/steering-panel";
import { StatusBadge } from "@/components/dashboard/status-badge";
import { TraceOverview } from "@/components/dashboard/trace-overview";
import { ThemeToggle } from "@/components/theme/theme-toggle";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Separator } from "@/components/ui/separator";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
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
  const [desktopSidebarOpen, setDesktopSidebarOpen] = useState(true);
  const [killPending, setKillPending] = useState(false);
  const [killError, setKillError] = useState<string | null>(null);
  const {
    challengeItems,
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

  const sidebarChallenges = useMemo(() => {
    const filtered = challengeItems.filter((challenge) => {
      const hasStarted = Boolean(challenge.startedAt);
      const hasRunningTrace = challenge.traces.some((trace) => trace.status === "running");
      return hasStarted || hasRunningTrace;
    });

    const hasActive = activeChallengeId
      ? filtered.some((challenge) => challenge.id === activeChallengeId)
      : false;

    if (!hasActive && activeChallengeId) {
      const active = challengeItems.find((challenge) => challenge.id === activeChallengeId);
      if (active) {
        return [active, ...filtered];
      }
    }

    return filtered;
  }, [activeChallengeId, challengeItems]);

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

  return (
    <div className="flex h-full w-full flex-col overflow-hidden bg-background **:rounded-none">
      <header className="shrink-0 border-b border-border/60 bg-[#e7eddc] dark:bg-background">
        <div className="flex w-full items-center justify-between gap-4 px-4 py-5 sm:px-6 lg:px-8">
          <div className="min-w-0">
            <Link
              href="/"
              className="inline-block text-2xl font-semibold tracking-tight text-foreground transition-opacity hover:opacity-80 sm:text-3xl"
            >
              CryptoAgent
            </Link>
          </div>

          <div className="flex items-center gap-2 self-start sm:self-auto">
            {activeChallengeId ? (
              <Button
                type="button"
                variant="destructive"
                onClick={handleKillAgent}
                disabled={killPending}
              >
                {killPending ? "Killing..." : "Kill Agent"}
              </Button>
            ) : null}

            <Sheet>
              <SheetTrigger
                render={
                  <Button
                    type="button"
                    variant="outline"
                    className="lg:hidden"
                    aria-label="Open challenge list"
                  />
                }
              >
                Challenges
              </SheetTrigger>
              <SheetContent side="left" className="w-[24rem] max-w-[90vw] p-0">
                <SheetHeader className="border-b border-border/60 bg-[#e7eddc] px-5 py-4 text-left dark:bg-background">
                  <SheetTitle>CryptoAgent</SheetTitle>
                </SheetHeader>
                <div className="h-[calc(100%-4.5rem)] p-4">
                  <ChallengeSidebar
                    challenges={sidebarChallenges}
                    activeChallengeId={activeChallengeId}
                  />
                </div>
              </SheetContent>
            </Sheet>

            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button
                    type="button"
                    variant="outline"
                    className="hidden lg:inline-flex"
                    aria-label="Dashboard actions"
                  />
                }
              >
                View
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" sideOffset={8}>
                <DropdownMenuItem onClick={() => setDesktopSidebarOpen((value) => !value)}>
                  {desktopSidebarOpen ? "Hide sidebar" : "Show sidebar"}
                </DropdownMenuItem>
                <DropdownMenuItem onClick={refreshNow}>Refresh now</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            <Button
              type="button"
              variant="outline"
              className="gap-2"
              onClick={refreshNow}
            >
              Sync
            </Button>
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className={`grid min-h-0 w-full flex-1 gap-6 px-4 py-6 sm:px-6 lg:px-8 ${desktopSidebarOpen ? "lg:grid-cols-[19rem_minmax(0,1fr)]" : "lg:grid-cols-[minmax(0,1fr)]"}`}>
        <aside className={`min-h-0 ${desktopSidebarOpen ? "hidden lg:flex" : "hidden"}`}>
          <Card className="flex h-full min-h-0 w-full flex-col rounded-none border-border/60 bg-[#f0f4e6] shadow-none dark:bg-card">
            <CardHeader className="border-b border-border/60 bg-[#e7eddc] px-4 py-4 dark:bg-background/40">
              <CardTitle className="text-sm">CryptoAgent</CardTitle>
              <CardDescription className="text-xs">
                Started and running challenges
              </CardDescription>
            </CardHeader>
            <CardContent className="min-h-0 flex-1 p-4">
              <ChallengeSidebar
                challenges={sidebarChallenges}
                activeChallengeId={activeChallengeId}
              />
            </CardContent>
          </Card>
        </aside>

        <section className="min-h-0 space-y-6 overflow-y-auto pr-1">
          <div className="grid gap-6">
            <Card className="rounded-none border-border/60 bg-[#f0f4e6] shadow-none dark:bg-card">
              <CardHeader className="px-5 py-5 pb-3">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      {selectedTrace ? <StatusBadge status={selectedTrace.status} /> : null}
                    </div>
                    <CardTitle className="text-xl font-semibold sm:text-2xl">
                      {selectedTrace
                        ? `${selectedTrace.challengeName} on ${selectedTrace.modelName}`
                        : activeChallenge?.name ?? activeChallengeName ?? "CryptoAgent"}
                    </CardTitle>
                  </div>
                  <div className="grid gap-2 text-sm text-muted-foreground sm:grid-cols-2">
                    <div className="border border-border/60 bg-[#e7eddc] px-4 py-3 dark:bg-background/40">
                      <span className="block text-xs uppercase tracking-[0.2em] text-muted-foreground">
                        Active file
                      </span>
                      <span className="mt-1 block font-medium text-foreground">
                        {selectedTrace?.fileName ?? "No file selected"}
                      </span>
                    </div>
                    <div className="border border-border/60 bg-[#e7eddc] px-4 py-3 dark:bg-background/40">
                      <span className="block text-xs uppercase tracking-[0.2em] text-muted-foreground">
                        Refresh state
                      </span>
                      <span className="mt-1 block font-medium text-foreground">
                        {listPending || detailPending ? "Refreshing…" : formatLastSync(lastSyncedAt)}
                      </span>
                    </div>
                  </div>
                </div>
              </CardHeader>
              {error || killError ? (
                <CardContent className="px-5 pb-5 pt-0">
                  <Separator className="mb-5" />
                  <p className="text-sm text-rose-600 dark:text-rose-300">{killError ?? error}</p>
                </CardContent>
              ) : null}
            </Card>

            <OverviewCards totals={totals} />

            {activeChallengeId ? <SteeringPanel challengeId={activeChallengeId} /> : null}

            {filteredTraces.length > 1 ? (
              <Card className="rounded-none border-border/60 bg-card shadow-none">
                <CardHeader className="px-5 py-4 pb-2">
                  <CardTitle className="text-base">Session Traces</CardTitle>
                </CardHeader>
                <CardContent className="p-5 pt-0">
                <SessionList
                  traces={filteredTraces}
                  selectedId={selectedId}
                  onSelect={(traceId) => setSelectedId(traceId)}
                />
                </CardContent>
              </Card>
            ) : null}

            {filteredTraces.length ? (
              <LogTerminal
                summary={selectedTrace}
                content={detail?.terminalOutput ?? ""}
                onRefresh={refreshNow}
              />
            ) : (
              <Card className="rounded-none border-dashed border-border/70 bg-card shadow-none">
                <CardContent className="p-10 text-center">
                  <h2 className="text-xl font-semibold text-foreground">
                    CryptoAgent
                  </h2>
                </CardContent>
              </Card>
            )}
          </div>

          <div className="grid gap-6 2xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
            <ActivityFeed events={detail?.events ?? []} />
            <TraceOverview trace={selectedTrace} detail={detail} />
          </div>
        </section>
      </main>
    </div>
  );
}
