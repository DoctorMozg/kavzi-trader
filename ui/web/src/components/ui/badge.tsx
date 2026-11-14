import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

const badge = cva(
  "inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase leading-none tracking-wider",
  {
    variants: {
      tone: {
        neutral: "bg-muted text-muted-foreground",
        green: "bg-profit/15 text-profit",
        red: "bg-loss/15 text-loss",
        amber: "bg-warn/20 text-warn",
        blue: "bg-sky-400/15 text-sky-300",
        violet: "bg-violet-400/15 text-violet-300",
        cyan: "bg-cyan-400/15 text-cyan-300",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export type BadgeTone = NonNullable<VariantProps<typeof badge>["tone"]>;

export function Badge({
  tone,
  className,
  ...props
}: ComponentProps<"span"> & VariantProps<typeof badge>) {
  return <span className={cn(badge({ tone }), className)} {...props} />;
}
