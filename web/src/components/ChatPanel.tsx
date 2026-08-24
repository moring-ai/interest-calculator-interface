import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatMessage, ToolResult } from "../types";
import { streamChat } from "../api/client";
import { humanize } from "../lib/format";
import { Callout, Spinner } from "./Primitives";
import { Markdown } from "./Markdown";

const SUGGESTIONS = [
  "What would a $600k house cost me monthly with 20% down?",
  "Compare a 30-year and a 15-year on a $450k loan",
  "If I save $800/month for 20 years, what do I end up with?",
  "I'd sell stock for $180k that cost me $120k. What's the tax?",
];

function uid() {
  return Math.random().toString(36).slice(2, 10);
}

export function ChatPanel({
  agentReady,
  onResults,
}: {
  agentReady: boolean;
  /** Lifts tool results to the canvas so charts render beside the chat. */
  onResults: (results: ToolResult[]) => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || busy) return;

      const assistantId = uid();
      setMessages((prev) => [
        ...prev,
        { id: uid(), role: "user", text: trimmed, toolsUsed: [], results: [] },
        { id: assistantId, role: "assistant", text: "", toolsUsed: [], results: [], streaming: true },
      ]);
      setInput("");
      setBusy(true);

      const controller = new AbortController();
      abortRef.current = controller;
      const collected: ToolResult[] = [];

      const patch = (fn: (m: ChatMessage) => ChatMessage) =>
        setMessages((prev) => prev.map((m) => (m.id === assistantId ? fn(m) : m)));

      try {
        await streamChat(trimmed, sessionId, (event) => {
          switch (event.type) {
            case "session":
              setSessionId(event.session_id);
              break;
            case "text":
              patch((m) => ({ ...m, text: m.text + event.text }));
              break;
            case "tool_start":
              patch((m) => ({
                ...m,
                toolsUsed: m.toolsUsed.includes(event.name)
                  ? m.toolsUsed
                  : [...m.toolsUsed, event.name],
              }));
              break;
            case "tool_result":
              if (!event.payload?.isError) collected.push(event.payload);
              patch((m) => ({ ...m, results: [...m.results, event.payload] }));
              break;
            case "error":
              patch((m) => ({ ...m, error: event.message }));
              break;
            case "done":
              patch((m) => ({ ...m, streaming: false }));
              break;
          }
        }, controller.signal);
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          patch((m) => ({ ...m, error: (err as Error).message, streaming: false }));
        }
      } finally {
        patch((m) => ({ ...m, streaming: false }));
        setBusy(false);
        abortRef.current = null;
        if (collected.length) onResults(collected);
      }
    },
    [busy, sessionId, onResults],
  );

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {messages.length === 0 && (
          <div className="space-y-4 pt-6">
            <div>
              <h3 className="text-sm font-semibold" style={{ color: "var(--text)" }}>
                Ask about rates
              </h3>
              <p className="mt-1 text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>
                Every number comes from a calculation tool, never from the model's
                own arithmetic. Charts appear on the right as they are computed.
              </p>
            </div>
            {!agentReady && (
              <Callout tone="warn">
                No agent runtime is configured, so chat is unavailable. The
                Calculators tab works without it.
              </Callout>
            )}
            <div className="space-y-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  disabled={!agentReady}
                  onClick={() => send(s)}
                  className="w-full rounded-lg border px-3 py-2 text-left text-xs transition-colors disabled:opacity-40"
                  style={{
                    borderColor: "var(--border)",
                    background: "var(--surface)",
                    color: "var(--text-muted)",
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => (
          <div key={m.id} className="animate-in">
            {m.role === "user" ? (
              <div className="flex justify-end">
                <div
                  className="max-w-[85%] rounded-2xl rounded-br-sm px-3.5 py-2 text-sm"
                  style={{ background: "var(--accent-soft)", color: "var(--text)" }}
                >
                  {m.text}
                </div>
              </div>
            ) : (
              <div className="space-y-2.5">
                {m.toolsUsed.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {m.toolsUsed.map((t) => (
                      <span
                        key={t}
                        className="rounded-md px-1.5 py-0.5 text-[10px] font-medium"
                        style={{ background: "var(--surface-2)", color: "var(--text-faint)" }}
                      >
                        {humanize(t)}
                      </span>
                    ))}
                  </div>
                )}

                {m.text && <Markdown text={m.text} />}

                {m.streaming && !m.text && <Spinner label="Thinking…" />}
                {m.error && <Callout tone="danger">{m.error}</Callout>}

                {m.results.filter((r) => r.isError).map((r, i) => (
                  <Callout key={i} tone="danger">{r.error}</Callout>
                ))}
              </div>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={(e) => { e.preventDefault(); send(input); }}
        className="border-t p-3"
        style={{ borderColor: "var(--border)" }}
      >
        <div
          className="flex items-end gap-2 rounded-xl border px-3 py-2"
          style={{ borderColor: "var(--border-strong)", background: "var(--surface)" }}
        >
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); }
            }}
            rows={1}
            disabled={!agentReady || busy}
            placeholder={agentReady ? "Ask about a mortgage, savings, or a sale…" : "Agent unavailable"}
            className="max-h-32 flex-1 resize-none bg-transparent text-sm outline-none disabled:opacity-50"
            style={{ color: "var(--text)" }}
          />
          <button
            type="submit"
            disabled={!agentReady || busy || !input.trim()}
            className="rounded-lg px-3 py-1.5 text-xs font-semibold transition-opacity disabled:opacity-30"
            style={{ background: "var(--accent)", color: "#fff" }}
          >
            {busy ? "…" : "Send"}
          </button>
        </div>
      </form>
    </div>
  );
}
