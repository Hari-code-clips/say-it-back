# Say It Back runbook

For whoever runs the deployed app. How to deploy and check it is in `README.md`; this page is what to do afterwards. Set these first, in every shell (`REGION` is `asia-southeast1` with `DATA_REGION=sg`):

```bash
export PROJECT_ID=your-project-id REGION=asia-south1 SERVICE=say-it-back-api
```

## Deploy order

`01_setup_project.sh`, `probe_models.sh`, `02_deploy_backend.sh`, Verify, `03_deploy_web.sh`, Verify, the webhook secret, `04_deploy_ptw_stub.sh`, `02` again, then `05_monitoring.sh`, and, only with the e-permit outbox on (`OUTBOX=1`), `06_outbox_retry.sh`. Every script is safe to run again. Change a setting in `config.sh` and run the step that uses it; `RETENTION_DAYS` needs both 01 and 02.

## Verify (after any deploy)

1. `curl -fsS "$(gcloud run services describe $SERVICE --region $REGION --project $PROJECT_ID --format='value(status.url)')/api/health"` shows `"ok": true`, `"store": "firestore"`, and the pinned model ids.
2. `https://$PROJECT_ID.web.app` loads, and one briefing runs end to end.
3. Monitoring, Uptime checks: both checks are green (results appear about 10 minutes after step 5).

## Where the data is

Briefing records, permits and the daily counts are at rest in the data region (`DATA_REGION`: `in` is Mumbai, `sg` is Singapore). Model processing is not: Gemini Flash and TTS run on Agent Platform's `global` endpoint and Gemini Live in `us-central1`, the only places they are served. Say this plainly to any site that asks.

## Roll back a bad revision

```bash
gcloud run revisions list --service $SERVICE --region $REGION --project $PROJECT_ID
gcloud run services update-traffic $SERVICE --region $REGION --project $PROJECT_ID --to-revisions=GOOD_REVISION=100
```

Error Reporting names the revision each error came from (its version), so the last good one is the one before the errors start. While traffic is pinned, a new deploy gets none: after the fix, run `02` and then `gcloud run services update-traffic $SERVICE --region $REGION --project $PROJECT_ID --to-latest`. The web app rolls back in the Firebase console, Hosting, Release history.

## Raise or lower the daily caps

For a judging window or a recording, without a rebuild (a new revision in about a minute):

```bash
gcloud run services update $SERVICE --region $REGION --project $PROJECT_ID \
  --update-env-vars SIB_DAILY_GEMINI_CALLS=900,SIB_DAILY_CALLS_PER_IP=450
```

Lower them the same way (`SIB_DAILY_GEMINI_CALLS=200` stops most spending; `0` refuses every Gemini call). The next `02` puts back what `config.sh` says, so change `DAILY_CALLS` and `DAILY_CALLS_PER_IP` there too. The count resets at 00:00 UTC (05:30 IST).

## Rotate the webhook secret

1. Add a new version without the value touching your history: `openssl rand -hex 32 | tr -d '\n' | gcloud secrets versions add "$WEBHOOK_SECRET_NAME" --data-file=- --project $PROJECT_ID`.
2. Run `04_deploy_ptw_stub.sh`, then `02_deploy_backend.sh`: each new revision reads `latest` when it starts. Between the two, the stub refuses the backend's posts (401); decisions still record, so rotate outside a demo.
3. Disable the old version: `gcloud secrets versions list "$WEBHOOK_SECRET_NAME" --project $PROJECT_ID`, then `gcloud secrets versions disable OLD_VERSION --secret "$WEBHOOK_SECRET_NAME" --project $PROJECT_ID`.

## Alerts: what each means, and the first three things to check

