"use client";

import { usePathname } from "next/navigation";
import { SiteHeader } from "@/components/navigation/site-header";

export function ConditionalHeader() {
  const pathname = usePathname();
  
  if (pathname !== "/") {
    return null;
  }
  
  return <SiteHeader />;
}
