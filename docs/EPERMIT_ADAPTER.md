# Connecting a site's e-permit system

Say It Back checks that each worker on a high-risk permit-to-work can say the critical steps back. The supervisor then decides Go or No-go. The AI never approves work, and Say It Back never releases a permit. It sends the supervisor's decision to the site's e-permit system, and that system releases or holds the permit.

This page is the contract a vendor implements. Connecting a vendor takes configuration, plus a field map when the vendor's API wants its own field names. `integrations/ptw-stub` is the reference receiver: it implements everything below and its tests prove it.

## What gets sent, and when

One POST per decision per target, as soon as the supervisor decides (endpoint 14). Targets:

| Target | Set by | Body | Auth |
|---|---|---|---|
| Google Chat space | a `chat.googleapis.com` URL in `SIB_WEBHOOK_URL` | `{"text": ...}` summary | the URL's own key |
| Receiver of the native record (the stub) | any other URL in `SIB_WEBHOOK_URL` (up to 3 in all) | the decision record | HMAC signature |
| The site's e-permit system | `SIB_PTW_URL` (one URL) | the decision record, or the vendor's fields mapped from it (`SIB_PTW_FIELD_MAP`) | HMAC signature, plus `Authorization: Bearer` with `SIB_PTW_TOKEN` |

With `SIB_OUTBOX=true` every delivery is stored first, retried when it fails, and shown on the record. Without it, each target gets one try within `SIB_WEBHOOK_TIMEOUT_S`, as in v0.5. Turn the outbox on for any real site.

## The request

```
POST <SIB_PTW_URL>
Content-Type: application/json
Idempotency-Key: sib-b_k3j9x2m4p7qa-6f1c2a9b0d3e4f58
X-SIB-Timestamp: 1792000000
X-SIB-Signature: sha256=5d2c...e9
Authorization: Bearer <SIB_PTW_TOKEN>          (only when it is set)

<body: compact UTF-8 JSON>
```

### The decision record (the native body)

```json
{
  "event": "briefing_decided",
  "briefingId": "b_k3j9x2m4p7qa",
  "siteId": "sg",
  "taskId": "lifting-zone",
  "sop": {"id": "SOP-LF-03", "version": "v2"},
  "supervisorLang": "en",
  "workerLang": "ta",
  "rounds": 2,
  "steps": [{"id": "s1", "text": "Never stand under the load", "source": "instruction", "finalVerdict": "covered"}],
  "decision": {"value": "go", "reason": null, "by": "J. Tan", "openStepIds": [], "openHazardIds": [], "at": "2026-10-17T09:00:00.000Z", "inPerson": false},
  "decidedAt": "2026-10-17T09:00:00.000Z",
  "hazards": [{"id": "h1", "kind": "voice", "acknowledged": true}],
  "sampleAnswers": [],
  "permit": {"ref": "PTW-2026/114", "crewSize": 3, "slot": 2},
  "events": 11,
  "recordHash": "6f1c2a9b0d3e4f58...64 hex",
  "promptVersion": "2026-10-16.12"
}
```

- `decision.value` is the supervisor's: `go` or `no_go`. `openStepIds` lists the steps that were not confirmed when they decided. A Go with open steps carries the supervisor's typed reason in the Say It Back record.
- `decision.inPerson` (2026-10-17, always a boolean) is true when the worker declined the AI check and the supervisor briefed and checked them in person: no model heard the worker, every step of that round is in `openStepIds`, and the Go carries the supervisor's reason. Show it as "checked in person", never as a check result.
- `permit` is `null` for a briefing outside any permit. Otherwise it is one worker on the permit: `ref` is the permit number as typed (1 to 32 of `A-Z a-z 0-9 . _ / -`, compare it case-insensitively), `crewSize` is 1 to 6, `slot` is 1 to `crewSize`. A worker is never named. The slot number is the only per-worker field.
- `sampleAnswers` is non-empty when an evaluator used stored synthetic answers instead of a worker. Treat such a decision as a demo, never as a real release.
- `recordHash` is the last link of the record's hash chain. Keep it with the permit: it lets anyone check later, against `GET /api/briefings/{id}/verify`, that the record was not changed.
- The record carries no transcript, no audio and no worker identity. It does carry `decision.reason` and `decision.by`, which are free text. **Never show the reason on a shared board or screen.** It could name a worker. The reference stub never stores it.

