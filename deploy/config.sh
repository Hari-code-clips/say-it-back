#!/usr/bin/env bash
# Settings and helpers shared by deploy/01 to 06. Sourced, never run on its own.
# Nothing in this folder runs in CI. The project owner runs the scripts by hand (see deploy/README.md).

# Required. No default. Export PROJECT_ID in your shell, or type your project id on the line below.
PROJECT_ID="${PROJECT_ID:-}"

# Where the data is kept: Cloud Run and Firestore run in REGION, set from this preset below. in is
# asia-south1 (Mumbai), sg is asia-southeast1 (Singapore). Step 1 fixes the Firestore database's
# location when it creates it, and a database cannot move. Gemini is served in neither: Flash and TTS
# run on Agent Platform's global endpoint and Live in LIVE_LOCATION. Data at rest stays in the region;
# model processing does not (deploy/README.md, "Where the data is").
DATA_REGION="${DATA_REGION:-in}"
LIVE_LOCATION="us-central1"         # Gemini Live is served from US or EU Agent Platform endpoints only.
SERVICE="say-it-back-api"           # Cloud Run service name. Step 3 reads its URL for VITE_API_BASE.
RUNTIME_SA_NAME="say-it-back-run"   # Runtime service account. Its email address is derived below.

# Optional BigQuery dataset for the ADK analytics plugin (letters, digits, underscores). Empty skips it.
BQ_DATASET="${BQ_DATASET:-}"

MAX_INSTANCES="3"                   # Small ceiling.
MEMORY="1Gi"                        # Cloud Run defaults to 512Mi, which may be tight for ADK.
MIN_INSTANCES="${MIN_INSTANCES:-1}" # 1 for the judging window (19 Oct to 14 Nov, and to the 4 Dec finale
                                    # if shortlisted): no cold start, and the TTS cache and rate state
                                    # survive. About US$13 a month idle. Set 0 once judging is over.
PTW_MIN_INSTANCES="${PTW_MIN_INSTANCES:-0}" # The permit stub keeps its permits in Firestore, so it can
                                            # scale to zero: a cold start costs the first board view a
                                            # few seconds, and no permit is lost.

# Exact model ids, pinned here so the deployed service never follows a moving alias (the older preview
# ids shut down on 17 Nov). The Developer API names are the defaults. The exact Agent Platform id of
# each MUST be checked at deploy (Model Garden, or a one-call probe in the project): they can differ.
FLASH_MODEL="${FLASH_MODEL:-gemini-3.8-flash}"           # SIB_FLASH_MODEL. Check the exact Agent Platform id at deploy.
JUDGE_B_MODEL="${JUDGE_B_MODEL-gemini-3.1-flash-lite}"   # SIB_JUDGE_B_MODEL, judge B's second model. Check the exact
                                                         # Agent Platform id at deploy. Empty runs judge B on FLASH_MODEL.
LIVE_MODEL="${LIVE_MODEL:-gemini-3.8-live}"              # SIB_LIVE_MODEL. Check the exact Agent Platform id at deploy
                                                         # (Live is served from LIVE_LOCATION).
TTS_MODEL="${TTS_MODEL:-gemini-3.8-flash-tts}"           # SIB_TTS_MODEL. Check the exact Agent Platform id at deploy.

# Daily cost bounds (docs/API.md, "Daily cap"), counted in Firestore across every instance.
# Sized for the free-trial credit (about INR 28,800) over the judging window: 600 units is about 27 full
# takes a day and about INR 510 a day in ordinary use; the worst case (every call at the output ceiling
# below) is about INR 1,700 a day, which the budget alert (BILLING_ACCOUNT, below) reports long before
# the credit runs out. Lower the cap without a rebuild: gcloud run services update ... --update-env-vars.
DAILY_CALLS="${DAILY_CALLS:-600}"                 # SIB_DAILY_GEMINI_CALLS.
DAILY_CALLS_PER_IP="${DAILY_CALLS_PER_IP:-300}"   # SIB_DAILY_CALLS_PER_IP: a room of judges on one Wi-Fi
                                                  # shares one address.
RATE_LIMIT_PER_MIN="${RATE_LIMIT_PER_MIN:-120}"   # SIB_RATE_LIMIT_PER_MIN: turn mode fetches every line at once.
MAX_SOCKETS_PER_IP="${MAX_SOCKETS_PER_IP:-12}"    # SIB_MAX_SOCKETS_PER_IP: open Live sockets per address and instance.
MAX_OUTPUT_TOKENS="${MAX_OUTPUT_TOKENS:-4096}"    # SIB_MAX_OUTPUT_TOKENS per Flash and TTS call, thinking included.
                                                  # The largest measured reply was 587; 4096 halves the worst case.
