# interest-calculator-interface

Frontend and API for the interest calculator. Reaches the agent through a
**LiteLLM** gateway and the tools through **ToolHive** over MCP.

The math lives in
[interest-calculator-agent](https://github.com/moring-ai/interest-calculator-agent).
This repository imports none of it — both paths here go over the network, which
is what stops the two repositories drifting apart on a number.

---

## Architecture

```
web/ (React + Recharts)
  │ REST + SSE
backend/ (FastAPI)
  ├─► LiteLLM proxy ──► AgentCore Runtime ──► MCP tools     /api/chat
  └─► MCP client ─────────────────────────► MCP tools       /api/calc, /api/rates
```

Two upstreams, deliberately independent. The calculators keep working when the
model is throttled or the gateway is down.

| Route | Path | LLM? |
|---|---|---|
| `/api/chat` | LiteLLM → AgentCore → tools | yes |
| `/api/calc/*` | MCP → tools | no |
| `/api/rates/*` | MCP → tools | no |

## Layout

```
backend/app/
  agent_client.py    OpenAI-shaped calls to the LiteLLM gateway
  payload_parser.py  recovers chart payloads from the text stream
  mcp_client.py      calls the tool server directly for calculators
  routers/           chat, calc, rates
litellm/config.yaml  gateway config: maps `interest-agent` to the runtime ARN
docker-compose.yml   LiteLLM + API
web/                 React frontend
```

## Setup

```bash
cp .env.example .env
```

Fill in `MCP_SERVER_URL` and `MCP_SERVER_TOKEN` from the agent repo:

```bash
cd ../interest-calculator-agent/infra/toolhive && terraform output -raw mcp_url && terraform output -raw mcp_token
```

AWS credentials are **not** copied into `.env` — the gateway mounts `~/.aws`
read-only, so the secret lives in one place and the API never sees it.

## Running

```bash
docker compose up
```

That starts the LiteLLM gateway on `:4000` and the API on `:8000`. Then the
frontend, outside compose so Vite's hot reload works:

```bash
cd web && npm install && npm run dev
```

Open http://localhost:5173.

If Vite fails to boot with a missing `@rolldown/binding-darwin-arm64`, npm
skipped a platform-specific optional dependency:

```bash
cd web && npm install --no-save @rolldown/binding-darwin-arm64
```

Or run everything with one command, which also sets up TLS trust:

```bash
./scripts/dev.sh
```

## Deploying to EC2

Production runs on its own Graviton instance at **https://interest.moring.ai**,
behind Google sign-in restricted to `@moring.ai` accounts.

```
EC2 t4g.small
  Caddy :443
   ├── /oauth2/*  → oauth2-proxy      Google sign-in
   ├── forward_auth → oauth2-proxy    gate on everything below
   ├── /api/*     → backend
   └── /*         → static frontend
                      backend → litellm → AgentCore Runtime
```

Three properties worth knowing:

- **No AWS credentials on the box.** The instance has an IAM role granting only
  `bedrock-agentcore:InvokeAgentRuntime` and `ssm:GetParameter`; LiteLLM picks
  it up from IMDS. The `~/.aws` mount in `docker-compose.yml` is a local-development
  pattern and is deliberately absent from the deployed stack.
- **Everything is same-origin.** Caddy serves the static build and proxies
  `/api` from one hostname, so there is no CORS and no API base URL to configure.
- **Auth needs no application code.** oauth2-proxy sits in front of the whole
  app and passes `X-Forwarded-Email` through, so per-user features can be added
  later without revisiting authentication.

### First deploy

There is an ordering constraint: Caddy cannot obtain a certificate until DNS
resolves, and Google will not redirect to a URL you have not registered.

```bash
cd infra/app-host && terraform init && terraform apply
```

1. `terraform output dns_record_required` prints the A record to create.
   **`moring.ai` is not in Route53 in this account**, so add it wherever the
   domain is registered.
2. Create an OAuth client at
   [console.cloud.google.com/apis/credentials](https://console.cloud.google.com/apis/credentials)
   → *OAuth client ID* → *Web application*, using the origin and redirect URI
   from `terraform output`.
3. Store the credentials — the secret is read with echo off and written
   straight to SSM, never to a file:

```bash
./scripts/set-google-oauth.sh
```

4. Build, push and start:

```bash
./scripts/deploy-app.sh
```

Subsequent deploys are just step 4. Shell access is via Session Manager
(`aws ssm start-session --target $(terraform output -raw instance_id)`); there
is no SSH port open.

## Tests

```bash
cd backend && ../.venv/bin/python -m pytest tests/ -q
```

20 tests, all on `payload_parser`. That module is where the chart pipeline can
silently break, so the suite feeds it text one character at a time to prove no
chunk boundary can lose a payload or leak a fence into the prose.

## Design notes

**Why the chart payloads need parsing at all.** LiteLLM's AgentCore adapter
extracts only `event.contentBlockDelta.delta.text` from the runtime's stream and
drops everything else. Tool results sent as their own event type vanish. The
agent works around it by emitting each result as a fenced ```` ```ic-payload ````
block inside its text; `payload_parser` lifts those back out and re-emits them
as structured events, so the browser-facing protocol is unchanged.

**Why the gateway is a proxy, not the SDK.** Running LiteLLM as a service means
virtual keys, spend limits, request logs and model swaps are all configuration
rather than code. The backend holds no AWS credentials at all.

**Tool chips arrive late.** LiteLLM drops `contentBlockStart`, so there is no
live "a tool is running" signal. `agent_client` synthesises a `tool_start` from
each payload's `tool` field — the chip appears when the tool finishes rather
than when it starts.

**The synthetic-rate warning is derived, not configured.** The backend no longer
owns the rate provider, so the honest signal is the `freshness` field on the
rates that actually came back, not a config flag.

---

Estimates for comparison only. Not financial, investment, or tax advice.
