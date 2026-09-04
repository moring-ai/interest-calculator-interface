"""Bridge between the browser and the agent.

Two routes, chosen by configuration:

1. **Token vending** (`AICP_AGENT_URL`). Used when the agent is hosted on AICP.
   The platform mints a short-lived bearer scoped to one agent, and the runtime
   is then called directly with it. This is the only route that works for a
   platform-hosted agent: its runtime uses a JWT authorizer, so anything
   presenting a SigV4 signature is refused with an authorization-method
   mismatch -- including the platform's own /invoke proxy, which signs.

   Calling the runtime directly also returns the agent's real event stream
   rather than a flattened answer, so text arrives incrementally.

2. **A LiteLLM gateway** speaking OpenAI chat-completions, which routes
   `interest-agent` to `bedrock/agentcore/{runtime_arn}`. Works when the runtime
   uses an AWS_IAM authorizer, which is what a CLI deploy into your own account
   produces.

Either way, chart payloads survive because the agent emits them as fenced
blocks that `payload_parser` lifts back out -- see that module for why.

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


async def _vend_agent_token(client: httpx.AsyncClient) -> dict:
    """Exchange the platform token for a short-lived, agent-scoped one.

    The runtime is configured with a JWT authorizer, so it expects a bearer
    token -- not a SigV4 signature. The platform's own /invoke proxy signs with
    SigV4 and is therefore refused by its own runtime, which is why this takes
    the token-vending path instead: mint a bearer scoped to this one agent and
    call AgentCore directly with it.

    Returns the platform's response: access_token, expires_in, invoke_url and
    session_header.
    """
    settings = get_settings()
    token_url = settings.aicp_token_url
    response = await client.post(
        token_url,
        json={},
        headers={
            "Authorization": f"Bearer {settings.aicp_access_token}",
            "Content-Type": "application/json",
        },
    )
    response.raise_for_status()
    return response.json()


def _text_from_agent_event(event: dict) -> str:
    """Pull assistant text out of one raw AgentCore stream event.

    Calling the runtime directly returns the agent's own event stream rather
    than a flattened answer, so the text arrives in the same shape the agent
    emits it -- including the fenced payload blocks the parser is looking for.
    """
    inner = event.get("event", event)
    if not isinstance(inner, dict):
        return ""
    delta = inner.get("contentBlockDelta", {}).get("delta", {})
    if isinstance(delta, dict) and isinstance(delta.get("text"), str):
        return delta["text"]
    return ""


def _error_from_agent_event(event: dict) -> str:
    """Return an agent-side error carried in the stream, if there is one.

    The runtime reports its own failures as `{"error": ..., "error_type": ...}`
    events rather than a non-200 status. Ignoring those is why a broken agent
    looked like a hang: the stream completed normally having produced no text,
    so the UI showed a sent question and nothing else. Anything that stops the
    agent answering should reach the user as words.
    """
    if not isinstance(event, dict):
        return ""
    error = event.get("error")
    if not error:
        return ""
    if isinstance(error, dict):
        error = error.get("message") or json.dumps(error, default=str)
    kind = event.get("error_type")
    return f"{kind}: {error}" if kind else str(error)


def _explain_agent_error(raw: str) -> str:
    """Translate the agent's own error into something actionable.

    The MCP failure in particular arrives wrapped by anyio as "unhandled errors
    in a TaskGroup", which names neither the tool server nor the reason.
    """
    if "Failed to start MCP client" in raw or "Failed to load tool" in raw:
        return ("The agent could not connect to its tool server. Usually its "
                "MCP_SERVER_TOKEN is wrong or its MCP_SERVER_URL is "
                "unreachable -- check those on the agent in the platform. "
                f"Underlying error: {raw[:200]}")
    return f"The agent reported an error: {raw[:300]}"


async def _stream_via_aicp(message: str, session_id: str) -> AsyncIterator[dict]:
    """Invoke a platform-hosted agent using a vended, agent-scoped token."""
    settings = get_settings()
    seen_tools: set[str] = set()

    parser = PayloadStreamParser()
    saw_text = False
    saw_error = False

    def announce(event: dict):
        """Emit a tool_start the first time each tool reports a result."""
        out = []
        if event["type"] == "tool_result":
            name = event.get("name", "tool")
            if name not in seen_tools:
                seen_tools.add(name)
                out.append({"type": "tool_start", "name": name})
        out.append(event)
        return out

    try:
        async with httpx.AsyncClient(
            timeout=settings.agent_timeout_seconds, verify=resolve_ca_bundle()
        ) as client:
            # --- 1. mint an agent-scoped bearer -------------------------------
            try:
                vended = await _vend_agent_token(client)
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                if code == 401:
                    yield {"type": "error", "message":
                           "The platform rejected the access token. It is short "
                           "lived -- refresh the dashboard and update "
                           "AICP_ACCESS_TOKEN."}
                elif code == 403:
                    yield {"type": "error", "message":
                           "Authenticated, but this account lacks can_call on "
                           "the agent. Request access in the platform."}
                else:
                    log.error("token vending failed %s: %s", code,
                              exc.response.text[:300])
                    yield {"type": "error", "message":
                           f"Could not mint an agent token ({code}): "
                           f"{exc.response.text[:160]}"}
                return

            token = vended.get("access_token")
            invoke_url = vended.get("invoke_url")
            session_header = vended.get(
                "session_header", "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id")
            if not token or not invoke_url:
                log.error("unexpected token response: %s",
                          json.dumps(vended, default=str)[:300])
                yield {"type": "error", "message":
                       "The platform returned a token response this app could "
                       "not read. See the API logs for the raw body."}
                return

            # --- 2. call the runtime directly with that bearer ----------------
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream, application/json",
                session_header: session_id,
            }

            async with client.stream(
                "POST", invoke_url, json={"prompt": message}, headers=headers
            ) as response:
                if response.status_code >= 400:
                    raw = (await response.aread()).decode("utf-8", "replace")
                    log.error("runtime returned %s: %s", response.status_code, raw[:400])
                    yield {"type": "error", "message":
                           f"The agent runtime returned {response.status_code}: "
                           f"{raw[:200]}"}
                    return

                content_type = response.headers.get("content-type", "")

                if "text/event-stream" in content_type:
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line.startswith("data:"):
                            continue
                        blob = line[5:].strip()
                        if not blob or blob == "[DONE]":
                            continue
                        try:
                            event = json.loads(blob)
                        except json.JSONDecodeError:
                            continue
                        agent_error = _error_from_agent_event(event)
                        if agent_error:
                            log.error("agent reported: %s", agent_error)
                            yield {"type": "error",
                                   "message": _explain_agent_error(agent_error)}
                            saw_error = True
                            continue

                        text = _text_from_agent_event(event)
                        if not text:
                            continue
                        saw_text = True
                        for parsed in parser.feed(text):
                            for out in announce(parsed):
                                yield out
                else:
                    raw = (await response.aread()).decode("utf-8", "replace")
                    try:
                        answer = _extract_answer(json.loads(raw))
                    except json.JSONDecodeError:
                        answer = raw
                    if not answer:
                        log.warning("no answer in runtime response: %s", raw[:300])
                        yield {"type": "error", "message":
                               "The agent returned a response this app could not read."}
                        return
                    for parsed in parser.feed(answer):
                        for out in announce(parsed):
                            yield out

    except httpx.HTTPError as exc:
        log.error("AICP invoke failed: %s", exc)
        yield {"type": "error",
               "message": f"Could not reach the platform: {exc}"}
        return

    for parsed in parser.flush():
        for out in announce(parsed):
            yield out

    if not saw_text and not saw_error:
        # Completing with nothing at all previously rendered as a hang: the
        # question sent, no answer, no explanation.
        log.error("agent stream produced no text and no error")
        yield {"type": "error", "message":
               "The agent returned an empty response. It is deployed but "
               "produced no output -- check its logs in the platform."}

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
