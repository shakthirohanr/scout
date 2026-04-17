"use client";

import "@xterm/xterm/css/xterm.css";

import { useDeferredValue, useEffect, useEffectEvent, useRef, useState } from "react";
import { FitAddon } from "@xterm/addon-fit";
import { SearchAddon } from "@xterm/addon-search";
import { WebLinksAddon } from "@xterm/addon-web-links";
import { Terminal } from "@xterm/xterm";

import { useTheme } from "@/components/theme/theme-provider";
import { StatusBadge } from "@/components/dashboard/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useMounted } from "@/hooks/use-mounted";
import { terminalThemes } from "@/lib/terminal";
import type { TraceSummary } from "@/lib/types";

type LogTerminalProps = {
  summary: TraceSummary | null;
  content: string;
  onRefresh: () => void;
  className?: string;
};

type TerminalInstance = {
  terminal: Terminal;
  fitAddon: FitAddon;
  searchAddon: SearchAddon;
  resizeObserver: ResizeObserver;
};

export function LogTerminal({
  summary,
  content,
  onRefresh,
  className,
}: LogTerminalProps) {
  const mounted = useMounted();
  const { resolvedTheme } = useTheme();
  const activeTheme = resolvedTheme === "light" ? "light" : "dark";
  const terminalRootRef = useRef<HTMLDivElement | null>(null);
  const instanceRef = useRef<TerminalInstance | null>(null);
  const writeQueueRef = useRef<string[]>([]);
  const flushFrameRef = useRef<number | null>(null);
  const writeInFlightRef = useRef(false);
  const [searchValue, setSearchValue] = useState("");
  const deferredSearch = useDeferredValue(searchValue);

  const prevContentRef = useRef<string>("");

  const flushWriteQueue = useEffectEvent(function runFlushWriteQueue() {
    const instance = instanceRef.current;
    if (!instance || writeInFlightRef.current || !writeQueueRef.current.length) {
      return;
    }

    writeInFlightRef.current = true;
    const chunk = writeQueueRef.current.join("");
    writeQueueRef.current = [];

    instance.terminal.write(chunk, () => {
      writeInFlightRef.current = false;
      if (writeQueueRef.current.length) {
        runFlushWriteQueue();
      }
    });
  });

  const enqueueWrite = useEffectEvent((chunk: string) => {
    if (!chunk) {
      return;
    }

    writeQueueRef.current.push(chunk);
    if (flushFrameRef.current !== null) {
      return;
    }

    flushFrameRef.current = window.requestAnimationFrame(() => {
      flushFrameRef.current = null;
      flushWriteQueue();
    });
  });

  const writeContent = useEffectEvent((nextContent: string) => {
    const instance = instanceRef.current;
    if (!instance) {
      return;
    }

    instance.terminal.options.theme = terminalThemes[activeTheme];
    
    const safeContent = nextContent || "No trace output available yet.\n";
    const prevContent = prevContentRef.current;
    
    if (safeContent === prevContent) {
      return;
    }

    if (prevContent && safeContent.startsWith(prevContent)) {
      const appended = safeContent.slice(prevContent.length);
      if (appended) {
        // Only auto-scroll if the viewport is currently at the bottom
        // This prevents the scrollbar from jumping while the user is reading upwards
        const buffer = instance.terminal.buffer.active;
        const isAtBottom = buffer.viewportY === buffer.baseY;

        enqueueWrite(appended);

        if (isAtBottom) {
          instance.terminal.scrollToBottom();
        }
      }
    } else if (prevContent.startsWith(safeContent)) {
      // Ignore out-of-order stale snapshots to avoid destructive redraw flicker.
      return;
    } else {
      writeQueueRef.current = [];
      writeInFlightRef.current = false;
      instance.terminal.reset();
      enqueueWrite(safeContent);
      instance.terminal.scrollToBottom();
    }
    
    prevContentRef.current = safeContent;
  });

  useEffect(() => {
    if (!mounted || !terminalRootRef.current || instanceRef.current) {
      return;
    }

    const terminal = new Terminal({
      allowTransparency: true,
      convertEol: true,
      cursorBlink: false,
      disableStdin: true,
      fontFamily: "var(--font-mono)",
      fontSize: 14,
      lineHeight: 1.45,
      smoothScrollDuration: 120,
      scrollSensitivity: 1.1,
      fastScrollSensitivity: 4,
      scrollback: 7000,
      theme: terminalThemes[activeTheme],
    });
    const fitAddon = new FitAddon();
    const searchAddon = new SearchAddon();
    const webLinksAddon = new WebLinksAddon();

    terminal.loadAddon(fitAddon);
    terminal.loadAddon(searchAddon);
    terminal.loadAddon(webLinksAddon);
    terminal.open(terminalRootRef.current);
    terminal.attachCustomWheelEventHandler(() => true);
    fitAddon.fit();

    const resizeObserver = new ResizeObserver(() => {
      fitAddon.fit();
    });

    resizeObserver.observe(terminalRootRef.current);

    instanceRef.current = {
      terminal,
      fitAddon,
      searchAddon,
      resizeObserver,
    };

    writeContent(content);

    return () => {
      if (flushFrameRef.current !== null) {
        window.cancelAnimationFrame(flushFrameRef.current);
        flushFrameRef.current = null;
      }
      writeQueueRef.current = [];
      writeInFlightRef.current = false;
      resizeObserver.disconnect();
      terminal.dispose();
      instanceRef.current = null;
    };
  }, [activeTheme, content, mounted]);

  useEffect(() => {
    const instance = instanceRef.current;
    if (!instance) {
      return;
    }

    instance.terminal.options.theme = terminalThemes[activeTheme];
  }, [activeTheme]);

  useEffect(() => {
    writeContent(content);
  }, [content]);

  useEffect(() => {
    const instance = instanceRef.current;
    if (!instance || !deferredSearch.trim()) {
      return;
    }

    instance.searchAddon.findNext(deferredSearch, {
      incremental: true,
      caseSensitive: false,
    });
  }, [deferredSearch]);

  if (!mounted) {
    return <Skeleton className="h-120 w-full rounded-none" />;
  }

  return (
    <Card className={cn("gap-0 rounded-none flex flex-col border-border/60 bg-card py-0 shadow-none", className)}>
      <CardHeader className="flex flex-col gap-5 border-b border-border/60 bg-muted/35 px-6 py-5 md:flex-row md:items-center md:justify-between">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            {summary ? <StatusBadge status={summary.status} /> : null}
          </div>
          <div>
            <CardTitle className="text-xl font-semibold text-foreground">
              {summary ? `${summary.challengeName} · ${summary.modelName}` : "No trace selected"}
            </CardTitle>
          </div>
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <Input
            value={searchValue}
            onChange={(event) => setSearchValue(event.target.value)}
            placeholder="Search in trace output"
            aria-label="Search terminal output"
            className="h-11 min-w-0 flex-1 border-border/60 bg-background/65 text-base sm:w-80"
          />

          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              className="h-11 px-4 text-base"
              onClick={() => {
                const instance = instanceRef.current;
                if (!instance || !searchValue.trim()) {
                  return;
                }

                instance.searchAddon.findPrevious(searchValue, {
                  caseSensitive: false,
                });
              }}
              aria-label="Find previous match"
            >
              Prev
            </Button>
            <Button
              type="button"
              variant="outline"
              className="h-11 px-4 text-base"
              onClick={() => {
                const instance = instanceRef.current;
                if (!instance || !searchValue.trim()) {
                  return;
                }

                instance.searchAddon.findNext(searchValue, {
                  caseSensitive: false,
                });
              }}
              aria-label="Find next match"
            >
              Next
            </Button>
            <Button
              type="button"
              variant="outline"
              className="h-11 gap-2 px-4 text-base"
              onClick={onRefresh}
            >
              Refresh
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="terminal-shell relative p-0 flex-1 min-h-0 overscroll-contain">
        <div
          ref={terminalRootRef}
          className="h-full w-full pl-5 py-5 overscroll-contain"
          aria-label="Agent log terminal"
        />
      </CardContent>
    </Card>
  );
}
