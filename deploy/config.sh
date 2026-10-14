#!/usr/bin/env bash
# Settings and helpers shared by deploy/01, 02 and 03. Sourced, never run on its own.
# Nothing in this folder runs in CI. The project owner runs the scripts by hand (see deploy/README.md).

# Required. No default. Export PROJECT_ID in your shell, or type your project id on the line below.
PROJECT_ID="${PROJECT_ID:-}"

REGION="asia-south1"                # Cloud Run and Firestore.
LIVE_LOCATION="us-central1"         # Gemini Live is served from US or EU Agent Platform endpoints only.
SERVICE="say-it-back-api"           # Cloud Run service name. firebase.json repeats it; keep them equal.
RUNTIME_SA_NAME="say-it-back-run"   # Runtime service account. Its email address is derived below.

# Optional BigQuery dataset for the ADK analytics plugin (letters, digits, underscores). Empty skips it.
BQ_DATASET="${BQ_DATASET:-}"

MAX_INSTANCES="3"                   # Small ceiling. Minimum instances stay at 0.
MEMORY="1Gi"                        # Cloud Run defaults to 512Mi, which may be tight for ADK.

# Optional Developer API key path. Keep 0 unless a *_BACKEND is developer-api (docs/ARCHITECTURE.md).
# The key value never passes through these scripts. Create the Secret Manager entry yourself.
USE_DEVELOPER_API_KEY="${USE_DEVELOPER_API_KEY:-0}"
GEMINI_KEY_SECRET="${GEMINI_KEY_SECRET:-say-it-back-gemini-key}"

if [[ -z "$PROJECT_ID" ]]; then
  echo "error: PROJECT_ID is required. Export it, or set it in deploy/config.sh." >&2
  exit 1
fi
project_pattern='^[a-z][a-z0-9-]{4,28}[a-z0-9]$'
if [[ ! "$PROJECT_ID" =~ $project_pattern ]]; then
  echo "error: '$PROJECT_ID' is not a valid Google Cloud project id." >&2
  exit 1
fi
dataset_pattern='^[A-Za-z0-9_]+$'
if [[ -n "$BQ_DATASET" && ! "$BQ_DATASET" =~ $dataset_pattern ]]; then
  echo "error: BQ_DATASET may contain only letters, digits and underscores." >&2
  exit 1
fi

RUNTIME_SA="${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Helpers. Each one prints the command to stderr before it runs.
run()     { printf '+ %s\n' "$*" >&2; "$@"; }                   # changes something
probe()   { printf '? %s\n' "$*" >&2; "$@" >/dev/null 2>&1; }   # read-only check; exit status only
capture() { printf '+ %s\n' "$*" >&2; "$@"; }                    # read-only; the caller captures stdout
die()     { printf 'error: %s\n' "$*" >&2; exit 1; }
