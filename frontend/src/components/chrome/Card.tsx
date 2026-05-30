import * as React from "react";
import { cn } from "@/lib/cn";

type CardProps = {
  title?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
};

export function Card({ title, action, className, children }: CardProps) {
  return (
    <div className={cn("rounded-md border border-bd1 bg-bg2 overflow-hidden", className)}>
      {(title || action) && (
        <div className="flex items-center px-4 h-11 border-b border-bd1">
          {title && (
            <div className="text-[13px] font-medium text-fg1 tracking-tight">{title}</div>
          )}
          <div className="flex-1" />
          {action}
        </div>
      )}
      {children}
    </div>
  );
}
