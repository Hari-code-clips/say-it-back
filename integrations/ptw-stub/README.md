# Permit-to-work stub

A small stand-in for a site's permit-to-work (PTW) system, so Say It Back's decision webhook has a
receiver that maps to the buyer's world. When a supervisor decides in Say It Back, the backend posts
the signed decision record here (docs/API.md v0.4, "Webhooks"):

- **Go** releases a permit `PTW-<n>`;
- **No-go** holds it.

Each permit carries the briefing id, site, task, the steps and hazards still open when the decision
was made, the record's `recordHash` (the hash-chained record's last link, anchored here outside the
backend's store) and the time it was received. A permit whose briefing used stored synthetic sample
answers is marked "Demo: synthetic sample answers" on the board and in its JSON. The decision is always the supervisor's: the stub
only follows it, and the board says so.

**One permit, several workers (API v0.5.2).** A high-risk permit names a crew of 1 to 6, and each
worker is briefed and checked on their own. A record whose briefing carries `permit`
(`{ref, crewSize, slot}`) is filed under that permit's `ref`, matched case-insensitively and kept
as first typed: one entry per worker slot, holding that slot's latest decision. A later decision
for the same slot replaces it (a re-brief); a repeat of the same briefing, or an older decision
arriving late, changes nothing. The permit is `released` only when every slot 1..`crewSize` holds
a Go; otherwise it is `held`, with `verified` (slots with a Go) and `waiting` (slots with no
decision yet, or a No-go). A post whose `crewSize` differs from the permit's is refused with 409
`crew_mismatch` and changes nothing. Workers are never named: the slot number is the only
per-worker field, and the decider's name is kept but never shown. A record without `permit` gets
its own permit, as before.

**The reference e-permit system (pilot).** The stub implements the contract a vendor implements
(`../../docs/EPERMIT_ADAPTER.md`). A post's `Idempotency-Key` is kept with the permit it filed, in
the same write as the permit (the memory file's `deliveries`; Firestore `permit_deliveries/{key}`,
in the same transaction). The same key again answers 409 `{"error": {"code": "duplicate"}, "permit"}`
and changes nothing, so a retried delivery never files twice, and never undoes a re-brief. The same
key with another briefing is 422 `idempotency_key_reused`; a malformed key (not 8 to 128 of
`A-Za-z0-9._:-`) is 422 `bad_idempotency_key`; a key that is not the record's own,
`sib-<briefingId>-<first 16 hex of recordHash>` of the signed body it came with, is 422
`idempotency_key_mismatch` and changes nothing, so a replayed body cannot take a later delivery's
key. A post without a key behaves as before.

