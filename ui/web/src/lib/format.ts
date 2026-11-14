const time = new Intl.DateTimeFormat("en-GB", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});
const dateTime = new Intl.DateTimeFormat("en-GB", {
  month: "short",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const fixed = (digits: number, signed = false): Intl.NumberFormat =>
  new Intl.NumberFormat("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    signDisplay: signed ? "exceptZero" : "auto",
  });

const usd = fixed(2);
const usdSigned = fixed(2, true);
const pct = fixed(2, true);
const plainPct = fixed(1);
const priceFormats = [2, 3, 4, 5, 6].map((d) => fixed(d));

export const fmtTime = (ms: number): string => time.format(ms);
export const fmtDateTime = (ms: number): string => dateTime.format(ms);
export const fmtUsd = (n: number): string => usd.format(n);
export const fmtSignedUsd = (n: number): string => usdSigned.format(n);
export const fmtPct = (n: number): string => `${pct.format(n)}%`;
export const fmtPlainPct = (n: number): string => `${plainPct.format(n)}%`;

export function fmtPrice(n: number): string {
  const abs = Math.abs(n);
  const index = abs >= 1000 ? 0 : abs >= 10 ? 1 : abs >= 1 ? 2 : abs >= 0.1 ? 3 : 4;
  return (priceFormats[index] ?? usd).format(n);
}

export function fmtQty(n: number): string {
  return new Intl.NumberFormat("en-US", { maximumSignificantDigits: 6 }).format(n);
}

export function fmtDuration(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const d = Math.floor(total / 86400);
  const h = Math.floor((total % 86400) / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

export const pnlClass = (n: number): string =>
  n > 0 ? "text-profit" : n < 0 ? "text-loss" : "text-muted-foreground";
