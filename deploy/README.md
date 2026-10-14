# Deploy Say It Back to Google Cloud

> **Warning.** These scripts create billable resources in your Google Cloud project. Only the project owner runs them, by hand, after reading this file. No CI job runs them.

## Before you start

- A Google Cloud project you own, with billing enabled. Export its id in your shell rather than committing it: `export PROJECT_ID=your-project-id`.
- Firebase added to that same project (Firebase console, add Firebase to an existing Google Cloud project). Hosting and the Firestore rules need it.
- Tools: the gcloud CLI signed in (`gcloud auth login`), Node 22, and a one-time `npx firebase-tools login`.
- A budget alert on the billing account (Billing, then Budgets and alerts). The backend is public by design, so cap the spend.
- Settings in `deploy/config.sh`: region, Live location, service name, optional BigQuery dataset, instance limits.
- `backend/.gcloudignore`. Step 2 refuses to run without it. gcloud reads that file, not the repository `.gitignore`, when it uploads `backend/`. It must exclude `.data/`, `.venv/`, `__pycache__/` and any dotenv file.

## How the pieces connect

The browser calls the Cloud Run service directly, for the API and for the Live WebSocket. Firebase Hosting serves the web app as static files and has **no `/api` rewrite**: per-address limits read `X-Forwarded-For` from the right, so every request must arrive through the same hops (`docs/ARCHITECTURE.md`). Three settings tie the two halves together:

- `VITE_API_BASE` (web build): the service URL plus `/api`. Step 3 reads the URL with gcloud and sets it. The page's Content-Security-Policy is written from it, so `connect-src` names that origin and nothing else.
- `SIB_ALLOWED_ORIGINS` (backend): the web origins, for CORS and the WebSocket Origin check. Step 2 sets `https://$PROJECT_ID.web.app` and `https://$PROJECT_ID.firebaseapp.com`. A custom domain has to be added to that list (the `ENV_VARS` line in step 2), or the browser's requests are refused.
- `SIB_PUBLIC_WS_BASE` (backend): the service's `wss://` address. Step 2 sets it once the service exists.

Each browser sends its own device key in an `X-SIB-Device` header. That header makes every cross-origin request preflighted, and the backend answers the preflight for the web origins.

## Order

1. `bash deploy/01_setup_project.sh` enables the APIs and creates:
   - the Firestore database, and the composite index `briefings(owner ascending, createdAt descending)`. A caller's list of briefings and the CSV export need it, and both answer 500 without it. This script is the only place the index is managed;
   - the runtime service account and its roles. `roles/bigquery.dataEditor` is granted only when `BQ_DATASET` is set. A project set up by an earlier version of the script still holds it: remove it with `gcloud projects remove-iam-policy-binding` if BigQuery is not used;
   - the optional BigQuery dataset.
2. `bash deploy/02_deploy_backend.sh` builds `backend/` and deploys it to Cloud Run.
   - It copies `eval/testset` and `eval/reports/latest.json` into `backend/eval_data/` for the build and removes the copy afterwards, so the Sample page has its data in the image. Refresh `eval/reports/latest.json` before a deploy: the image carries what was there.
   - It sets the backend's settings, then reads the service URL and sets `SIB_PUBLIC_WS_BASE` to the matching `wss://` address.
3. Check the backend (see Verify).
4. `bash deploy/03_deploy_web.sh` reads the service URL, builds `web/` with `VITE_API_BASE="<service URL>/api"` and deploys Firebase Hosting and the Firestore client rules (`firestore.rules`, deny all). It does not deploy Firestore indexes.
   - Before building it checks `firebase.json` (no `/api` rewrite, no rewrite to Cloud Run, the frame and opener headers, the rules file wired in, no indexes) and `firestore.rules` (one rule, deny all).
   - It runs `npm test`, which covers the same files.
   - After building it checks the built `index.html`: the CSP `connect-src` names exactly the service over `https` and `wss`, nothing allows `unsafe-eval`, and the bundle holds no mock-mode code.
   - If `firebase deploy` says the Firebase Rules API is not enabled, run `gcloud services enable firebaserules.googleapis.com --project "$PROJECT_ID"` and run `03_deploy_web.sh` again. Step 1 does not enable it, and whether the Firebase CLI does so itself has not been checked.
5. Check the web app (see Verify).

Every script prints each command before it runs. Re-running a script is safe: existing resources are left alone, and a redeploy creates a new Cloud Run revision.

## What each step costs

| Step | Creates | Cost at prototype volume |
|---|---|---|
| 01 | Enabled APIs, Firestore database and index, service account, IAM bindings, optional BigQuery dataset | Enabling APIs and creating the account are free. Firestore and BigQuery charge only past their free tiers. |
| 02 | Cloud Build runs, an Artifact Registry image, a Cloud Run service | Build minutes and image storage fall within free tiers. Cloud Run scales to zero (minimum instances 0) and bills only while requests or WebSocket sessions run. |
| 03 | A Firebase Hosting release and a Firestore rules release | Within the Hosting free tier. Rules releases are free. |
| Runtime | Gemini calls (Flash, Live, TTS), Cloud Trace, BigQuery writes | Gemini calls are the main cost. The steps above fit within free tiers or the Google Cloud trial credit at prototype volume. Confirm on the pricing pages before a long rehearsal. |

