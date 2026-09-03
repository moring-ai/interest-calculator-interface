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

if [ $# -ge 1 ]; then
    ARN="$1"
else
    echo "Reading the runtime ARN from stack $STACK in $REGION..."
    ARN="$(aws cloudformation describe-stacks \
        --stack-name "$STACK" --region "$REGION" \
        --query "Stacks[0].Outputs[?ends_with(OutputKey, 'RuntimeArnOutput') || contains(OutputKey, 'RuntimeArn')].OutputValue | [0]" \
        --output text 2>/dev/null || echo "")"
fi

if [ -z "$ARN" ] || [ "$ARN" = "None" ]; then
    echo "Could not find a runtime ARN." >&2
    echo "Deploy the agent first (agentcore deploy -y in the agent repo)," >&2
    echo "or pass the ARN as an argument." >&2
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
