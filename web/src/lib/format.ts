/** Display formatting. Every number arrives already rounded by the backend;
 *  this only decides how it is written, never what it is. */

const currency0 = new Intl.NumberFormat("en-US", {
  style: "currency", currency: "USD",
  minimumFractionDigits: 0, maximumFractionDigits: 0,
});
const currency2 = new Intl.NumberFormat("en-US", {
  style: "currency", currency: "USD",
  minimumFractionDigits: 2, maximumFractionDigits: 2,
});

export function money(value: number, cents = false): string {
  if (!Number.isFinite(value)) return "—";
  return (cents ? currency2 : currency0).format(value);
}

/** Compact axis labels: 1.2M, 450K. Keeps long money axes readable. */
export function moneyCompact(value: number): string {
  if (!Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `$${(value / 1_000_000).toFixed(abs >= 10_000_000 ? 0 : 1)}M`;
  if (abs >= 1_000) return `$${(value / 1_000).toFixed(abs >= 10_000 ? 0 : 1)}K`;
  return `$${value.toFixed(0)}`;
}

export function percent(value: number, digits = 2): string {
  if (!Number.isFinite(value)) return "—";
  return `${value.toFixed(digits)}%`;
}

export function formatValue(value: number, kind: string): string {
  switch (kind) {
    case "currency": return money(value);
    case "percent": return percent(value);
    default: return new Intl.NumberFormat("en-US").format(value);
  }
}

export function formatAxis(value: number, kind: string): string {
  switch (kind) {
    case "currency": return moneyCompact(value);
    case "percent": return `${value.toFixed(1)}%`;
    default: return String(value);
  }
}

/** Turn a snake_case summary key into a readable label. */
export function humanize(key: string): string {
  return key
    .replace(/_percent$/, " (%)")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Summary values are money unless the key says otherwise. */
export function formatSummaryValue(key: string, value: unknown): string {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value !== "number") return String(value ?? "—");
  if (/percent|rate/.test(key)) return percent(value);
  if (/years|months|count|observations/.test(key)) return String(value);
  return money(value, Math.abs(value) < 10_000);
}

export function relativeDate(iso: string): string {
  const then = new Date(iso + (iso.length === 10 ? "T00:00:00Z" : ""));
  const days = Math.floor((Date.now() - then.getTime()) / 86_400_000);
  if (Number.isNaN(days)) return iso;
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days}d ago`;
  if (days < 365) return `${Math.floor(days / 30)}mo ago`;
  return `${Math.floor(days / 365)}y ago`;
}