## Verify

Backend. Replace `say-it-back-api` and `asia-south1` if you changed them in `config.sh`:

```bash
SERVICE_URL="$(gcloud run services describe say-it-back-api --region asia-south1 \
  --project "$PROJECT_ID" --format='value(status.url)')"
curl -fsS "$SERVICE_URL/api/health"
```

The JSON should show `"store": "firestore"`, and every value under `backends` should be `"agent-platform"`. A `"developer-api"` value is expected only if you set that backend variable on purpose.

The device key and the preflight the browser sends:

```bash
curl -si "$SERVICE_URL/api/briefings" | head -n 1
curl -si -X OPTIONS "$SERVICE_URL/api/briefings" \
  -H "Origin: https://$PROJECT_ID.web.app" \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-sib-device'
```

The first answers `401` (a request with no device key is refused before anything else). The second answers `200` with `access-control-allow-origin: https://<project>.web.app`, an `access-control-allow-headers` list that holds `x-sib-device`, and `access-control-max-age: 7200`. If `access-control-allow-origin` is missing, `SIB_ALLOWED_ORIGINS` does not list the web origin.

The client address. Per-address limits and daily allowances assume the entry `SIB_TRUSTED_PROXY_HOPS` from the right of `X-Forwarded-For` is the client's. That comes from Google's documentation and has never been observed on a real deployment. Run the check in `backend/README.md`, section "Cloud Run", item "The client address", before the app is public.

Web, after step 4:

```bash
curl -sI "https://$PROJECT_ID.web.app/" | grep -iE '^(x-frame-options|cross-origin-opener-policy|content-security-policy):'
curl -s "https://$PROJECT_ID.web.app/" | grep -o '<meta http-equiv="Content-Security-Policy"[^>]*>'
```

The headers are `X-Frame-Options: DENY`, `Cross-Origin-Opener-Policy: same-origin` and `Content-Security-Policy: frame-ancestors 'none'`. The full policy is in the page's `<meta>` tag, and its `connect-src` names the service. Hosting enforces both policies, and the header one is only `frame-ancestors`, so they do not narrow each other. `https://$PROJECT_ID.web.app/api/health` returns the app's HTML, not JSON: there is no rewrite, and that is correct.

Then open `https://$PROJECT_ID.web.app` and run a briefing in live mode. In the browser's developer tools:

- every API request goes to the Cloud Run URL and carries `X-SIB-Device`;
- the Live WebSocket connects to the same address, with no device key in its URL (its ticket is the capability);
- the console shows no Content-Security-Policy violation.

Open the same page in a private window: Records is empty, and the first window's briefing address answers "Briefing not found".

The Firestore rules. The Firebase console, Firestore, Rules, should show `allow read, write: if false;` as the published rules. The web API key is public (Hosting serves it to every visitor), so check that it opens nothing:

```bash
WEB_KEY="$(curl -fsS "https://$PROJECT_ID.web.app/__/firebase/init.json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["apiKey"])')"
curl -s -o /dev/null -w '%{http_code}\n' \
  "https://firestore.googleapis.com/v1/projects/$PROJECT_ID/databases/(default)/documents/briefings?key=$WEB_KEY"
```

The answer should be `403`. The first command does not print the key.

## Roll back

- **Backend.** List the revisions, then send all traffic to the one you want:

  ```bash
  gcloud run revisions list --service say-it-back-api --region asia-south1 --project "$PROJECT_ID"
  gcloud run services update-traffic say-it-back-api --region asia-south1 --project "$PROJECT_ID" \
    --to-revisions=REVISION_NAME=100
  ```

- **Web.** In the Firebase console, open Hosting, then Release history. Choose Roll back on the earlier release. The CSP is part of each release's `index.html`, so a rolled-back page keeps the API origin it was built with.
- **Settings.** Correct `deploy/config.sh` and run `02_deploy_backend.sh` again.
- **Stop the app's spending.** Delete the Cloud Run service with `gcloud run services delete`, and remove the Hosting site in the console. Deleting the whole project also removes its Firestore data. Do that only on purpose.

## Settings you decide

- `PROJECT_ID`, which has no default.
- `REGION` (Cloud Run and Firestore) and `LIVE_LOCATION` (Gemini Live is served only from US or EU endpoints).
- `BQ_DATASET`. Empty turns off the BigQuery analytics plugin, and its project-wide role is not granted.
- `USE_DEVELOPER_API_KEY`. Keep it at 0 for the Agent Platform path described in `docs/ARCHITECTURE.md`.