WEBHOOK_TIMEOUT_S="${WEBHOOK_TIMEOUT_S:-5}"       # SIB_WEBHOOK_TIMEOUT_S: the decision waits this long, at most,
                                                  # for every webhook together.
TTS_LOCATION="${TTS_LOCATION:-global}"            # SIB_TTS_LOCATION. If probe_models.sh finds TTS missing on
                                                  # global, set us-central1.

# Extra browser origins the API accepts, comma-separated https:// origins, for example a named Hosting
# site (https://say-it-back-demo.web.app). The project's own web.app and firebaseapp.com are always in.
EXTRA_ORIGINS="${EXTRA_ORIGINS:-}"

# Optional https link to the recorded demo video. Step 3 builds it into the page (VITE_DEMO_VIDEO_URL): a
# link on the landing page and in the daily-limit message. Empty shows nothing.
DEMO_VIDEO_URL="${DEMO_VIDEO_URL:-}"

# Optional budget alert, created by 01_setup_project.sh when BILLING_ACCOUNT is set (gcloud billing
# accounts list). The amount is in the billing account's currency, for example 28797INR. The alert
# ignores credits: on a free trial, cost after credits stays at zero, so an alert that counted them
# would never fire. Alerts only notify; when the trial credit runs out, the project stops.
BILLING_ACCOUNT="${BILLING_ACCOUNT:-}"
BUDGET_AMOUNT="${BUDGET_AMOUNT:-28797INR}"

# Optional decision webhooks (docs/API.md, "Webhooks"): up to 3 comma-separated URLs, for example the
# permit-to-work stub of step 4 ("<its URL>/webhook") and a Google Chat space. Empty sends none. A URL
# can hold a key, so the scripts never print it.
WEBHOOK_URLS="${WEBHOOK_URLS:-}"
# Optional Secret Manager secret that holds SIB_WEBHOOK_SECRET, the HMAC key that signs the JSON posts.
# Create it yourself; the scripts never read or print its value. Empty sends unsigned posts. Step 4
# needs it: the permit-to-work stub refuses unsigned posts.
WEBHOOK_SECRET_NAME="${WEBHOOK_SECRET_NAME:-}"

# Days a briefing record is kept: SIB_RETENTION_DAYS, 0 (keep) to 3650. The backend stamps each new
# record with expireAt, and step 1's Firestore TTL policy deletes it within about 24 hours after that.
# 0 keeps every record, and step 1 then switches the TTL policy off, so records stamped earlier stay
# too. A change applies to records created after it: run 01 and 02 again.
RETENTION_DAYS="${RETENTION_DAYS:-90}"

# Optional address for step 5's email alerts (05_monitoring.sh): the API's health check or the web
# app failing, or many 5xx answers. Empty skips step 5.
ALERT_EMAIL="${ALERT_EMAIL:-}"

# Optional pilot e-permit link (docs/EPERMIT_ADAPTER.md), off by default. It needs SIB_AUTH_MODE=firebase, which
# these scripts do not deploy yet, so 02 stops on OUTBOX=1 or PTW_URL (build-notes/36). OUTBOX=1 sets SIB_OUTBOX=true:
# each decision's deliveries are kept in Firestore and retried through POST /admin/outbox/retry, which
# step 6 (06_outbox_retry.sh) has Cloud Scheduler call every minute with the bearer SIB_OUTBOX_TOKEN. That
# token lives in the Secret Manager secret OUTBOX_TOKEN_SECRET_NAME, which OUTBOX=1 requires. Only once a
# vendor exists: PTW_URL (SIB_PTW_URL, https; it can hold a key, so it is never printed), PTW_FIELD_MAP
# (SIB_PTW_FIELD_MAP, a one-line JSON object; empty sends the native record) and PTW_TOKEN_SECRET_NAME
# (the secret that holds SIB_PTW_TOKEN, the bearer sent to PTW_URL).
OUTBOX="${OUTBOX:-0}"
OUTBOX_TOKEN_SECRET_NAME="${OUTBOX_TOKEN_SECRET_NAME:-}"
PTW_URL="${PTW_URL:-}"
PTW_FIELD_MAP="${PTW_FIELD_MAP:-}"
PTW_TOKEN_SECRET_NAME="${PTW_TOKEN_SECRET_NAME:-}"

