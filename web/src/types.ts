/** Mirrors the chart and envelope shapes produced by the agent repo's
 *  `finance_core.charts` and `interest_tools`. Kept in sync by hand: this repo
 *  deliberately does not import that code, it only consumes it over MCP. */

export type ChartType =
  | "line" | "area" | "bar" | "stacked-bar" | "stacked-area";
export type ValueFormat = "currency" | "percent" | "number";

export interface SeriesSpec {
  key: string;
  label: string;
  /** Semantic slot ("interest", "principal", "scenario0") -> palette colour. */
  role: string;
}

export interface ChartSpec {
  id: string;
  type: ChartType;
  title: string;
  subtitle?: string | null;
  footnote?: string | null;
  x_key: string;
  x_label: string;
  y_label: string;
  y_format: ValueFormat;
  x_format: ValueFormat;
  series: SeriesSpec[];
  data: Record<string, number | string>[];
}

export type Freshness = "live" | "cached" | "stale" | "synthetic";

export interface RateQuote {
  key: string;
  label: string;
  value: number;      // decimal fraction
  percent: number;    // display percentage
  as_of: string;
  source: string;
  series_id: string;
  unit: string;
  freshness: Freshness;
  fetched_at: string;
  citation_url: string | null;
}

export interface Assumption {
  key: string;
  value: unknown;
  description: string;
  user_supplied: boolean;
}

export interface Citation {
  label: string;
  source: string;
  as_of: string;
  url: string | null;
  freshness: string;
}

export interface ToolResult {
  summary: Record<string, unknown>;
  detail: Record<string, unknown>;
  charts: ChartSpec[];
  assumptions: Assumption[];
  citations: Citation[];
  notes: string[];
  /** Present only when a tool rejected the call. */
  isError?: boolean;
  error?: string;
}

/** Normalized events from the backend's /api/chat SSE stream. */
export type ChatEvent =
  | { type: "session"; session_id: string }
  | { type: "text"; text: string }
  | { type: "tool_start"; name: string }
  | { type: "tool_result"; name: string; payload: ToolResult }
  | { type: "done" }
  | { type: "error"; message: string };

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  toolsUsed: string[];
  results: ToolResult[];
  streaming?: boolean;
  error?: string;
}
