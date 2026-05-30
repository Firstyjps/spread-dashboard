import * as React from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/cn";

type FieldProps = {
  label: string;
  hint?: string;
  error?: string;
  children: React.ReactNode;
};

export function Field({ label, hint, error, children }: FieldProps) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="label text-[9.5px]">{label}</span>
      {children}
      {(hint || error) && (
        <span className={cn("text-[11px]", error ? "text-short" : "text-fg3")}>
          {error || hint}
        </span>
      )}
    </label>
  );
}

type InputProps = React.InputHTMLAttributes<HTMLInputElement> & { mono?: boolean };

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ mono = true, className, ...rest }, ref) => {
    return (
      <input
        ref={ref}
        {...rest}
        className={cn(
          "h-9 w-full rounded-md bg-bg3 border border-bd1 px-3 text-[13px] text-fg1",
          "placeholder:text-fg3 focus:outline-none focus:border-bd2 transition-colors",
          mono && "num",
          className,
        )}
      />
    );
  },
);
Input.displayName = "Input";

type SelectProps = React.SelectHTMLAttributes<HTMLSelectElement>;

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ children, className, ...rest }, ref) => {
    return (
      <div className="relative">
        <select
          ref={ref}
          {...rest}
          className={cn(
            "h-9 w-full appearance-none rounded-md bg-bg3 border border-bd1 px-3 pr-8",
            "text-[13px] text-fg1 focus:outline-none focus:border-bd2",
            className,
          )}
        >
          {children}
        </select>
        <span className="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none text-fg3">
          <ChevronDown size={12} strokeWidth={1.75} />
        </span>
      </div>
    );
  },
);
Select.displayName = "Select";