PTW_SERVICE="say-it-back-ptw"       # Step 4: the permit-to-work stub's Cloud Run service.
PTW_SA_NAME="say-it-back-ptw"       # Its own service account: it may read the webhook secret, nothing else.

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
case "$DATA_REGION" in
  in) REGION="asia-south1" ;;
  sg) REGION="asia-southeast1" ;;
  *) echo "error: DATA_REGION must be in (asia-south1, Mumbai) or sg (asia-southeast1, Singapore)." >&2; exit 1 ;;
esac
dataset_pattern='^[A-Za-z0-9_]+$'
if [[ -n "$BQ_DATASET" && ! "$BQ_DATASET" =~ $dataset_pattern ]]; then
  echo "error: BQ_DATASET may contain only letters, digits and underscores." >&2
  exit 1
fi

model_pattern='^[a-z0-9][a-z0-9._-]*$'
for model_var in FLASH_MODEL LIVE_MODEL TTS_MODEL; do
  [[ "${!model_var}" =~ $model_pattern ]] || { echo "error: $model_var is not a model id." >&2; exit 1; }
done
if [[ -n "$JUDGE_B_MODEL" && ! "$JUDGE_B_MODEL" =~ $model_pattern ]]; then
  echo "error: JUDGE_B_MODEL is not a model id (leave it empty to use FLASH_MODEL)." >&2
  exit 1
fi
count_pattern='^[0-9]+$'
for count_var in DAILY_CALLS DAILY_CALLS_PER_IP MIN_INSTANCES PTW_MIN_INSTANCES RATE_LIMIT_PER_MIN \
  MAX_SOCKETS_PER_IP MAX_OUTPUT_TOKENS RETENTION_DAYS; do
  [[ "${!count_var}" =~ $count_pattern ]] || { echo "error: $count_var must be a whole number." >&2; exit 1; }
