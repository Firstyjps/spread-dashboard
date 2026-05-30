import { cn } from "@/lib/cn";

type ExchangeChipProps = { name: string; className?: string };

export function ExchangeChip({ name, className }: ExchangeChipProps) {
  const seed = name.charAt(0);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 h-5 pl-1 pr-2 rounded border border-bd1 bg-bg3",
        className,
      )}
    >
      <span className="num text-[9px] w-3 h-3 rounded-sm bg-bg1 border border-bd1 inline-flex items-center justify-center text-fg2">
        {seed}
      </span>
      <span className="text-[10.5px] text-fg2 tracking-tight">{name}</span>
    </span>
  );
}

type StatusPillStatus =
  | "Running"
  | "Paused"
  | "Filled"
  | "Stopped"
  | "Cancelled"
  | "Errored"
  | "Active"
  | "Revoked"
  | "Expired";

const PILL_TONE: Record<StatusPillStatus, string> = {
  Running: "border-long/25 bg-long/10 text-long",
  Paused: "border-warn/25 bg-warn/10 text-warn",
  Filled: "border-long/25 bg-long/10 text-long",
  Stopped: "border-bd1 bg-bg3 text-fg2",
  Cancelled: "border-bd1 bg-bg3 text-fg2",
  Errored: "border-short/25 bg-short/10 text-short",
  Active: "border-long/25 bg-long/10 text-long",
  Revoked: "border-bd1 bg-bg3 text-fg3",
  Expired: "border-warn/25 bg-warn/10 text-warn",
};

export function StatusPill({ status }: { status: StatusPillStatus }) {
  const live = status === "Running" || status === "Active";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-1.5 py-1 rounded border label text-[9px]",
        PILL_TONE[status],
      )}
    >
      {live && <span className="w-1 h-1 rounded-full bg-current status-pulse" />}
      {status}
    </span>
  );
}
