"""Bridge between the browser and the agent, via the LiteLLM gateway.

The backend no longer talks to AWS directly. It speaks plain OpenAI
chat-completions to the LiteLLM proxy, which holds the AWS credentials and
routes `interest-agent` to `bedrock/agentcore/{runtime_arn}`. That indirection
is what makes the gateway useful: virtual keys, spend limits, request logs and
model swaps all happen in the proxy, not here.

The cost of going through a chat-completions shape is that the agent's rich
event stream is flattened to text. Chart payloads survive because the agent
emits them as fenced blocks, which `payload_parser` lifts back out -- see that
module for why.

The event protocol handed to the browser is unchanged from before the split:

    {"type": "session",     "session_id": ...}
    {"type": "text",        "text": ...}
    {"type": "tool_start",  "name": ...}
    {"type": "tool_result", "name": ..., "payload": {...}}
    {"type": "done"}
    {"type": "error",       "message": ...}
"""

from __future__ import annotations

import logging
from typing import AsyncIterator

from openai import APIStatusError, APITimeoutError, AsyncOpenAI, OpenAIError

from .config import get_settings
from .payload_parser import PayloadStreamParser

log = logging.getLogger(__name__)


def _client() -> AsyncOpenAI:
    settings = get_settings()
    return AsyncOpenAI(
        base_url=settings.litellm_base_url,
        api_key=settings.litellm_api_key,
        timeout=settings.agent_timeout_seconds,
        max_retries=1,
    )


def _friendly_error(exc: Exception) -> str:
    """Turn a gateway failure into something worth showing a user."""
    if isinstance(exc, APITimeoutError):
        return "The agent took too long to respond. Try a simpler question."
    if isinstance(exc, APIStatusError):
        status = exc.status_code
        if status == 401:
            return ("The gateway rejected the API key. Check LITELLM_API_KEY "
                    "against the keys in litellm/config.yaml.")
        if status == 404:
            return ("The gateway has no model by that name. Check AGENT_MODEL "
                    "against model_list in litellm/config.yaml.")
        if status == 429:
            return "The agent is rate limited right now. Try again shortly."
        if status >= 500:
            return ("The gateway could not reach the agent runtime. Check the "
                    "LiteLLM logs for the underlying AWS error.")
        return f"The gateway returned {status}: {exc}"
    if isinstance(exc, OpenAIError):
        return (f"Could not reach the LiteLLM gateway at "
                f"{get_settings().litellm_base_url}: {exc}")
    return f"Unexpected error talking to the agent: {exc}"


async def stream_turn(message: str, session_id: str) -> AsyncIterator[dict]:
    """Run one conversational turn and yield normalized events."""
    settings = get_settings()
    parser = PayloadStreamParser()
    seen_tools: set[str] = set()

    def announce(event: dict) -> list[dict]:
        """Emit a tool_start before the first result from each tool.

        LiteLLM drops the runtime's `contentBlockStart` events, so there is no
        live signal for "a tool is running" any more. Deriving it from the
        payload keeps the UI's tool chips working; they simply appear when the
        tool finishes rather than when it starts.
        """
        if event["type"] != "tool_result":
            return [event]
        name = event.get("name", "tool")
        if name in seen_tools:
            return [event]
        seen_tools.add(name)
        return [{"type": "tool_start", "name": name}, event]

    try:
        stream = await _client().chat.completions.create(
            model=settings.agent_model,
            messages=[{"role": "user", "content": message}],
            stream=True,
            # AgentCore keeps per-session conversation state; reusing the id
            # across turns is what makes follow-up questions work.
            extra_body={"runtimeSessionId": session_id},
        )
    except Exception as exc:                          # noqa: BLE001
        log.error("chat completion failed: %s", exc)
        yield {"type": "error", "message": _friendly_error(exc)}
        return

    try:
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None)
            if not content:
                continue
            for event in parser.feed(content):
                for out in announce(event):
                    yield out
        for event in parser.flush():
            for out in announce(event):
                yield out
    except Exception as exc:                          # noqa: BLE001
        log.exception("error while reading the agent stream")
        yield {"type": "error", "message": _friendly_error(exc)}
        return

    yield {"type": "done"}
