#!/usr/bin/env bash
# Build the frontend and API images, push them to ECR, and restart the app host.
#
#   ./scripts/deploy-app.sh
#
# Reads every identifier from Terraform outputs, so there is nothing to keep in
# sync by hand. Images are linux/arm64 to match the Graviton instance.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
TF_DIR="$REPO_ROOT/infra/app-host"
REGION="${AWS_REGION:-us-east-2}"

if [ ! -d "$TF_DIR/.terraform" ]; then
    echo "Run 'terraform apply' in infra/app-host first." >&2
    exit 1
fi

cd "$TF_DIR"
WEB_REPO="$(terraform output -raw ecr_web_repository_url)"
API_REPO="$(terraform output -raw ecr_backend_repository_url)"
INSTANCE_ID="$(terraform output -raw instance_id)"
APP_URL="$(terraform output -raw app_url)"
REGISTRY="${WEB_REPO%%/*}"
cd "$REPO_ROOT"

echo "==> Logging in to ECR"
aws ecr get-login-password --region "$REGION" \
    | docker login --username AWS --password-stdin "$REGISTRY"

# Braces around the variable are load-bearing: in zsh, "$VAR:latest" is parsed
# as the :l lowercase modifier and silently mangles the tag.
echo "==> Building frontend"
docker build --platform linux/arm64 -t "${WEB_REPO}:latest" web/

echo "==> Building API"
docker build --platform linux/arm64 -t "${API_REPO}:latest" backend/

echo "==> Pushing"
docker push "${WEB_REPO}:latest"
docker push "${API_REPO}:latest"

echo "==> Restarting the app host"
CMD_ID="$(aws ssm send-command --region "$REGION" \
    --instance-ids "$INSTANCE_ID" \
    --document-name AWS-RunShellScript \
    --comment "Redeploy app" \
    --parameters 'commands=["systemctl restart interest-app.service"]' \
    --query 'Command.CommandId' --output text)"

aws ssm wait command-executed --region "$REGION" \
    --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" 2>/dev/null || true

aws ssm get-command-invocation --region "$REGION" \
    --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" \
    --query '{Status:Status,Error:StandardErrorContent}' --output json

echo
echo "Deployed: $APP_URL"
