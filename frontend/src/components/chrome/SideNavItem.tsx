"use client";

import {
  History,
  Key,
  LayoutDashboard,
  ListOrdered,
  Megaphone,
  Plus,
  Settings,
  ShieldCheck,
  Users,
  Wallet,
  Activity,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/cn";

const ICONS: Record<string, LucideIcon> = {
  LayoutDashboard,
  Plus,
  Megaphone,
  Settings,
  ListOrdered,
  Wallet,
  History,
  Users,
  Key,
  ShieldCheck,
  Activity
};

type SideNavItemProps = {
  icon: keyof typeof ICONS;
  label: string;
  pageId: string;
  currentPage: string;
  onClick: (pageId: string) => void;
  badge?: number;
};

export function SideNavItem({ icon, label, pageId, currentPage, onClick, badge }: SideNavItemProps) {
  const active = currentPage === pageId;
  const Icon = ICONS[icon] as LucideIcon;

  return (
    <button
      onClick={() => onClick(pageId)}
      className={cn(
        "group flex items-center w-full gap-2.5 h-8 px-2.5 rounded-md text-[13px] transition-colors focus-ring",
        active
          ? "bg-bg3 text-fg1 border border-bd1"
          : "text-fg2 hover:text-fg1 hover:bg-bg2 border border-transparent",
      )}
    >
      <Icon size={14} strokeWidth={1.75} className={active ? "text-long" : ""} />
      <span className="flex-1 truncate text-left">{label}</span>
      {badge !== undefined && (
        <span className="num text-[10.5px] text-fg3 px-1.5 py-0.5 rounded bg-bg3 border border-bd1 group-hover:text-fg2">
          {badge}
        </span>
      )}
    </button>
  );
}
