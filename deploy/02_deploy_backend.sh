#!/usr/bin/env bash
# Step 2 of 3. Build backend/ with Cloud Build and deploy it to Cloud Run as $SERVICE.
# This creates billable build and Cloud Run usage. With min-instances 0, idle time costs nothing.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=config.sh
source "$SCRIPT_DIR/config.sh"

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
# SIB_DAILY_GEMINI_CALLS caps Gemini calls per UTC day across all instances, counted in Firestore
# (docs/API.md, "Daily cap"). 300 is the app's default; 0 refuses every Gemini-backed call.
# SIB_DAILY_CALLS_PER_IP is each client address's share of it (100, the app's default; 0 turns it off).
# SIB_TRUSTED_PROXY_HOPS says which X-Forwarded-For entry, counted from the right, is the client
# address: 1 is the one Cloud Run's front end appends. Per-address limits depend on it, so check it
# after the first deploy (backend/README.md, "Cloud Run"). Both are set here although they match the
# defaults, so the values the deployed service runs on are in one visible place.
ENV_VARS="^@^GOOGLE_GENAI_USE_ENTERPRISE=true@GOOGLE_CLOUD_PROJECT=$PROJECT_ID@GOOGLE_CLOUD_LOCATION=global@SIB_LIVE_LOCATION=$LIVE_LOCATION@SIB_STORE=firestore@SIB_TRACE_TO_CLOUD=true@SIB_DAILY_GEMINI_CALLS=300@SIB_DAILY_CALLS_PER_IP=100@SIB_TRUSTED_PROXY_HOPS=1@SIB_ALLOWED_ORIGINS=https://$PROJECT_ID.web.app,https://$PROJECT_ID.firebaseapp.com"
if [[ -n "$BQ_DATASET" ]]; then
  ENV_VARS="$ENV_VARS@SIB_BQ_DATASET=$PROJECT_ID.$BQ_DATASET"
fi

# Optional. Only when USE_DEVELOPER_API_KEY=1. The key stays in Secret Manager, and this script
# never reads or prints its value. Cloud Run exposes it to the app as the GOOGLE_API_KEY variable.
# The runtime service account gets read access to that one secret.
SECRET_ARGS=()
if [[ "$USE_DEVELOPER_API_KEY" == "1" ]]; then
  probe gcloud secrets describe "$GEMINI_KEY_SECRET" --project "$PROJECT_ID" \
    || die "Secret $GEMINI_KEY_SECRET not found. Create it in Secret Manager, or set USE_DEVELOPER_API_KEY=0."
  run gcloud secrets add-iam-policy-binding "$GEMINI_KEY_SECRET" \
    --member="serviceAccount:$RUNTIME_SA" --role=roles/secretmanager.secretAccessor \
    --project "$PROJECT_ID" >/dev/null
  SECRET_ARGS=(--set-secrets "GOOGLE_API_KEY=$GEMINI_KEY_SECRET:latest")
fi

# --allow-unauthenticated is deliberate. The browser calls this URL directly, for the API and for the
# Live WebSocket (Firebase Hosting does not proxy WebSockets, and a rewrite would put another proxy in
# front of the client address; docs/ARCHITECTURE.md). The app guards its endpoints itself: a device key
# per browser that owns its briefings, an Origin allow-list for the WebSocket, single-use tickets, and
# per-address limits and daily allowances (docs/API.md).
# --update-env-vars merges with the variables already set on the service.
run gcloud run deploy "$SERVICE" \
  --source "$REPO_ROOT/backend" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --service-account "$RUNTIME_SA" \
  --allow-unauthenticated \
  --timeout=900 \
  --min-instances=0 \
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
echo "Next: deploy/03_deploy_web.sh"
