import { useEffect, useState } from "react";
import { api } from "./api/client";
import type { ToolResult } from "./types";
import { Calculators } from "./components/Calculators";
import { ChatPanel } from "./components/ChatPanel";
import { RateBoard } from "./components/RateBoard";
import { ToolResultView } from "./components/ToolResultView";
import { Callout } from "./components/Primitives";

type Mode = "chat" | "calculators";

export default function App() {
  const [mode, setMode] = useState<Mode>("chat");
  const [agentReady, setAgentReady] = useState(false);
  //: null until the rate board loads. Derived from the rates themselves rather
  //: than a health flag: the backend no longer owns the rate provider -- the
  //: MCP tool server does -- so the only honest signal is what came back.
  const [syntheticRates, setSyntheticRates] = useState<boolean | null>(null);
  /** Charts produced by the agent, newest first. */
  const [canvas, setCanvas] = useState<ToolResult[]>([]);

  useEffect(() => {
    api.health()
      .then((h) => setAgentReady(Boolean(h.agent_configured)))
      .catch(() => setAgentReady(false));
  }, []);

  return (
    <div className="flex h-full flex-col" style={{ background: "var(--bg)" }}>
      <header
        className="flex shrink-0 items-center justify-between border-b px-5 py-3"
        style={{ borderColor: "var(--border)", background: "var(--surface)" }}
      >
        <div className="flex items-baseline gap-3">
          <h1 className="text-base font-semibold tracking-tight" style={{ color: "var(--text)" }}>
            Interest<span style={{ color: "var(--accent)" }}>Calc</span>
          </h1>
          <span className="text-[11px]" style={{ color: "var(--text-faint)" }}>
            Live rates, real math
          </span>
        </div>

        <div className="flex gap-1 rounded-lg p-0.5" style={{ background: "var(--surface-2)" }}>
          {(["chat", "calculators"] as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className="rounded-md px-3 py-1 text-xs font-medium capitalize transition-colors"
              style={{
                background: mode === m ? "var(--surface)" : "transparent",
                color: mode === m ? "var(--text)" : "var(--text-muted)",
              }}
            >
              {m}
            </button>
          ))}
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[1500px] space-y-4 p-4">
          {syntheticRates && (
            <Callout tone="danger">
              <strong>No live rate source configured.</strong> Rates shown are
              synthetic placeholders, not market data. Set <code>FRED_API_KEY</code>{" "}
              on the MCP tool server and redeploy it
              (<code>./scripts/deploy-mcp.sh</code> in the agent repo).
            </Callout>
          )}

          <section>
            <h2
              className="mb-2 text-[11px] font-semibold uppercase tracking-wide"
              style={{ color: "var(--text-faint)" }}
            >
              Today's rates
            </h2>
            <RateBoard
              onRatesLoaded={(rates) =>
                setSyntheticRates(rates.some((r) => r.freshness === "synthetic"))
              }
            />
          </section>

          {mode === "chat" ? (
            <div className="grid gap-4 lg:grid-cols-[minmax(340px,2fr)_3fr]">
              <section
                className="flex h-[calc(100vh-19rem)] min-h-[420px] flex-col overflow-hidden rounded-xl border"
                style={{ background: "var(--surface)", borderColor: "var(--border)" }}
              >
                <ChatPanel
                  agentReady={agentReady}
                  onResults={(results) => setCanvas((prev) => [...results, ...prev])}
                />
              </section>

              <section className="h-[calc(100vh-19rem)] min-h-[420px] space-y-4 overflow-y-auto pr-1">
                {canvas.length === 0 ? (
                  <div
                    className="flex h-full min-h-[420px] items-center justify-center rounded-xl border border-dashed"
                    style={{ borderColor: "var(--border)" }}
                  >
                    <div className="max-w-xs text-center">
                      <p className="text-sm font-medium" style={{ color: "var(--text-muted)" }}>
                        Charts appear here
                      </p>
                      <p className="mt-1 text-xs leading-relaxed" style={{ color: "var(--text-faint)" }}>
                        Ask a question and the agent's calculations render as
                        interactive charts, with the source of every rate it used.
                      </p>
                    </div>
                  </div>
                ) : (
                  canvas.map((result, i) => (
                    <div key={i} className="animate-in">
                      <ToolResultView result={result} />
                    </div>
                  ))
                )}
              </section>
            </div>
          ) : (
            <Calculators />
          )}
        </div>
      </div>

      <footer
        className="shrink-0 border-t px-5 py-2 text-[10px]"
        style={{ borderColor: "var(--border)", color: "var(--text-faint)" }}
      >
        Estimates for comparison only. Not financial, investment, or tax advice.
        Tax figures are federal estimates and ignore many real-return details.
      </footer>
    </div>
  );
}
