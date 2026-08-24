#!/usr/bin/env bash
# Store the Google OAuth client credentials in SSM.
#
#   ./scripts/set-google-oauth.sh
#
# The secret is read with the terminal echo off and written straight to SSM as
# a SecureString. It is never printed, never written to a file in the repo, and
# never passes through Terraform state -- which is why the parameters are
# created as placeholders and filled in here.
#
# Get the credentials first:
#   1. https://console.cloud.google.com/apis/credentials
#   2. Create credentials -> OAuth client ID -> Web application
#   3. Authorized JavaScript origin:  https://interest.moring.ai
#      Authorized redirect URI:       https://interest.moring.ai/oauth2/callback
#      (both are printed by `terraform output` in infra/app-host)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TF_DIR="$HERE/../infra/app-host"
REGION="${AWS_REGION:-us-east-2}"

if [ ! -d "$TF_DIR/.terraform" ]; then
    echo "Run 'terraform apply' in infra/app-host first." >&2
    exit 1
fi

ID_PARAM="$(cd "$TF_DIR" && terraform output -raw google_client_id_parameter)"
SECRET_PARAM="$(cd "$TF_DIR" && terraform output -raw google_client_secret_parameter)"
INSTANCE_ID="$(cd "$TF_DIR" && terraform output -raw instance_id)"

printf 'Google OAuth client ID: '
read -r CLIENT_ID
printf 'Google OAuth client secret (hidden): '
read -rs CLIENT_SECRET
printf '\n'

[ -z "$CLIENT_ID" ] && { echo "No client ID given." >&2; exit 1; }
[ -z "$CLIENT_SECRET" ] && { echo "No client secret given." >&2; exit 1; }

case "$CLIENT_ID" in
    *.apps.googleusercontent.com) ;;
    *) echo "That does not look like a Google client ID (expected it to end in" >&2
       echo ".apps.googleusercontent.com). Continuing anyway." >&2 ;;
esac

aws ssm put-parameter --region "$REGION" --name "$ID_PARAM" \
    --value "$CLIENT_ID" --type String --overwrite >/dev/null
aws ssm put-parameter --region "$REGION" --name "$SECRET_PARAM" \
    --value "$CLIENT_SECRET" --type SecureString --overwrite >/dev/null

echo "Stored in SSM ($ID_PARAM, $SECRET_PARAM)."
echo "==> Restarting the app so it picks them up"

CMD_ID="$(aws ssm send-command --region "$REGION" \
    --instance-ids "$INSTANCE_ID" \
    --document-name AWS-RunShellScript \
    --comment "Reload OAuth credentials" \
    --parameters 'commands=["systemctl restart interest-app.service"]' \
    --query 'Command.CommandId' --output text)"

aws ssm wait command-executed --region "$REGION" \
    --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" 2>/dev/null || true

aws ssm get-command-invocation --region "$REGION" \
    --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" \
    --query 'Status' --output text

echo "Done."
