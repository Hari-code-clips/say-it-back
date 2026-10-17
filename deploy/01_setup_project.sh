#!/usr/bin/env bash
# Step 1 of 3. One-time project setup: APIs, Firestore (Native mode) with the index the app's
# queries need and the TTL policy that deletes expired records, the runtime service account and its
# roles, and an optional BigQuery dataset. Every create is preceded by a check, so the script is safe
# to run again.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "$SCRIPT_DIR/config.sh"

echo "Project $PROJECT_ID. Cloud Run and Firestore in $REGION (DATA_REGION=$DATA_REGION). Live in $LIVE_LOCATION."

# Enabling an API that is already on changes nothing. firebase and firebaserules are needed by
# 03 (adding Firebase to the project, deploying the Firestore rules); telemetry is where ADK's
# OpenTelemetry exporter sends spans (SIB_TRACE_TO_CLOUD); clouderrorreporting groups the backend's
# unhandled errors (observability.report_error).
run gcloud services enable \
  run.googleapis.com \
  aiplatform.googleapis.com \
  firestore.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  cloudtrace.googleapis.com \
  telemetry.googleapis.com \
  bigquery.googleapis.com \
  secretmanager.googleapis.com \
  firebase.googleapis.com \
  firebaserules.googleapis.com \
  firebasehosting.googleapis.com \
  clouderrorreporting.googleapis.com \
  --project "$PROJECT_ID"

# gcloud run deploy --source stores its images in this repository. Without it, the first deploy stops
# to ask whether to create it; creating it here keeps 02 and 04 non-interactive.
if probe gcloud artifacts repositories describe cloud-run-source-deploy --location="$REGION" \
  --project "$PROJECT_ID"; then
  echo "Artifact Registry repository cloud-run-source-deploy already exists."
else
  run gcloud artifacts repositories create cloud-run-source-deploy --repository-format=docker \
    --location="$REGION" --description="Cloud Run source deployments" --project "$PROJECT_ID"
fi

# Firestore "(default)" database in Native mode. Its location cannot be changed later, so a database
# outside the data region stops the setup: Cloud Run would run in one region and keep data in another.
if probe gcloud firestore databases describe --database="(default)" --project "$PROJECT_ID"; then
  existing_loc="$(capture gcloud firestore databases describe --database="(default)" \
    --project "$PROJECT_ID" --format='value(locationId)')"
  echo "Firestore (default) already exists in $existing_loc."
  [[ "$existing_loc" == "$REGION" ]] \
    || die "Firestore is in $existing_loc, but DATA_REGION=$DATA_REGION means $REGION. A database cannot move: set the DATA_REGION that matches it, or use a new project."
else
  run gcloud firestore databases create --database="(default)" --location="$REGION" \
    --type=firestore-native --project "$PROJECT_ID"
fi

# Composite index behind a caller's own list of briefings: GET /api/briefings and the CSV export
# read the briefings whose owner is the caller's, newest first (where owner == X, order by createdAt
# descending). Firestore refuses that query without this index. It is created only when no index
# with these fields exists, so the script can run again. The command returns once the index is built,
# which takes a minute or two on an empty collection.
index_filter='name~/collectionGroups/briefings/indexes/ AND queryScope=COLLECTION'
index_filter+=' AND fields[0].fieldPath=owner AND fields[0].order=ASCENDING'
index_filter+=' AND fields[1].fieldPath=createdAt AND fields[1].order=DESCENDING'
existing_index="$(capture gcloud firestore indexes composite list --database="(default)" \
  --project "$PROJECT_ID" --filter="$index_filter" --format='value(name.basename())')"
if [[ -n "$existing_index" ]]; then
  echo "Firestore index briefings(owner, createdAt desc) already exists."
else
  run gcloud firestore indexes composite create --database="(default)" \
    --collection-group=briefings --query-scope=collection \
    --field-config=field-path=owner,order=ascending \
    --field-config=field-path=createdAt,order=descending \
    --project "$PROJECT_ID"
fi

