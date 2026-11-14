export function SlTpBar({ stop, take, mark }: { stop: number; take: number; mark: number }) {
  const span = take - stop;
  // Works for both sides: 0 is always the SL end, 1 the TP end.
  const progress = span === 0 ? 0.5 : Math.min(1, Math.max(0, (mark - stop) / span));
  return (
    <div className="relative h-1.5 w-24 rounded-full bg-gradient-to-r from-loss/50 to-profit/50">
      <span
        className="absolute top-1/2 h-3 w-0.5 -translate-x-1/2 -translate-y-1/2 rounded bg-foreground"
        style={{ left: `${progress * 100}%` }}
      />
    </div>
  );
}
