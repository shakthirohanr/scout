"use client";

import { Play, RefreshCw, ShieldPlus, Upload } from "lucide-react";
import { useRouter } from "next/navigation";
import { type FormEvent, useMemo, useState, useTransition } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
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
import type { ChallengeCatalogItem, ChallengeRunState, ImportCTFInput } from "@/lib/types";

type ChallengeHomeProps = {
  challenges: ChallengeCatalogItem[];
};

type AuthMode = "token" | "credentials" | "none";

function formatStartedAt(value: string | null): string {
  if (!value) {
    return "Not started";
  }
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatChallengeState(state: ChallengeRunState): string {
  if (state === "starting") {
    return "Starting";
  }
  if (state === "running") {
    return "Running";
  }
  if (state === "solved") {
    return "Solved";
  }
  if (state === "gave_up") {
    return "Gave up";
  }
  if (state === "cancelled") {
    return "Cancelled";
  }
  if (state === "failed") {
    return "Failed";
  }
  if (state === "finished") {
    return "Finished";
  }
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

  const [name, setName] = useState("");
  const [ctfdUrl, setCtfdUrl] = useState("");
  const [authMode, setAuthMode] = useState<AuthMode>("token");
  const [token, setToken] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [challengesRoot, setChallengesRoot] = useState("challenges");

  const [isPending, startTransition] = useTransition();
  const [isImporting, startImportTransition] = useTransition();

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      return challenges;
    }

    return challenges.filter((item) => {
      return (
        item.name.toLowerCase().includes(normalized) ||
        item.ctfName.toLowerCase().includes(normalized) ||
        item.category.toLowerCase().includes(normalized) ||
        item.path.toLowerCase().includes(normalized)
      );
    });
  }, [challenges, query]);

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

  function handleStart(challengeId: string) {
    setPendingId(challengeId);
    setError(null);

    startTransition(async () => {
      try {
        const response = await fetch("/api/challenges/start", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ challengeId }),
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
          headers: {
            "Content-Type": "application/json",
          },
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
      <section
        aria-labelledby="challenge-catalog-heading"
        className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between"
      >
        <div className="space-y-2">
          <h1
            id="challenge-catalog-heading"
            className="text-3xl font-semibold tracking-tight text-foreground"
          >
            Challenge Catalog
          </h1>
          <p className="text-sm text-muted-foreground">
            Import CTFs from CTFd, browse challenges, and launch the solver agent.
          </p>
        </div>
        <div className="w-full sm:w-96">
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by challenge, CTF, category, or path"
            aria-label="Search challenges"
            className="h-10 border-input bg-background"
          />
        </div>
      </section>

      <Card className="mb-6 border-border bg-card shadow-none">
        <CardHeader className="pb-4">
          <CardTitle className="flex items-center gap-2 text-base text-card-foreground">
            <ShieldPlus className="size-5 text-muted-foreground" aria-hidden="true" />
            Add New CTF
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4 md:grid-cols-2 xl:grid-cols-4" onSubmit={handleImport}>
            <div className="space-y-2">
              <label htmlFor="ctf-name" className="text-xs uppercase tracking-wide text-muted-foreground">
                CTF Name
              </label>
              <Input
                id="ctf-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="PlaidCTF 2026"
                className="h-10"
              />
            </div>

            <div className="space-y-2">
              <label htmlFor="ctf-url" className="text-xs uppercase tracking-wide text-muted-foreground">
                CTFd URL
              </label>
              <Input
                id="ctf-url"
                value={ctfdUrl}
                onChange={(event) => setCtfdUrl(event.target.value)}
                placeholder="https://ctf.example.com"
                className="h-10"
              />
            </div>

            <div className="space-y-2">
              <label htmlFor="ctf-root" className="text-xs uppercase tracking-wide text-muted-foreground">
                Challenges Root
              </label>
              <Input
                id="ctf-root"
                value={challengesRoot}
                onChange={(event) => setChallengesRoot(event.target.value)}
                placeholder="challenges"
                className="h-10"
              />
            </div>

            <div className="space-y-2">
              <label className="text-xs uppercase tracking-wide text-muted-foreground">Auth Mode</label>
              <Select
                value={authMode}
                onValueChange={(value) => setAuthMode(value as AuthMode)}
              >
                <SelectTrigger className="h-10 w-full">
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
              <>
                <div className="md:col-span-2 xl:col-span-4 xl:grid xl:grid-cols-[minmax(0,1fr)_11rem] xl:items-end xl:gap-4">
                  <div className="space-y-2">
                    <label htmlFor="ctf-token" className="text-xs uppercase tracking-wide text-muted-foreground">
                      CTFd Token
                    </label>
                    <Input
                      id="ctf-token"
                      value={token}
                      onChange={(event) => setToken(event.target.value)}
                      type="password"
                      placeholder="ctfd_xxxxxxxxx"
                      className="h-10"
                    />
                  </div>

                  <Button
                    type="submit"
                    size="lg"
                    disabled={isImporting}
                    className="mt-4 w-full gap-2 xl:mt-0"
                  >
                    {isImporting ? (
                      <RefreshCw className="size-4 animate-spin" aria-hidden="true" />
                    ) : (
                      <Upload className="size-4" aria-hidden="true" />
                    )}
                    Import CTF
                  </Button>
                </div>
              </>
            ) : authMode === "credentials" ? (
              <>
                <div className="md:col-span-2 xl:col-span-4 xl:grid xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_11rem] xl:items-end xl:gap-4">
                  <div className="space-y-2">
                    <label
                      htmlFor="ctf-username"
                      className="text-xs uppercase tracking-wide text-muted-foreground"
                    >
                      Username
                    </label>
                    <Input
                      id="ctf-username"
                      value={username}
                      onChange={(event) => setUsername(event.target.value)}
                      placeholder="teamname"
                      className="h-10"
                    />
                  </div>
                  <div className="space-y-2">
                    <label
                      htmlFor="ctf-password"
                      className="text-xs uppercase tracking-wide text-muted-foreground"
                    >
                      Password
                    </label>
                    <Input
                      id="ctf-password"
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      type="password"
                      placeholder="password"
                      className="h-10"
                    />
                  </div>

                  <Button
                    type="submit"
                    size="lg"
                    disabled={isImporting}
                    className="mt-4 w-full gap-2 xl:mt-0"
                  >
                    {isImporting ? (
                      <RefreshCw className="size-4 animate-spin" aria-hidden="true" />
                    ) : (
                      <Upload className="size-4" aria-hidden="true" />
                    )}
                    Import CTF
                  </Button>
                </div>
              </>
            ) : (
              <div className="md:col-span-2 xl:col-span-4 xl:grid xl:grid-cols-[minmax(0,1fr)_11rem] xl:items-end xl:gap-4">
                <p className="text-sm text-muted-foreground">
                  Public CTF selected. No token or credentials are required.
                </p>

                <Button
                  type="submit"
                  size="lg"
                  disabled={isImporting}
                  className="mt-4 w-full gap-2 xl:mt-0"
                >
                  {isImporting ? (
                    <RefreshCw className="size-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <Upload className="size-4" aria-hidden="true" />
                  )}
                  Import CTF
                </Button>
              </div>
            )}
          </form>

          {importError ? (
            <p className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-4 py-2 text-sm text-destructive">
              {importError}
            </p>
          ) : null}
          {importMessage ? (
            <p className="mt-4 rounded-md border border-primary/35 bg-primary/10 px-4 py-2 text-sm text-foreground">
              {importMessage}
            </p>
          ) : null}
        </CardContent>
      </Card>

      {error ? (
        <p className="mb-4 rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </p>
      ) : null}

      <main className="flex-1 pr-1">
        {!filtered.length ? (
          <div className="mt-8 rounded-lg border border-dashed border-border bg-card px-6 py-10 text-center text-sm text-muted-foreground">
            No challenges match your filter.
          </div>
        ) : (
          <div className="space-y-6">
            {groupedChallenges.map(([ctfName, ctfChallenges]) => (
              <Card key={ctfName} className="border-border bg-card shadow-none">
                <CardHeader className="space-y-2 pb-4">
                  <div className="flex items-center justify-between gap-3">
                    <CardTitle className="text-lg text-card-foreground">{ctfName}</CardTitle>
                    <Badge variant="secondary" className="font-medium">
                      {ctfChallenges.length}
                    </Badge>
                  </div>
                  <CardDescription>
                    {ctfChallenges.length} challenge{ctfChallenges.length === 1 ? "" : "s"}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                    {ctfChallenges.map((challenge) => {
                      const isStarting = pendingId === challenge.id;
                      const challengeBusy = isChallengeBusy(challenge.state);
                      return (
                        <Card
                          key={challenge.id}
                          className="rounded-lg border-border bg-background shadow-none"
                        >
                          <CardHeader className="space-y-3 pb-2">
                            <div className="flex items-start justify-between gap-3">
                              <CardTitle className="line-clamp-2 text-base text-card-foreground">
                                {challenge.name}
                              </CardTitle>
                              <Button
                                type="button"
                                size="sm"
                                className="gap-1.5"
                                onClick={() => handleStart(challenge.id)}
                                disabled={isStarting || isPending || challengeBusy}
                              >
                                {isStarting ? (
                                  <RefreshCw className="size-3.5 animate-spin" aria-hidden="true" />
                                ) : (
                                  <Play className="size-3.5" aria-hidden="true" />
                                )}
                                {challengeBusy ? "Running" : "Solve"}
                              </Button>
                            </div>
                          </CardHeader>
                          <CardContent className="space-y-4">
                            <p className="line-clamp-4 min-h-[5.2rem] text-sm text-muted-foreground">
                              {challenge.description || "No description provided."}
                            </p>
                            <div className="space-y-1.5 text-xs text-muted-foreground">
                              <p>Status: {formatChallengeState(challenge.state)}</p>
                              <p>Category: {challenge.category || "uncategorized"}</p>
                              <p>Value: {challenge.value || 0}</p>
                              <p>Distfiles: {challenge.distfileCount}</p>
                              <p>Started: {formatStartedAt(challenge.startedAt)}</p>
                              {challenge.latestFlag ? <p>Flag: {challenge.latestFlag}</p> : null}
                            </div>
                          </CardContent>
                        </Card>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
