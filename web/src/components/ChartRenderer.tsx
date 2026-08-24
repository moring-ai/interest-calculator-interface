import { useId } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { ChartSpec } from "../types";
import { formatAxis, formatValue } from "../lib/format";

/**
 * Renders any ChartSpec the backend produces.
 *
 * The component is deliberately generic: it never knows whether it is drawing
 * a mortgage or a savings account. The backend decides what the chart means;
 * this decides how it looks. That is what keeps a chart from a chat answer and
 * a chart from the calculator panel pixel-identical.
 */

/** Maps a series' semantic role to its palette slot. */
function colorFor(role: string): string {
  const known = [
    "interest", "principal", "balance", "real", "rate",
    "scenario0", "scenario1", "scenario2", "scenario3",
  ];
  return known.includes(role) ? `var(--c-${role})` : "var(--accent)";
}

interface TooltipEntry {
  name?: string;
  value?: number;
  color?: string;
  dataKey?: string;
}

function ChartTooltip({
  active, payload, label, spec,
}: {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: string | number;
  spec: ChartSpec;
}) {
  if (!active || !payload?.length) return null;

  const total = payload.reduce((sum, e) => sum + (e.value ?? 0), 0);
  const isStacked = spec.type.startsWith("stacked");

  return (
    <div
      className="rounded-lg border px-3 py-2 text-xs shadow-xl backdrop-blur"
      style={{
        background: "color-mix(in srgb, var(--surface) 92%, transparent)",
        borderColor: "var(--border-strong)",
      }}
    >
      <div className="mb-1.5 font-medium" style={{ color: "var(--text-muted)" }}>
        {spec.x_label} {label}
      </div>
      <div className="space-y-1">
        {payload.map((entry) => (
          <div key={entry.dataKey} className="flex items-center gap-2.5">
            <span
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ background: entry.color }}
            />
            <span className="flex-1" style={{ color: "var(--text-muted)" }}>
              {entry.name}
            </span>
            <span className="tnum font-medium" style={{ color: "var(--text)" }}>
              {formatValue(entry.value ?? 0, spec.y_format)}
            </span>
          </div>
        ))}
        {isStacked && payload.length > 1 && (
          <div
            className="mt-1.5 flex items-center gap-2.5 border-t pt-1.5"
            style={{ borderColor: "var(--border)" }}
          >
            <span className="h-2 w-2 shrink-0" />
            <span className="flex-1" style={{ color: "var(--text-muted)" }}>Total</span>
            <span className="tnum font-semibold" style={{ color: "var(--text)" }}>
              {formatValue(total, spec.y_format)}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

export function ChartRenderer({ spec, height = 280 }: { spec: ChartSpec; height?: number }) {
  const uid = useId().replace(/:/g, "");

  if (!spec.data?.length) {
    return (
      <div
        className="flex items-center justify-center rounded-lg border border-dashed text-sm"
        style={{ height, borderColor: "var(--border)", color: "var(--text-faint)" }}
      >
        No data to plot
      </div>
    );
  }

  const axisStyle = { fill: "var(--text-faint)", fontSize: 11 };
  const common = {
    data: spec.data,
    margin: { top: 8, right: 8, left: 4, bottom: 4 },
  };

  const grid = (
    <CartesianGrid
      strokeDasharray="2 4"
      stroke="var(--border)"
      vertical={false}
    />
  );
  const xAxis = (
    <XAxis
      dataKey={spec.x_key}
      tick={axisStyle}
      tickLine={false}
      axisLine={{ stroke: "var(--border)" }}
      minTickGap={24}
    />
  );
  const yAxis = (
    <YAxis
      tick={axisStyle}
      tickLine={false}
      axisLine={false}
      width={58}
      tickFormatter={(v: number) => formatAxis(v, spec.y_format)}
    />
  );
  const tooltip = (
    <Tooltip
      content={<ChartTooltip spec={spec} />}
      cursor={{ stroke: "var(--border-strong)", strokeWidth: 1 }}
    />
  );
  const legend =
    spec.series.length > 1 ? (
      <Legend
        verticalAlign="top"
        align="left"
        height={28}
        iconType="circle"
        iconSize={7}
        wrapperStyle={{ fontSize: 12, color: "var(--text-muted)", paddingLeft: 4 }}
      />
    ) : null;

  // --- Bar / stacked bar -------------------------------------------------
  if (spec.type === "bar" || spec.type === "stacked-bar") {
    const stackId = spec.type === "stacked-bar" ? "a" : undefined;
    return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart {...common}>
          {grid}{xAxis}{yAxis}{tooltip}{legend}
          {spec.series.map((s, i) => (
            <Bar
              key={s.key}
              dataKey={s.key}
              name={s.label}
              stackId={stackId}
              fill={colorFor(s.role)}
              radius={
                spec.type === "stacked-bar" && i === spec.series.length - 1
                  ? [3, 3, 0, 0]
                  : spec.type === "bar"
                    ? [3, 3, 0, 0]
                    : undefined
              }
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    );
  }

  // --- Area / stacked area ----------------------------------------------
  if (spec.type === "area" || spec.type === "stacked-area") {
    const stackId = spec.type === "stacked-area" ? "a" : undefined;
    return (
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart {...common}>
          <defs>
            {spec.series.map((s) => (
              <linearGradient key={s.key} id={`g-${uid}-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={colorFor(s.role)} stopOpacity={0.55} />
                <stop offset="100%" stopColor={colorFor(s.role)} stopOpacity={0.04} />
              </linearGradient>
            ))}
          </defs>
          {grid}{xAxis}{yAxis}{tooltip}{legend}
          {spec.series.map((s) => (
            <Area
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.label}
              stackId={stackId}
              stroke={colorFor(s.role)}
              strokeWidth={2}
              fill={`url(#g-${uid}-${s.key})`}
              dot={false}
              activeDot={{ r: 3.5, strokeWidth: 0 }}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    );
  }

  // --- Line (default) ----------------------------------------------------
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart {...common}>
        {grid}{xAxis}{yAxis}{tooltip}{legend}
        {spec.series.map((s) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label}
            stroke={colorFor(s.role)}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 3.5, strokeWidth: 0 }}
            // Gaps are real: a 15-year loan simply has no year-20 balance.
            connectNulls={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

/** A chart with its title, subtitle and footnote, as one card. */
export function ChartCard({ spec, height }: { spec: ChartSpec; height?: number }) {
  return (
    <figure
      className="rounded-xl border p-4"
      style={{ background: "var(--surface)", borderColor: "var(--border)" }}
    >
      <figcaption className="mb-3">
        <h4 className="text-sm font-semibold" style={{ color: "var(--text)" }}>
          {spec.title}
        </h4>
        {spec.subtitle && (
          <p className="mt-0.5 text-xs" style={{ color: "var(--text-muted)" }}>
            {spec.subtitle}
          </p>
        )}
      </figcaption>
      <ChartRenderer spec={spec} height={height} />
      {spec.footnote && (
        <p className="mt-3 text-xs leading-relaxed" style={{ color: "var(--text-faint)" }}>
          {spec.footnote}
        </p>
      )}
    </figure>
  );
}
