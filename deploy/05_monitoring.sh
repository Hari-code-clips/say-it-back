#!/usr/bin/env bash
# Step 5 (optional, after 03). Email alerts to ALERT_EMAIL (config.sh): an uptime check on the API's
# health endpoint and one on the web app, a policy that fires when either check fails from more than
# one of Google's checker regions, and one that fires when more than 5 % of the API's answers are 5xx
# over 5 minutes. deploy/RUNBOOK.md says what each alert means and what to check first.
#
# Each resource is looked up by its display name before it is created, so the script is safe to run
# again; it never changes one that exists. To change a policy or the address, delete the policy
# (Monitoring, Alerting) and run this again. Uptime checks and alerting conditions are billed by Cloud
# Monitoring past its free allotment (deploy/README.md, "What each step costs"); email costs nothing.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "$SCRIPT_DIR/config.sh"

if [[ -z "$ALERT_EMAIL" ]]; then
  echo "ALERT_EMAIL is empty: no alerts created. Set it in deploy/config.sh and run this step again." >&2
  exit 0
fi

# gcloud keeps the notification-channel commands in its beta track and the alerting-policy commands in
# alpha. Read the installed list whole before searching it (grep -q closing a pipe early fails under
# pipefail).
installed="$(capture gcloud components list --only-local-state --format='value(id)')" || installed=""
for component in alpha beta; do
  grep -qx "$component" <<< "$installed" \
    || die "This step needs gcloud's $component commands. Run 'gcloud components install $component' first."
done

run gcloud services enable monitoring.googleapis.com --project "$PROJECT_ID"

SERVICE_URL="$(capture gcloud run services describe "$SERVICE" --region "$REGION" \
  --project "$PROJECT_ID" --format='value(status.url)')" \
  || die "Could not read the Cloud Run service $SERVICE in $REGION. Run deploy/02_deploy_backend.sh first."
[[ "$SERVICE_URL" == https://* ]] || die "Could not read the service URL (got '$SERVICE_URL')."
API_HOST="${SERVICE_URL#https://}"
WEB_HOST="$PROJECT_ID.web.app"

# The email channel. One that already sends to this address is reused.
channel="$(capture gcloud beta monitoring channels list --project "$PROJECT_ID" \
  --filter="type=\"email\" AND labels.email_address=\"$ALERT_EMAIL\"" --format='value(name)')"
channel="${channel%%$'\n'*}"
if [[ -n "$channel" ]]; then
  echo "Notification channel for $ALERT_EMAIL already exists."
else
  channel="$(run gcloud beta monitoring channels create --project "$PROJECT_ID" \
    --display-name="Say It Back alerts" --type=email \
    --channel-labels="email_address=$ALERT_EMAIL" --format='value(name)')"
fi
channel_pattern='^projects/[^/]+/notificationChannels/[0-9]+$'
[[ "$channel" =~ $channel_pattern ]] || die "Could not read the notification channel's name (got '$channel')."

# An HTTPS uptime check every 5 minutes from each checker region, failing an answer that is not 2xx
# within 10 s. Prints the check's id.
check_pattern='^projects/[^/]+/uptimeCheckConfigs/[A-Za-z0-9_-]+$'
uptime_check() {
  local name="$1" host="$2" path="$3" found
  found="$(capture gcloud monitoring uptime list-configs --project "$PROJECT_ID" \
    --filter="displayName=\"$name\"" --format='value(name)')"
  found="${found%%$'\n'*}"
  if [[ -n "$found" ]]; then
    echo "Uptime check '$name' already exists." >&2
  else
    found="$(run gcloud monitoring uptime create "$name" --project "$PROJECT_ID" \
      --resource-type=uptime-url --resource-labels="host=$host,project_id=$PROJECT_ID" \
      --protocol=https --path="$path" --period=5 --timeout=10 --format='value(name)')"
  fi
  [[ "$found" =~ $check_pattern ]] || die "Could not read uptime check '$name' (got '$found')."
  printf '%s' "${found##*/}"
}
api_check="$(uptime_check "say-it-back API health" "$API_HOST" /api/health)"
web_check="$(uptime_check "say-it-back web app" "$WEB_HOST" /)"

