"use client";

import Link from "next/link";

import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { ChallengeItem } from "@/lib/types";

type ChallengeSidebarProps = {
  challenges: ChallengeItem[];
  activeChallengeId: string | null;
  className?: string;
};

function formatUpdatedAt(value: string | null): string {
  if (!value) return "No updates";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function ChallengeSidebar({
  challenges,
  activeChallengeId,
  className,
}: ChallengeSidebarProps) {
  return (
    <div className={cn("flex min-h-0 flex-col", className)}>
      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-1">
          {challenges.map((challenge) => {
            const isActive = challenge.id === activeChallengeId;
            return (
              <Link
                key={challenge.id}
                href={`/challenge/${encodeURIComponent(challenge.id)}`}
                className={cn(
                  "block rounded-md border p-3 text-left transition-colors",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
                  isActive
                    ? "border-primary/20 bg-accent"
                    : "border-border bg-background hover:bg-muted/30",
                )}
              >
                <p className="text-sm font-medium text-foreground">
                  {challenge.name}
                </p>
                <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
                  <span>{challenge.traceCount} trace{challenge.traceCount === 1 ? "" : "s"}</span>
                  <span>{formatUpdatedAt(challenge.updatedAt)}</span>
                </div>
              </Link>
            );
          })}

          {!challenges.length && (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No challenges available.
            </p>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
