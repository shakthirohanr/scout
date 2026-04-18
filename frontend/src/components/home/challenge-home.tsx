"use client";

import { Minus, Play, Plus, RefreshCw, ShieldPlus, Upload, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { type FormEvent, useMemo, useState, useTransition } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { cn } from "@/lib/utils";
import type { ChallengeCatalogItem, ChallengeRunState, ImportCTFInput } from "@/lib/types";

type ChallengeHomeProps = {
  challenges: ChallengeCatalogItem[];
};

type AuthMode = "token" | "credentials" | "none";

type FilterKey = `category:${string}` | `state:${string}` | `ctf:${string}`;

function formatChallengeState(state: ChallengeRunState): string {
  if (state === "starting") return "Starting";
  if (state === "running") return "Running";
  if (state === "solved") return "Solved";
  if (state === "gave_up") return "Gave up";
  if (state === "cancelled") return "Cancelled";
  if (state === "failed") return "Failed";
  if (state === "finished") return "Finished";
  return "Idle";
}

function isChallengeBusy(state: ChallengeRunState): boolean {
  return state === "starting" || state === "running";
}

export function ChallengeHome({ challenges }: ChallengeHomeProps) {
  const router = useRouter();

  const [query, setQuery] = useState("");
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [importMessage, setImportMessage] = useState<string | null>(null);
  const [agentCount, setAgentCount] = useState(1);

  const [name, setName] = useState("");
  const [ctfdUrl, setCtfdUrl] = useState("");
  const [authMode, setAuthMode] = useState<AuthMode>("token");
  const [token, setToken] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [challengesRoot, setChallengesRoot] = useState("challenges");

  const [activeFilters, setActiveFilters] = useState<Set<FilterKey>>(new Set());

  const [isPending, startTransition] = useTransition();
  const [isImporting, startImportTransition] = useTransition();

  const uniqueCategories = useMemo(() => {
    const cats = new Set<string>();
    for (const c of challenges) {
      if (c.category) cats.add(c.category);
    }
    return Array.from(cats).sort((a, b) =>
      a.localeCompare(b, undefined, { sensitivity: "base" }),
    );
  }, [challenges]);

  const uniqueStates = useMemo(() => {
    const states = new Set<string>();
    for (const c of challenges) {
      states.add(c.state);
    }
    return Array.from(states).sort();
  }, [challenges]);

  const uniqueCtfNames = useMemo(() => {
    const names = new Set<string>();
    for (const c of challenges) {
      if (c.ctfName) names.add(c.ctfName);
    }
    return Array.from(names).sort((a, b) =>
      a.localeCompare(b, undefined, { sensitivity: "base" }),
    );
  }, [challenges]);

  const filtered = useMemo(() => {
    let result = challenges;

    const normalized = query.trim().toLowerCase();
    if (normalized) {
      result = result.filter(
        (item) =>
          item.name.toLowerCase().includes(normalized) ||
          item.ctfName.toLowerCase().includes(normalized) ||
          item.category.toLowerCase().includes(normalized) ||
          item.path.toLowerCase().includes(normalized),
      );
    }

    if (activeFilters.size > 0) {
      const activeCategories = new Set<string>();
      const activeStates = new Set<string>();
      const activeCtfs = new Set<string>();

      for (const key of activeFilters) {
        if (key.startsWith("category:")) activeCategories.add(key.slice(9));
        else if (key.startsWith("state:")) activeStates.add(key.slice(6));
        else if (key.startsWith("ctf:")) activeCtfs.add(key.slice(4));
      }

      result = result.filter((item) => {
        if (activeCategories.size > 0 && !activeCategories.has(item.category)) return false;
        if (activeStates.size > 0 && !activeStates.has(item.state)) return false;
        if (activeCtfs.size > 0 && !activeCtfs.has(item.ctfName)) return false;
        return true;
      });
    }

    return result;
  }, [challenges, query, activeFilters]);

  const groupedChallenges = useMemo(() => {
    const grouped = new Map<string, ChallengeCatalogItem[]>();
    for (const item of filtered) {
      const key = item.ctfName || "Unknown CTF";
      const existing = grouped.get(key);
      if (existing) {
        existing.push(item);
      } else {
        grouped.set(key, [item]);
      }
    }
    return Array.from(grouped.entries()).sort(([a], [b]) =>
      a.localeCompare(b, undefined, { sensitivity: "base" }),
    );
  }, [filtered]);

  function toggleFilter(key: FilterKey) {
    setActiveFilters((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }

  function clearFilters() {
    setActiveFilters(new Set());
  }

  function handleStart(challengeId: string) {
    setPendingId(challengeId);
    setError(null);

    startTransition(async () => {
      try {
        const response = await fetch("/api/challenges/start", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ challengeId, agentCount }),
        });

        if (!response.ok) {
          const payload = (await response.json().catch(() => null)) as
            | { error?: string }
            | null;
          throw new Error(payload?.error || `Request failed: ${response.status}`);
        }

        router.push(`/challenge/${encodeURIComponent(challengeId)}`);
      } catch (caughtError) {
        setError(
          caughtError instanceof Error
            ? caughtError.message
            : "Unable to start challenge.",
        );
      } finally {
        setPendingId(null);
      }
    });
  }

  function handleImport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setImportError(null);
    setImportMessage(null);

    const payload: ImportCTFInput = {
      name: name.trim(),
      ctfdUrl: ctfdUrl.trim(),
      authMode,
      token: token.trim(),
      username: username.trim(),
      password,
      challengesRoot: challengesRoot.trim() || "challenges",
    };

    if (!payload.name || !payload.ctfdUrl) {
      setImportError("CTF name and CTFd URL are required.");
      return;
    }
    if (payload.authMode === "token" && !payload.token) {
      setImportError("Token is required for token-based authentication.");
      return;
    }
    if (
      payload.authMode === "credentials" &&
      (!payload.username || !payload.password)
    ) {
      setImportError("Username and password are required for credentials mode.");
      return;
    }

    startImportTransition(async () => {
      try {
        const response = await fetch("/api/ctfs/import", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        if (!response.ok) {
          const body = (await response.json().catch(() => null)) as
            | { error?: string }
            | null;
          throw new Error(body?.error || `Import failed: ${response.status}`);
        }

        const result = (await response.json()) as {
          importedChallenges: number;
          downloadedFiles: number;
        };

        setImportMessage(
          `Imported ${result.importedChallenges} challenges and ${result.downloadedFiles} files.`,
        );

        setToken("");
        setPassword("");
        router.refresh();
      } catch (caughtError) {
        setImportError(
          caughtError instanceof Error
            ? caughtError.message
            : "Failed to import CTF.",
        );
      }
    });
  }

  return (
    <div className="page-shell">
      <Card className="mb-6">
        <CardHeader className="px-6 pt-6 pb-4">
          <CardTitle className="flex items-center gap-2 text-sm font-medium uppercase tracking-wide text-muted-foreground">
            <ShieldPlus className="size-4" aria-hidden="true" />
            Import CTF
          </CardTitle>
        </CardHeader>
        <CardContent className="px-6 pb-6">
          <form className="grid gap-4 md:grid-cols-2 xl:grid-cols-4" onSubmit={handleImport}>
            <div className="space-y-1.5">
              <label htmlFor="ctf-name" className="text-xs text-muted-foreground">
                CTF Name
              </label>
              <Input
                id="ctf-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="PlaidCTF 2026"
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="ctf-url" className="text-xs text-muted-foreground">
                CTFd URL
              </label>
              <Input
                id="ctf-url"
                value={ctfdUrl}
                onChange={(event) => setCtfdUrl(event.target.value)}
                placeholder="https://ctf.example.com"
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="ctf-root" className="text-xs text-muted-foreground">
                Challenges Root
              </label>
              <Input
                id="ctf-root"
                value={challengesRoot}
                onChange={(event) => setChallengesRoot(event.target.value)}
                placeholder="challenges"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground">Auth Mode</label>
              <Select
                value={authMode}
                onValueChange={(value) => setAuthMode(value as AuthMode)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select auth mode" />
                </SelectTrigger>
                <SelectContent
                  side="bottom"
                  alignItemWithTrigger={false}
                  collisionAvoidance={{
                    side: "none",
                    align: "none",
                    fallbackAxisSide: "none",
                  }}
                >
                  <SelectItem value="none">No Auth (Public CTF)</SelectItem>
                  <SelectItem value="token">Token</SelectItem>
                  <SelectItem value="credentials">Username / Password</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {authMode === "token" ? (
              <div className="md:col-span-2 xl:col-span-4 xl:grid xl:grid-cols-[minmax(0,1fr)_10rem] xl:items-end xl:gap-4">
                <div className="space-y-1.5">
                  <label htmlFor="ctf-token" className="text-xs text-muted-foreground">
                    CTFd Token
                  </label>
                  <Input
                    id="ctf-token"
                    value={token}
                    onChange={(event) => setToken(event.target.value)}
                    type="password"
                    placeholder="ctfd_xxxxxxxxx"
                  />
                </div>
                <Button
                  type="submit"
                  size="lg"
                  disabled={isImporting}
                  className="mt-4 w-full gap-2 xl:mt-0"
                >
                  {isImporting ? (
                    <RefreshCw className="size-3.5 animate-spin" aria-hidden="true" />
                  ) : (
                    <Upload className="size-3.5" aria-hidden="true" />
                  )}
                  Import CTF
                </Button>
              </div>
            ) : authMode === "credentials" ? (
              <div className="md:col-span-2 xl:col-span-4 xl:grid xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_10rem] xl:items-end xl:gap-4">
                <div className="space-y-1.5">
                  <label htmlFor="ctf-username" className="text-xs text-muted-foreground">
                    Username
                  </label>
                  <Input
                    id="ctf-username"
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                    placeholder="teamname"
                  />
                </div>
                <div className="space-y-1.5">
                  <label htmlFor="ctf-password" className="text-xs text-muted-foreground">
                    Password
                  </label>
                  <Input
                    id="ctf-password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    type="password"
                    placeholder="password"
                  />
                </div>
                <Button
                  type="submit"
                  size="lg"
                  disabled={isImporting}
                  className="mt-4 w-full gap-2 xl:mt-0"
                >
                  {isImporting ? (
                    <RefreshCw className="size-3.5 animate-spin" aria-hidden="true" />
                  ) : (
                    <Upload className="size-3.5" aria-hidden="true" />
                  )}
                  Import CTF
                </Button>
              </div>
            ) : (
              <div className="md:col-span-2 xl:col-span-4 xl:grid xl:grid-cols-[minmax(0,1fr)_10rem] xl:items-end xl:gap-4">
                <p className="text-sm text-muted-foreground">
                  Public CTF selected. No authentication required.
                </p>
                <Button
                  type="submit"
                  size="lg"
                  disabled={isImporting}
                  className="mt-4 w-full gap-2 xl:mt-0"
                >
                  {isImporting ? (
                    <RefreshCw className="size-3.5 animate-spin" aria-hidden="true" />
                  ) : (
                    <Upload className="size-3.5" aria-hidden="true" />
                  )}
                  Import CTF
                </Button>
              </div>
            )}
          </form>

          {importError && (
            <p className="mt-4 rounded-md border border-destructive/30 bg-destructive/8 px-3 py-2 text-sm text-destructive">
              {importError}
            </p>
          )}
          {importMessage && (
            <p className="mt-4 rounded-md border border-primary/20 bg-primary/8 px-3 py-2 text-sm text-foreground">
              {importMessage}
            </p>
          )}
        </CardContent>
      </Card>

      <section className="mb-4 flex flex-col gap-3">
        <div className="relative w-full sm:max-w-sm">
          <svg
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by challenge, CTF, or category"
            aria-label="Search challenges"
            className="pl-9"
          />
        </div>
      </section>

      {(uniqueCategories.length > 0 || uniqueStates.length > 0 || uniqueCtfNames.length > 0) && (
        <section className="mb-6 space-y-3">
          {uniqueCategories.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="mr-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Category
              </span>
              {uniqueCategories.map((cat) => {
                const key = `category:${cat}` as FilterKey;
                const active = activeFilters.has(key);
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => toggleFilter(key)}
                    className={cn(
                      "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs transition-colors",
                      active
                        ? "bg-surface-500 text-foreground"
                        : "bg-surface-300 text-muted-foreground hover:text-warm-hover",
                    )}
                  >
                    {cat}
                  </button>
                );
              })}
            </div>
          )}

          {uniqueStates.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="mr-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                State
              </span>
              {uniqueStates.map((state) => {
                const key = `state:${state}` as FilterKey;
                const active = activeFilters.has(key);
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => toggleFilter(key)}
                    className={cn(
                      "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs transition-colors",
                      active
                        ? "bg-surface-500 text-foreground"
                        : "bg-surface-300 text-muted-foreground hover:text-warm-hover",
                    )}
                  >
                    {formatChallengeState(state as ChallengeRunState).toLowerCase()}
                  </button>
                );
              })}
            </div>
          )}

          {uniqueCtfNames.length > 1 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="mr-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                CTF
              </span>
              {uniqueCtfNames.map((ctfName) => {
                const key = `ctf:${ctfName}` as FilterKey;
                const active = activeFilters.has(key);
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => toggleFilter(key)}
                    className={cn(
                      "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs transition-colors",
                      active
                        ? "bg-surface-500 text-foreground"
                        : "bg-surface-300 text-muted-foreground hover:text-warm-hover",
                    )}
                  >
                    {ctfName}
                  </button>
                );
              })}
            </div>
          )}

          {activeFilters.size > 0 && (
            <button
              type="button"
              onClick={clearFilters}
              className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-warm-hover transition-colors"
            >
              <X className="size-3" />
              Clear filters
            </button>
          )}
        </section>
      )}

      {error && (
        <p className="mb-4 rounded-md border border-destructive/30 bg-destructive/8 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      <main className="flex-1">
        {!filtered.length ? (
          <p className="py-12 text-center text-sm text-muted-foreground">
            No challenges match your filter.
          </p>
        ) : (
          <Accordion defaultValue={groupedChallenges.map(([ctfName]) => ctfName)} className="w-full space-y-3">
            {groupedChallenges.map(([ctfName, ctfChallenges]) => (
              <AccordionItem key={ctfName} value={ctfName} className="rounded-lg border border-border bg-card overflow-hidden">
                <AccordionTrigger className="px-5 py-3.5 hover:bg-muted/30 transition-colors [&[data-state=open]]:border-b [&[data-state=open]]:border-border hover:no-underline">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-foreground">{ctfName}</span>
                    <Badge variant="secondary" className="text-xs">
                      {ctfChallenges.length}
                    </Badge>
                  </div>
                </AccordionTrigger>
                <AccordionContent className="px-5 py-3">
                  <div className="flex flex-col gap-2">
                    {ctfChallenges.map((challenge) => {
                      const isStarting = pendingId === challenge.id;
                      const challengeBusy = isChallengeBusy(challenge.state);

                      return (
                        <div
                          key={challenge.id}
                          className="flex flex-col md:flex-row md:items-center justify-between gap-3 p-4 rounded-md border border-border bg-background"
                        >
                          <div className="flex-1 min-w-0 space-y-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <h3 className="font-medium text-sm text-foreground">
                                {challenge.name}
                              </h3>
                              <Badge variant="outline" className="text-xs font-mono">
                                {challenge.value || 0} pts
                              </Badge>
                              {challenge.latestFlag && (
                                <Badge className="bg-emerald-600/10 text-emerald-700 border-none text-xs font-mono">
                                  Captured
                                </Badge>
                              )}
                            </div>
                            <p className="text-sm text-muted-foreground line-clamp-1">
                              {challenge.description || "No description available."}
                            </p>
                            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                              <span>{challenge.category || "Uncategorized"}</span>
                              <span className="text-border">·</span>
                              <span className="capitalize">{formatChallengeState(challenge.state).toLowerCase()}</span>
                              <span className="text-border">·</span>
                              <span>{challenge.distfileCount} files</span>
                            </div>
                          </div>

                          <div className="flex items-center gap-3 shrink-0">
                            <div className="flex items-center gap-1.5 rounded-md border border-border bg-surface-100 px-1 py-0.5">
                              <button
                                type="button"
                                onClick={() => setAgentCount((c) => Math.max(1, c - 1))}
                                disabled={challengeBusy}
                                className="flex size-6 items-center justify-center rounded-sm text-muted-foreground hover:text-foreground transition-colors disabled:opacity-40"
                                aria-label="Decrease agent count"
                              >
                                <Minus className="size-3.5" />
                              </button>
                              <span className="min-w-[2ch] text-center text-xs font-medium tabular-nums text-foreground">
                                {agentCount}
                              </span>
                              <button
                                type="button"
                                onClick={() => setAgentCount((c) => Math.min(10, c + 1))}
                                disabled={challengeBusy}
                                className="flex size-6 items-center justify-center rounded-sm text-muted-foreground hover:text-foreground transition-colors disabled:opacity-40"
                                aria-label="Increase agent count"
                              >
                                <Plus className="size-3.5" />
                              </button>
                            </div>
                            <Button
                              type="button"
                              size="sm"
                              variant={challengeBusy ? "outline" : "default"}
                              onClick={() => handleStart(challenge.id)}
                              disabled={isStarting || isPending || challengeBusy}
                              className="gap-1.5"
                            >
                              {isStarting ? (
                                <RefreshCw className="size-3.5 animate-spin" aria-hidden="true" />
                              ) : (
                                <Play className="size-3.5" aria-hidden="true" />
                              )}
                              {challengeBusy ? "Running" : "Run"}
                            </Button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        )}
      </main>
    </div>
  );
}