### The generic adapter (`SIB_PTW_FIELD_MAP`)

A vendor that wants its own field names gets a body built from a JSON map. Each key is the vendor's field, and a dotted key nests (`"permit.number"` gives `{"permit": {"number": ...}}`). Each value is one of:

| Source | Example | Gives |
|---|---|---|
| a record path | `"permit.ref"` | that value; `null` when the record has none |
| `"$idempotencyKey"` | `"$idempotencyKey"` | the delivery's key, also in the body |
| `{"const": <scalar>}` | `{"const": "say-it-back"}` | that constant |
| `{"from": <path>, "map": {...}, "default": <scalar>}` | `{"from": "decision.value", "map": {"go": "CLEARED", "no_go": "ON_HOLD"}}` | the mapped value; `default` (or `null`) for a value the map does not name |

```bash
SIB_PTW_FIELD_MAP='{"externalRef":"briefingId","permit.number":"permit.ref","permit.worker":"permit.slot",
  "clearance":{"from":"decision.value","map":{"go":"CLEARED","no_go":"ON_HOLD"}},
  "openSteps":"decision.openStepIds","evidenceHash":"recordHash","requestId":"$idempotencyKey"}'
```

The map is an allow-list: only mapped fields are sent, so leaving out `decision.reason` keeps it out of the vendor's system. A path must start at a field of the record above, and anything malformed stops the service at start-up. The signature covers the mapped bytes, exactly as sent.

## Verifying the signature

`X-SIB-Signature` is `sha256=` followed by the hex HMAC-SHA256 of `"<X-SIB-Timestamp>.<raw body>"`, keyed with the shared `SIB_WEBHOOK_SECRET`. Verify the raw bytes before parsing them, refuse a timestamp more than 300 s from your clock (either way), and compare in constant time:

```python
import hashlib, hmac, time

def verified(secret: bytes, timestamp: str, signature: str, body: bytes) -> bool:
    if not timestamp.isdigit() or abs(time.time() - int(timestamp)) > 300:
        return False
    mac = hmac.new(secret, timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest("sha256=" + mac, signature)
```

A retry is signed again with a fresh timestamp. The body and the `Idempotency-Key` stay the same.

## The idempotency key

`Idempotency-Key: sib-<briefingId>-<first 16 hex of recordHash>`. There is one key per decision, and every retry of it sends the same key. Both parts are inside the signed body, so you can check that the key belongs to it.

- Check that it does, after the signature and before you keep the key. The reference receiver checks it: a key that is not `sib-<briefingId>-<first 16 hex of recordHash>` of the record it came with is 422 `idempotency_key_mismatch`, and nothing changes. Without the check, a replayed signed body sent under another key could take the key a later briefing's delivery needs, and that delivery would then be refused.
- Keep each key you accepted, with what you did, for at least the retry window (about 64 minutes with the defaults; keep 7 days to be safe).
- The same key again: change nothing, and answer 2xx (ideally the same answer as the first time) or `409` with `{"error": {"code": "duplicate"}}`. The stub answers 409 `duplicate` with the permit it filed.
- The same key with another briefing: refuse it with 422. The stub answers `idempotency_key_reused`.
- Delivery is at least once, and order is not guaranteed. A re-brief of the same worker is a new briefing with a later `decidedAt`. Per `(permit ref, slot)`, keep the decision with the latest `decidedAt` and ignore an older one that arrives late. The stub does this.
- Google Chat has no de-duplication: after a lost answer, a retried Chat message can appear twice.

## How to answer

