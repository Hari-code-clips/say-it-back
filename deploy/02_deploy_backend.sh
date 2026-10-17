#!/usr/bin/env bash
# Step 2. Build backend/ with Cloud Build and deploy it to Cloud Run as $SERVICE.
# This creates billable build and Cloud Run usage. MIN_INSTANCES (config.sh) is 1 for the judging
# window, so one idle instance bills; with 0, idle time costs nothing.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=config.sh
source "$SCRIPT_DIR/config.sh"

# The pilot e-permit link releases real permits, so it needs accounts (SIB_AUTH_MODE=firebase): in
# device mode no person stands behind a decision, and the service refuses to start with the link on.
# These scripts deploy device mode only, so stop before anything is built or deployed. The message
# never prints PTW_URL (it can hold a key).
if [[ "$OUTBOX" == 1 || -n "$PTW_URL" ]]; then
  die "The e-permit link (OUTBOX=1, PTW_URL) needs a service with SIB_AUTH_MODE=firebase, and these scripts deploy device mode only (build-notes/34-auth.md). Set OUTBOX=0 and leave PTW_URL empty."
fi

# gcloud uploads backend/ as the build context. It reads backend/.gcloudignore and does not
# read the repository-root .gitignore, so refuse to upload until that file exists. Local .data/
# and .venv/ must stay out of the image.
[[ -f "$REPO_ROOT/backend/.gcloudignore" ]] \
  || die "backend/.gcloudignore is missing. Add it before deploying (see deploy/README.md)."

# Endpoints 16-19 (the Sample page) read the evaluation test set and its latest report (SIB_EVAL_DIR,
# which the Dockerfile points at /app/eval). They live in eval/, outside the backend/ folder that
# gcloud uploads, so copy them into backend/eval_data/ for the build and remove the copy when this
# script ends. Either may be missing: that endpoint then answers 404, as it does without eval data.
EVAL_STAGE="$REPO_ROOT/backend/eval_data"
unstage_eval() { rm -rf "$EVAL_STAGE/testset" "$EVAL_STAGE/reports"; }
unstage_eval # a copy left by an interrupted run must not ship
trap unstage_eval EXIT
run mkdir -p "$EVAL_STAGE"
run touch "$EVAL_STAGE/.gitkeep" # the Dockerfile copies this folder, so it must not be empty
if [[ -d "$REPO_ROOT/eval/testset" ]]; then
  run cp -R "$REPO_ROOT/eval/testset" "$EVAL_STAGE/testset"
else
  echo "warning: eval/testset not found. /api/eval/items will answer 404." >&2
fi
if [[ -f "$REPO_ROOT/eval/reports/latest.json" ]]; then
  run mkdir -p "$EVAL_STAGE/reports"
  run cp "$REPO_ROOT/eval/reports/latest.json" "$EVAL_STAGE/reports/latest.json"
else
  echo "warning: eval/reports/latest.json not found. /api/eval/latest will answer 404." >&2
fi

