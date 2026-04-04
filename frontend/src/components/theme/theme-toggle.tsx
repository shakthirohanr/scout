"use client";

import { MoonStar, SunMedium } from "lucide-react";

import { useTheme } from "@/components/theme/theme-provider";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useMounted } from "@/hooks/use-mounted";

export function ThemeToggle() {
  const mounted = useMounted();
  const { resolvedTheme, setTheme } = useTheme();
  const isDark = resolvedTheme !== "light";

  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="rounded-full border-border/70 bg-card/75 backdrop-blur-sm"
            aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
            onClick={() => {
              if (!mounted) {
                return;
              }

              setTheme(isDark ? "light" : "dark");
            }}
          />
        }
      >
        {mounted && isDark ? (
          <SunMedium className="size-4" aria-hidden="true" />
        ) : (
          <MoonStar className="size-4" aria-hidden="true" />
        )}
      </TooltipTrigger>
      <TooltipContent side="bottom">
        {isDark ? "Use light mode" : "Use dark mode"}
      </TooltipContent>
    </Tooltip>
  );
}
