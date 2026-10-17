# Example: sending the decision to Novade Permit to Work

**What this is:** a worked example of the e-permit link (`docs/EPERMIT_ADAPTER.md`) aimed at one named vendor. It is a proposal for a conversation with Novade. It is **not** an integration, not a partnership and not a certification: nothing here has been sent to Novade, tested against a Novade system or reviewed by Novade. Every vendor-side detail Novade has not published is marked **[A1]**, **[A2]** and so on, and listed under "Assumptions". Written 17 Oct 2026 (build note 37, review P1-3).

## What Novade publishes (read 17 Oct 2026)

- **The product.** Novade Permit to Work "digitise[s] and control[s] your Permit to Work system from risk assessment to closure", alerts "safety teams before conflicting permits are approved", works offline on mobile and tracks worker credentials ([Novade, Permit to Work](https://www.novade.net/en/permit-to-work-software/)). Novade presents it as meeting Singapore's ePTW requirement for public-sector projects of S$3 million or more ([Novade, ePTW article](https://www.novade.net/comply-with-wsh-regulations-singapore-eptw/)).
- **An API, but no public contract.** Novade's integrations page answers "Does Novade offer APIs?" with "Yes. Novade provides secure, versioned APIs to support enterprise integrations and custom system connections", and offers "secure custom integrations" for enterprise needs ([Novade Connect](https://www.novade.net/en/novade-connect/)). Novade also embeds Workato for its clients' ERP integrations ([Workato, 4 May 2026](https://www.workato.com/the-connector/why-novade-embedded-workato/)). We found no public endpoint list, authentication scheme, permit resource, field list, error format or rate limit.
- **Why a buyer asks for this.** IMDA's pre-approval guide for e-PTW solutions lists, as a *preferred* (not mandatory) question, "Does your solution provide APIs for sharing information with external platforms or solutions"; mobile submission and approval, audit trails and data export are mandatory ([IMDA pre-approval guide, e-PTW](https://preapproval-guide.imda.gov.sg/pre-approval-guide/stage-1-vendor-self-assessment/identify-suitable-solution-category/built-environment/smart-inspection-and-management-e-permit-to-work-e-ptw)).

So the honest shape is: Say It Back sends a signed, idempotent decision per worker; a Novade-side receiver (a custom integration or a Workato recipe, Novade's choice) turns it into whatever the permit needs. Say It Back never releases a permit: Novade's own workflow does.

## The ask, in one line

"When a supervisor decides Go or No-go for worker *k* of permit *P*, can a Novade-side endpoint take one signed JSON post (below), and either hold the permit's release until every worker on it has a Go, or attach the decision as evidence to the permit for the approver?"

## Route A (ask for this first): Novade receives the native record

No field map: Novade's receiver takes `docs/EPERMIT_ADAPTER.md`'s decision record as it is, verifies the signature, and maps it on its side. This keeps every rule of that contract (signature, key, ordering) in one place.

```bash
SIB_AUTH_MODE=firebase            # the link needs accounts (security fixes A, H1): a person stands behind each decision
SIB_OUTBOX=true                   # store, retry and show every delivery
SIB_PTW_URL=https://<tenant>.novade-integration.example/say-it-back/decisions   # [A1] the endpoint Novade gives us
SIB_PTW_TOKEN=<from Secret Manager>                                              # [A2] a static bearer token Novade issues
SIB_WEBHOOK_SECRET=<from Secret Manager>                                         # the HMAC key, shared with Novade
```

## Route B: Novade's own field names (`SIB_PTW_FIELD_MAP`)

If Novade's receiver wants its own names, the generic adapter builds them. The names on the left are **assumed** [A3]; the sources on the right are the record's fields. This map was checked with the backend's own `parse_field_map` and `map_record` (build note 37):

```json
{"externalId": "briefingId", "requestId": "$idempotencyKey", "source": {"const": "say-it-back"},
 "permit.number": "permit.ref", "permit.crewSize": "permit.crewSize", "permit.workerSlot": "permit.slot",
 "check.result": {"from": "decision.value", "map": {"go": "GO", "no_go": "NO_GO"}, "default": "UNKNOWN"},
 "check.decidedAt": "decidedAt", "check.rounds": "rounds",
 "check.openSteps": "decision.openStepIds", "check.openHazards": "decision.openHazardIds",
 "check.sampleAnswers": "sampleAnswers", "check.sop.id": "sop.id", "check.sop.version": "sop.version",
 "evidence.recordHash": "recordHash", "evidence.promptVersion": "promptVersion"}
```

| Say It Back field | Novade-side field (assumed) | Why |
|---|---|---|
| `permit.ref` | `permit.number` [A4] | the permit the worker is on; compare case-insensitively, as typed by the supervisor |
| `permit.slot`, `permit.crewSize` | `permit.workerSlot`, `permit.crewSize` [A5] | one decision per worker; the permit waits for a Go in every slot. A worker is never named |
| `decision.value` | `check.result`: `GO` or `NO_GO` [A6] | the supervisor's decision, never the AI's; there is no "passed" |
| `decision.openStepIds`, `decision.openHazardIds` | `check.openSteps`, `check.openHazards` | a Go with open steps carries the supervisor's reason in Say It Back's own record |
| `sampleAnswers` | `check.sampleAnswers` | non-empty means an evaluator used stored synthetic answers: Novade must never release a real permit on it |
| `recordHash` | `evidence.recordHash` | anchors the hash chain outside Say It Back; anyone can check it later against `GET /api/briefings/{id}/verify` |
| `decision.reason`, `decision.by` | **not mapped** | free text that could name a worker; the map is an allow-list, so it never reaches Novade |

For the sample record in `docs/EPERMIT_ADAPTER.md` (a Go with step `s4` open), the body is:

```json
{"externalId": "b_k3j9x2m4p7qa", "requestId": "sib-b_k3j9x2m4p7qa-6f1c2a9b0d3e4f58", "source": "say-it-back",
 "permit": {"number": "PTW-2026/114", "crewSize": 3, "workerSlot": 2},
 "check": {"result": "GO", "decidedAt": "2026-10-17T09:00:00.000Z", "rounds": 2, "openSteps": ["s4"], "openHazards": [],
           "sampleAnswers": [], "sop": {"id": "SOP-LF-03", "version": "v2"}},
 "evidence": {"recordHash": "6f1c2a9b0d3e4f58…", "promptVersion": "2026-10-16.12"}}
```

## The request (both routes)

```
POST <SIB_PTW_URL>
Content-Type: application/json
Idempotency-Key: sib-b_k3j9x2m4p7qa-6f1c2a9b0d3e4f58
X-SIB-Timestamp: 1792000000
X-SIB-Signature: sha256=<hex HMAC-SHA256 of "<timestamp>.<raw body>">
Authorization: Bearer <SIB_PTW_TOKEN>
```

Novade's receiver verifies the signature on the raw bytes before parsing, refuses a timestamp more than 300 s off, checks that the key is `sib-<briefingId>-<first 16 hex of recordHash>` of the body, and keeps accepted keys for at least 7 days (`docs/EPERMIT_ADAPTER.md`, "Verifying the signature" and "The idempotency key").

## Answers and retries

| Novade answers | Say It Back does | The record shows |
|---|---|---|
| 2xx within `SIB_WEBHOOK_TIMEOUT_S` (5 s) | delivered | "Sent to the permit system" |
| 409 `{"error": {"code": "duplicate"}}` (the key again) [A7] | delivered | "Sent to the permit system" |
| 408, 425, 429, 5xx, a timeout, a dropped connection | retries with the same key and body, re-signed: 30 s, then doubling to 1 h, 8 tries (about 64 minutes) | "Not delivered yet: retrying" |
| any other 4xx (a bad signature 401, an unknown permit 422 [A8], a crew size that does not match 409) | never retries | "Not delivered to the permit system. Tell the permit office." |

Delivery is at least once and not in order: per `(permit, slot)`, Novade keeps the decision with the latest `decidedAt` (a re-brief of the same worker is a new briefing) [A9]. Novade should answer first and do slow work after, inside 5 s.

## Assumptions (each to be replaced by Novade's documentation)

- **[A1]** Novade gives a tenant-specific https endpoint for this post (custom integration or a Workato recipe trigger). The `.example` host above is a placeholder.
- **[A2]** A static bearer token is acceptable. If Novade requires OAuth 2 client credentials or mutual TLS, Say It Back needs one more adapter (`docs/EPERMIT_ADAPTER.md`, "Not here yet").
- **[A3]** Novade accepts our field names, or names its own and we change only the map's left side.
- **[A4]** The supervisor types Novade's own permit number into Say It Back's permit field (1 to 32 of `A-Z a-z 0-9 . _ / -`); a longer or other format needs the permit-link rule widened first.
- **[A5]** Novade can hold a permit until every listed worker has a Go, or at least show the per-worker decisions to the approver. If it cannot, the post is evidence only, and the release stays a person's act in Novade.
- **[A6]** `GO` and `NO_GO` are acceptable values; a checklist or status field may want others, which only the map's `map` table changes.
- **[A7]** Novade de-duplicates on `Idempotency-Key` (or `requestId` in the body) and answers 2xx or 409 `duplicate` for a repeat.
- **[A8]** An unknown or closed permit is a 4xx that a retry cannot fix; a person then follows up from the Say It Back record.
- **[A9]** Novade's receiver can order by `decidedAt` per permit and slot.

## Before any pilot

- A data processing agreement covering the post (permit number, slot, step ids, verdict, hashes; no transcript, audio or name), and where Novade stores it.
- A sandbox tenant: run the reference stub's tests' cases (signature, wrong key, duplicate, late older decision, crew mismatch) against Novade's receiver.
- An account-backed Say It Back deployment (`SIB_AUTH_MODE=firebase`); `deploy/02` deploys device mode only, so this is not the judging deployment.

## Other Singapore ePTW vendors

- **Hubble** offers "paperless PTW/ePTW" with multi-level approval routing and a separate toolbox-meeting module, and lists ePTW as a Productivity Solutions Grant pre-approved solution ([Hubble, Safety](https://hubble.build/safety-management-system)). We found no public permit API for it, so the same receiver-side proposal applies.
- Other vendors in IMDA's e-PTW category can be checked the same way: the IMDA guide prefers, but does not require, an API for sharing information with external platforms.
