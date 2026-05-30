"use client";

import { useCallback, useState } from "react";
import { SideNav } from "@/components/chrome/SideNav";
import { TopNav } from "@/components/chrome/TopNav";

type AppShellProps = {
  currentPage: string;
  onPageChange: (page: any) => void;
  wsLatencyMs: number | null;
  children: React.ReactNode;
};

export function AppShell({ currentPage, onPageChange, wsLatencyMs, children }: AppShellProps) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const closeMobileNav = useCallback(() => setMobileNavOpen(false), []);
  const toggleMobileNav = useCallback(() => setMobileNavOpen((open) => !open), []);

  return (
    <div className="min-h-screen flex flex-col">
      <TopNav
        currentPage={currentPage}
        onPageChange={onPageChange}
        wsLatencyMs={wsLatencyMs}
        mobileNavOpen={mobileNavOpen}
        onMobileNavToggle={toggleMobileNav}
      />
      <div className="flex flex-1">
        <SideNav 
          currentPage={currentPage}
          onPageChange={onPageChange}
          mobileOpen={mobileNavOpen} 
          onMobileClose={closeMobileNav} 
        />
        <main className="flex-1 min-w-0">{children}</main>
      </div>
    </div>
  );
}
