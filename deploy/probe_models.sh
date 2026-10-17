#!/usr/bin/env bash
# After 01, before 02. One tiny call to each pinned model on Agent Platform, with the same project,
# locations and model ids the service will use, so a wrong id fails here and not in front of a judge.
# It spends a fraction of a cent. Needs `gcloud auth application-default login` (the probe runs with
# your credentials, not the service account's) and `uv sync` in backend/.
#
# Each line reads OK or FAIL with the model kind, id, location and either the latency or a short
# reason (not_found, permission, quota, bad_request, timeout, other). It exits 1 if any model fails.
# On a FAIL:
# - judge B: set JUDGE_B_MODEL="" in config.sh (judge B then runs on FLASH_MODEL);
# - TTS on global: if the us-central1 line is OK, set TTS_LOCATION=us-central1;
# - Flash or Live: look up the exact Agent Platform id in Model Garden and pin it in config.sh.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=config.sh
source "$SCRIPT_DIR/config.sh"

cd "$REPO_ROOT/backend"
run env \
  GOOGLE_GENAI_USE_ENTERPRISE=true \
  GOOGLE_CLOUD_PROJECT="$PROJECT_ID" \
  GOOGLE_CLOUD_LOCATION=global \
  SIB_LIVE_LOCATION="$LIVE_LOCATION" \
  SIB_TTS_LOCATION="$TTS_LOCATION" \
  SIB_FLASH_MODEL="$FLASH_MODEL" \
  SIB_JUDGE_B_MODEL="$JUDGE_B_MODEL" \
  SIB_LIVE_MODEL="$LIVE_MODEL" \
  SIB_TTS_MODEL="$TTS_MODEL" \
  uv run python -m sayitback.probe --also-location us-central1
