import Link from "next/link";

import { ThemeToggle } from "@/components/theme/theme-toggle";

export function SiteHeader() {
  return (
    <header className="shrink-0 border-b border-border/60 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="flex items-center justify-between gap-4 py-4 pr-5 pl-16 sm:pr-6 sm:pl-20 md:px-7 lg:px-10">
        <div className="min-w-0">
          <Link
            href="/"
            className="inline-flex items-center text-2xl font-semibold tracking-tight text-foreground transition-opacity hover:opacity-80"
            aria-label="Go to the CryptoAgent home page"
          >
            CryptoAgent
          </Link>
          <p className="mt-1 hidden text-sm text-muted-foreground sm:block">
            Import CTFs, launch runs, and review challenge traces from one workspace.
          </p>
        </div>

        <ThemeToggle />
      </div>
    </header>
  );
}
