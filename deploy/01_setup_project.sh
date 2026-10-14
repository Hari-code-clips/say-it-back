#!/usr/bin/env bash
# Step 1 of 3. One-time project setup: APIs, Firestore (Native mode) with the index the app's
# queries need, the runtime service account and its roles, and an optional BigQuery dataset.
# Every create is preceded by a check, so the script is safe to run again.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "$SCRIPT_DIR/config.sh"

echo "Project $PROJECT_ID. Cloud Run and Firestore in $REGION. Live in $LIVE_LOCATION."

# Enabling an API that is already on changes nothing.
run gcloud services enable \
  run.googleapis.com \
  aiplatform.googleapis.com \
  firestore.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  cloudtrace.googleapis.com \
  bigquery.googleapis.com \
  secretmanager.googleapis.com \
  firebasehosting.googleapis.com \
  --project "$PROJECT_ID"

# Firestore "(default)" database in Native mode. Its location cannot be changed later.
if probe gcloud firestore databases describe --database="(default)" --project "$PROJECT_ID"; then
  existing_loc="$(capture gcloud firestore databases describe --database="(default)" \
    --project "$PROJECT_ID" --format='value(locationId)')"
  echo "Firestore (default) already exists in $existing_loc."
  if [[ "$existing_loc" != "$REGION" ]]; then
    echo "warning: expected $REGION. Review the existing database in the console." >&2
  fi
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

echo "Done. Next: deploy/02_deploy_backend.sh"
