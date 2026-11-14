import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Panel({ className, ...props }: ComponentProps<"section">) {
  return (
    <section
      className={cn("flex min-w-0 flex-col rounded-lg border bg-card", className)}
      {...props}
    />
  );
}

export function PanelHeader({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <header className="flex min-h-9 flex-wrap items-center justify-between gap-2 border-b px-3 py-1.5">
      <h2 className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
        {title}
      </h2>
      {children}
    </header>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full min-h-24 items-center justify-center p-4 text-center text-muted-foreground">
      {children}
    </div>
  );
}
