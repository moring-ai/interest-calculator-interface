#!/usr/bin/env bash
# Point the LiteLLM gateway at the AgentCore runtime in the current account.
#
#   AWS_PROFILE=moring ./scripts/set-agent-arn.sh
#   ./scripts/set-agent-arn.sh arn:aws:bedrock-agentcore:...    # explicit
#
# Reads the ARN from the agent's CloudFormation stack rather than asking you to
# copy it. An ARN embeds both an account and a region, so a stale one in
# litellm/config.yaml points the gateway at a runtime in a different account --
# which fails as an opaque permissions error at the first chat message, not at
# deploy time.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
CONFIG="$REPO_ROOT/litellm/config.yaml"
REGION="${AWS_REGION:-$(aws configure get region 2>/dev/null || echo us-east-1)}"
STACK="${AGENT_STACK:-AgentCore-InterestCalculatorAgent-default}"

#: Substring used to pick our runtime out of the account's list.
AGENT_MATCH="${AGENT_MATCH:-interest}"

if [ $# -ge 1 ]; then
    ARN="$1"
else
    # Two lookups, because the runtime can be created two different ways and
    # only one of them leaves a CloudFormation stack behind:
    #   agentcore CLI -> CDK -> CloudFormation  (stack exists)
    #   AICP / any direct API caller            (no stack at all)
    echo "Looking for the runtime ARN in $REGION..."

    ARN="$(aws cloudformation describe-stacks \
        --stack-name "$STACK" --region "$REGION" \
        --query "Stacks[0].Outputs[?ends_with(OutputKey, 'RuntimeArnOutput') || contains(OutputKey, 'RuntimeArn')].OutputValue | [0]" \
        --output text 2>/dev/null || echo "")"

    if [ -n "$ARN" ] && [ "$ARN" != "None" ]; then
        echo "  found via CloudFormation stack $STACK"
    else
        echo "  no CloudFormation stack; listing agent runtimes instead"

        # The bundled AWS CLI predates bedrock-agentcore-control, so this needs
        # a Python with a recent boto3. Prefer the repo venvs over the system
        # interpreter, which typically has no boto3 at all.
        PYBIN=""
        for CANDIDATE in \
            "$REPO_ROOT/.venv/bin/python" \
            "$REPO_ROOT/../interest-calculator-agent/.venv/bin/python" \
            python3
        do
            if command -v "$CANDIDATE" >/dev/null 2>&1 && \
               "$CANDIDATE" -c "import boto3" >/dev/null 2>&1; then
                PYBIN="$CANDIDATE"; break
            fi
        done

        if [ -z "$PYBIN" ]; then
            echo "  no Python with boto3 found; cannot list runtimes" >&2
            echo "  install it with: uv pip install --python .venv/bin/python boto3" >&2
        fi

        ARN="$([ -n "$PYBIN" ] && "$PYBIN" - "$REGION" "$AGENT_MATCH" <<'PY' 2>/dev/null || echo ""
import sys
try:
    import boto3
except ImportError:
    sys.exit(1)
region, match = sys.argv[1], sys.argv[2].lower()
try:
    rts = boto3.client("bedrock-agentcore-control", region_name=region) \
               .list_agent_runtimes(maxResults=50).get("agentRuntimes", [])
except Exception:
    sys.exit(1)
hits = [r for r in rts if match in r.get("agentRuntimeName", "").lower()]
# Newest first, so a redeploy under a new name wins over a stale one.
hits.sort(key=lambda r: r.get("lastUpdatedAt") or r.get("createdAt") or "", reverse=True)
if hits:
    print(hits[0]["agentRuntimeArn"])
PY
)"
        [ -n "$ARN" ] && echo "  found by listing runtimes (name contains '$AGENT_MATCH')"
    fi
fi

if [ -z "$ARN" ] || [ "$ARN" = "None" ]; then
    echo "Could not find a runtime ARN." >&2
    echo "Checked: CloudFormation stack '$STACK', and runtimes whose name" >&2
    echo "contains '$AGENT_MATCH', in region $REGION." >&2
    echo >&2
    echo "If the agent is deployed, your credentials may have expired:" >&2
    echo "  aws sso login --profile \${AWS_PROFILE:-moring}" >&2
    echo "Otherwise pass the ARN directly:" >&2
    echo "  $0 arn:aws:bedrock-agentcore:...:runtime/..." >&2
    exit 1
fi

case "$ARN" in
    arn:aws:bedrock-agentcore:*:runtime/*) ;;
    *) echo "That does not look like an AgentCore runtime ARN: $ARN" >&2; exit 1 ;;
esac

ARN_REGION="$(printf '%s' "$ARN" | cut -d: -f4)"
ARN_ACCOUNT="$(printf '%s' "$ARN" | cut -d: -f5)"

python3 - "$CONFIG" "$ARN" "$ARN_REGION" <<'PY'
import pathlib, re, sys
path, arn, region = sys.argv[1], sys.argv[2], sys.argv[3]
p = pathlib.Path(path)
s = p.read_text()
s = re.sub(r"model: bedrock/agentcore/\S+", f"model: bedrock/agentcore/{arn}", s)
s = re.sub(r"aws_region_name: \S+", f"aws_region_name: {region}", s)
p.write_text(s)
PY

echo "litellm/config.yaml ->"
echo "  account : $ARN_ACCOUNT"
echo "  region  : $ARN_REGION"
echo "  runtime : ${ARN##*/}"
echo
echo "Pass the same ARN to the app-host stack:"
echo "  terraform apply -var agent_runtime_arn=$ARN"
