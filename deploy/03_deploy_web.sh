#!/usr/bin/env bash
# Step 3 of 3. Build web/ against the Cloud Run service and deploy it to Firebase Hosting for PROJECT_ID, together with the
# Firestore client rules (deny all).
#
# The browser calls the Cloud Run service directly (docs/ARCHITECTURE.md): Hosting serves static files and has no /api
# rewrite, so every request reaches the service through the same hops and its per-address limits can read X-Forwarded-For.
# The page is built with VITE_API_BASE set to the service URL, and its Content-Security-Policy names that origin.
#
# Only Hosting and the Firestore rules are deployed. The Firestore index is managed in 01_setup_project.sh, never here.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=config.sh
source "$SCRIPT_DIR/config.sh"
cd "$REPO_ROOT"

# The service has to exist first: the page is built against its URL.
SERVICE_URL="$(capture gcloud run services describe "$SERVICE" --region "$REGION" \
  --project "$PROJECT_ID" --format='value(status.url)')" \
  || die "Could not read the Cloud Run service $SERVICE in $REGION. Run deploy/02_deploy_backend.sh first."
[[ "$SERVICE_URL" == https://* ]] || die "Could not read the service URL (got '$SERVICE_URL')."
SERVICE_HOST="${SERVICE_URL#https://}"

# What Hosting and Firestore are told to do, checked before anything is built or deployed.
# No /api rewrite and no rewrite to Cloud Run: a rewrite would put another proxy in front of the client address.
if grep -Fq '/api' firebase.json || grep -Eq '"(run|function)"' firebase.json; then
  die "firebase.json must not rewrite /api or route to Cloud Run. The browser calls $SERVICE_URL directly."
fi
# Security headers. The header CSP is frame-ancestors alone (a <meta> tag cannot carry it); the rest is in the page.
grep -Fq '"X-Frame-Options"' firebase.json \
  || die "firebase.json must send X-Frame-Options."
grep -Fq "frame-ancestors 'none'" firebase.json \
  || die "firebase.json must send a Content-Security-Policy of frame-ancestors 'none'."
grep -Fq '"Cross-Origin-Opener-Policy"' firebase.json \
  || die "firebase.json must send Cross-Origin-Opener-Policy."
# Firestore client rules: deployed with this release, deny all. The index is not deployed from here.
grep -Fq '"rules": "firestore.rules"' firebase.json \
  || die "firebase.json must deploy firestore.rules."
if grep -Fq '"indexes"' firebase.json; then
  die "firebase.json must not deploy Firestore indexes. 01_setup_project.sh creates the one index."
fi
[[ -f firestore.rules ]] || die "firestore.rules is missing."
rules_allowed="$(grep -E '^[[:space:]]*allow[[:space:]]' firestore.rules | sed -E 's/[[:space:]]+/ /g; s/^ //')"
[[ "$rules_allowed" == "allow read, write: if false;" ]] \
  || die "firestore.rules must hold one rule, 'allow read, write: if false;'."

# Build the web app. The subshell keeps the working directory at the repository root afterwards.
# VITE_API_BASE is the API's base URL. vite.config.ts also reads it to write the CSP's connect-src.
(
  cd "$REPO_ROOT/web"
  run npm ci
  run npm run typecheck
  run npm test
  run env VITE_API_BASE="$SERVICE_URL/api" VITE_DEMO_VIDEO_URL="$DEMO_VIDEO_URL" npm run build
)
[[ -f web/dist/index.html ]] || die "web/dist/index.html is missing after the build."

# What was built. The CSP must name the service and nothing else for connect-src, and allow no eval; the bundle must hold no mock code.
csp_meta="$(grep -o '<meta http-equiv="Content-Security-Policy"[^>]*>' web/dist/index.html || true)"
[[ -n "$csp_meta" ]] || die "web/dist/index.html has no Content-Security-Policy <meta> tag."
connect_src="$(printf '%s' "$csp_meta" | sed -n 's/.*connect-src \([^;"]*\).*/\1/p')"
[[ "$connect_src" == "https://$SERVICE_HOST wss://$SERVICE_HOST" ]] \
  || die "The page's CSP connect-src is '$connect_src'. It must be 'https://$SERVICE_HOST wss://$SERVICE_HOST'."
[[ "$csp_meta" != *unsafe-eval* ]] || die "The page's CSP must not allow unsafe-eval."
if grep -rIqE 'sib\.mock|browser sessionStorage|__SIB_MOCK_BUNDLE__' web/dist; then
  die "web/dist holds mock-mode code. Build without VITE_API_MOCK."
fi
# The fuller check (the sentinel, src/mock paths, the mock catalog's text), the same one web/tests/build/noMock.test.ts runs.
(cd "$REPO_ROOT/web" && run node noMock.ts dist) \
  || die "web/dist holds mock-mode code (listed above). Build without VITE_API_MOCK."

# A Google Cloud project needs Firebase added once before Hosting can deploy to it.
# Run `npx firebase-tools login` once beforehand.
# The list is read whole before it is searched: under pipefail, grep -q closing the pipe early could fail npx.
firebase_projects="$(capture npx --yes firebase-tools projects:list --json)" \
  || die "Could not list Firebase projects. Run 'npx firebase-tools login' first."
if grep -Fq "\"$PROJECT_ID\"" <<< "$firebase_projects"; then
  echo "Firebase is already added to $PROJECT_ID."
else
  run npx --yes firebase-tools projects:addfirebase "$PROJECT_ID"
fi

# Hosting and the Firestore rules only. --project overrides the placeholder in .firebaserc.
run npx --yes firebase-tools deploy --only hosting,firestore:rules --project "$PROJECT_ID"

echo "Web app: https://$PROJECT_ID.web.app (calls $SERVICE_URL/api)"
echo "Next: the checks in deploy/README.md, Verify."
