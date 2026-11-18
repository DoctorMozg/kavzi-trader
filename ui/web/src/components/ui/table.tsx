import type { ComponentProps, ReactNode } from "react";
import { Hint } from "@/components/ui/hint";
import { cn } from "@/lib/utils";

export function Table({ className, ...props }: ComponentProps<"table">) {
  return (
    <div className="overflow-auto">
      <table className={cn("w-full border-collapse tabular-nums", className)} {...props} />
    </div>
  );
}

type CellProps = ComponentProps<"td"> & { right?: boolean };

export function Th({
  right,
  hint,
  className,
  children,
  ...props
}: ComponentProps<"th"> & { right?: boolean; hint?: ReactNode }) {
  return (
    <th
      className={cn(
        "sticky top-0 whitespace-nowrap bg-card px-3 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground",
        right ? "text-right" : "text-left",
        className,
      )}
      {...props}
    >
      {hint ? <Hint content={hint}>{children}</Hint> : children}
    </th>
  );
}

export function Td({ right, className, ...props }: CellProps) {
  return (
    <td
      className={cn("whitespace-nowrap border-t px-3 py-1.5", right && "text-right", className)}
      {...props}
    />
  );
}