done
# The ranges the service itself enforces at start-up, so a bad value stops here and not as a failed revision.
(( 10#$MAX_OUTPUT_TOKENS >= 1024 )) || { echo "error: MAX_OUTPUT_TOKENS must be at least 1024." >&2; exit 1; }
(( 10#$RATE_LIMIT_PER_MIN >= 1 && 10#$MAX_SOCKETS_PER_IP >= 1 )) \
  || { echo "error: RATE_LIMIT_PER_MIN and MAX_SOCKETS_PER_IP must be at least 1." >&2; exit 1; }
(( 10#$RETENTION_DAYS <= 3650 )) || { echo "error: RETENTION_DAYS must be 0 (keep) to 3650." >&2; exit 1; }
# The browser waits 20 s for a decision, which includes the webhooks, so they get at most 10 s.
timeout_pattern='^([0-9]|10)(\.[0-9]+)?$'
if [[ ! "$WEBHOOK_TIMEOUT_S" =~ $timeout_pattern || "$WEBHOOK_TIMEOUT_S" =~ ^0(\.0*)?$ \
  || "$WEBHOOK_TIMEOUT_S" =~ ^10\.0*[1-9] ]]; then
  echo "error: WEBHOOK_TIMEOUT_S must be above 0 and at most 10 (seconds)." >&2
  exit 1
fi
location_pattern='^[a-z0-9-]+$'
[[ "$TTS_LOCATION" =~ $location_pattern ]] || { echo "error: TTS_LOCATION is not a location." >&2; exit 1; }
origin_pattern='^https://[a-z0-9.-]+$'
IFS=',' read -r -a extra_origin_list <<< "$EXTRA_ORIGINS"
for origin in "${extra_origin_list[@]+"${extra_origin_list[@]}"}"; do
  origin="${origin// /}"
  [[ -z "$origin" || "$origin" =~ $origin_pattern ]] \
    || { echo "error: EXTRA_ORIGINS entries must look like https://name.web.app (no path)." >&2; exit 1; }
done
video_pattern='^https://[^[:space:]"<>]+$'
if [[ -n "$DEMO_VIDEO_URL" && ! "$DEMO_VIDEO_URL" =~ $video_pattern ]]; then
  echo "error: DEMO_VIDEO_URL must be an https:// link." >&2
  exit 1
fi
billing_pattern='^[0-9A-F]{6}-[0-9A-F]{6}-[0-9A-F]{6}$'
if [[ -n "$BILLING_ACCOUNT" && ! "$BILLING_ACCOUNT" =~ $billing_pattern ]]; then
  echo "error: BILLING_ACCOUNT must look like 012345-6789AB-CDEF01." >&2
  exit 1
fi
budget_pattern='^[0-9]+(\.[0-9]+)?[A-Z]{3}$'
[[ "$BUDGET_AMOUNT" =~ $budget_pattern ]] || { echo "error: BUDGET_AMOUNT must look like 28797INR." >&2; exit 1; }
# The webhook URLs travel inside a ^@^-delimited --update-env-vars value, so they may not hold an "@".
# Neither message prints a URL.
if [[ "$WEBHOOK_URLS" == *"@"* ]]; then
  echo "error: WEBHOOK_URLS may not contain '@'." >&2
  exit 1
fi
IFS=',' read -r -a webhook_list <<< "$WEBHOOK_URLS"
webhook_count=0
for webhook in "${webhook_list[@]+"${webhook_list[@]}"}"; do
  webhook="${webhook// /}"
  [[ -z "$webhook" ]] && continue
  webhook_count=$((webhook_count + 1))
  [[ "$webhook" == https://* ]] || { echo "error: WEBHOOK_URLS entry $webhook_count is not https." >&2; exit 1; }
done
if (( webhook_count > 3 )); then
  echo "error: WEBHOOK_URLS holds at most 3 URLs." >&2
  exit 1
fi
# Step 5 passes the address inside --channel-labels=key=value pairs, so no comma, "=" or space.
email_pattern='^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'
if [[ -n "$ALERT_EMAIL" && ! "$ALERT_EMAIL" =~ $email_pattern ]]; then
  echo "error: ALERT_EMAIL must be one email address, like ops@example.com." >&2
  exit 1
fi
secret_pattern='^[A-Za-z0-9_-]+$'
if [[ -n "$WEBHOOK_SECRET_NAME" && ! "$WEBHOOK_SECRET_NAME" =~ $secret_pattern ]]; then
  echo "error: WEBHOOK_SECRET_NAME must be a Secret Manager secret name." >&2
  exit 1
fi
[[ "$OUTBOX" == 0 || "$OUTBOX" == 1 ]] || { echo "error: OUTBOX must be 0 or 1." >&2; exit 1; }
for secret_var in OUTBOX_TOKEN_SECRET_NAME PTW_TOKEN_SECRET_NAME; do
  [[ -z "${!secret_var}" || "${!secret_var}" =~ $secret_pattern ]] \
    || { echo "error: $secret_var must be a Secret Manager secret name." >&2; exit 1; }
done
if [[ "$OUTBOX" == 1 && -z "$OUTBOX_TOKEN_SECRET_NAME" ]]; then
  echo "error: OUTBOX=1 needs OUTBOX_TOKEN_SECRET_NAME: without its token nothing retries a delivery." >&2
  exit 1
fi
# PTW_URL travels inside the ^@^-delimited --update-env-vars, like the webhook URLs. No message prints it.
space_pattern='[[:space:]]'
if [[ -n "$PTW_URL" && ( "$PTW_URL" != https://* || "$PTW_URL" == *"@"* || "$PTW_URL" =~ $space_pattern ) ]]; then
  echo "error: PTW_URL must be one https:// URL, with no '@' and no space." >&2
  exit 1
fi
if [[ ( -n "$PTW_FIELD_MAP" || -n "$PTW_TOKEN_SECRET_NAME" ) && -z "$PTW_URL" ]]; then
  echo "error: PTW_FIELD_MAP and PTW_TOKEN_SECRET_NAME need PTW_URL." >&2
  exit 1
fi
# The service parses the map at start-up; this only keeps it one value of the ^@^ list.
if [[ -n "$PTW_FIELD_MAP" && ( "$PTW_FIELD_MAP" != "{"*"}" || "$PTW_FIELD_MAP" == *"@"* \
  || "$PTW_FIELD_MAP" == *$'\n'* ) ]]; then
  echo "error: PTW_FIELD_MAP must be a one-line JSON object with no '@'." >&2
  exit 1
fi

RUNTIME_SA="${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
PTW_SA="${PTW_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Helpers. Each one prints the command to stderr before it runs.
run()     { printf '+ %s\n' "$*" >&2; "$@"; }                   # changes something
# Like run, but the printed command shows <hidden> in place of each line of $1 (values that hold a
# key). It runs the rest unchanged.
run_hiding() {
  local hidden="$1" value; shift
  local shown="$*"
  while IFS= read -r value; do
    if [[ -n "$value" ]]; then shown="${shown//"$value"/<hidden>}"; fi
  done <<< "$hidden"
  printf '+ %s\n' "$shown" >&2
  "$@"
}
probe()   { printf '? %s\n' "$*" >&2; "$@" >/dev/null 2>&1; }   # read-only check; exit status only
capture() { printf '+ %s\n' "$*" >&2; "$@"; }                    # read-only; the caller captures stdout
die()     { printf 'error: %s\n' "$*" >&2; exit 1; }
