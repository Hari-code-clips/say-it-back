#!/usr/bin/env bash
# Step 6 (optional, pilot only, with OUTBOX=1, after 02; the outbox needs a firebase-mode service,
# which 02 does not deploy yet, so 02 stops on OUTBOX=1: build-notes/36-security-fixes-a.md). A Cloud Scheduler job that calls the backend's
# POST /admin/outbox/retry every minute with the bearer SIB_OUTBOX_TOKEN, so a decision the permit system
# did not take is retried (docs/EPERMIT_ADAPTER.md, "Retries"). Cloud Run gives an instance CPU only while
# it serves a request, so the retries run inside these calls.
#
# The job has to send the token itself, so this script reads the latest version of
# OUTBOX_TOKEN_SECRET_NAME and never prints it. The token then sits in the job's configuration: limit who
# can read Cloud Scheduler jobs. Running the script again updates the job to the current service URL and
# token, which is how a rotated token reaches it (deploy/RUNBOOK.md). Cloud Scheduler bills US$0.10 a job
# a month past three free jobs per billing account.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "$SCRIPT_DIR/config.sh"

if [[ "$OUTBOX" != 1 ]]; then
  echo "OUTBOX is 0: no retry job. Set OUTBOX=1 and OUTBOX_TOKEN_SECRET_NAME, run 02, then this step." >&2
  exit 0
fi

run gcloud services enable cloudscheduler.googleapis.com --project "$PROJECT_ID"

SERVICE_URL="$(capture gcloud run services describe "$SERVICE" --region "$REGION" \
  --project "$PROJECT_ID" --format='value(status.url)')" \
  || die "Could not read the Cloud Run service $SERVICE in $REGION. Run deploy/02_deploy_backend.sh first."
[[ "$SERVICE_URL" == https://* ]] || die "Could not read the service URL (got '$SERVICE_URL')."

token="$(capture gcloud secrets versions access latest --secret="$OUTBOX_TOKEN_SECRET_NAME" \
  --project "$PROJECT_ID")" || die "Could not read the latest version of $OUTBOX_TOKEN_SECRET_NAME."
# --headers takes KEY=VALUE pairs split on commas, so the token must be one plain word. Never printed.
token_pattern='^[A-Za-z0-9._~+/=-]{16,}$'
[[ "$token" =~ $token_pattern ]] \
  || die "The token in $OUTBOX_TOKEN_SECRET_NAME must be 16 or more letters, digits or ._~+/=- (openssl rand -hex 32 makes one)."

JOB="say-it-back-outbox-retry"
RETRY_URL="$SERVICE_URL/admin/outbox/retry"
# --format keeps gcloud from printing the job, whose headers hold the token.
if probe gcloud scheduler jobs describe "$JOB" --location="$REGION" --project "$PROJECT_ID"; then
  run_hiding "$token" gcloud scheduler jobs update http "$JOB" --location="$REGION" --project "$PROJECT_ID" \
    --schedule="* * * * *" --uri="$RETRY_URL" --http-method=post \
    --update-headers="Authorization=Bearer $token" --format='value(name)'
else
  run_hiding "$token" gcloud scheduler jobs create http "$JOB" --location="$REGION" --project "$PROJECT_ID" \
    --schedule="* * * * *" --uri="$RETRY_URL" --http-method=post \
    --headers="Authorization=Bearer $token" --format='value(name)'
fi

echo "Retry job $JOB calls $RETRY_URL every minute."
echo "Next: decide a test briefing and check its record reads 'Sent to the permit system' (docs/EPERMIT_ADAPTER.md, Runbook)."
