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
  if (!value) {
    return "No updates";
  }
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
      <ScrollArea className="min-h-0 flex-1 pr-3">
        <div className="space-y-3">
          {challenges.map((challenge) => {
            const isActive = challenge.id === activeChallengeId;
            return (
              <Link
                key={challenge.id}
                href={`/challenge/${encodeURIComponent(challenge.id)}`}
                className={cn(
                  "block border p-5 text-left transition-colors",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70",
                  isActive
                    ? "border-primary/35 bg-accent/60"
                    : "border-border/60 bg-card/70 hover:border-primary/25 hover:bg-accent/45",
                )}
              >
                <p className="text-base font-semibold leading-tight text-foreground">
                  {challenge.name}
                </p>
                <div className="mt-3 flex items-center justify-between text-sm text-muted-foreground">
                  <span>{challenge.traceCount} trace{challenge.traceCount === 1 ? "" : "s"}</span>
                  <span>{formatUpdatedAt(challenge.updatedAt)}</span>
                </div>
              </Link>
            );
          })}

          {!challenges.length ? (
            <div className="border border-dashed border-border/70 bg-card/60 px-5 py-9 text-center text-base text-muted-foreground">
              No challenges available yet.
            </div>
          ) : null}
        </div>
      </ScrollArea>
    </div>
  );
}
