"use client";

import { useEffect } from "react";
import { ChevronsUpDown } from "lucide-react";
import { cn } from "@/lib/cn";
import { SideNavItem } from "./SideNavItem";
import { StatusDot } from "./StatusDot";

type SideNavProps = {
  currentPage: string;
  onPageChange: (pageId: string) => void;
  mobileOpen?: boolean;
  onMobileClose?: () => void;
};

export function SideNav({ currentPage, onPageChange, mobileOpen = false, onMobileClose }: SideNavProps) {
  useEffect(() => {
    onMobileClose?.();
  }, [currentPage, onMobileClose]);

  useEffect(() => {
    if (!mobileOpen) return;

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onMobileClose?.();
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [mobileOpen, onMobileClose]);

  return (
    <>
      <button
        type="button"
        aria-label="Close sidebar"
        className={cn(
          "fixed inset-x-0 top-14 bottom-0 z-30 bg-black/65 md:hidden transition-opacity",
          mobileOpen ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={onMobileClose}
      />

      <aside
        className={cn(
          "fixed left-0 top-14 z-40 w-64 shrink-0 border-r border-bd1 bg-bg1 flex flex-col h-[calc(100dvh-56px)] transition-transform duration-200 ease-deri md:sticky md:z-10 md:w-60 md:h-[calc(100vh-56px)] md:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="px-3 pt-3 pb-2">
          <button className="w-full flex items-center gap-2.5 h-9 px-2 rounded-md border border-bd1 ghost text-left focus-ring">
            <div className="w-6 h-6 rounded-[5px] bg-bg3 border border-bd1 flex items-center justify-center num text-[11px] text-fg1">
              K
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-[12px] text-fg1 leading-tight truncate">kornkasem</div>
              <div className="text-[10.5px] text-fg3 leading-tight truncate">
                Solo workspace
              </div>
            </div>
            <ChevronsUpDown size={12} strokeWidth={1.75} className="text-fg3" />
          </button>
        </div>

        <nav className="px-2 flex-1 overflow-y-auto nice-scroll mt-2">
          <div className="px-2 pt-2 pb-1.5 label">Dashboard</div>
          <div className="flex flex-col gap-0.5">
            <SideNavItem icon="LayoutDashboard" label="Overview" pageId="overview" currentPage={currentPage} onClick={onPageChange} />
            <SideNavItem icon="Wallet" label="Portfolio" pageId="portfolio" currentPage={currentPage} onClick={onPageChange} />
          </div>

          <div className="px-2 pt-5 pb-1.5 label">Activity</div>
          <div className="flex flex-col gap-0.5">
            <SideNavItem icon="ListOrdered" label="Trades" pageId="trades" currentPage={currentPage} onClick={onPageChange} />
            <SideNavItem icon="History" label="History" pageId="history" currentPage={currentPage} onClick={onPageChange} />
          </div>

          <div className="px-2 pt-5 pb-1.5 label">System</div>
          <div className="flex flex-col gap-0.5">
            <SideNavItem icon="Activity" label="Health" pageId="health" currentPage={currentPage} onClick={onPageChange} />
          </div>
        </nav>

        <div className="border-t border-bd1 px-3 py-2.5 flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <StatusDot tone="long" />
            <span className="label text-[9.5px]">All systems</span>
          </div>
          <span className="num text-[10.5px] text-fg3">v0.42.1</span>
        </div>
      </aside>
    </>
  );
}
