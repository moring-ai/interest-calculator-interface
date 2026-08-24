import type { ChatEvent, RateQuote, ToolResult } from "../types";

const BASE = "/api";

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch { /* keep the status text */ }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => json<{ status: string; agent_configured: boolean; rates: unknown }>("/health"),

  rateBoard: () => json<{ rates: RateQuote[] }>("/rates/board"),

  rateCatalog: () =>
    json<{ rates: { key: string; label: string; category: string; description: string }[] }>(
      "/rates/catalog",
    ),

  rateHistory: (key: string, months = 24) =>
    json<ToolResult>(`/rates/${key}/history?months=${months}`),

  chatStatus: () => json<{ agent_configured: boolean }>("/chat/status"),

  calcMortgage: (body: unknown) =>
    json<ToolResult>("/calc/mortgage", { method: "POST", body: JSON.stringify(body) }),

  calcCompare: (body: unknown) =>
    json<ToolResult>("/calc/mortgage/compare", { method: "POST", body: JSON.stringify(body) }),

  calcSavings: (body: unknown) =>
    json<ToolResult>("/calc/savings", { method: "POST", body: JSON.stringify(body) }),

  calcCapitalGains: (body: unknown) =>
    json<ToolResult>("/calc/capital-gains", { method: "POST", body: JSON.stringify(body) }),
};

/**
 * Stream a chat turn, invoking `onEvent` as each SSE event arrives.
 *
 * Uses fetch + ReadableStream rather than EventSource because the request is a
 * POST with a JSON body, which EventSource cannot express. The buffer is
 * carried across chunks since an SSE frame can split anywhere.
 */
export async function streamChat(
  message: string,
  sessionId: string | null,
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
    signal,
  });

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch { /* keep the generic message */ }
    onEvent({ type: "error", message: detail });
    onEvent({ type: "done" });
    return;
  }
  if (!res.body) {
    onEvent({ type: "error", message: "The server sent no response body." });
    onEvent({ type: "done" });
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE frames are separated by a blank line.
    let split: number;
    while ((split = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, split);
      buffer = buffer.slice(split + 2);
      for (const line of frame.split("\n")) {
        if (!line.startsWith("data:")) continue;
        const payload = line.slice(5).trim();
        if (!payload) continue;
        try {
          onEvent(JSON.parse(payload) as ChatEvent);
        } catch {
          console.warn("unparseable SSE frame", payload);
        }
      }
    }
  }
}
