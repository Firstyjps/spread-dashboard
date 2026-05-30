import * as React from "react";
import { cn } from "@/lib/cn";

type Variant = "ghost" | "ghost-danger" | "ghost-primary" | "primary";
type Size = "sm" | "md" | "lg";

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
};

const SIZE: Record<Size, string> = {
  sm: "h-7 px-2.5 text-[11.5px]",
  md: "h-8 px-3 text-[12px]",
  lg: "h-9 px-3.5 text-[12.5px]",
};

const VARIANT: Record<Variant, string> = {
  ghost: "rounded-md border border-bd1 ghost text-fg2 hover:text-fg1",
  "ghost-danger":
    "rounded-md border border-bd1 ghost text-short hover:text-short hover:border-short/40 hover:bg-short/5",
  "ghost-primary":
    "rounded-md border border-long/30 bg-long/10 text-long hover:bg-long/15 transition-colors",
  primary:
    "rounded-md bg-long text-bg1 font-medium hover:bg-long/90 transition-colors",
};

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "ghost", size = "md", className, children, ...rest }, ref) => {
    return (
      <button
        ref={ref}
        {...rest}
        className={cn(
          "inline-flex items-center gap-1.5 focus-ring",
          SIZE[size],
          VARIANT[variant],
          className,
        )}
      >
        {children}
      </button>
    );
  },
);
Button.displayName = "Button";