# Automatic deletion (RETENTION_DAYS, SIB_RETENTION_DAYS on the service). The backend stamps each new
# briefing with expireAt, as a Firestore Timestamp (TTL ignores any other type), and this TTL policy
# deletes the record once that time has passed: Firestore says typically within 24 hours. TTL deletes
# bill as ordinary document deletes. With RETENTION_DAYS=0 the policy is switched off, so records that
# already carry an expiry are kept as well. The command returns once Firestore has applied the change.
# The same policy on outbox.expireAt: a decision's delivery entry carries its briefing's expiry (outbox.py).
for ttl_group in briefings outbox; do
  ttl_fields="$(capture gcloud firestore fields ttls list --collection-group="$ttl_group" --database="(default)" \
    --project "$PROJECT_ID" --format='value(name.basename())')"
  if (( 10#$RETENTION_DAYS > 0 )); then
    if grep -qx expireAt <<< "$ttl_fields"; then
      echo "Firestore TTL policy on $ttl_group.expireAt already exists (records kept $RETENTION_DAYS days)."
    else
      run gcloud firestore fields ttls update expireAt --collection-group="$ttl_group" --database="(default)" \
        --enable-ttl --project "$PROJECT_ID"
    fi
  elif grep -qx expireAt <<< "$ttl_fields"; then
    run gcloud firestore fields ttls update expireAt --collection-group="$ttl_group" --database="(default)" \
      --disable-ttl --project "$PROJECT_ID"
  else
    echo "RETENTION_DAYS=0: $ttl_group records are kept until deleted by hand; no TTL policy."
  fi
done

# Runtime service account for the Cloud Run service.
if probe gcloud iam service-accounts describe "$RUNTIME_SA" --project "$PROJECT_ID"; then
  echo "Service account $RUNTIME_SA already exists."
else
  run gcloud iam service-accounts create "$RUNTIME_SA_NAME" \
    --display-name="Say It Back Cloud Run runtime" --project "$PROJECT_ID"
fi

# Project-level roles. add-iam-policy-binding adds a binding only when it is missing.
# BigQuery access is needed only for the analytics dataset (SIB_BQ_DATASET), so it is granted only
# when BQ_DATASET is set. It is granted project-wide because the bq tool can set dataset access only
# by overwriting the dataset's whole access list, which would remove existing grants. A project set
# up by an earlier version of this script still holds the role: remove it with
# gcloud projects remove-iam-policy-binding if BigQuery is not used.
roles=(roles/aiplatform.user roles/datastore.user roles/cloudtrace.agent)
# ADK sends spans through the Telemetry API, whose writer role is newer than Cloud Trace's. Grant it when this
# gcloud knows it; otherwise warn, so the rest of the setup still runs (traces are optional).
if probe gcloud iam roles describe roles/telemetry.tracesWriter; then
  roles+=(roles/telemetry.tracesWriter)
else
  echo "warning: roles/telemetry.tracesWriter not found; Cloud Trace spans may be refused (traces are optional)." >&2
fi
if [[ -n "$BQ_DATASET" ]]; then
  roles+=(roles/bigquery.dataEditor)
fi
for role in "${roles[@]}"; do
  run gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$RUNTIME_SA" --role="$role" --condition=None >/dev/null
done

# Optional BigQuery dataset for the ADK analytics plugin (SIB_BQ_DATASET). Skipped when BQ_DATASET is empty.
if [[ -n "$BQ_DATASET" ]]; then
  if probe bq show "$PROJECT_ID:$BQ_DATASET"; then
    echo "BigQuery dataset $BQ_DATASET already exists."
  else
    run bq --location="$REGION" mk -d \
      --description="Say It Back agent analytics, content redacted" "$PROJECT_ID:$BQ_DATASET"
  fi
fi

# Optional budget alert on the billing account, scoped to this project (BILLING_ACCOUNT in config.sh).
# It ignores credits, so it reports usage while the free-trial credit still pays for it, at 10, 25, 50,
# 75 and 90 % of BUDGET_AMOUNT. Alerts go to the billing account's admins by email.
if [[ -n "$BILLING_ACCOUNT" ]]; then
  run gcloud services enable billingbudgets.googleapis.com --project "$PROJECT_ID"
  budget_name="say-it-back $PROJECT_ID"
  existing_budget="$(capture gcloud billing budgets list --billing-account="$BILLING_ACCOUNT" \
    --billing-project="$PROJECT_ID" --filter="displayName=\"$budget_name\"" --format='value(name)')"
  if [[ -n "$existing_budget" ]]; then
    echo "Budget '$budget_name' already exists."
  else
    run gcloud billing budgets create --billing-account="$BILLING_ACCOUNT" --billing-project="$PROJECT_ID" \
      --display-name="$budget_name" --budget-amount="$BUDGET_AMOUNT" \
      --filter-projects="projects/$PROJECT_ID" --credit-types-treatment=exclude-all-credits \
      --threshold-rule=percent=0.10 --threshold-rule=percent=0.25 --threshold-rule=percent=0.50 \
      --threshold-rule=percent=0.75 --threshold-rule=percent=0.90
  fi
else
  echo "BILLING_ACCOUNT is empty: no budget alert created. Set one in the console (exclude credits)." >&2
fi

echo "Done. Next: deploy/probe_models.sh, then deploy/02_deploy_backend.sh"
