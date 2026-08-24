import { useEffect, useState } from "react";
import type { RateQuote, ToolResult } from "../types";
import { api } from "../api/client";
import { percent, relativeDate } from "../lib/format";
import { ChartRenderer } from "./ChartRenderer";
import { FreshnessBadge, Spinner } from "./Primitives";

/**
 * The live rate board.
 *
 * Selecting a rate loads its history inline rather than navigating away, so
 * "what is the 30-year at" and "where has it been" are one gesture apart.
 */
export function RateBoard({ onRatesLoaded }: { onRatesLoaded?: (rates: RateQuote[]) => void } = {}) {
  const [rates, setRates] = useState<RateQuote[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [history, setHistory] = useState<ToolResult | null>(null);
  const [loadingHistory, setLoadingHistory] = useState(false);

  useEffect(() => {
    api.rateBoard()
      .then((r) => { setRates(r.rates); onRatesLoaded?.(r.rates); })
      .catch((e) => setError(e.message));
    // Intentionally runs once: the board is a snapshot, and re-running on a
    // changing callback identity would refetch on every parent render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selected) { setHistory(null); return; }
    let cancelled = false;
    setLoadingHistory(true);
    api.rateHistory(selected, 36)
      .then((r) => { if (!cancelled) setHistory(r); })
      .catch(() => { if (!cancelled) setHistory(null); })
      .finally(() => { if (!cancelled) setLoadingHistory(false); });
    return () => { cancelled = true; };
  }, [selected]);

  if (error) {
    return (
      <div className="p-4 text-xs" style={{ color: "var(--danger)" }}>
        Could not load rates: {error}
      </div>
    );
  }

  if (!rates) {
    return (
      <div className="flex gap-2 p-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={i}
            className="pulse-soft h-[68px] flex-1 rounded-lg"
            style={{ background: "var(--surface-2)" }}
          />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-2" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
        {rates.map((rate) => {
          const active = selected === rate.key;
          return (
            <button
              key={rate.key}
              onClick={() => setSelected(active ? null : rate.key)}
              className="rounded-xl border p-3 text-left transition-colors"
              style={{
                background: active ? "var(--surface-2)" : "var(--surface)",
                borderColor: active ? "var(--accent)" : "var(--border)",
              }}
            >
              <div className="mb-1.5 flex items-start justify-between gap-2">
                <span
                  className="text-[11px] leading-tight font-medium"
                  style={{ color: "var(--text-muted)" }}
                >
                  {rate.label}
                </span>
                <FreshnessBadge freshness={rate.freshness} asOf={rate.as_of} />
              </div>
              <div className="tnum text-xl font-semibold" style={{ color: "var(--text)" }}>
                {percent(rate.percent)}
              </div>
              <div className="mt-0.5 text-[10px]" style={{ color: "var(--text-faint)" }}>
                {rate.source} · {relativeDate(rate.as_of)}
              </div>
            </button>
          );
        })}
      </div>

      {selected && (
        <div
          className="animate-in rounded-xl border p-4"
          style={{ background: "var(--surface)", borderColor: "var(--border)" }}
        >
          {loadingHistory && <Spinner label="Loading history…" />}
          {!loadingHistory && history?.charts?.[0] && (
            <>
              <div className="mb-3 flex items-baseline justify-between">
                <h4 className="text-sm font-semibold" style={{ color: "var(--text)" }}>
                  {history.charts[0].title}
                </h4>
                <span className="tnum text-[11px]" style={{ color: "var(--text-faint)" }}>
                  3-year range {percent(Number(history.summary.min_percent))} –{" "}
                  {percent(Number(history.summary.max_percent))}
                </span>
              </div>
              <ChartRenderer spec={history.charts[0]} height={200} />
            </>
          )}
          {!loadingHistory && !history?.charts?.length && (
            <p className="text-xs" style={{ color: "var(--text-faint)" }}>
              No history available for this rate.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