| Route | What it does |
|---|---|
| `POST /webhook` | Verifies `X-SIB-Timestamp` and `X-SIB-Signature: sha256=<HMAC-SHA256 of "<timestamp>.<raw body>">` with the shared secret, refuses a timestamp more than 300 s from now (401), then records the permit (201 for a new permit; 200 when a repeat post returns its permit, or a worker's decision is filed into an existing grouped permit; 409 `crew_mismatch`; with an `Idempotency-Key` already taken, 409 `duplicate` with the permit, or 422 `idempotency_key_reused`; with a key that is not the record's own, 422 `idempotency_key_mismatch`) |
| `GET /api/permits` | `{permits: [{id, status, briefingId, siteId, taskId, decision, decidedAt, openSteps, openHazards, recordHash, receivedAt, demo, sampleAnswers, inPerson, ref, crewSize, verified, waiting, slots}]}`, newest first. For a grouped permit, `slots` is `[{slot, decision, briefingId, recordHash, decidedAt, openSteps, openHazards, goWithOpenSteps, inPerson}]` (what was open at that worker's decision; `goWithOpenSteps` marks a Go the supervisor gave with steps still open, whose reason stays in the Say It Back record; `inPerson`, 2026-10-17, marks a Go after the worker declined the AI check, so the supervisor checked them in person), `openSteps` lists every worker's open steps, each with its `slot`, and `openHazards` every worker's as `"<id> (worker <n>)"`; `decision` is `go` only when it is released, and the briefing, hash and times are the latest post's; `ref`, `crewSize` and `verified` are null for a per-briefing permit. `demo` is `"Demo: synthetic sample answers"` when some answers were stored synthetic samples (endpoint 24), else null. `inPerson` is true when the record's `decision.inPerson` is (a JSON boolean; a record without it is false), and for a grouped permit when some worker on it was checked in person. The decider's name is kept in the stub's own record and is never served or shown |
| `GET /api/permits?ref=<ref>` | The same list narrowed to one permit number (case-insensitive): what a site's system polls by the number it knows |
| `GET /api/permits/{id}` | `{permit}` for one permit (`PTW-<n>`), the same fields as the list. It sends an `ETag`; `If-None-Match` with it answers 304 until the permit changes. 404 `not_found` for an unknown id |
| `GET /` | The permit board: server-rendered HTML, no script, no external asset, a CSP that allows only its own inline style. A grouped permit shows its ref, "2 of 3 workers verified · held" and one row per worker (Go, a Go given with steps open and those steps, "Go · checked in person" with its open steps, No-go with what was open, or no decision yet). The supervisor's reason is never shown: it stays in the Say It Back record. It refreshes every 5 s |
| `GET /healthz` | `{ok, signed, store, permits}`: `store` is `memory` or `firestore` |

## Settings

Environment variables only.

| Variable | Default | Meaning |
|---|---|---|
| `SIB_WEBHOOK_SECRET` | empty | The same HMAC secret as the backend's `SIB_WEBHOOK_SECRET`. Without it every post is refused (503 `not_configured`). Never logged |
| `PTW_ALLOW_UNSIGNED` | `false` | `true` accepts unsigned posts when no secret is set. Local tries only |
| `PTW_STORE` | `memory` | Where permits live. `memory`: in this process (and in `PTW_STORE_FILE` when set), so a new instance starts with an empty board. `firestore`: in Firestore, collection `permits` (one document per briefing id) plus `permit_counters/ptw` (the last permit number), in the project's default database, so every instance, and a new one, shows the same board. Anything else stops the service at start-up |
| `PTW_STORE_FILE` | empty | With `memory` only: a JSON file the permits are also written to (atomically), and read back at start. Empty keeps them in memory only |
| `PORT` | `8080` | The port uvicorn listens on in the image |

## Run and test

```bash
cd integrations/ptw-stub
uv sync
uv run ruff check .
uv run pytest -q
SIB_WEBHOOK_SECRET=dev-secret uv run uvicorn ptw_stub.app:app --port 8090
```

The Firestore store is tested against an in-memory fake (`tests/fake_firestore.py`) that locks
documents read in a transaction and interleaves concurrent posts as the real service does: a
retried post never makes a second permit, and two instances never give out the same number.
`google-cloud-firestore` is imported only with `PTW_STORE=firestore`.

Then point the backend at it: `SIB_WEBHOOK_URL=http://localhost:8090/webhook SIB_WEBHOOK_SECRET=dev-secret`
(a comma-separated list of up to 3 URLs; a Google Chat URL can sit beside it), decide a briefing,
and open `http://localhost:8090/`.

## Deploy

`deploy/04_deploy_ptw_stub.sh` deploys it as a second Cloud Run service (`say-it-back-ptw`,
`--allow-unauthenticated`, its own service account, the same Secret Manager secret as the backend,
one instance at most) with `PTW_STORE=firestore`. Its service account gets `roles/datastore.user`,
which is project-wide (Firestore roles cannot be narrowed to one collection). Permits persist, so
the service scales to zero (`PTW_MIN_INSTANCES=0`) without losing the board. Then add
`<its URL>/webhook` to `WEBHOOK_URLS` in `deploy/config.sh` and run `deploy/02_deploy_backend.sh`
again. See `deploy/README.md`.

## Not here

This is a demo receiver, not a PTW system: no accounts, no permit closing or handover, no audit trail
of its own beyond the `recordHash` it keeps. A real integration would post into the site's own PTW
product with the same signed record.
