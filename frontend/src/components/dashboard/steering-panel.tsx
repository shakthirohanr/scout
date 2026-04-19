"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

type SteeringPanelProps = {
  challengeId: string;
  activeRunIds: string[];
};

const MAX_STEERING_CHARS = 4000;

export function SteeringPanel({ challengeId, activeRunIds }: SteeringPanelProps) {
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [queuedAt, setQueuedAt] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  async function handleSubmit() {
    const trimmed = message.trim();
    if (!trimmed) {
      setError("Enter steering guidance before sending.");
      return;
    }

    setPending(true);
    setError(null);

    try {
      const body: Record<string, string> = { message: trimmed, source: "dashboard" };
      if (selectedRunId) {
        body.runId = selectedRunId;
      }

      const response = await fetch(`/api/challenges/${encodeURIComponent(challengeId)}/steer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { error?: string } | null;
        throw new Error(payload?.error || `Failed to steer run: ${response.status}`);
      }

      const payload = (await response.json()) as { createdAt?: string };
      setQueuedAt(payload.createdAt ?? new Date().toISOString());
      setMessage("");
      toast.success("Steering queued");
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Failed to queue steering guidance.",
      );
    } finally {
      setPending(false);
    }
  }

  const remaining = MAX_STEERING_CHARS - message.length;
  const showRunSelector = activeRunIds.length > 1;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">Steer Running Agent</CardTitle>
        <CardDescription className="text-xs">
          Send high-signal guidance while this challenge is actively running.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {showRunSelector && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-muted-foreground">Target:</span>
            <button
              type="button"
              onClick={() => setSelectedRunId(null)}
              className={cn(
                "inline-flex items-center rounded-full px-2 py-0.5 text-xs transition-colors",
                selectedRunId === null
                  ? "bg-surface-500 text-foreground"
                  : "bg-surface-300 text-muted-foreground hover:text-warm-hover",
              )}
            >
              All
            </button>
            {activeRunIds.map((runId, index) => (
              <button
                key={runId}
                type="button"
                onClick={() => setSelectedRunId(runId)}
                className={cn(
                  "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-mono transition-colors",
                  selectedRunId === runId
                    ? "bg-surface-500 text-foreground"
                    : "bg-surface-300 text-muted-foreground hover:text-warm-hover",
                )}
              >
                Agent {index + 1}
              </button>
            ))}
          </div>
        )}

        <Textarea
          value={message}
          onChange={(event) => setMessage(event.target.value.slice(0, MAX_STEERING_CHARS))}
          placeholder="Example: Prioritize timing attacks on nonce reuse in the signing endpoint."
          className="min-h-24 text-sm"
          aria-label="Steering guidance"
          disabled={pending}
        />

        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-muted-foreground">
            {remaining} characters remaining.
          </p>

          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                setMessage("");
                setError(null);
              }}
              disabled={pending || !message.length}
            >
              Clear
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={handleSubmit}
              disabled={pending || !message.trim().length}
            >
              {pending ? "Sending..." : "Send Steering"}
            </Button>
          </div>
        </div>

        {error && <p className="text-xs text-destructive">{error}</p>}

        {!error && queuedAt && (
          <p className="text-xs text-muted-foreground">
            Steering queued at {new Intl.DateTimeFormat("en-US", {
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
              hour12: false,
            }).format(new Date(queuedAt))}.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
