import type { Freshness } from "../types";
import { relativeDate } from "../lib/format";

/**
 * Provenance badge.
 *
 * Freshness is shown on every rate, not just bad ones, so the absence of a
 * warning is meaningful rather than ambiguous. Synthetic data is styled as a
 * hard warning because a plausible-looking fake rate is the most damaging
 * thing this app could quietly display.
 */
export function FreshnessBadge({ freshness, asOf }: { freshness: Freshness; asOf?: string }) {
  const styles: Record<Freshness, { label: string; color: string; bg: string; title: string }> = {
    live: {
      label: "Live", color: "var(--ok)",
      bg: "color-mix(in srgb, var(--ok) 14%, transparent)",
      title: "Fetched from the provider just now",
    },
    cached: {
      label: "Cached", color: "var(--text-muted)",
      bg: "color-mix(in srgb, var(--text-muted) 14%, transparent)",
      title: "Served from cache, still within its refresh window",
    },
    stale: {
      label: "Stale", color: "var(--warn)",
      bg: "color-mix(in srgb, var(--warn) 16%, transparent)",
      title: "The provider could not be reached; this is the last known value",
    },
    synthetic: {
      label: "Synthetic", color: "var(--danger)",
      bg: "color-mix(in srgb, var(--danger) 16%, transparent)",
      title: "PLACEHOLDER DATA — not a real market rate. Set FRED_API_KEY for live rates.",
    },
  };
  const s = styles[freshness] ?? styles.cached;
  return (
    <span
      title={s.title + (asOf ? ` · as of ${asOf}` : "")}
      className="inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
      style={{ color: s.color, background: s.bg }}
    >
      {s.label}
    </span>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-xs" style={{ color: "var(--text-muted)" }}>
      <span
        className="h-3 w-3 animate-spin rounded-full border-2 border-t-transparent"
        style={{ borderColor: "var(--border-strong)", borderTopColor: "transparent" }}
      />
      {label}
    </span>
  );
}

export function Callout({
  tone = "info", children,
}: {
  tone?: "info" | "warn" | "danger";
  children: React.ReactNode;
}) {
  const color = tone === "danger" ? "var(--danger)" : tone === "warn" ? "var(--warn)" : "var(--accent)";
  return (
    <div
      className="rounded-lg border-l-2 px-3 py-2 text-xs leading-relaxed"
      style={{
        borderColor: color,
        background: `color-mix(in srgb, ${color} 8%, transparent)`,
        color: "var(--text-muted)",
      }}
    >
      {children}
    </div>
  );
}

export function SourceLine({
  label, source, asOf, url,
}: {
  label: string; source: string; asOf: string; url?: string | null;
}) {
  const body = (
    <>
      <span style={{ color: "var(--text-muted)" }}>{label}</span>
      <span style={{ color: "var(--text-faint)" }}> · {source} · {relativeDate(asOf)}</span>
    </>
  );
  return url ? (
    <a href={url} target="_blank" rel="noopener noreferrer"
       className="hover:underline" style={{ textDecorationColor: "var(--text-faint)" }}>
      {body}
    </a>
  ) : (
    <span>{body}</span>
  );
}
