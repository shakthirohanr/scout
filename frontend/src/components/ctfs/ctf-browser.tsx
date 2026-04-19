"use client";

import { RefreshCw, Trash2, X } from "lucide-react";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
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
  if (!value) return "N/A";
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
          return { ...ctf, challenges: sourceChallenges, visibleChallenges: sourceChallenges };
        }

        const visibleChallenges = sourceChallenges.filter((challenge) => {
          return (
            challenge.name.toLowerCase().includes(normalizedQuery) ||
            challenge.category.toLowerCase().includes(normalizedQuery) ||
            challenge.path.toLowerCase().includes(normalizedQuery)
          );
        });

        return { ...ctf, challenges: sourceChallenges, visibleChallenges };
      })
      .filter((ctf) => {
        if (!normalizedQuery) return true;
        const sourceMatch =
          ctf.name.toLowerCase().includes(normalizedQuery) ||
          ctf.slug.toLowerCase().includes(normalizedQuery) ||
          ctf.baseUrl.toLowerCase().includes(normalizedQuery) ||
          ctf.challengesRoot.toLowerCase().includes(normalizedQuery);
        return sourceMatch || ctf.visibleChallenges.length > 0;
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
    if (!confirmed) return;

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
            ? { ...ctf, challengeCount: Math.max(0, ctf.challengeCount - 1) }
            : ctf,
        ),
      );
      setNotice({
        kind: "success",
        text: `Deleted ${challenge.name}. Removed ${payload.deletedRuns ?? 0} runs and ${payload.filesRemoved ?? 0} log files.`,
      });
      toast.success("Challenge deleted");
      router.refresh();
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Failed to delete challenge.";
      setNotice({
        kind: "error",
        text: errorMessage,
      });
      toast.error("Delete failed", { description: errorMessage });
    } finally {
      setPendingKey(null);
    }
  }

  async function handleDeleteCtf(ctf: CTFSourceSummary) {
    const confirmed = window.confirm(
      `Delete the CTF "${ctf.name}" and all of its imported challenges? This removes the full imported source from disk.`,
    );
    if (!confirmed) return;

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
      toast.success("CTF deleted");
      router.refresh();
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Failed to delete CTF.";
      setNotice({
        kind: "error",
        text: errorMessage,
      });
      toast.error("Delete failed", { description: errorMessage });
    } finally {
      setPendingKey(null);
    }
  }

  return (
    <div className="page-shell">
      <section className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-end">
        <div className="w-full sm:w-80">
          <div className="relative">
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
              placeholder="Search by CTF, challenge, or category"
              aria-label="Search CTF sources and challenges"
              className="pl-9"
            />
          </div>
        </div>
      </section>

      <Card className="mb-6">
        <CardHeader className="px-6 pt-6 pb-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div className="space-y-1">
              <CardTitle className="text-sm font-medium uppercase tracking-wide text-muted-foreground">Source Summary</CardTitle>
              <CardDescription>
                Review imported sources before deleting a full CTF or drilling into a challenge set.
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="secondary">{sourceCount} source{sourceCount === 1 ? "" : "s"}</Badge>
              <Badge variant="outline">{challengeCount} challenge{challengeCount === 1 ? "" : "s"}</Badge>
            </div>
          </div>
        </CardHeader>
        <CardContent className="px-6 pb-6">
          {!filteredSources.length ? (
            <p className="py-10 text-center text-sm text-muted-foreground">
              No CTF sources match this filter.
            </p>
          ) : (
            <div className="max-h-[26rem] overflow-y-auto overflow-x-hidden rounded-md border border-border">
              <Table className="table-fixed">
                <TableHeader>
                  <TableRow>
                    <TableHead>Source</TableHead>
                    <TableHead className="hidden md:table-cell">Status</TableHead>
                    <TableHead>Challenges</TableHead>
                    <TableHead className="hidden sm:table-cell">Last Import</TableHead>
                    <TableHead className="hidden lg:table-cell">Updated</TableHead>
                    <TableHead className="w-[10rem] text-right">Actions</TableHead>
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
                        className={cn(isSelected && "bg-muted/30")}
                      >
                        <TableCell className="align-top">
                          <div className="space-y-0.5">
                            <div className="flex items-center gap-2">
                              <button
                                type="button"
                                onClick={() => setSelectedCtfId(ctf.id)}
                                className="min-w-0 break-words text-left text-sm font-medium text-foreground transition-colors hover:text-warm-hover"
                              >
                                {ctf.name}
                              </button>
                              <Badge
                                variant={deletable ? "secondary" : "outline"}
                                className="shrink-0 text-xs"
                              >
                                {deletable ? "Imported" : "Local"}
                              </Badge>
                            </div>
                            <p className="break-all whitespace-normal font-mono text-xs text-muted-foreground">
                              {ctf.baseUrl}
                            </p>
                            <div className="space-y-0.5 text-xs text-muted-foreground md:hidden">
                              <p>Status: {ctf.lastImportStatus}</p>
                              <p className="sm:hidden">Last import: {formatDate(ctf.lastImportAt)}</p>
                              <p className="lg:hidden">Updated: {formatDate(ctf.updatedAt)}</p>
                            </div>
                          </div>
                        </TableCell>
                        <TableCell className="hidden text-muted-foreground md:table-cell">
                          {ctf.lastImportStatus}
                        </TableCell>
                        <TableCell>{ctf.challengeCount}</TableCell>
                        <TableCell className="hidden text-muted-foreground sm:table-cell">
                          {formatDate(ctf.lastImportAt)}
                        </TableCell>
                        <TableCell className="hidden text-muted-foreground lg:table-cell">
                          {formatDate(ctf.updatedAt)}
                        </TableCell>
                        <TableCell className="align-top">
                          <div className="flex flex-wrap justify-end gap-2">
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

      {notice && (
        <p
          className={cn(
            "mb-4 rounded-md border px-3 py-2 text-sm",
            notice.kind === "success"
              ? "border-primary/20 bg-primary/8 text-foreground"
              : "border-destructive/30 bg-destructive/8 text-destructive",
          )}
        >
          {notice.text}
        </p>
      )}

      {selectedSource && (
        <Card>
          <CardHeader className="px-6 pt-6 pb-4 space-y-3">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div className="space-y-1 w-full">
                <CardTitle className="flex items-start justify-between gap-3 text-base text-foreground">
                  <span className="break-words">{selectedSource.name}</span>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className="text-muted-foreground"
                    onClick={() => setSelectedCtfId(null)}
                  >
                    <X className="size-4" />
                    <span className="sr-only">Close</span>
                  </Button>
                </CardTitle>
                <CardDescription>
                  Review the current challenge set and delete stale imported challenges.
                </CardDescription>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge variant="outline">
                  {selectedSource.visibleChallenges.length} visible
                </Badge>
                <Badge variant="outline">{selectedSource.lastImportStatus}</Badge>
              </div>
            </div>

            <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-md border border-border bg-background px-3 py-2">
                <p className="text-xs text-muted-foreground">Source URL</p>
                <p className="mt-0.5 break-all font-mono text-xs text-foreground">
                  {selectedSource.baseUrl}
                </p>
              </div>
              <div className="rounded-md border border-border bg-background px-3 py-2">
                <p className="text-xs text-muted-foreground">Challenges Root</p>
                <p className="mt-0.5 break-all font-mono text-xs text-foreground">
                  {selectedSource.challengesRoot}
                </p>
              </div>
              <div className="rounded-md border border-border bg-background px-3 py-2">
                <p className="text-xs text-muted-foreground">Last Import</p>
                <p className="mt-0.5 text-sm text-foreground">{formatDate(selectedSource.lastImportAt)}</p>
              </div>
              <div className="rounded-md border border-border bg-background px-3 py-2">
                <p className="text-xs text-muted-foreground">Updated</p>
                <p className="mt-0.5 text-sm text-foreground">{formatDate(selectedSource.updatedAt)}</p>
              </div>
            </div>
          </CardHeader>
          <CardContent className="px-6 pb-6">
            {!selectedSource.visibleChallenges.length ? (
              <p className="py-10 text-center text-sm text-muted-foreground">
                {selectedSource.challenges.length
                  ? "No challenges match the current filter."
                  : "No challenges available for this source."}
              </p>
            ) : (
              <div className="max-h-[32rem] overflow-y-auto overflow-x-hidden rounded-md border border-border">
                <Table className="table-fixed">
                  <TableHeader>
                    <TableRow>
                      <TableHead>Challenge</TableHead>
                      <TableHead className="hidden sm:table-cell">Category</TableHead>
                      <TableHead className="hidden md:table-cell">Value</TableHead>
                      <TableHead className="hidden lg:table-cell">Runs</TableHead>
                      <TableHead className="hidden md:table-cell">State</TableHead>
                      <TableHead className="hidden lg:table-cell">Updated</TableHead>
                      <TableHead className="hidden xl:table-cell">Path</TableHead>
                      <TableHead className="w-[6rem] text-right">Action</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {selectedSource.visibleChallenges.map((challenge) => {
                      const deletable = selectedSource.baseUrl !== LOCAL_SOURCE_URL;
                      const challengePending = pendingKey === `challenge:${challenge.id}`;

                      return (
                        <TableRow key={challenge.id}>
                          <TableCell className="align-top">
                            <div className="space-y-1">
                              <p className="break-words font-medium text-foreground">{challenge.name}</p>
                              <p className="whitespace-pre-wrap break-words text-xs text-muted-foreground">
                                {challenge.description || "No description provided."}
                              </p>
                              <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground sm:hidden">
                                <span>{challenge.category || "uncategorized"}</span>
                                <span>{challenge.value || 0} pts</span>
                                <span>{challenge.state}</span>
                              </div>
                              <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground md:hidden">
                                <span>{challenge.runCount} runs</span>
                                <span>Updated {formatDate(challenge.updatedAt)}</span>
                              </div>
                              <p className="break-all font-mono text-[11px] text-muted-foreground xl:hidden">
                                {challenge.path}
                              </p>
                            </div>
                          </TableCell>
                          <TableCell className="hidden text-muted-foreground sm:table-cell">
                            {challenge.category || "uncategorized"}
                          </TableCell>
                          <TableCell className="hidden md:table-cell">{challenge.value || 0}</TableCell>
                          <TableCell className="hidden lg:table-cell">{challenge.runCount}</TableCell>
                          <TableCell className="hidden text-muted-foreground md:table-cell">
                            {challenge.state}
                          </TableCell>
                          <TableCell className="hidden text-muted-foreground lg:table-cell">
                            {formatDate(challenge.updatedAt)}
                          </TableCell>
                          <TableCell className="hidden break-all font-mono text-xs text-muted-foreground xl:table-cell">
                            {challenge.path}
                          </TableCell>
                          <TableCell className="align-top">
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
      )}
    </div>
  );
}
