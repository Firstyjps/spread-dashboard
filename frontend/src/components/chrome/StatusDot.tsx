import { cn } from "@/lib/cn";

type Tone = "long" | "warn" | "short" | "info" | "muted";

const TONE_CLASS: Record<Tone, string> = {
  long: "bg-long text-long",
  warn: "bg-warn text-warn",
  short: "bg-short text-short",
  info: "bg-info text-info",
  muted: "bg-fg3 text-fg3",
};

type StatusDotProps = {
  tone?: Tone;
  size?: number;
  halo?: boolean;
  className?: string;
};

export function StatusDot({ tone = "long", size = 6, halo = false, className }: StatusDotProps) {
  return (
    <span className="relative inline-flex">
      <span
        className={cn(
          "inline-block rounded-full status-pulse",
          TONE_CLASS[tone],
          halo && "dot-halo",
          className,
        )}
        style={{ width: size, height: size }}
      />
    </span>
  );
}
