#!/usr/bin/env bash
# Step 4 (optional). Deploy integrations/ptw-stub as a second Cloud Run service, $PTW_SERVICE: a small
# stand-in for a site's permit-to-work system. It receives the backend's signed decision webhook,
# releases (Go) or holds (No-go) a permit, and shows them on a permit board at its root URL.
#
# It needs the same webhook secret as the backend (WEBHOOK_SECRET_NAME in config.sh, a Secret Manager
# secret you create; this script never reads or prints its value): the stub refuses unsigned posts.
# Afterwards add "<its URL>/webhook" to WEBHOOK_URLS in config.sh and run 02_deploy_backend.sh again.
#
# This creates billable build and Cloud Run usage. Permits are kept in Firestore (PTW_STORE=firestore,
# collection `permits` in the project's database, which 01_setup_project.sh creates), so a new or
# restarted instance shows the same board and the stub can scale to zero (PTW_MIN_INSTANCES=0 in
# config.sh): the first board view after a quiet spell waits a few seconds for a cold start.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=config.sh
source "$SCRIPT_DIR/config.sh"

STUB_DIR="$REPO_ROOT/integrations/ptw-stub"
[[ -f "$STUB_DIR/Dockerfile" ]] || die "integrations/ptw-stub/Dockerfile is missing."
[[ -f "$STUB_DIR/.gcloudignore" ]] \
  || die "integrations/ptw-stub/.gcloudignore is missing. Add it before deploying (see deploy/README.md)."
[[ -n "$WEBHOOK_SECRET_NAME" ]] \
  || die "WEBHOOK_SECRET_NAME is empty. The permit-to-work stub refuses unsigned webhooks: create the secret and set it in deploy/config.sh."
probe gcloud secrets describe "$WEBHOOK_SECRET_NAME" --project "$PROJECT_ID" \
  || die "Secret $WEBHOOK_SECRET_NAME not found. Create it in Secret Manager first."
probe gcloud firestore databases describe --database="(default)" --project "$PROJECT_ID" \
  || die "No Firestore database in $PROJECT_ID. Run deploy/01_setup_project.sh first."

# Its own service account: it may read that one secret and use Firestore (roles/datastore.user). That
# role is project-wide, as Firestore roles cannot be narrowed to one collection, so the account could
# read the backend's briefings too; the stub's code touches only `permits` and `permit_counters`.
if probe gcloud iam service-accounts describe "$PTW_SA" --project "$PROJECT_ID"; then
  echo "Service account $PTW_SA already exists."
else
  run gcloud iam service-accounts create "$PTW_SA_NAME" \
    --display-name="Say It Back permit-to-work stub" --project "$PROJECT_ID"
fi
run gcloud secrets add-iam-policy-binding "$WEBHOOK_SECRET_NAME" \
  --member="serviceAccount:$PTW_SA" --role=roles/secretmanager.secretAccessor \
  --project "$PROJECT_ID" >/dev/null
run gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$PTW_SA" --role=roles/datastore.user --condition=None >/dev/null

# --allow-unauthenticated is deliberate: the backend's webhook carries no Google identity, and the
# permit board is the demo. Every post is checked against the HMAC signature (300 s window) instead.
run gcloud run deploy "$PTW_SERVICE" \
  --source "$STUB_DIR" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --service-account "$PTW_SA" \
  --allow-unauthenticated \
  --min-instances="$PTW_MIN_INSTANCES" \
  --max-instances=1 \
  --memory=256Mi \
  --set-env-vars PTW_STORE=firestore \
  --set-secrets "SIB_WEBHOOK_SECRET=$WEBHOOK_SECRET_NAME:latest"

PTW_URL="$(capture gcloud run services describe "$PTW_SERVICE" --region "$REGION" \
  --project "$PROJECT_ID" --format='value(status.url)')"
[[ "$PTW_URL" == https://* ]] || die "Could not read the stub's URL (got '$PTW_URL')."

echo "Permit board: $PTW_URL/"
echo "Next: add $PTW_URL/webhook to WEBHOOK_URLS in deploy/config.sh, then run deploy/02_deploy_backend.sh again."