| Your answer | Say It Back reads it as | The record shows |
|---|---|---|
| any 2xx | delivered | "Sent to the permit system" |
| 409 with error code `duplicate` | delivered (you already had it) | "Sent to the permit system" |
| 408, 425, 429, any 5xx, no answer within `SIB_WEBHOOK_TIMEOUT_S`, a connection error | retry later | "Not delivered yet: retrying" |
| any other 4xx, including a 409 with another code, and any 3xx | refused: never retried | "Not delivered to the permit system. Tell the permit office." |

- Answer within `SIB_WEBHOOK_TIMEOUT_S` (default 5 s, at most 10). Take the post, store it, answer, then do the slow work.
- A refusal is final, so refuse only what a retry cannot fix: a bad signature (401), a record you cannot take (422), a crew size that does not match the permit (the stub's 409 `crew_mismatch`). A person then follows up from the record.
- Error bodies are best as `{"error": {"code": "snake_case", "message": "..."}}`. Say It Back stores only the class (`http_422`), never your body.

## Retries (`SIB_OUTBOX=true`)

- When a delivery fails and can be retried, the next attempt waits `SIB_OUTBOX_BACKOFF_S` (30 s), doubling each time up to `SIB_OUTBOX_MAX_BACKOFF_S` (1 h): 30 s, 1, 2, 4, 8, 16, 32 min. After `SIB_OUTBOX_MAX_ATTEMPTS` (8) tries, about 64 minutes after the decision, it is failed.
- Cloud Run gives an instance CPU only while it serves a request. So the retries run inside one: `POST /admin/outbox/retry` with `Authorization: Bearer <SIB_OUTBOX_TOKEN>`. Cloud Scheduler calls it every minute (see Runbook). Each call takes at most `SIB_OUTBOX_RETRY_BATCH` (20) briefings that are due, posts them at once, and answers `{checked, delivered, pending, failed}`.
- An attempt first claims its targets in one atomic store update, so two passes never post one target at the same time. If an instance dies mid-post, its claim expires and a later pass retries the target.
- Each delivery is kept in the store (`outbox/{briefingId}`; Firestore in the cloud), one entry per target: `status` (`pending`, `delivered`, `failed`), `attempts`, `lastError` (a class such as `http_503`, `timeout`, `ConnectError`, `duplicate`), `nextAttemptAt`, `deliveredAt`. A target is stored as a SHA-256 prefix of its URL, never the URL or a token. A target removed from the configuration fails as `target_removed`, and a briefing deleted by retention fails as `briefing_gone`.
- The record (endpoints 6 and 14) carries `delivery: {status, targets: [{kind, status, attempts, lastError, nextAttemptAt, deliveredAt}]}`, where `kind` is `chat` or `permit`. It never carries a URL, a host, the key or a token. It is `null` before the decision and absent when the outbox is off.

## Reading a permit's status back (the reference stub)

A site's own systems (a turnstile, a crane interlock, a dashboard) can poll the receiver instead of Say It Back. The stub serves:

| Route | Gives |
|---|---|
| `GET /api/permits/{id}` | `{permit}`: `status` (`released` or `held`), `ref`, `crewSize`, `verified`, `waiting`, `slots[]`, `openSteps`, `openHazards`, `recordHash`, `decidedAt`, `demo`. It sends an `ETag`, and `If-None-Match` gets 304 until the permit changes |
| `GET /api/permits?ref=<ref>` | `{permits}` narrowed to that permit number (case-insensitive) |
| `GET /api/permits` | every permit, newest first |
| `GET /` | the public board, which never shows a reason or a name |

A grouped permit is `released` only when every slot 1..`crewSize` holds a Go.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `SIB_OUTBOX` | `false` | Store, retry and show every delivery |
| `SIB_OUTBOX_MAX_ATTEMPTS` | `8` | Tries before a delivery is failed (1-50) |
| `SIB_OUTBOX_BACKOFF_S` | `30` | Wait after the first failed try, doubling |
| `SIB_OUTBOX_MAX_BACKOFF_S` | `3600` | The longest wait |
| `SIB_OUTBOX_RETRY_BATCH` | `20` | Briefings one retry call works through (1-100) |
| `SIB_OUTBOX_TOKEN` | empty | Bearer token for `POST /admin/outbox/retry`; empty means the route answers 404. Secret Manager |
| `SIB_PTW_URL` | empty | The e-permit system's endpoint; an http(s) URL, never logged (only its host is) |
| `SIB_PTW_FIELD_MAP` | empty | The generic adapter's field map (JSON); empty sends the native record |
| `SIB_PTW_TOKEN` | empty | Sent as `Authorization: Bearer` to `SIB_PTW_URL` only, which must then be https (localhost excepted). Never logged. Secret Manager |
| `SIB_WEBHOOK_SECRET` | empty | The HMAC key; empty sends unsigned posts. Secret Manager |
| `SIB_WEBHOOK_TIMEOUT_S` | `5` | Each post's cut-off |

## Runbook

1. **Agree the contract with the vendor:** their URL, their field map (or the native record), their bearer token, the shared HMAC secret, and how they answer (above). Ask them to run their receiver against a signed sample first. The stub's tests show every case.
2. **Put the secrets in Secret Manager**, never in a file: `SIB_WEBHOOK_SECRET`, `SIB_PTW_TOKEN`, `SIB_OUTBOX_TOKEN`. Expose them to the Cloud Run service as environment variables.
3. **Set** `SIB_OUTBOX=true`, `SIB_PTW_URL`, and `SIB_PTW_FIELD_MAP` if needed. Deploy. A malformed map, an http URL with a token, or a token without a URL stops start-up with a message that names no secret. The link needs accounts: with either `SIB_OUTBOX` or `SIB_PTW_URL` set, the service starts only with `SIB_AUTH_MODE=firebase`, because in device mode no person stands behind a decision, and `deploy/02_deploy_backend.sh`, which deploys device mode only, stops before deploying (docs/API.md, Deviations 2026-10-16, security fixes A).
4. **Schedule the retries:**
   ```bash
   gcloud scheduler jobs create http sib-outbox-retry --location="$REGION" --schedule="* * * * *" \
     --uri="$SERVICE_URL/admin/outbox/retry" --http-method=POST \
     --headers="Authorization=Bearer $(gcloud secrets versions access latest --secret=sib-outbox-token)"
   ```
   The job holds the token in its configuration, so limit who can read Cloud Scheduler jobs. Rotate the token by updating the secret, redeploying, and updating the job.
5. **Check:** decide a test briefing and see "Sent to the permit system" on its record. Then stop the receiver, decide another, and watch it read "Not delivered yet: retrying" until the receiver is back and the next scheduled pass delivers it.
6. **When a record says "Not delivered to the permit system":** the vendor refused it, or the tries ran out. The record's `delivery.targets[].lastError` gives the class. Fix the cause, then tell the permit office: the permit is released or held by hand from the Say It Back record. The outbox does not retry a failed delivery. A new decision on a re-brief sends a new one.

## A worked example for one vendor: Novade (17 Oct 2026)

`integrations/ptw-stub/examples/novade.md` applies this contract to Novade Permit to Work, the Singapore ePTW vendor whose integration offer is the most public: Novade says it provides "secure, versioned APIs" for enterprise integrations, but publishes no endpoint, field list or authentication scheme, so the example is a proposal, not an integration and not a certification. It gives the configuration (native record, or a field map checked with this backend's own `parse_field_map`), the field map from the record to assumed Novade names (the supervisor's reason and name deliberately left out), the request, how each answer is read and retried, and nine numbered assumptions to replace with Novade's documentation. IMDA's pre-approval guide for e-PTW solutions lists an API for sharing information with external platforms as a preferred capability, not a mandatory one.

## Not here yet

- One vendor URL. Several e-permit systems would need `SIB_PTW_URL` to become a list.
- Bearer tokens only. OAuth 2 client credentials and mutual TLS would be one more adapter.
- No push back from the vendor: a permit closed or handed over in the vendor's system does not come back to Say It Back.
- No dead-letter view across briefings. Failed deliveries show on each record, and a failed delivery is logged with its target's kind and error class.
