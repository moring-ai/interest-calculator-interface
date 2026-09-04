"""Bridge between the browser and the agent.

Two routes, chosen by configuration:

1. **The platform Agent API** (`AICP_AGENT_URL`). Used when the agent is hosted
   on AICP. The platform authenticates the caller with Keycloak, checks
   `can_call` on that specific agent, and signs the AgentCore invocation
   server-side -- this process never holds AWS credentials or the runtime ARN.
   Required rather than optional for a platform-hosted agent: its runtime is
   locked to a JWT authorizer, so the SigV4 signing that route 2 performs is
   refused with an authorization-method mismatch.

2. **A LiteLLM gateway** speaking OpenAI chat-completions, which routes
   `interest-agent` to `bedrock/agentcore/{runtime_arn}`. Works when the runtime
   uses an AWS_IAM authorizer, which is what a CLI deploy into your own account
   produces.

Either way the agent's rich event stream is flattened to text. Chart payloads
survive because the agent emits them as fenced blocks, which `payload_parser`
lifts back out -- see that module for why.

The event protocol handed to the browser is unchanged from before the split:

    {"type": "session",     "session_id": ...}
    {"type": "text",        "text": ...}
    {"type": "tool_start",  "name": ...}
    {"type": "tool_result", "name": ..., "payload": {...}}
    {"type": "done"}
    {"type": "error",       "message": ...}
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

import httpx
from openai import APIStatusError, APITimeoutError, AsyncOpenAI, OpenAIError

from .config import get_settings
from .mcp_client import resolve_ca_bundle
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


# --------------------------------------------------------------------------
# AICP governed Agent API
# --------------------------------------------------------------------------

#: Keys the platform might return the agent's answer under. Checked in order;
#: the response envelope is not something this repo controls, so matching a few
#: plausible shapes is cheaper than failing on an unexpected one.
_ANSWER_KEYS = ("response", "output", "result", "answer", "completion",
                "content", "text", "message")


def _extract_answer(body: Any) -> str:
    """Pull the agent's text out of whatever envelope the platform returns."""
    if isinstance(body, str):
        return body
    if isinstance(body, dict):
        for key in _ANSWER_KEYS:
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value
            # One level of nesting, e.g. {"result": {"response": "..."}}.
            if isinstance(value, (dict, list)):
                nested = _extract_answer(value)
                if nested:
                    return nested
    if isinstance(body, list):
        parts = [_extract_answer(item) for item in body]
        joined = "".join(p for p in parts if p)
        if joined:
            return joined
    return ""


async def _stream_via_aicp(message: str, session_id: str) -> AsyncIterator[dict]:
    """Invoke a platform-hosted agent through its governed API.

    The platform authenticates the caller with Keycloak, checks `can_call` on
    this agent, and signs the AgentCore invocation server-side. The response
    arrives whole rather than streamed, so the payload parser sees it as a
    single chunk -- which it handles the same as any other chunking.
    """
    settings = get_settings()
    seen_tools: set[str] = set()

    payload = {"payload": {"prompt": message}, "session_id": session_id}
    headers = {
        "Authorization": f"Bearer {settings.aicp_access_token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(
            timeout=settings.agent_timeout_seconds, verify=resolve_ca_bundle()
        ) as client:
            response = await client.post(
                settings.aicp_agent_url, json=payload, headers=headers
            )
    except httpx.HTTPError as exc:
        log.error("AICP invoke failed: %s", exc)
        yield {"type": "error",
               "message": f"Could not reach the platform Agent API: {exc}"}
        return

    if response.status_code == 401:
        yield {"type": "error", "message":
               "The platform rejected the access token. It may have expired -- "
               "get a fresh Keycloak token and update AICP_ACCESS_TOKEN."}
        return
    if response.status_code == 403:
        yield {"type": "error", "message":
               "Authorized, but this account lacks can_call on the agent. "
               "Request access to it in the platform."}
        return
    if response.status_code >= 400:
        log.error("AICP returned %s: %s", response.status_code, response.text[:400])
        yield {"type": "error", "message":
               f"The platform returned {response.status_code}: {response.text[:200]}"}
        return

    try:
        body = response.json()
    except json.JSONDecodeError:
        body = response.text

    answer = _extract_answer(body)
    if not answer:
        log.warning("No answer field found in AICP response: %s",
                    json.dumps(body, default=str)[:400])
        yield {"type": "error",
               "message": "The platform returned a response this app could not "
                          "read. See the API logs for the raw body."}
        return

    parser = PayloadStreamParser()
    for event in list(parser.feed(answer)) + list(parser.flush()):
        if event["type"] == "tool_result":
            name = event.get("name", "tool")
            if name not in seen_tools:
                seen_tools.add(name)
                yield {"type": "tool_start", "name": name}
        yield event

    yield {"type": "done"}


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

    # A platform-hosted agent is locked to a JWT authorizer, so the LiteLLM
    # route below (which signs with SigV4) can never reach it. Prefer the
    # governed API whenever one is configured.
    if settings.uses_aicp:
        async for event in _stream_via_aicp(message, session_id):
            yield event
        return

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
