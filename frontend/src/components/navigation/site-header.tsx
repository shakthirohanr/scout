"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { ThemeToggle } from "@/components/theme/theme-toggle";

const ROUTE_DATA: Record<string, { title: string; description: string }> = {
  "/": {
    title: "Challenge Catalog",
    description: "Import CTFs from CTFd, browse challenges, and launch the solver agent.",
  },
  "/ctfs": {
    title: "CTF Sources",
    description:
      "Browse imported CTFs, inspect their challenge sets, and remove stale sources or individual imported challenges.",
  },
  "/challenges": {
    title: "Challenges",
    description: "Running and finished challenge sessions.",
  },
};

export function SiteHeader() {
  const pathname = usePathname();

  const activeData = ROUTE_DATA[pathname] || {
    title: "CryptoAgent",
    description: "Import CTFs, launch runs, and review challenge traces from one workspace.",
  };

  return (
    <header className="shrink-0 border-b border-border/60 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="flex items-center justify-between gap-4 py-4 pr-5 pl-16 sm:pr-6 sm:pl-20 md:px-7 lg:px-10">
        <div className="min-w-0">
          <Link
            href="/"
            className="inline-flex items-center text-xl sm:text-2xl font-extrabold tracking-tight text-foreground transition-opacity hover:opacity-80"
            aria-label="Go to the CryptoAgent home page"
          >
            {activeData.title}
          </Link>
          <p className="mt-1 hidden text-sm text-muted-foreground sm:block truncate">
            {activeData.description}
          </p>
        </div>

        <ThemeToggle />
      </div>
    </header>
  );
}