policy_dir="$(mktemp -d)"
trap 'rm -rf "$policy_dir"' EXIT

# A failing uptime check: the newest result of each checker region, counted false, above 1 (two or more
# regions fail, so one region's network trouble alone does not page anyone).
uptime_condition() {
  cat <<EOF
    {
      "displayName": "$1",
      "conditionThreshold": {
        "filter": "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND metric.label.check_id=\"$2\" AND resource.type=\"uptime_url\"",
        "aggregations": [{"alignmentPeriod": "1200s", "perSeriesAligner": "ALIGN_NEXT_OLDER",
          "crossSeriesReducer": "REDUCE_COUNT_FALSE", "groupByFields": ["resource.label.*"]}],
        "comparison": "COMPARISON_GT",
        "thresholdValue": 1,
        "duration": "60s",
        "trigger": {"count": 1}
      }
    }
EOF
}

UPTIME_POLICY="Say It Back: site down"
cat > "$policy_dir/uptime.json" <<EOF
{
  "displayName": "$UPTIME_POLICY",
  "combiner": "OR",
  "conditions": [
$(uptime_condition "API health check failing ($API_HOST/api/health)" "$api_check"),
$(uptime_condition "Web app check failing ($WEB_HOST)" "$web_check")
  ],
  "notificationChannels": ["$channel"],
  "documentation": {"mimeType": "text/markdown",
    "content": "The API or the web app has failed its uptime check from two or more regions. See deploy/RUNBOOK.md, Alerts, Site down."}
}
EOF

# The share of the API's answers that are 5xx: 503 upstream_busy (Gemini busy or out of quota) and
# 502 upstream_error count as well as 500 internal_error.
SERVER_ERRORS_POLICY="Say It Back: API 5xx answers"
run_count_filter="resource.type=\\\"cloud_run_revision\\\" AND resource.labels.service_name=\\\"$SERVICE\\\" AND metric.type=\\\"run.googleapis.com/request_count\\\""
cat > "$policy_dir/server-errors.json" <<EOF
{
  "displayName": "$SERVER_ERRORS_POLICY",
  "combiner": "OR",
  "conditions": [
    {
      "displayName": "More than 5 % of API answers are 5xx over 5 minutes",
      "conditionThreshold": {
        "filter": "$run_count_filter AND metric.labels.response_code_class=\\"5xx\\"",
        "aggregations": [{"alignmentPeriod": "300s", "perSeriesAligner": "ALIGN_RATE",
          "crossSeriesReducer": "REDUCE_SUM"}],
        "denominatorFilter": "$run_count_filter",
        "denominatorAggregations": [{"alignmentPeriod": "300s", "perSeriesAligner": "ALIGN_RATE",
          "crossSeriesReducer": "REDUCE_SUM"}],
        "comparison": "COMPARISON_GT",
        "thresholdValue": 0.05,
        "duration": "0s",
        "trigger": {"count": 1}
      }
    }
  ],
  "notificationChannels": ["$channel"],
  "documentation": {"mimeType": "text/markdown",
    "content": "More than 5 % of the API's answers were 5xx for 5 minutes. See deploy/RUNBOOK.md, Alerts, API 5xx answers."}
}
EOF

# Created only when no policy has this display name.
create_policy() {
  local existing
  existing="$(capture gcloud alpha monitoring policies list --project "$PROJECT_ID" \
    --filter="displayName=\"$1\"" --format='value(name)')"
  if [[ -n "$existing" ]]; then
    echo "Alerting policy '$1' already exists. To change it, delete it (Monitoring, Alerting) and run this again."
  else
    run gcloud alpha monitoring policies create --project "$PROJECT_ID" \
      --policy-from-file="$2" --format='value(name)'
  fi
}
create_policy "$UPTIME_POLICY" "$policy_dir/uptime.json"
create_policy "$SERVER_ERRORS_POLICY" "$policy_dir/server-errors.json"

echo "Alerts go to $ALERT_EMAIL. Uptime results appear after about 10 minutes (Monitoring, Uptime checks)."
echo "Next: deploy/RUNBOOK.md says what each alert means and what to check first."
