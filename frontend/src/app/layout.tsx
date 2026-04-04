import type { Metadata } from "next";
import { IBM_Plex_Mono, Space_Grotesk } from "next/font/google";

import { SiteSidebar } from "@/components/navigation/site-sidebar";
import { ThemeProvider } from "@/components/theme/theme-provider";
import { TooltipProvider } from "@/components/ui/tooltip";

import "./globals.css";

const headingFont = Space_Grotesk({
  variable: "--font-space-grotesk",
  subsets: ["latin"],
});

const monoFont = IBM_Plex_Mono({
  variable: "--font-ibm-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "CryptoAgent",
  description: "CryptoAgent",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${headingFont.variable} ${monoFont.variable} h-full antialiased dark`}
    >
      <body className="h-full overflow-hidden">
        <ThemeProvider>
          <TooltipProvider>
            <div className="flex h-full w-full overflow-hidden">
              <SiteSidebar />
              <main className="min-h-0 min-w-0 flex-1 overflow-y-auto">{children}</main>
            </div>
          </TooltipProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
