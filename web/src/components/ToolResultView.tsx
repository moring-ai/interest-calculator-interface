import { useState } from "react";
import type { ToolResult } from "../types";
import { formatSummaryValue, humanize } from "../lib/format";
import { ChartCard } from "./ChartRenderer";
import { Callout, SourceLine } from "./Primitives";

/**
 * Renders one tool result: headline numbers, charts, then the provenance.
 *
 * Assumptions and citations sit below the charts rather than being hidden
 * behind a link. A projection is only as good as what was assumed, and a user
 * who does not notice that inflation was guessed at 2.5% has been misled even
 * though every number is correct.
 */
export function ToolResultView({ result, compact = false }: { result: ToolResult; compact?: boolean }) {
  const [showDetail, setShowDetail] = useState(false);

  if (result.isError) {
    return <Callout tone="danger">{result.error ?? "That tool call failed."}</Callout>;
  }

  const summaryEntries = Object.entries(result.summary ?? {}).filter(
    ([, v]) => typeof v !== "object" || v === null,
  );
  const inferred = (result.assumptions ?? []).filter((a) => !a.user_supplied);

  return (
    <div className="space-y-3">
      {summaryEntries.length > 0 && (
        <div
          className="grid gap-px overflow-hidden rounded-xl border"
          style={{
            borderColor: "var(--border)",
            background: "var(--border)",
            gridTemplateColumns: `repeat(auto-fit, minmax(${compact ? 130 : 150}px, 1fr))`,
          }}
        >
          {summaryEntries.map(([key, value]) => (
            <div key={key} className="px-3 py-2.5" style={{ background: "var(--surface)" }}>
              <div
                className="mb-1 text-[10px] font-medium uppercase tracking-wide"
                style={{ color: "var(--text-faint)" }}
              >
                {humanize(key)}
              </div>
              <div className="tnum text-sm font-semibold" style={{ color: "var(--text)" }}>
                {formatSummaryValue(key, value)}
              </div>
            </div>
          ))}
        </div>
      )}

      {result.notes?.map((note, i) => (
        <Callout key={i} tone={/SYNTHETIC/.test(note) ? "danger" : "warn"}>
          {note}
        </Callout>
      ))}

      {result.charts?.map((spec) => (
        <ChartCard key={spec.id} spec={spec} height={compact ? 220 : 280} />
      ))}

      {inferred.length > 0 && (
        <div
          className="rounded-lg border px-3 py-2.5"
          style={{ borderColor: "var(--border)", background: "var(--surface-2)" }}
        >
          <div
            className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide"
            style={{ color: "var(--text-faint)" }}
          >
            Assumed for you
          </div>
          <ul className="space-y-1">
            {inferred.map((a) => (
              <li key={a.key} className="text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>
                <span className="tnum font-medium" style={{ color: "var(--text)" }}>
                  {humanize(a.key)}: {String(a.value)}
                </span>{" "}
                — {a.description}
              </li>
            ))}
          </ul>
        </div>
      )}

      {result.citations?.length > 0 && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px]">
          {result.citations.map((c, i) => (
            <SourceLine key={i} label={c.label} source={c.source} asOf={c.as_of} url={c.url} />
          ))}
        </div>
      )}

      {Object.keys(result.detail ?? {}).length > 0 && (
        <div>
          <button
            onClick={() => setShowDetail((v) => !v)}
            className="text-[11px] underline-offset-2 hover:underline"
            style={{ color: "var(--text-faint)" }}
          >
            {showDetail ? "Hide" : "Show"} full schedule
          </button>
          {showDetail && (
            <pre
              className="tnum mt-2 max-h-64 overflow-auto rounded-lg border p-3 text-[11px] leading-relaxed"
              style={{
                borderColor: "var(--border)", background: "var(--surface-2)",
                color: "var(--text-muted)",
              }}
            >
              {JSON.stringify(result.detail, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
