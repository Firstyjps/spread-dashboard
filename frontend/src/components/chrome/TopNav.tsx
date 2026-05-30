"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { Activity, Bell, LogOut, Menu, Search, Settings, User, X } from "lucide-react";
import { StatusDot } from "./StatusDot";
import { formatNumber } from "@/lib/format";

type TopNavProps = {
  currentPage: string;
  onPageChange: (pageId: string) => void;
  wsLatencyMs: number | null;
  mobileNavOpen?: boolean;
  onMobileNavToggle?: () => void;
};

const RECENT_PAGES = [
  { label: "Overview", pageId: "overview", description: "Main dashboard and metrics" },
  { label: "Portfolio", pageId: "portfolio", description: "Positions and balances" },
  { label: "Trades", pageId: "trades", description: "Recent order activity" },
  { label: "History", pageId: "history", description: "Historical metrics" },
  { label: "Health", pageId: "health", description: "System and connection health" },
];

export function TopNav({
  currentPage,
  onPageChange,
  wsLatencyMs,
  mobileNavOpen = false,
  onMobileNavToggle,
}: TopNavProps) {
  const { logout } = useAuth();
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const notificationsRef = useRef<HTMLDivElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);

  const filteredPages = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return RECENT_PAGES;

    return RECENT_PAGES.filter((page) =>
      `${page.label} ${page.description}`.toLowerCase().includes(query),
    );
  }, [searchQuery]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const isSearchShortcut = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k";

      if (isSearchShortcut) {
        event.preventDefault();
        setSearchOpen(true);
        setNotificationsOpen(false);
        setUserMenuOpen(false);
        return;
      }

      if (event.key === "Escape") {
        setSearchOpen(false);
        setNotificationsOpen(false);
        setUserMenuOpen(false);
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  useEffect(() => {
    if (!searchOpen) return;

    searchInputRef.current?.focus();
  }, [searchOpen]);

  useEffect(() => {
    function handleMouseDown(event: MouseEvent) {
      const target = event.target as Node;

      if (notificationsRef.current && !notificationsRef.current.contains(target)) {
        setNotificationsOpen(false);
      }

      if (userMenuRef.current && !userMenuRef.current.contains(target)) {
        setUserMenuOpen(false);
      }
    }

    document.addEventListener("mousedown", handleMouseDown);
    return () => document.removeEventListener("mousedown", handleMouseDown);
  }, []);

  function openSearch() {
    setSearchOpen(true);
    setNotificationsOpen(false);
    setUserMenuOpen(false);
  }

  function closeSearch() {
    setSearchOpen(false);
    setSearchQuery("");
  }

  async function handleLogout() {
    setLoggingOut(true);
    setUserMenuOpen(false);
    localStorage.removeItem("auth_token");
    window.location.reload();
  }

  return (
    <header className="h-14 shrink-0 border-b border-bd1 bg-bg1 flex items-center px-4 gap-4 sticky top-0 z-30">
      <button
        type="button"
        aria-label={mobileNavOpen ? "Close navigation" : "Open navigation"}
        aria-expanded={mobileNavOpen}
        onClick={onMobileNavToggle}
        className="md:hidden w-8 h-8 rounded-md border border-bd1 ghost flex items-center justify-center text-fg2 hover:text-fg1 focus-ring"
      >
        {mobileNavOpen ? (
          <X size={15} strokeWidth={1.75} />
        ) : (
          <Menu size={15} strokeWidth={1.75} />
        )}
      </button>

      <button
        type="button"
        onClick={() => onPageChange('overview')}
        className="flex items-center gap-2.5 pr-3 sm:pr-4 sm:border-r sm:border-bd1 h-full focus-ring"
      >
        <img src="/logo-icon.png" alt="SpreadDash" className="w-8 h-8 rounded-[5px] object-cover bg-black" />
        <span className="font-semibold text-[17px] tracking-tight text-white">spread<span className="text-warn">.</span>dash</span>
      </button>

      <div className="hidden sm:flex items-center gap-2 pl-1">
        <StatusDot tone="long" halo />
        <span className="label text-[12px] capitalize">{currentPage}</span>
      </div>

      <div className="flex-1" />

      <button
        type="button"
        onClick={openSearch}
        aria-haspopup="dialog"
        aria-expanded={searchOpen}
        className="hidden md:flex items-center gap-2 h-8 px-2.5 rounded-md border border-bd1 ghost text-fg3 hover:text-fg2 focus-ring"
      >
        <Search size={13} strokeWidth={1.75} />
        <span className="text-[12px]">Search</span>
        <span className="ml-2 num text-[10px] px-1.5 py-0.5 rounded bg-bg3 border border-bd1 text-fg3">
          ⌘K
        </span>
      </button>

      <div className="hidden sm:flex items-center gap-1.5 px-2 h-8 rounded-md border border-bd1 bg-bg2">
        <StatusDot tone="long" />
        <span className="label text-[9.5px]">WS</span>
        <span className="num text-[11px] text-fg2">
          {wsLatencyMs === null ? "n/a" : `${formatNumber(wsLatencyMs)}ms`}
        </span>
      </div>

      <div ref={notificationsRef} className="relative">
        <button
          type="button"
          aria-label="Notifications"
          aria-haspopup="menu"
          aria-expanded={notificationsOpen}
          onClick={() => {
            setNotificationsOpen((open) => !open);
            setUserMenuOpen(false);
          }}
          className="w-8 h-8 rounded-md border border-bd1 ghost flex items-center justify-center text-fg2 hover:text-fg1 focus-ring"
        >
          <Bell size={14} strokeWidth={1.75} />
        </button>
        {notificationsOpen && (
          <div className="absolute right-0 top-10 w-72 rounded-md border border-bd1 bg-bg2 shadow-2xl shadow-black/40 overflow-hidden z-50">
            <div className="h-10 px-3 border-b border-bd1 flex items-center justify-between">
              <span className="text-[12px] font-medium text-fg1">Notifications</span>
              <span className="label text-[9px]">0 new</span>
            </div>
            <div className="px-4 py-8 text-center">
              <div className="mx-auto mb-3 w-8 h-8 rounded-md border border-bd1 bg-bg3 flex items-center justify-center text-fg3">
                <Bell size={14} strokeWidth={1.75} />
              </div>
              <div className="text-[12.5px] text-fg1">No notifications yet</div>
              <div className="mt-1 text-[11px] text-fg3">
                Bot alerts and campaign events will appear here.
              </div>
            </div>
          </div>
        )}
      </div>
      <button
        type="button"
        onClick={() => onPageChange('settings')}
        aria-label="Settings"
        className="w-8 h-8 rounded-md border border-bd1 ghost flex items-center justify-center text-fg2 hover:text-fg1 focus-ring"
      >
        <Settings size={14} strokeWidth={1.75} />
      </button>
      <div ref={userMenuRef} className="relative">
        <button
          type="button"
          aria-label="User menu"
          aria-haspopup="menu"
          aria-expanded={userMenuOpen}
          onClick={() => {
            setUserMenuOpen((open) => !open);
            setNotificationsOpen(false);
          }}
          className="w-8 h-8 rounded-md bg-bg3 border border-bd1 flex items-center justify-center num text-[11px] text-fg2 hover:text-fg1 focus-ring"
        >
          KJ
        </button>
        {userMenuOpen && (
          <div className="absolute right-0 top-10 w-44 rounded-md border border-bd1 bg-bg2 shadow-2xl shadow-black/40 overflow-hidden z-50">
            <button
              type="button"
              onClick={() => {
                onPageChange('settings');
                setUserMenuOpen(false);
              }}
              className="flex items-center gap-2.5 w-full h-9 px-3 text-[12px] text-fg2 hover:text-fg1 hover:bg-bg3 focus-ring"
            >
              <User size={13} strokeWidth={1.75} />
              <span>Profile</span>
            </button>
            <button
              type="button"
              disabled={loggingOut}
              onClick={handleLogout}
              className="w-full flex items-center gap-2.5 h-9 px-3 text-[12px] text-fg2 hover:text-fg1 hover:bg-bg3 focus-ring"
            >
              <LogOut size={13} strokeWidth={1.75} />
              <span>{loggingOut ? "Logging out" : "Logout"}</span>
            </button>
          </div>
        )}
      </div>

      {searchOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Search"
          className="fixed inset-0 z-50 bg-black/65 px-4 pt-[12vh]"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeSearch();
          }}
        >
          <div className="mx-auto w-full max-w-xl rounded-md border border-bd1 bg-bg2 shadow-2xl shadow-black/50 overflow-hidden">
            <div className="h-12 px-3 border-b border-bd1 flex items-center gap-2.5">
              <Search size={15} strokeWidth={1.75} className="text-fg3" />
              <input
                ref={searchInputRef}
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="Search pages"
                className="flex-1 bg-transparent text-[14px] text-fg1 placeholder:text-fg3 outline-none"
              />
              <button
                type="button"
                onClick={closeSearch}
                className="num text-[10px] px-1.5 py-0.5 rounded border border-bd1 bg-bg3 text-fg3 hover:text-fg2 focus-ring"
              >
                ESC
              </button>
            </div>

            <div className="p-2">
              <div className="px-2 pt-1 pb-2 label">Recent pages</div>
              <div className="flex flex-col gap-1">
                {filteredPages.length > 0 ? (
                  filteredPages.map((page) => (
                    <button
                      key={page.pageId}
                      type="button"
                      onClick={() => {
                        onPageChange(page.pageId);
                        closeSearch();
                      }}
                      className="group flex w-full items-center gap-3 rounded-md border border-transparent px-2.5 py-2.5 text-left hover:bg-bg3 hover:border-bd1 focus-ring"
                    >
                      <div className="w-7 h-7 shrink-0 rounded-md border border-bd1 bg-bg3 flex items-center justify-center text-fg3 group-hover:text-fg1">
                        <Search size={13} strokeWidth={1.75} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-[13px] text-fg1 truncate">{page.label}</div>
                        <div className="text-[11px] text-fg3 truncate">{page.description}</div>
                      </div>
                    </button>
                  ))
                ) : (
                  <div className="px-3 py-8 text-center text-[12px] text-fg3">
                    No matching pages
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
