import * as Tooltip from "@radix-ui/react-tooltip";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function HintProvider({ children }: { children: ReactNode }) {
  return (
    <Tooltip.Provider delayDuration={150} skipDelayDuration={100}>
      {children}
    </Tooltip.Provider>
  );
}

// Dotted underline marks text that explains itself on hover or keyboard focus.
export function Hint({
  content,
  children,
  plain = false,
  className,
}: {
  content: ReactNode;
  children: ReactNode;
  plain?: boolean;
  className?: string;
}) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>
        <span
          tabIndex={0}
          className={cn(
            "cursor-help outline-none focus-visible:ring-1 focus-visible:ring-sky-400",
            !plain && "underline decoration-muted-foreground/40 decoration-dotted underline-offset-2",
            className,
          )}
        >
          {children}
        </span>
      </Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content
          side="top"
          sideOffset={6}
          collisionPadding={8}
          className="animate-in fade-in z-50 max-w-sm rounded-md border bg-card px-3 py-2 text-xs normal-case leading-relaxed tracking-normal text-foreground shadow-xl"
        >
          {content}
          <Tooltip.Arrow className="fill-border" />
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}
