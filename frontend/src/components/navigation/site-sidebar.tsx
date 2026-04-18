"use client";

import Link from "next/link";
import { Home, ListChecks, FolderOpen, PanelLeft, PanelLeftClose, Menu } from "lucide-react";
import { usePathname } from "next/navigation";
import { useMemo, useState, useSyncExternalStore } from "react";

import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

import type { ChallengeCatalogItem } from "@/lib/types";

const SIDEBAR_COLLAPSED_KEY = "cryptoagent-sidebar-collapsed";
const SIDEBAR_PREFERENCE_EVENT = "cryptoagent-sidebar-preference-change";

type NavItem = {
  href: string;
  label: string;
  icon: typeof Home;
  active: boolean;
};

function subscribeToSidebarPreference(onStoreChange: () => void): () => void {
  if (typeof window === "undefined") {
    return () => {};
  }
  const handleChange = () => onStoreChange();
  window.addEventListener("storage", handleChange);
  window.addEventListener(SIDEBAR_PREFERENCE_EVENT, handleChange);
  return () => {
    window.removeEventListener("storage", handleChange);
    window.removeEventListener(SIDEBAR_PREFERENCE_EVENT, handleChange);
  };
}

function getSidebarPreferenceSnapshot(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true";
}

function getSidebarPreferenceServerSnapshot(): boolean {
  return false;
}

function setSidebarPreference(collapsed: boolean): void {
  window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(collapsed));
  window.dispatchEvent(new Event(SIDEBAR_PREFERENCE_EVENT));
}

export function SiteSidebar({
  runningChallenges = [],
}: {
  runningChallenges?: ChallengeCatalogItem[];
}) {
  const pathname = usePathname();
  const collapsed = useSyncExternalStore(
    subscribeToSidebarPreference,
    getSidebarPreferenceSnapshot,
    getSidebarPreferenceServerSnapshot,
  );
  const [mobileOpen, setMobileOpen] = useState(false);

  const navItems = useMemo<NavItem[]>(() => {
    const challengesActive = pathname === "/challenges" || pathname.startsWith("/challenge/");
    const ctfsActive = pathname === "/ctfs";
    return [
      { href: "/", label: "Home", icon: Home, active: pathname === "/" },
      { href: "/ctfs", label: "CTFs", icon: FolderOpen, active: ctfsActive },
      { href: "/challenges", label: "Challenges", icon: ListChecks, active: challengesActive },
    ];
  }, [pathname]);

  return (
    <>
      <aside
        className={cn(
          "hidden h-full shrink-0 flex-col border-r border-border bg-sidebar md:flex",
          collapsed ? "w-14" : "w-52",
        )}
      >
        <div className="flex items-center justify-between border-b border-border px-3 py-3">
          <Link
            href="/"
            className={cn(
              "truncate text-sm font-semibold text-sidebar-foreground",
              collapsed && "mx-auto text-center",
            )}
          >
            {collapsed ? "CA" : "CryptoAgent"}
          </Link>
          {!collapsed && (
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              onClick={() => setSidebarPreference(true)}
              aria-label="Collapse sidebar"
            >
              <PanelLeftClose className="size-4" aria-hidden="true" />
            </Button>
          )}
        </div>

        {collapsed && (
          <div className="border-b border-border px-2 py-2">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              onClick={() => setSidebarPreference(false)}
              aria-label="Expand sidebar"
              className="w-full"
            >
              <PanelLeft className="size-4" aria-hidden="true" />
            </Button>
          </div>
        )}

        <nav className="flex-1 space-y-0.5 p-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isChallenges = item.label === "Challenges";
            return (
              <div key={item.href} className="flex flex-col">
                <Link
                  href={item.href}
                  className={cn(
                    "flex h-8 items-center gap-2 rounded-md px-2 text-sm font-medium transition-colors",
                    collapsed && "justify-center px-0",
                    item.active && !isChallenges
                      ? "bg-sidebar-accent text-sidebar-accent-foreground"
                      : "text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground",
                  )}
                >
                  <Icon className="size-4 shrink-0" aria-hidden="true" />
                  {!collapsed && <span className="truncate">{item.label}</span>}
                </Link>
                {isChallenges && !collapsed && runningChallenges.length > 0 && (
                  <div className="ml-4 mt-1 space-y-0.5 border-l border-border pl-3">
                    {runningChallenges.map((c) => {
                      const cActive = pathname.startsWith(`/challenge/${c.id}`);
                      return (
                        <Link
                          key={c.id}
                          href={`/challenge/${encodeURIComponent(c.id)}`}
                          className={cn(
                            "flex h-7 items-center rounded-md px-2 text-xs transition-colors",
                            cActive
                              ? "bg-sidebar-accent text-sidebar-accent-foreground"
                              : "text-sidebar-foreground/60 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground",
                          )}
                        >
                          <span className="truncate">{c.name}</span>
                        </Link>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </nav>
      </aside>

      <div className="fixed top-3 left-3 z-50 md:hidden">
        <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
          <SheetTrigger
            render={
              <Button
                type="button"
                variant="outline"
                size="icon"
                aria-label="Open navigation"
              />
            }
          >
            <Menu className="size-4" aria-hidden="true" />
          </SheetTrigger>
          <SheetContent side="left" className="w-72 p-0">
            <SheetHeader className="border-b border-border bg-sidebar px-4 py-4 text-left">
              <SheetTitle>CryptoAgent</SheetTitle>
            </SheetHeader>
            <nav className="space-y-0.5 p-2">
              {navItems.map((item) => {
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setMobileOpen(false)}
                    className={cn(
                      "flex h-8 items-center gap-2 rounded-md px-2 text-sm font-medium transition-colors",
                      item.active
                        ? "bg-sidebar-accent text-sidebar-accent-foreground"
                        : "text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground",
                    )}
                  >
                    <Icon className="size-4 shrink-0" aria-hidden="true" />
                    <span className="truncate">{item.label}</span>
                  </Link>
                );
              })}
            </nav>
          </SheetContent>
        </Sheet>
      </div>
    </>
  );
}
