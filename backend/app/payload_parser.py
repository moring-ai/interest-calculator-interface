"""Extract structured tool payloads from a plain text stream.

Why this exists
---------------
The agent's tool results carry the chart specs. LiteLLM's AgentCore adapter
reads only ``event.contentBlockDelta.delta.text`` out of the runtime's SSE
stream and drops every other event shape, so a tool result sent as its own
event type never survives the hop. The agent therefore emits each result as a
fenced block inside its text:

    ```ic-payload
    {"tool":"calculate_mortgage","summary":{...},"charts":[...]}
    ```

This module pulls those blocks back out of the streamed text and hands them on
as structured events, leaving the surrounding prose untouched.

The parsing is incremental because the text arrives in arbitrary chunks: a
fence can be split across two chunks, and a single payload can span dozens of
them. The parser therefore holds back any trailing text that might be the start
of a fence, rather than emitting it and discovering the fence too late.
"""

from __future__ import annotations

import json
import logging
from typing import Iterator

log = logging.getLogger(__name__)

FENCE_TAG = "ic-payload"
FENCE_OPEN = f"```{FENCE_TAG}"
FENCE_CLOSE = "```"

#: Refuse to buffer an unbounded payload. A malformed or unterminated fence
#: would otherwise swallow the rest of the response into memory and the user
#: would see the answer simply stop.
MAX_PAYLOAD_CHARS = 2_000_000


class PayloadStreamParser:
    """Splits a text stream into prose and `ic-payload` blocks.

    Usage:
        parser = PayloadStreamParser()
        for chunk in stream:
            for event in parser.feed(chunk):
                ...
        for event in parser.flush():
            ...

    Events are ``{"type": "text", "text": ...}`` or
    ``{"type": "tool_result", "name": ..., "payload": {...}}``.
    """

    def __init__(self) -> None:
        self._buffer = ""
        self._in_payload = False

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _longest_partial_suffix(text: str, token: str) -> int:
        """Length of the longest suffix of `text` that prefixes `token`.

        Used to decide how much trailing text to hold back: if the buffer ends
        with "``" we cannot emit it yet, because the next chunk may complete a
        fence and that text would then belong to the payload, not the prose.
        """
        limit = min(len(text), len(token) - 1)
        for size in range(limit, 0, -1):
            if token.startswith(text[-size:]):
                return size
        return 0

    def _emit_payload(self, raw: str) -> Iterator[dict]:
        body = raw.strip()
        if not body:
            return
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            # Surface nothing rather than corrupt the transcript; the prose is
            # still perfectly readable without the chart.
            log.warning("discarding unparseable %s block: %s", FENCE_TAG, exc)
            return
        if not isinstance(payload, dict):
            log.warning("%s block was not a JSON object; discarding", FENCE_TAG)
            return
        yield {
            "type": "tool_result",
            "name": payload.get("tool", "tool"),
            "payload": payload,
        }

    # -- streaming --------------------------------------------------------

    def feed(self, chunk: str) -> Iterator[dict]:
        if not chunk:
            return
        self._buffer += chunk

        if len(self._buffer) > MAX_PAYLOAD_CHARS:
            log.error("payload buffer exceeded %d chars; resetting", MAX_PAYLOAD_CHARS)
            self._buffer = ""
            self._in_payload = False
            return

        while True:
            if not self._in_payload:
                start = self._buffer.find(FENCE_OPEN)
                if start == -1:
                    # No fence yet. Emit everything except a trailing fragment
                    # that might turn out to be the beginning of one.
                    hold = self._longest_partial_suffix(self._buffer, FENCE_OPEN)
                    emit, self._buffer = self._buffer[:len(self._buffer) - hold], self._buffer[len(self._buffer) - hold:]
                    if emit:
                        yield {"type": "text", "text": emit}
                    return

                before = self._buffer[:start]
                if before:
                    yield {"type": "text", "text": before}
                # Skip the opening fence and the newline that follows it.
                rest = self._buffer[start + len(FENCE_OPEN):]
                self._buffer = rest[1:] if rest.startswith("\n") else rest
                self._in_payload = True
                continue

            end = self._buffer.find(FENCE_CLOSE)
            if end == -1:
                return  # Still accumulating the payload body.

            yield from self._emit_payload(self._buffer[:end])
            self._buffer = self._buffer[end + len(FENCE_CLOSE):]
            self._in_payload = False

    def flush(self) -> Iterator[dict]:
        """Emit whatever is left once the stream ends."""
        if self._in_payload:
            # An unterminated fence means the agent was cut off mid-payload.
            log.warning("stream ended inside an %s block; discarding it", FENCE_TAG)
            self._buffer = ""
            self._in_payload = False
            return
        if self._buffer:
            yield {"type": "text", "text": self._buffer}
            self._buffer = ""


def strip_payloads(text: str) -> str:
    """Remove every payload block from a complete (non-streamed) string."""
    parser = PayloadStreamParser()
    parts = [e["text"] for e in parser.feed(text) if e["type"] == "text"]
    parts += [e["text"] for e in parser.flush() if e["type"] == "text"]
    return "".join(parts)
