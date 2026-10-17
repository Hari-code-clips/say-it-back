# Deploy Say It Back to Google Cloud

> **Warning.** These scripts create billable resources in your Google Cloud project. Only the project owner runs them, by hand, after reading this file. No CI job runs them.

Running the deployed app (rollback, daily caps, secret rotation, alerts, deleting a record) is in [`RUNBOOK.md`](RUNBOOK.md).

## Before you start

- A Google Cloud project you own, with billing enabled (the free trial is fine). Export its id in your shell rather than committing it: `export PROJECT_ID=your-project-id`. The web address is `https://$PROJECT_ID.web.app`, so a readable project id (create a new project on the same trial billing account) gives judges a readable link.
- Firebase is added to that project by step 3 if it is not there yet.
- Tools: the gcloud CLI signed in (`gcloud auth login` and `gcloud auth application-default login`, the second for `probe_models.sh`), Node 22 on `PATH` (on Hari's Mac: `export PATH="$HOME/.nvm/versions/node/v22.22.1/bin:$PATH"; unset -f node npm npx`), `uv`, and a one-time `npx firebase-tools login`. Step 5 also needs gcloud's alpha and beta commands (`gcloud components install alpha beta`); it stops and says so when they are missing.
- A budget alert. Set `BILLING_ACCOUNT` (from `gcloud billing accounts list`) and `BUDGET_AMOUNT` in `config.sh` and step 1 creates one that ignores credits, with alerts at 10, 25, 50, 75 and 90 %. If you make it in the console instead, untick the credits under "Credits": on a free trial, cost after credits stays at zero and an alert that counts them never fires. The backend is public by design, so watch the spend.
- On a free trial nothing is charged to your card, but when the credit runs out the project stops, and the app goes dark. A trial also cannot raise quotas: after step 2, check IAM and Admin, Quotas, for the Gemini Live concurrent sessions and the Flash requests per minute.
- Settings in `deploy/config.sh`: the data region (`DATA_REGION`), Live location, service name, optional BigQuery dataset, instance limits, the exact model ids, the daily caps, how long records are kept (`RETENTION_DAYS`), the optional alert address (`ALERT_EMAIL`), and the optional webhook URLs and webhook secret name (see "Settings you decide").
- `backend/.gcloudignore`. Step 2 refuses to run without it. gcloud reads that file, not the repository `.gitignore`, when it uploads `backend/`. It must exclude `.data/`, `.venv/`, `__pycache__/` and any dotenv file.

## How the pieces connect

The browser calls the Cloud Run service directly, for the API and for the Live WebSocket. Firebase Hosting serves the web app as static files and has **no `/api` rewrite**: per-address limits read `X-Forwarded-For` from the right, so every request must arrive through the same hops (`docs/ARCHITECTURE.md`). Three settings tie the two halves together:

- `VITE_API_BASE` (web build): the service URL plus `/api`. Step 3 reads the URL with gcloud and sets it. The page's Content-Security-Policy is written from it, so `connect-src` names that origin and nothing else.
- `SIB_ALLOWED_ORIGINS` (backend): the web origins, for CORS and the WebSocket Origin check. Step 2 sets `https://$PROJECT_ID.web.app` and `https://$PROJECT_ID.firebaseapp.com`. A custom domain has to be added to that list (the `ENV_VARS` line in step 2), or the browser's requests are refused.
- `SIB_PUBLIC_WS_BASE` (backend): the service's `wss://` address. Step 2 sets it once the service exists.

Each browser sends its own device key in an `X-SIB-Device` header. That header makes every cross-origin request preflighted, and the backend answers the preflight for the web origins.

## Order

1. `bash deploy/01_setup_project.sh` enables the APIs (Firebase, Firebase Rules, the Telemetry API and Error Reporting included) and creates:
   - the Firestore database in the data region (it stops if the project's database is in another region: a database cannot move), and the composite index `briefings(owner ascending, createdAt descending)`. A caller's list of briefings and the CSV export need it, and both answer 500 without it. This script is the only place the index is managed;
   - the Firestore TTL policy on `briefings.expireAt`, which deletes each briefing record `RETENTION_DAYS` after it was created. Firestore runs the deletion within about 24 hours after a record's expiry, not at the second; until then the backend already treats an expired record as gone. TTL acts only on a Timestamp value, which is what the backend writes. With `RETENTION_DAYS=0` the script switches the policy off instead, so records written earlier with an expiry are kept as well;
   - the Artifact Registry repository `cloud-run-source-deploy`, so steps 2 and 4 never stop to ask;
   - the runtime service account and its roles. `roles/bigquery.dataEditor` is granted only when `BQ_DATASET` is set. A project set up by an earlier version of the script still holds it: remove it with `gcloud projects remove-iam-policy-binding` if BigQuery is not used;
   - the optional BigQuery dataset;
   - the optional budget alert (`BILLING_ACCOUNT`).
2. `bash deploy/probe_models.sh` makes one tiny call to each pinned model on Agent Platform, with the service's locations: Flash, judge B, TTS (also tried in `us-central1`) and Live. Every line must read `OK`. On a `FAIL`, the script's header says which `config.sh` value to change. It costs a fraction of a cent.
3. `bash deploy/02_deploy_backend.sh` builds `backend/` and deploys it to Cloud Run.
   - It copies `eval/testset` and `eval/reports/latest.json` into `backend/eval_data/` for the build and removes the copy afterwards, so the Sample page has its data in the image. Refresh `eval/reports/latest.json` before a deploy: the image carries what was there.
   - It sets the backend's settings, then reads the service URL and sets `SIB_PUBLIC_WS_BASE` to the matching `wss://` address.
4. Check the backend (see Verify).
5. `bash deploy/03_deploy_web.sh` adds Firebase to the project when it is missing, reads the service URL, builds `web/` with `VITE_API_BASE="<service URL>/api"` and deploys Firebase Hosting and the Firestore client rules (`firestore.rules`, deny all). It does not deploy Firestore indexes.
   - Before building it checks `firebase.json` (no `/api` rewrite, no rewrite to Cloud Run, the frame and opener headers, the rules file wired in, no indexes) and `firestore.rules` (one rule, deny all).
   - It runs `npm test`, which covers the same files.
   - After building it checks the built `index.html`: the CSP `connect-src` names exactly the service over `https` and `wss`, nothing allows `unsafe-eval`, and the bundle holds no mock-mode code.
6. Check the web app (see Verify), then on a real iPhone (Safari) and a real Android phone (Chrome): one whole briefing in Live mode and one in Turn mode, with the phone's speaker. Links opened inside WhatsApp, LinkedIn or Gmail may have no microphone; the app then asks to open the page in Chrome or Safari.
7. Optional: `bash deploy/04_deploy_ptw_stub.sh` deploys `integrations/ptw-stub` as a second Cloud Run service, `say-it-back-ptw`: a stand-in permit-to-work system that receives the signed decision webhook and releases (Go) or holds (No-go) a permit on a board at its root URL.
   - It needs `WEBHOOK_SECRET_NAME`: the stub refuses unsigned posts. Create the secret first (see "Settings you decide").
   - It runs as its own service account, `say-it-back-ptw`, which may read that one secret and use Firestore (`roles/datastore.user`; that role is project-wide, as Firestore roles cannot be narrowed to one collection, and the stub's code touches only `permits` and `permit_counters`), with `--allow-unauthenticated` (the webhook carries no Google identity; the signature, checked within 300 s, is the guard) and one instance at most.
   - It runs with `PTW_STORE=firestore`: permits are kept in the project's Firestore database (which step 1 creates; the script stops if it is missing), so a new instance shows the same board and the service scales to zero (`PTW_MIN_INSTANCES=0`). The first board view after a quiet spell waits a few seconds for a cold start.
   - Then add `<its URL>/webhook` to `WEBHOOK_URLS` in `config.sh` and run `02_deploy_backend.sh` again.
8. Optional, after 3: `ALERT_EMAIL=you@example.com bash deploy/05_monitoring.sh` (or set `ALERT_EMAIL` in `config.sh`). It creates:
   - an email notification channel for that address;
   - two HTTPS uptime checks, every 5 minutes from each of Google's checker regions: `GET <service URL>/api/health` and `https://$PROJECT_ID.web.app/`, each failing on anything but a 2xx within 10 s;
   - the alerting policy `Say It Back: site down`, which emails when either check fails from two or more regions;
   - the alerting policy `Say It Back: API 5xx answers`, which emails when more than 5 % of the API's answers over 5 minutes are 5xx (Gemini's `upstream_busy` 503 counts, as does a 500).
   - Each is looked up by its display name first and never changed once it exists. To change the address or a policy, delete the policy (Monitoring, Alerting) and run the step again. `RUNBOOK.md` says what each alert means and what to check first.
9. Not with these scripts yet: the pilot e-permit link (`docs/EPERMIT_ADAPTER.md`; off by default). It releases and holds real permits, so it needs a service with accounts (`SIB_AUTH_MODE=firebase`, `docs/API.md` Deviations 2026-10-16, "pilot accounts"): in device mode no person stands behind a decision. These scripts deploy device mode only, so `02_deploy_backend.sh` stops before deploying when `OUTBOX=1` or `PTW_URL` is set, and the service itself refuses to start with `SIB_OUTBOX` or `SIB_PTW_URL` in device mode. The demo permit stub of step 7 is not the e-permit link: it is reached through `WEBHOOK_URLS` and works in device mode. Once a firebase-mode service exists, step 6 is the retry half: create the outbox token's secret like the webhook secret (`openssl rand -hex 32 | tr -d '\n' | gcloud secrets create sib-outbox-token --data-file=- --project "$PROJECT_ID"`), then run `OUTBOX=1 OUTBOX_TOKEN_SECRET_NAME=sib-outbox-token bash deploy/06_outbox_retry.sh`. Step 6 creates the Cloud Scheduler job `say-it-back-outbox-retry`, which calls `POST <service URL>/admin/outbox/retry` every minute with that token; run again, it updates the job, which is how a rotated token reaches it. The job holds the token in its configuration (the script reads the secret and never prints it), so limit who can read Cloud Scheduler jobs.

Unhandled backend errors reach Error Reporting (Google Cloud console, Error Reporting) with no setup beyond step 1: the backend writes each as one JSON line on stderr with its stack trace and exception type, and the Cloud Run revision as its version. The line never holds the error's message, a device key, its hash, a client address, a ticket or a request body. To be emailed about a new kind of error, open Error Reporting, Configure notifications, and pick the channel step 5 made.

Every script prints each command before it runs. Re-running a script is safe: existing resources are left alone, and a redeploy creates a new Cloud Run revision.

## Where the data is

`DATA_REGION` in `config.sh` picks where data is kept at rest: `in` (the default) is `asia-south1`, Mumbai; `sg` is `asia-southeast1`, Singapore. Cloud Run (the API and the permit stub), the Firestore database (briefing records, permits, the daily counts), the Artifact Registry images and the optional BigQuery dataset go there. Set it before step 1 runs for the first time: the database's location is fixed when it is created, and step 1 refuses to continue with a database in another region.

Model processing does not stay in the region. Gemini Flash and TTS are served only on Agent Platform's `global` endpoint, and Gemini Live only in `LIVE_LOCATION` (`us-central1`), so an instruction, a script and a worker's spoken answer are processed there, whichever preset is set. Cloud Logging, Cloud Trace and Error Reporting keep their data in Google's global location by default; by design they hold no transcript, audio, device key or client address. Firebase Hosting serves the static web app from Google's global CDN.

## What each step costs

| Step | Creates | Cost at prototype volume |
|---|---|---|
| 01 | Enabled APIs, Firestore database, index and TTL policy, Artifact Registry repository, service account, IAM bindings, optional BigQuery dataset and budget | Enabling APIs and creating the account are free. Firestore and BigQuery charge only past their free tiers. A TTL deletion bills as an ordinary document delete (free for the first 20,000 a day). |
| probe | One small call to each of the four models | A fraction of a cent. |
| 02 | Cloud Build runs, an Artifact Registry image, a Cloud Run service | Build minutes and image storage fall within free tiers. With `MIN_INSTANCES=1` (the judging-window default) one idle instance bills, about US$13 a month; with 0 it scales to zero and bills only while requests or WebSocket sessions run. |
| 03 | A Firebase Hosting release and a Firestore rules release | Within the Hosting free tier. Rules releases are free. |
| 04 | A second service account, a Cloud Build run and image, a second Cloud Run service (256 MiB, one instance at most), a few Firestore documents | Nothing idle at the default `PTW_MIN_INSTANCES=0`; about US$13 a month at 1. Firestore use is within the free tier. |
| 05 | A notification channel, two uptime checks, two alerting policies (three conditions) | Email is free. The two checks run about 100,000 times a month together (every 5 minutes from six regions), inside the uptime-check free allotment Google lists. Cloud Monitoring may bill each alerting condition a small monthly amount: check the current rate on the Google Cloud Observability pricing page (it was not confirmed for this note). Error Reporting has no charge of its own; its lines count toward Cloud Logging's free 50 GiB a month. |
| 06 | One Cloud Scheduler job, calling the API once a minute | Free within three jobs per billing account, then US$0.10 a job a month. Each call is one short request and a small Firestore query, inside the free tiers. |
| Runtime | Gemini calls (Flash, Live, TTS), Cloud Trace, BigQuery writes | Gemini calls are the main cost: about US$0.20 for a whole two-round briefing, and the daily cap (600 units, `config.sh`) bounds a day at about INR 510 in ordinary use and about INR 1,700 in the worst case. |

## The judging window

The defaults in `config.sh` are for 19 Oct to 14 Nov (and to the 4 Dec finale if shortlisted): `MIN_INSTANCES=1`, `PTW_MIN_INSTANCES=0`, `DAILY_CALLS=600`, `DAILY_CALLS_PER_IP=300`, `RATE_LIMIT_PER_MIN=120`, `MAX_SOCKETS_PER_IP=12` and `MAX_OUTPUT_TOKENS=4096`. Expected spend over the whole window is about INR 8,000 to 16,000 of a INR 28,797 trial credit. If a budget alert fires early, lower the cap in about a minute, with no rebuild (`--region asia-southeast1` if `DATA_REGION=sg`; `RUNBOOK.md` has the raise and lower commands):

```bash
gcloud run services update say-it-back-api --region asia-south1 --project "$PROJECT_ID" \
  --update-env-vars SIB_DAILY_GEMINI_CALLS=200
```

Afterwards, set both minimum-instance values to 0 and run 02 and 04 again.

## Verify

Backend. Replace `say-it-back-api` if you changed it in `config.sh`, and `asia-south1` with `asia-southeast1` if `DATA_REGION=sg` (the same in every command below):

```bash
SERVICE_URL="$(gcloud run services describe say-it-back-api --region asia-south1 \
  --project "$PROJECT_ID" --format='value(status.url)')"
curl -fsS "$SERVICE_URL/api/health"
```

The JSON should show `"store": "firestore"`, and every value under `backends` should be `"agent-platform"`. A `"developer-api"` value is expected only if you set that backend variable on purpose. `models` should name the exact ids pinned in `config.sh`, `judgeB` included. The ids are the Developer API names until checked: before a judging window, confirm each one on Agent Platform with one real call per model, and correct `config.sh` if the platform names them differently.

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

The record chain and the webhook (API v0.4). After deciding a briefing, `GET $SERVICE_URL/api/briefings/<id>/verify` with that browser's device key answers `"ok": true`. With step 4 deployed and its URL in `WEBHOOK_URLS`, the permit board (`https://<stub URL>/`) shows a new permit within a few seconds, released for a Go and held for a No-go, and its record hash equals the briefing's `recordHash`. A post to `<stub URL>/webhook` without a signature answers `401`. Run step 4 again (a new revision, a new instance): the board still lists the earlier permits, and `<stub URL>/healthz` says `"store": "firestore"`.

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
- `DATA_REGION`: `in` (`asia-south1`, the default) or `sg` (`asia-southeast1`), for Cloud Run and Firestore; anything else is refused. See "Where the data is". `LIVE_LOCATION` (Gemini Live is served only from US or EU endpoints) does not follow it.
- `RETENTION_DAYS` (90): `SIB_RETENTION_DAYS`, how many days a briefing record is kept, 0 (keep) to 3650. It applies to records created after the change; run 01 and 02 again when it changes, since 01 switches the TTL policy on or off.
- `ALERT_EMAIL`: one address for step 5's alerts. Empty skips step 5.
- `OUTBOX` (0), `OUTBOX_TOKEN_SECRET_NAME`, `PTW_URL`, `PTW_FIELD_MAP`, `PTW_TOKEN_SECRET_NAME`: the pilot e-permit link, off by default. It needs a service with accounts (`SIB_AUTH_MODE=firebase`), which these scripts do not deploy yet, so step 2 stops when `OUTBOX=1` or `PTW_URL` is set (see step 9), and every deploy sets `SIB_OUTBOX=false` and an empty `SIB_PTW_URL`, which also turns off a link set on the service by hand. For a firebase-mode service they mean: `SIB_OUTBOX`, the Secret Manager secrets behind `SIB_OUTBOX_TOKEN` and `SIB_PTW_TOKEN`, `SIB_PTW_URL` (https, no `@`, never printed because it can hold a key) and `SIB_PTW_FIELD_MAP` (a one-line JSON object; the service parses it at start-up). `OUTBOX=1` needs the token secret, and the field map and the vendor token need `PTW_URL`.
- `BQ_DATASET`. Empty turns off the BigQuery analytics plugin, and its project-wide role is not granted.
- `USE_DEVELOPER_API_KEY`. Keep it at 0 for the Agent Platform path described in `docs/ARCHITECTURE.md`.
- `FLASH_MODEL`, `JUDGE_B_MODEL`, `LIVE_MODEL`, `TTS_MODEL`: exact model ids, set on the service as `SIB_FLASH_MODEL`, `SIB_JUDGE_B_MODEL`, `SIB_LIVE_MODEL` and `SIB_TTS_MODEL`, so it never follows a moving alias. The defaults are the Developer API names; check the exact Agent Platform id of each at deploy. An empty `JUDGE_B_MODEL` runs judge B on `FLASH_MODEL`.
- `DAILY_CALLS` (600) and `DAILY_CALLS_PER_IP` (300): `SIB_DAILY_GEMINI_CALLS` and `SIB_DAILY_CALLS_PER_IP`, sized for the judging window and the free-trial credit (a room of judges on one Wi-Fi shares one address). The app's own defaults, without this script, stay 300 and 100.
- `RATE_LIMIT_PER_MIN` (120), `MAX_SOCKETS_PER_IP` (12), `MAX_OUTPUT_TOKENS` (4096, at least 1024), `WEBHOOK_TIMEOUT_S` (5, above 0 and at most 10, because the browser waits 20 s for a decision) and `TTS_LOCATION` (`global`): `SIB_RATE_LIMIT_PER_MIN`, `SIB_MAX_SOCKETS_PER_IP`, `SIB_MAX_OUTPUT_TOKENS`, `SIB_WEBHOOK_TIMEOUT_S` and `SIB_TTS_LOCATION`.
- `MIN_INSTANCES` (1): warm through the judging window, so the first visitor meets no cold start. Set it to 0 afterwards.
- `PTW_MIN_INSTANCES` (0): the permit board keeps its permits in Firestore, so the stub can scale to zero; set 1 only to spare the first board view a cold start.
- `EXTRA_ORIGINS`: more web origins for CORS and the WebSocket check, for example a named Hosting site.
- `BILLING_ACCOUNT` and `BUDGET_AMOUNT` (`28797INR`): the optional budget alert of step 1, which ignores credits.
- `WEBHOOK_URLS`: up to 3 comma-separated `https://` URLs (no `@`), for example the stub's `/webhook` and a Google Chat incoming webhook. A URL can hold a key: the scripts print `<hidden>` in its place and never echo it. Empty sends no webhook (and a deploy with it empty removes any URL set before).
  Known limit, left out of v0.4 on purpose: the URLs, a Google Chat URL's key and token included, are a plain environment variable on the service, not a Secret Manager secret, so anyone who can read the service's configuration can read them.
- `WEBHOOK_SECRET_NAME`: the Secret Manager secret that holds `SIB_WEBHOOK_SECRET`, the HMAC key of the signed JSON posts, for the backend and step 4 alike. Create it without the value passing through your terminal history or this folder, for example `openssl rand -hex 32 | tr -d '\n' | gcloud secrets create sib-webhook-secret --data-file=- --project "$PROJECT_ID"`. The scripts set it with `--set-secrets` and grant each service account read access to that one secret; they never read or print its value. Empty sends unsigned posts, and step 4 refuses to run. The signature covers the timestamp and the body, not the URL path (a known limit, left out of v0.4 on purpose).