**Say It Back: site down.** The API's `/api/health` or the web app failed its uptime check from two or more regions.
1. `gcloud run services describe $SERVICE --region $REGION --project $PROJECT_ID`: is the latest revision ready? If a deploy just ran, roll back (above).
2. The service's recent errors: `gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="'$SERVICE'" AND severity>=ERROR' --project $PROJECT_ID --freshness=30m --limit=20`.
3. Billing: when the trial credit runs out, the project stops serving. For the web check alone: Firebase console, Hosting, Release history.

**Say It Back: API 5xx answers.** More than 5 % of the API's answers over 5 minutes were 5xx. In a quiet spell one failure is enough.
1. Error Reporting: a new error group, and the revision it names. A new revision with new errors: roll back.
2. Which 5xx: `gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="'$SERVICE'" AND httpRequest.status>=500' --project $PROJECT_ID --freshness=30m --limit=20`. Mostly 503 (`upstream_busy`) means Gemini is refusing or slow: IAM and Admin, Quotas (Gemini requests per minute, Live sessions), and the Google Cloud status page.
3. 502 `upstream_error` or `script_incomplete` means the model answered something unusable: check the newest `usage` and `audit` log lines for `finish_reason` and the model ids, and run `probe_models.sh`.

**Error Reporting** (optional email: Error Reporting, Configure notifications). A new kind of unhandled error. The entry has the stack trace and the revision, never the message or anything the request held: reproduce from the frames.

**A stuck e-permit delivery** (`OUTBOX=1`). A record reading "Not delivered yet: retrying" for more than a few minutes:
1. Cloud Scheduler, `say-it-back-outbox-retry`: did the last run succeed? A 401 means the job's token is stale: run `06_outbox_retry.sh` again (also the last step of rotating `OUTBOX_TOKEN_SECRET_NAME`, after a new version and `02`).
2. The record's `delivery.targets[].lastError` (`http_503`, `timeout`, ...): the vendor's side is down or refusing; ask them.
3. "Not delivered to the permit system" is final: after 8 tries (about an hour) nothing retries it. Fix the cause and tell the permit office, which releases or holds the permit by hand from the Say It Back record (`docs/EPERMIT_ADAPTER.md`, Runbook).

## Cost alarms

The budget alert (step 1, `BILLING_ACCOUNT`) emails the billing admins at 10, 25, 50, 75 and 90 % of `BUDGET_AMOUNT`, ignoring credits. When one fires:
1. Billing, Reports, grouped by SKU: Gemini calls are the usual cause; an idle instance (`MIN_INSTANCES=1`) is about US$13 a month.
2. Lower the daily caps (above). The cap is the hard stop: past it, the API answers 429 `daily_limit` and spends nothing.
3. After judging, set `MIN_INSTANCES=0` and `PTW_MIN_INSTANCES=0` in `config.sh` and run 02 and 04.

## Delete a record on request

Records expire by themselves after `RETENTION_DAYS` (Firestore's TTL deletes them within about 24 hours after expiry; this needs `expireAt` stored as a Timestamp, which the backend does). To delete one now:
1. The browser that created it can delete it at once: `DELETE /api/briefings/{id}` with that browser's device key.
2. Without that browser, by its briefing id (Records, or the CSV): `npx --yes firebase-tools firestore:delete "briefings/BRIEFING_ID" --project $PROJECT_ID` (it asks to confirm), or the Firestore console.
3. Copies outside the record, which the backend cannot reach: a Google Chat message (delete it in the space) and the permit board's entry (Firestore `permits`: the document named by the briefing id, or the crew permit's document that lists it; delete or edit it the same way). Audio is never kept in the cloud: step 2 never sets `SIB_KEEP_AUDIO`. Log lines hold no briefing content.

## Who to call

- **Deploy owner** (holds the project's Owner role): deploys, rollbacks, caps, secrets, deletions.
- **Billing admin** of the billing account: budget alerts, the trial credit.
- **Backend owner**: Error Reporting groups, 5xx alerts, model failures.
- **Web owner**: the web app's uptime alert, Hosting releases.
- **A site's safety lead**, for a pilot: told whenever the app is down during a permit window, so the permit goes back to the site's normal briefing.
