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
import { useMounted } from "@/hooks/use-mounted";
import { terminalThemes } from "@/lib/terminal";
import type { TraceSummary } from "@/lib/types";

type LogTerminalProps = {
  summary: TraceSummary | null;
  content: string;
  onRefresh: () => void;
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
}: LogTerminalProps) {
  const mounted = useMounted();
  const { resolvedTheme } = useTheme();
  const activeTheme = resolvedTheme === "light" ? "light" : "dark";
  const terminalRootRef = useRef<HTMLDivElement | null>(null);
  const instanceRef = useRef<TerminalInstance | null>(null);
  const [searchValue, setSearchValue] = useState("");
  const deferredSearch = useDeferredValue(searchValue);

  const writeContent = useEffectEvent((nextContent: string) => {
    const instance = instanceRef.current;
    if (!instance) {
      return;
    }

    instance.terminal.reset();
    instance.terminal.options.theme = terminalThemes[activeTheme];
    instance.terminal.write(nextContent || "No trace output available yet.\n");
    instance.terminal.scrollToBottom();
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
      fontSize: 13,
      lineHeight: 1.35,
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
    <Card className="gap-0 rounded-none border-border/60 bg-card py-0 shadow-none">
      <CardHeader className="flex flex-col gap-4 border-b border-border/60 bg-[#e7eddc] px-5 py-4 md:flex-row md:items-center md:justify-between dark:bg-muted/35">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            {summary ? <StatusBadge status={summary.status} /> : null}
          </div>
          <div>
            <CardTitle className="text-lg font-semibold text-foreground">
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
            className="min-w-0 flex-1 border-border/60 bg-background/65 sm:w-72"
          />

          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              className="border-border/60 bg-background/65"
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
              className="border-border/60 bg-background/65"
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
              className="gap-2 border-border/60 bg-background/65"
              onClick={onRefresh}
            >
              Refresh
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="terminal-shell relative p-0">
        <div
          ref={terminalRootRef}
          className="h-120 w-full px-4 py-4 md:h-136"
          aria-label="Agent log terminal"
        />
      </CardContent>
    </Card>
  );
}