# Backend settings. Some values contain commas, so the list uses the ^@^ form: a leading
# ^DELIM^ makes gcloud split key=value pairs on DELIM ("@") instead of ",".
# The model ids are the exact pins in config.sh (check each Agent Platform id at deploy).
# SIB_DAILY_GEMINI_CALLS caps Gemini calls per UTC day across all instances, counted in Firestore
# (docs/API.md, "Daily cap"); 0 refuses every Gemini-backed call. SIB_DAILY_CALLS_PER_IP is each
# client address's share of it (0 turns it off). Both come from config.sh (DAILY_CALLS,
# DAILY_CALLS_PER_IP): raise them for a judging or recording window.
# SIB_TRUSTED_PROXY_HOPS says which X-Forwarded-For entry, counted from the right, is the client
# address: 1 is the one Cloud Run's front end appends. Per-address limits depend on it, so check it
# after the first deploy (backend/README.md, "Cloud Run"). Values that match the app's defaults are
# still set here, so the values the deployed service runs on are in one visible place.
# SIB_WEBHOOK_URL is set every time (empty sends no webhook), so removing a URL from config.sh removes
# it from the service. It can hold a key, so the deploy command is printed with it hidden.
# SIB_RETENTION_DAYS (RETENTION_DAYS) stamps each new briefing with its expiry; step 1's Firestore TTL
# policy does the deleting, so run 01 again whenever this changes to or from 0.
ENV_VARS="^@^GOOGLE_GENAI_USE_ENTERPRISE=true@GOOGLE_CLOUD_PROJECT=$PROJECT_ID@GOOGLE_CLOUD_LOCATION=global@SIB_LIVE_LOCATION=$LIVE_LOCATION@SIB_STORE=firestore@SIB_TRACE_TO_CLOUD=true"
ENV_VARS="$ENV_VARS@SIB_FLASH_MODEL=$FLASH_MODEL@SIB_JUDGE_B_MODEL=$JUDGE_B_MODEL@SIB_LIVE_MODEL=$LIVE_MODEL@SIB_TTS_MODEL=$TTS_MODEL"
ENV_VARS="$ENV_VARS@SIB_DAILY_GEMINI_CALLS=$DAILY_CALLS@SIB_DAILY_CALLS_PER_IP=$DAILY_CALLS_PER_IP@SIB_TRUSTED_PROXY_HOPS=1"
ENV_VARS="$ENV_VARS@SIB_RATE_LIMIT_PER_MIN=$RATE_LIMIT_PER_MIN@SIB_MAX_SOCKETS_PER_IP=$MAX_SOCKETS_PER_IP"
ENV_VARS="$ENV_VARS@SIB_MAX_OUTPUT_TOKENS=$MAX_OUTPUT_TOKENS@SIB_WEBHOOK_TIMEOUT_S=$WEBHOOK_TIMEOUT_S@SIB_TTS_LOCATION=$TTS_LOCATION"
ENV_VARS="$ENV_VARS@SIB_RETENTION_DAYS=$RETENTION_DAYS"
ALLOWED_ORIGINS="https://$PROJECT_ID.web.app,https://$PROJECT_ID.firebaseapp.com"
if [[ -n "${EXTRA_ORIGINS// /}" ]]; then
  ALLOWED_ORIGINS="$ALLOWED_ORIGINS,${EXTRA_ORIGINS// /}"
fi
ENV_VARS="$ENV_VARS@SIB_ALLOWED_ORIGINS=$ALLOWED_ORIGINS"
ENV_VARS="$ENV_VARS@SIB_WEBHOOK_URL=${WEBHOOK_URLS// /}"
# The pilot e-permit link (OUTBOX, PTW_URL, PTW_FIELD_MAP in config.sh) is off here (the check at the
# top), and set every time, so a deploy also turns off a link set on the service by hand.
if [[ "$OUTBOX" == 1 ]]; then OUTBOX_FLAG=true; else OUTBOX_FLAG=false; fi
ENV_VARS="$ENV_VARS@SIB_OUTBOX=$OUTBOX_FLAG@SIB_PTW_URL=$PTW_URL@SIB_PTW_FIELD_MAP=$PTW_FIELD_MAP"
if [[ -n "$BQ_DATASET" ]]; then
  ENV_VARS="$ENV_VARS@SIB_BQ_DATASET=$PROJECT_ID.$BQ_DATASET"
fi

# Secrets stay in Secret Manager: this script never reads or prints a value, only the secret's name.
# Cloud Run exposes each to the app as an environment variable, and the runtime service account gets
# read access to that one secret.
# - GOOGLE_API_KEY, only when USE_DEVELOPER_API_KEY=1.
# - SIB_WEBHOOK_SECRET (the HMAC key of the signed webhooks), only when WEBHOOK_SECRET_NAME is set.
SECRETS=()
grant_secret() {
  probe gcloud secrets describe "$1" --project "$PROJECT_ID" \
    || die "Secret $1 not found. Create it in Secret Manager first ($2)."
  run gcloud secrets add-iam-policy-binding "$1" \
    --member="serviceAccount:$RUNTIME_SA" --role=roles/secretmanager.secretAccessor \
    --project "$PROJECT_ID" >/dev/null
}
if [[ "$USE_DEVELOPER_API_KEY" == "1" ]]; then
  grant_secret "$GEMINI_KEY_SECRET" "or set USE_DEVELOPER_API_KEY=0"
  SECRETS+=("GOOGLE_API_KEY=$GEMINI_KEY_SECRET:latest")
