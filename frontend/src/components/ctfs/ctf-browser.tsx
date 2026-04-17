"use client";

import { FolderOpen, RefreshCw, Search, Trash2, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { ChallengeCatalogItem, CTFSourceSummary } from "@/lib/types";

type CtfBrowserProps = {
  initialCtfs: CTFSourceSummary[];
  initialChallenges: ChallengeCatalogItem[];
};

type SourceWithChallenges = CTFSourceSummary & {
  challenges: ChallengeCatalogItem[];
  visibleChallenges: ChallengeCatalogItem[];
};

type Notice = {
  kind: "success" | "error";
  text: string;
} | null;

const LOCAL_SOURCE_URL = "local://filesystem";

function formatDate(value: string | null): string {
  if (!value) {
    return "Not available";
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

async function parseErrorMessage(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { error?: string } | null;
  return payload?.error || fallback;
}

export function CtfBrowser({ initialCtfs, initialChallenges }: CtfBrowserProps) {
  const router = useRouter();
  const [ctfs, setCtfs] = useState(initialCtfs);
  const [challenges, setChallenges] = useState(initialChallenges);
  const [query, setQuery] = useState("");
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [selectedCtfId, setSelectedCtfId] = useState<number | null>(null);

  const filteredSources = useMemo<SourceWithChallenges[]>(() => {
    const challengesByCtfId = new Map<number, ChallengeCatalogItem[]>();
    for (const challenge of challenges) {
      const existing = challengesByCtfId.get(challenge.ctfId);
      if (existing) {
        existing.push(challenge);
      } else {
        challengesByCtfId.set(challenge.ctfId, [challenge]);
      }
    }

    const normalizedQuery = query.trim().toLowerCase();

    return ctfs
      .filter((ctf) => ctf.baseUrl !== LOCAL_SOURCE_URL)
      .map((ctf) => {
        const sourceChallenges = [...(challengesByCtfId.get(ctf.id) ?? [])].sort((a, b) =>
          a.name.localeCompare(b.name, undefined, { sensitivity: "base" }),
        );

        if (!normalizedQuery) {
          return {
            ...ctf,
            challenges: sourceChallenges,
            visibleChallenges: sourceChallenges,
          };
        }

        const visibleChallenges = sourceChallenges.filter((challenge) => {
          return (
            challenge.name.toLowerCase().includes(normalizedQuery) ||
            challenge.category.toLowerCase().includes(normalizedQuery) ||
            challenge.path.toLowerCase().includes(normalizedQuery)
          );
        });

        return {
          ...ctf,
          challenges: sourceChallenges,
          visibleChallenges,
        };
      })
      .filter((ctf) => {
        if (!normalizedQuery) {
          return true;
        }

        const sourceMatch =
          ctf.name.toLowerCase().includes(normalizedQuery) ||
          ctf.slug.toLowerCase().includes(normalizedQuery) ||
          ctf.baseUrl.toLowerCase().includes(normalizedQuery) ||
          ctf.challengesRoot.toLowerCase().includes(normalizedQuery);

        if (sourceMatch) {
          return true;
        }

        return ctf.visibleChallenges.length > 0;
      });
  }, [ctfs, challenges, query]);

  useEffect(() => {
    if (selectedCtfId !== null && !filteredSources.some((ctf) => ctf.id === selectedCtfId)) {
      setSelectedCtfId(null);
    }
  }, [filteredSources, selectedCtfId]);

  const selectedSource =
    filteredSources.find((ctf) => ctf.id === selectedCtfId) ?? null;

  const sourceCount = ctfs.length;
  const challengeCount = challenges.length;

  async function handleDeleteChallenge(challenge: ChallengeCatalogItem) {
    const confirmed = window.confirm(
      `Delete the challenge "${challenge.name}" from ${challenge.ctfName}? This removes its imported files and stored runs.`,
    );
    if (!confirmed) {
      return;
    }

    const actionKey = `challenge:${challenge.id}`;
    setPendingKey(actionKey);
    setNotice(null);

    try {
      const response = await fetch(`/api/challenges/${encodeURIComponent(challenge.id)}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        throw new Error(await parseErrorMessage(response, "Failed to delete challenge."));
      }

      const payload = (await response.json()) as {
        deletedRuns?: number;
        filesRemoved?: number;
      };

      setChallenges((current) => current.filter((item) => item.id !== challenge.id));
      setCtfs((current) =>
        current.map((ctf) =>
          ctf.id === challenge.ctfId
            ? {
                ...ctf,
                challengeCount: Math.max(0, ctf.challengeCount - 1),
              }
            : ctf,
        ),
      );
      setNotice({
        kind: "success",
        text: `Deleted ${challenge.name}. Removed ${payload.deletedRuns ?? 0} runs and ${payload.filesRemoved ?? 0} log files.`,
      });
      router.refresh();
    } catch (error) {
      setNotice({
        kind: "error",
        text: error instanceof Error ? error.message : "Failed to delete challenge.",
      });
    } finally {
      setPendingKey(null);
    }
  }

  async function handleDeleteCtf(ctf: CTFSourceSummary) {
    const confirmed = window.confirm(
      `Delete the CTF "${ctf.name}" and all of its imported challenges? This removes the full imported source from disk.`,
    );
    if (!confirmed) {
      return;
    }

    const actionKey = `ctf:${ctf.id}`;
    setPendingKey(actionKey);
    setNotice(null);

    try {
      const response = await fetch(`/api/ctfs/${ctf.id}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        throw new Error(await parseErrorMessage(response, "Failed to delete CTF."));
      }

      const payload = (await response.json()) as {
        deletedChallenges?: number;
        deletedRuns?: number;
      };

      setCtfs((current) => current.filter((item) => item.id !== ctf.id));
      setChallenges((current) => current.filter((item) => item.ctfId !== ctf.id));
      setNotice({
        kind: "success",
        text: `Deleted ${ctf.name}. Removed ${payload.deletedChallenges ?? 0} challenges and ${payload.deletedRuns ?? 0} stored runs.`,
      });
      router.refresh();
    } catch (error) {
      setNotice({
        kind: "error",
        text: error instanceof Error ? error.message : "Failed to delete CTF.",
      });
    } finally {
      setPendingKey(null);
    }
  }

  return (
    <div className="page-shell">
      <section
        aria-labelledby="ctf-browser-heading"
        className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-end"
      >
        <div className="w-full sm:w-96">
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by CTF, URL, challenge, category, or path"
            aria-label="Search CTF sources and challenges"
            className="h-10 border-input bg-background pl-10"
          />
          <Search className="pointer-events-none relative -mt-7 ml-3 size-4 text-muted-foreground" />
        </div>
      </section>

      <Card className="mb-6 border-border bg-card shadow-none">
        <CardHeader className="pb-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div className="space-y-1">
              <CardTitle className="text-base text-card-foreground">Source Summary</CardTitle>
              <CardDescription>
                Review imported sources before deleting a full CTF or drilling into a challenge set.
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="secondary" className="font-medium">
                {sourceCount} source{sourceCount === 1 ? "" : "s"}
              </Badge>
              <Badge variant="outline">
                {challengeCount} challenge{challengeCount === 1 ? "" : "s"}
              </Badge>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {!filteredSources.length ? (
            <div className="rounded-lg border border-dashed border-border bg-background px-6 py-10 text-center text-sm text-muted-foreground">
              No CTF sources match this filter.
            </div>
          ) : (
            <div className="max-h-[26rem] overflow-auto rounded-md border border-border/60">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Source</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Challenges</TableHead>
                    <TableHead>Last Import</TableHead>
                    <TableHead>Updated</TableHead>
                    <TableHead className="w-[11rem] text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredSources.map((ctf) => {
                    const deletable = ctf.baseUrl !== LOCAL_SOURCE_URL;
                    const isSelected = selectedSource?.id === ctf.id;
                    const ctfPending = pendingKey === `ctf:${ctf.id}`;

                    return (
                      <TableRow
                        key={ctf.id}
                        data-state={isSelected ? "selected" : undefined}
                        className={cn(isSelected && "bg-muted/40")}
                      >
                        <TableCell>
                          <div className="space-y-1">
                            <div className="flex items-center gap-2">
                              <button
                                type="button"
                                onClick={() => setSelectedCtfId(ctf.id)}
                                className="text-left text-sm font-medium text-foreground hover:underline"
                              >
                                {ctf.name}
                              </button>
                              <Badge variant={deletable ? "secondary" : "outline"}>
                                {deletable ? "Imported" : "Local"}
                              </Badge>
                            </div>
                            <p className="font-mono text-xs text-muted-foreground">{ctf.baseUrl}</p>
                          </div>
                        </TableCell>
                        <TableCell className="text-muted-foreground">{ctf.lastImportStatus}</TableCell>
                        <TableCell>{ctf.challengeCount}</TableCell>
                        <TableCell className="text-muted-foreground">{formatDate(ctf.lastImportAt)}</TableCell>
                        <TableCell className="text-muted-foreground">{formatDate(ctf.updatedAt)}</TableCell>
                        <TableCell>
                          <div className="flex justify-end gap-2">
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={() => setSelectedCtfId(ctf.id)}
                            >
                              Inspect
                            </Button>
                            <Button
                              type="button"
                              variant="destructive"
                              size="sm"
                              onClick={() => handleDeleteCtf(ctf)}
                              disabled={!deletable || ctfPending || pendingKey !== null}
                              className="gap-1.5"
                            >
                              {ctfPending ? (
                                <RefreshCw className="size-3.5 animate-spin" />
                              ) : (
                                <Trash2 className="size-3.5" />
                              )}
                              Delete
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {notice ? (
        <p
          className={cn(
            "mb-4 rounded-md px-4 py-3 text-sm",
            notice.kind === "success"
              ? "border border-primary/35 bg-primary/10 text-foreground"
              : "border border-destructive/40 bg-destructive/10 text-destructive",
          )}
        >
          {notice.text}
        </p>
      ) : null}

      {selectedSource ? (
        <Card className="border-border bg-card shadow-none">
          <CardHeader className="space-y-3 pb-4">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div className="space-y-1 w-full">
                <CardTitle className="text-lg text-card-foreground flex items-center justify-between">
                  {selectedSource.name}
                  <Button 
                    variant="ghost" 
                    size="icon" 
                    className="h-8 w-8 text-muted-foreground" 
                    onClick={() => setSelectedCtfId(null)}
                  >
                    <X className="size-4" />
                    <span className="sr-only">Close Inspect</span>
                  </Button>
                </CardTitle>
                <CardDescription>
                  Review the current challenge set and delete stale imported challenges one at a time.
                </CardDescription>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge variant="outline">
                  {selectedSource.visibleChallenges.length} visible challenge
                  {selectedSource.visibleChallenges.length === 1 ? "" : "s"}
                </Badge>
                <Badge variant="outline">{selectedSource.lastImportStatus}</Badge>
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-lg border border-border bg-background px-4 py-3">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Source URL</p>
                <p className="mt-1 break-all font-mono text-xs text-foreground">
                  {selectedSource.baseUrl}
                </p>
              </div>
              <div className="rounded-lg border border-border bg-background px-4 py-3">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Challenges Root</p>
                <p className="mt-1 break-all font-mono text-xs text-foreground">
                  {selectedSource.challengesRoot}
                </p>
              </div>
              <div className="rounded-lg border border-border bg-background px-4 py-3">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Last Import</p>
                <p className="mt-1 text-sm text-foreground">{formatDate(selectedSource.lastImportAt)}</p>
              </div>
              <div className="rounded-lg border border-border bg-background px-4 py-3">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Updated</p>
                <p className="mt-1 text-sm text-foreground">{formatDate(selectedSource.updatedAt)}</p>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {!selectedSource.visibleChallenges.length ? (
              <div className="rounded-lg border border-dashed border-border bg-background px-6 py-10 text-center text-sm text-muted-foreground">
                {selectedSource.challenges.length
                  ? "No challenges in this source match the current filter."
                  : "No challenges are available for this source yet."}
              </div>
            ) : (
              <div className="max-h-[32rem] overflow-auto rounded-md border border-border/60">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Challenge</TableHead>
                      <TableHead>Category</TableHead>
                      <TableHead>Value</TableHead>
                      <TableHead>Runs</TableHead>
                      <TableHead>State</TableHead>
                      <TableHead>Updated</TableHead>
                      <TableHead className="min-w-[14rem]">Path</TableHead>
                      <TableHead className="w-[8rem] text-right">Action</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {selectedSource.visibleChallenges.map((challenge) => {
                      const deletable = selectedSource.baseUrl !== LOCAL_SOURCE_URL;
                      const challengePending = pendingKey === `challenge:${challenge.id}`;

                      return (
                        <TableRow key={challenge.id}>
                          <TableCell>
                            <div className="space-y-1">
                              <p className="font-medium text-foreground">{challenge.name}</p>
                              <p className="line-clamp-2 text-xs text-muted-foreground">
                                {challenge.description || "No description provided."}
                              </p>
                            </div>
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {challenge.category || "uncategorized"}
                          </TableCell>
                          <TableCell>{challenge.value || 0}</TableCell>
                          <TableCell>{challenge.runCount}</TableCell>
                          <TableCell className="text-muted-foreground">{challenge.state}</TableCell>
                          <TableCell className="text-muted-foreground">
                            {formatDate(challenge.updatedAt)}
                          </TableCell>
                          <TableCell className="font-mono text-xs text-muted-foreground">
                            {challenge.path}
                          </TableCell>
                          <TableCell>
                            <div className="flex justify-end">
                              <Button
                                type="button"
                                variant="destructive"
                                size="sm"
                                onClick={() => handleDeleteChallenge(challenge)}
                                disabled={!deletable || challengePending || pendingKey !== null}
                                className="gap-1.5"
                              >
                                {challengePending ? (
                                  <RefreshCw className="size-3.5 animate-spin" />
                                ) : (
                                  <Trash2 className="size-3.5" />
                                )}
                                Delete
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