fi
if [[ -n "$WEBHOOK_SECRET_NAME" ]]; then
  grant_secret "$WEBHOOK_SECRET_NAME" "or leave WEBHOOK_SECRET_NAME empty for unsigned webhooks"
  SECRETS+=("SIB_WEBHOOK_SECRET=$WEBHOOK_SECRET_NAME:latest")
fi
# - SIB_OUTBOX_TOKEN (the bearer of POST /admin/outbox/retry) and SIB_PTW_TOKEN (the bearer sent to
#   SIB_PTW_URL), each only when its secret is named (docs/EPERMIT_ADAPTER.md).
if [[ -n "$OUTBOX_TOKEN_SECRET_NAME" ]]; then
  grant_secret "$OUTBOX_TOKEN_SECRET_NAME" "or set OUTBOX=0 and leave OUTBOX_TOKEN_SECRET_NAME empty"
  SECRETS+=("SIB_OUTBOX_TOKEN=$OUTBOX_TOKEN_SECRET_NAME:latest")
fi
if [[ -n "$PTW_TOKEN_SECRET_NAME" ]]; then
  grant_secret "$PTW_TOKEN_SECRET_NAME" "or leave PTW_TOKEN_SECRET_NAME empty"
  SECRETS+=("SIB_PTW_TOKEN=$PTW_TOKEN_SECRET_NAME:latest")
fi
SECRET_ARGS=()
if (( ${#SECRETS[@]} > 0 )); then
  SECRET_ARGS=(--set-secrets "$(IFS=,; echo "${SECRETS[*]}")")
fi

# --allow-unauthenticated is deliberate. The browser calls this URL directly, for the API and for the
# Live WebSocket (Firebase Hosting does not proxy WebSockets, and a rewrite would put another proxy in
# front of the client address; docs/ARCHITECTURE.md). The app guards its endpoints itself: a device key
# per browser that owns its briefings, an Origin allow-list for the WebSocket, single-use tickets, and
# per-address limits and daily allowances (docs/API.md).
# --update-env-vars merges with the variables already set on the service.
run_hiding "${WEBHOOK_URLS// /}"$'\n'"$PTW_URL" gcloud run deploy "$SERVICE" \
  --source "$REPO_ROOT/backend" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --service-account "$RUNTIME_SA" \
  --allow-unauthenticated \
  --timeout=900 \
  --min-instances="$MIN_INSTANCES" \
  --max-instances="$MAX_INSTANCES" \
  --memory="$MEMORY" \
  --session-affinity \
  --update-env-vars "$ENV_VARS" \
  ${SECRET_ARGS[@]+"${SECRET_ARGS[@]}"}

# The WebSocket base is the service's own wss:// address. It exists only after the first deploy.
SERVICE_URL="$(capture gcloud run services describe "$SERVICE" --region "$REGION" \
  --project "$PROJECT_ID" --format='value(status.url)')"
[[ "$SERVICE_URL" == https://* ]] || die "Could not read the service URL (got '$SERVICE_URL')."
run gcloud run services update "$SERVICE" --region "$REGION" --project "$PROJECT_ID" \
  --update-env-vars "SIB_PUBLIC_WS_BASE=wss://${SERVICE_URL#https://}"

echo "Backend URL: $SERVICE_URL"
echo "Next: deploy/03_deploy_web.sh (and, optionally, deploy/04_deploy_ptw_stub.sh)"
