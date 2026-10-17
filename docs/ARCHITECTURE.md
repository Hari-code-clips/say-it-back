# Say It Back — Architecture (v0.2, 13 Oct 2026, Google-native)

Before a migrant worker starts a new or changed task, the supervisor's instruction is spoken to them in their own language. The worker explains back, out loud, what they will do. Gemini checks the answer against the task's critical steps and shows the supervisor, in the supervisor's language, which step was missed. The supervisor decides whether work starts. The AI informs the decision; it never makes it.

v0.2 makes the build Google-native end to end. ADK runs every agent, including the live voice briefing; only turn-mode TTS is a plain google-genai call, because it needs no agent. In the cloud all Gemini traffic goes through Gemini Enterprise Agent Platform (formerly Vertex AI). Changes from v0.1 are listed at the end.

## System

```
Supervisor's phone (React web app on Firebase Hosting)
 ├─ HTTPS /api/**  ──(straight to the Cloud Run URL, X-SIB-Device)──▶  Cloud Run "say-it-back-api"  (FastAPI + one ADK 2.11 agent package)
 └─ WSS  /api/live/... ──(straight to the Cloud Run URL)──▶ same service
                                             │
       ADK agents ───────────────────────────┤  extract steps · write script · back-translate · re-explain · hazard report
       (one Runner + App per phase)          │  check (ADK Workflow): blind transcriber → (judge A ‖ judge B on a 2nd model) → join → guard (code)
                                             │  briefer: run_live() bidi-streaming ⇄ Gemini Live API (gemini-3.8-live)
       google-genai (no agent needed) ───────┤  TTS for turn mode (gemini-3.8-flash-tts)
                                             ├─ Firestore: briefing records (hash-chained events) and the state machine
                                             ├─ Cloud Trace: ADK OpenTelemetry spans        (SIB_TRACE_TO_CLOUD)
                                             ├─ BigQuery: ADK Agent Analytics plugin, content redacted (SIB_BQ_DATASET)
                                             └─ Webhooks (SIB_WEBHOOK_URL, up to 3): Google Chat text, or the signed JSON
                                                record to a permit-to-work system (integrations/ptw-stub, Cloud Run)

Gemini backend: Agent Platform with the Cloud Run service account in the cloud (trial credit, no API key);
Gemini Developer API key on a laptop. The same code serves both (google-genai / ADK env switch).
```

## Built on Google

| Google product | Role in Say It Back | Status (13 Oct) |
|---|---|---|
| Gemini 3.8 Flash | Extract steps, write script, back-translate, blind-transcribe, two judges, re-explain | Verified by probe (Developer API) |
| Gemini 3.8 Live | Speaks the approved script in the worker's language and listens | Verified by probe, raw and through ADK `run_live` |
| Gemini 3.8 Flash TTS | Turn-mode voice; synthetic evaluation set | Verified by probe |
| ADK 2.11 (Python) | Every agent; the check as an ADK 2 `Workflow` graph (fan-out judges, `JoinNode`, guard `FunctionNode`); Live through `run_live`; App with plugins; `adk web` dev UI over the same agents | `run_live` and HITL verified by probe |
| Gemini Enterprise Agent Platform | Gemini backend in the cloud on the service account | Verify in the hackathon project (Live: US/EU endpoints only) |
| Cloud Run | Hosts the ADK service, REST plus WebSocket | Deploy pending |
| Firebase Hosting | Serves the web app (static files only, no `/api` rewrite); deploys the deny-all Firestore client rules | Deploy pending |
| Firestore | Briefing records | Fake-tested; deploy pending |
| Cloud Trace | Per-agent spans and latency through ADK's OpenTelemetry | Env-gated |
| BigQuery | Agent event analytics through ADK's plugin; transcripts and audio redacted | Env-gated |
| Google Chat | Go/No-go decisions posted to the site's space by incoming webhook | Env-gated |
| Secret Manager | Only if a Developer API key is still needed in the cloud (e.g. TTS) | Conditional |
| Cloud Build, Artifact Registry | Used by `gcloud run deploy --source` | Deploy pending |
| Google Fonts, Material Design 3 | Noto for every script, Material Symbols icons, M3 colour tokens | Web build |

## The flow (one briefing)

1. **Instruction.** The supervisor picks site, task and languages, then speaks or types the instruction in the site language. Speech is transcribed by an ADK agent (Flash) and shown for editing.
2. **Critical steps.** The extractor agent reads the instruction against the task's SOP and returns atomic critical steps, each with its hazard and its essential elements. Steps found only in the SOP are tagged `sop` ("you didn't say this"); instruction-vs-SOP conflicts are listed. The supervisor edits and **confirms** (human gate 1). Nothing is spoken before this.
3. **Script.** The scripter agent writes the worker-language instruction (short sentences, explicit negations, the everyday word a worker on site says for each object and action: a native word when one is in use, a borrowed word only when that is the spoken word, never an English technical term spelled letter for letter in the worker's script; `PROMPT_VERSION` .12) and 2–3 open questions that don't contain the answer's key words. A **separate** back-translator agent renders both into the site language, so the supervisor sees what the worker will hear. Code checks that every confirmed step is delivered (`stepMap`) and asked about. The supervisor **approves** the script (API v0.4, endpoint 23); until then the server issues no Live ticket, speaks no TTS and runs no check (409 `script_not_approved`).
4. **Briefing.** Live mode: the browser opens a WebSocket to the backend with a single-use ticket. The backend runs the ADK **briefer** agent with `Runner.run_live()`. Its instruction is built on the server from the round's script and the language lock, so the browser can't change it. The browser streams mic audio only during answer windows and plays the model's audio. The briefer reads and asks; it never sees the steps, never judges, never hints. The backend keeps what Live said and heard per segment. Turn mode (fallback): TTS audio for each segment. In both modes the browser records each answer locally as a 16 kHz WAV.
5. **Check.** One request runs the ADK check workflow:
   - a **blind transcriber** (steps withheld) writes verbatim transcripts in the original script, with a site-language translation;
   - two judges run in parallel (a fan-out in the ADK 2 `Workflow` graph, then a `JoinNode`): judge A on the audio plus the transcript, judge B on the transcript only;
   - a **guard** `FunctionNode` (pure code, no model) applies the guard rules (API.md) and writes the final ratings.

   A step is `covered` only if both judges agree, the quote is really in the transcript, the language is right and confidence is high. Everything uncertain becomes `unclear`: ask again. Whenever Live spoke in the round (live mode, or a live session before a turn-mode fallback), guard rule 8 then compares what Live actually said with the approved script (similarity, script, negations sentence by sentence, the numbers in order, and whether each reply stayed a short, neutral thanks), and a step whose delivery fails becomes `unclear` too. A stored synthetic sample answer, offered to evaluators, never counts as the worker's: a step it alone covered is open at the decision. Since 16 Oct the two demos store one per question of each round (endpoint 24), and the browser gives each question the stored answer that shares the most steps with it, so an evaluator who speaks no worker language can run the whole loop.
6. **Re-explain.** For open steps the supervisor re-explains, in their own words or with a generated focused re-explanation. The app then asks new questions about those steps only. After 3 rounds it suggests "verify by demonstration".
7. **Decision.** The supervisor taps Go or No-go (human gate 2). Go with open steps requires a typed reason. At any point after the steps are confirmed the worker can report a hazard (by voice, transcribed verbatim and translated, or by a tap); Go is refused while any hazard is unacknowledged. The record says what was checked and what was decided, and it never scores the worker. Every change appends a hash-chained event, so an edit to the stored record is detectable (verify, endpoint 25). The decision can be posted to the site's Google Chat space and, signed, to a permit-to-work system, which releases or holds a permit and keeps the record's hash outside the store.

## ADK structure

- `backend/sayitback/agents/` is an ADK agents directory. Each phase is a folder exporting `root_agent`: `extract_steps`, `write_script`, `back_translate`, `transcribe_instruction`, `check_answer`, `re_explain`, `briefer_live` and (v0.4) `hazard_report`. `uv run adk web sayitback/agents` opens Google's dev UI over the same agents. Event traces, the agent graph and live voice there are useful for development and for the demo video. If state is empty, every agent loads the catalog's lead demo task (`lifting-zone`, the `sg-lead` demo script; v0.5.1).
- The API runs each phase with `Runner(app=App(name, root_agent, plugins), session_service=InMemorySessionService())`. The Runner exists only for the request, and the briefing state lives in the store. Audio stays out of any persistent ADK session (privacy), so ADK sessions are deliberately in-memory.
- Instructions are callables (InstructionProvider) that read session state, so JSON braces in prompts are never template-substituted. Output schemas give typed results, and judge B uses `include_contents="none"` so audio never reaches it.
- Plugins: an always-on audit plugin (model ids, timings and call counts per phase, no content), and Google's BigQuery Agent Analytics plugin when `SIB_BQ_DATASET` is set, with a content formatter that drops transcripts and audio.
- The production path for the human gates is an ADK 2.x `Workflow` with `RequestInput` nodes on Agent Engine Sessions (verified offline in probes). The prototype enforces the gates with the store's state machine instead, because a paused workflow on in-memory sessions dies when the instance is recycled.

## Design decisions

| Decision | Why |
|---|---|
| ADK runs every agent, including Live through `run_live` (turn-mode TTS is a plain google-genai call) | One agent framework end to end, as Google's own guidance recommends; one place for instructions, schemas, callbacks, plugins and tracing; the dev UI shows the real agents. |
| Live is relayed by the backend, not opened from the browser | In the cloud all Gemini traffic, Live included, runs on Agent Platform with the service account and the trial credit. No API key is deployed, and no free-tier rate limit hits the judged demo. The lock is server-side by construction, and the server keeps the transcripts. The cost is one extra hop and a WebSocket that goes straight to the Cloud Run URL (Hosting can't proxy it). Browser-direct Live with config-locked ephemeral credentials was verified in probes, but those credentials exist only on the Developer API, so it isn't built. |
| No accounts: each browser holds a random device key that owns its briefings | A public demo needs visitors kept apart without a sign-up step. The key scopes reads, writes, the list and the export to one browser; its ticket alone opens the Live socket. The production path is Firebase Authentication or Identity Platform for the org's users, plus App Check against scripted clients. |
| The browser calls Cloud Run directly, not through a Hosting rewrite | Per-address limits read `X-Forwarded-For` from the right, so every request must arrive through the same hops; the WebSocket already goes direct. It also removes Hosting's 60 s cut on long requests. |
| Live is voice only; judging is a separate Flash workflow | Live has no response schema. Separating the judge keeps it auditable and lets it run twice. |
| Blind transcription before judging | A transcriber that knows the expected steps can "hear" them. Withholding the steps keeps the evidence independent of the rubric. |
| Two judge passes, a split is "Ask again", plus a code guard node | Asymmetric safety: a false "covered" is the one error that matters, so agreement is required to pass and any doubt abstains. Judges that disagree give `unclear` (a contradiction in either stays `contradicted`), so neither judge can overrule the other into a pass, or into a "Missed" the other did not see: "missed" means the answer said nothing about the step, and a judge that heard the worker touch it is not outvoted by one that did not (v0.5.3). The guard is a `FunctionNode` in the same ADK 2 `Workflow` graph as the judges, so it appears in traces and in the `adk web` graph like the model steps. |
| Judge B on a second model (`gemini-3.1-flash-lite` by default) | Two models make the judges' mistakes less correlated. A split is never a pass, so a weaker second judge can never produce a pass: when it disagrees the step reads "Ask again" (or "Wrong" if either judge found a contradiction). |
| Script approval and hazards are server-side gates | The approval (endpoint 23) and an open hazard (Go is 409 `hazard_open`) are enforced by the state machine over the store, like the other human gates, not by the browser. |
| A hash-chained record instead of an append-only store | Each change appends an event in the same atomic update, and verify re-derives every bound digest from the stored record, so an edit is detectable on Firestore without another product. The decision's record hash goes to the webhooks, outside the store, for a rewrite of the whole chain. |
| The delivery check counts negations and numbers | Live can't be forced to read verbatim, and similarity alone never catches a dropped "not" (a dropped Tamil `இல்லை` still scores 0.95). Per-language markers from the catalog catch it in code, and the affected steps become "Ask again". |
| Back-translation by a separate agent | Guards the forward translation, not just the judgement: the supervisor sees what the worker actually hears. |
| Language lock by instruction, checked by Unicode script | The Live API ignores `language_code`. An instruction lock held for Odia in probes, and script detection catches Odia drifting to Hindi. |
| WAV from an AudioWorklet, not MediaRecorder | One format on Chrome, Safari and Firefox. The same PCM feeds Live and the judge. |
| Stateless phases with state in Firestore; human gates enforced by the state machine | It is impossible to brief before steps are confirmed, or to record without a human decision, and this survives Cloud Run instance recycling. |
| No worker identity, no scores, audio not kept by default | The tool checks a briefing, not a person. |

## Repository layout

```
say-it-back/
  backend/   Python 3.13 (uv): FastAPI app, ADK agents (sayitback/agents), store, tests  → Cloud Run
  web/       Vite + React 19 + TypeScript + Tailwind v4, Material 3 tokens            → Firebase Hosting
  eval/      labelled synthetic test set, generators, runner, reports
  docs/      ARCHITECTURE.md, API.md
  deploy/    gcloud / firebase scripts (run only with the owner's go-ahead)
```

## Configuration (environment variables only; no dotenv files)

| Variable | Default | Meaning |
|---|---|---|
| `GOOGLE_GENAI_USE_ENTERPRISE` | unset | `true` = Gemini through Agent Platform (`GOOGLE_GENAI_USE_VERTEXAI` is the legacy name) |
| `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION` | — / `global` | Agent Platform project and location for Flash and TTS |
| `SIB_LIVE_LOCATION` | `us-central1` | Agent Platform location for Live (Live has US/EU endpoints only) |
| `SIB_LIVE_BACKEND` / `SIB_TTS_BACKEND` | follow the global switch | `developer-api` or `agent-platform`, per model kind, if one model isn't on Agent Platform |
| `GOOGLE_API_KEY` | — | Gemini Developer API key (laptop; in the cloud only if a `*_BACKEND` is `developer-api`, from Secret Manager). Never sent to the browser. |
| `SIB_FLASH_MODEL` | `gemini-3.8-flash` | extract, script, back-translate, transcribe, judge, re-explain |
| `SIB_LIVE_MODEL` | `gemini-3.8-live` | voice briefing (the Agent Platform model id may differ: check it at deploy) |
| `SIB_TTS_MODEL` | `gemini-3.8-flash-tts` | turn-based voice |
| `SIB_TTS_LOCATION` | empty (= `GOOGLE_CLOUD_LOCATION`) | Agent Platform location for TTS only (v0.5), if TTS is not served on `global` |
| `SIB_LIVE_VOICE` / `SIB_TTS_VOICE` | `Kore` / `Kore` | prebuilt voices |
| `SIB_JUDGE_PASSES` | `2` | 1 = judge A only |
| `SIB_JUDGE_B_MODEL` | `gemini-3.1-flash-lite` | judge B's model (a Gemini 3.x model); empty = `SIB_FLASH_MODEL` |
| `SIB_FLASH_FALLBACK_MODEL` | empty | asked instead of `SIB_FLASH_MODEL` for one call when that model answers 429 on every retry (Agent Platform's shared pool out of capacity); a Gemini 3.x model; empty = none. Judge B has no fallback. The deployment sets `gemini-3.7-flash` (17 Oct) |
| `SIB_THINKING_<AGENT>` | per agent (`settings.py`) | `low`/`medium`/`high` for each Flash agent, `HAZARD_REPORT` (default `low`) included |
| `SIB_COVERED_MIN_CONFIDENCE` | `0.75` | below this, `covered` becomes `unclear` |
| `SIB_STORE` | `local` | `local` (JSON files in `backend/.data/`) or `firestore` |
| `SIB_ALLOWED_ORIGINS` | `http://localhost:5173` | CORS and WebSocket Origin check, comma-separated |
| `SIB_PUBLIC_WS_BASE` | empty | e.g. `wss://say-it-back-api-xxxx.a.run.app`; empty = same origin (local dev through the Vite proxy) |
| `SIB_TRACE_TO_CLOUD` | `false` | export ADK OpenTelemetry spans to Cloud Trace |
| `K_SERVICE` / `K_REVISION` | set by Cloud Run; else `say-it-back-api` / the package version | `serviceContext.service` and `version` of each Cloud Error Reporting line (16 Oct, ops): an unhandled error is one JSON line on stderr with its stack frames and type, never its message (`observability.report_error`) |
| `DATA_REGION` (`deploy/config.sh`) | `in` | deploy-time: `in` = `asia-south1`, `sg` = `asia-southeast1` for Cloud Run and Firestore (16 Oct, ops). Gemini stays on `global` and Live on `SIB_LIVE_LOCATION`: data at rest stays in the region, model processing does not |
| `RETENTION_DAYS`, `ALERT_EMAIL` (`deploy/config.sh`) | `90`, empty | deploy-time (16 Oct, ops): `RETENTION_DAYS` sets `SIB_RETENTION_DAYS`, and step 1 keeps the Firestore TTL policy on `briefings.expireAt` (off at 0); `ALERT_EMAIL` turns on step 5's uptime and 5xx email alerts |
| `SIB_BQ_DATASET` | empty | `project.dataset` for the ADK BigQuery Agent Analytics plugin (content redacted) |
| `SIB_WEBHOOK_URL` | empty | up to 3 comma-separated URLs; each decided briefing is POSTed to all; a `chat.googleapis.com` URL gets a Google Chat message, any other the JSON record |
| `SIB_WEBHOOK_TIMEOUT_S` | `5.0` | v0.5, above 0 and at most 10: the decision waits at most this long, in total, for every webhook (sent at once); a slow or failing receiver never fails the decision |
| `SIB_WEBHOOK_SECRET` | empty | HMAC-SHA256 key that signs each JSON post (`X-SIB-Timestamp`, `X-SIB-Signature`); empty = unsigned. From Secret Manager in the cloud |
| `SIB_OUTBOX` | `false` | pilot e-permit link (docs/EPERMIT_ADAPTER.md): store every delivery in `outbox/{briefingId}`, retry it with backoff, show `delivery` on the record. Needs `SIB_AUTH_MODE=firebase`: in device mode the service refuses to start with it (security fixes A, H1) |
| `SIB_OUTBOX_MAX_ATTEMPTS` | `8` | 1-50: tries before a delivery is `failed` |
| `SIB_OUTBOX_BACKOFF_S` | `30` | the wait after the first failed try; doubles each time, at most `SIB_OUTBOX_MAX_BACKOFF_S` |
| `SIB_OUTBOX_MAX_BACKOFF_S` | `3600` | the longest wait between tries |
| `SIB_OUTBOX_RETRY_BATCH` | `20` | 1-100: briefings one `POST /admin/outbox/retry` works through |
| `SIB_OUTBOX_TOKEN` | empty | bearer token for `POST /admin/outbox/retry` (Cloud Scheduler); empty = the route answers 404. Secret Manager |
| `SIB_PTW_URL` | empty | the site's e-permit endpoint: one more target besides `SIB_WEBHOOK_URL`; never logged (only its host). Needs `SIB_AUTH_MODE=firebase`, as `SIB_OUTBOX` does |
| `SIB_PTW_FIELD_MAP` | empty | JSON field map for the `generic` adapter (vendor field → record path, `$idempotencyKey`, `{const}` or `{from, map, default}`); empty = the native record; malformed stops start-up |
| `SIB_PTW_TOKEN` | empty | sent as `Authorization: Bearer` to `SIB_PTW_URL` only, which must then be https (localhost excepted); never logged. Secret Manager |
| `SIB_EVAL_DIR` | `../eval` | test set and reports for `/api/eval/*` |
| `SIB_RATE_LIMIT_PER_MIN` | `30` | per-address limit on the Gemini-backed endpoints and the free writes (create, edit, hazard tap, hazard acknowledgement, script approval) |
| `SIB_DAILY_GEMINI_CALLS` | `300` | global Gemini calls per UTC day, shared by all instances through the store; over it, 429 `daily_limit`. `deploy/config.sh` sets 600 for the judging window |
| `SIB_MAX_SENTENCES_PER_STEP` | `3` | most script sentences per step, and 3 times the round's steps in all; a script over it is retried once, then 502 `script_incomplete` |
| `SIB_MAX_LINE_CHARS` | `160` | most characters in any spoken line (sentence, question, closing); same retry, then 502 |
| `SIB_MAX_OUTPUT_TOKENS` | `8192` | `max_output_tokens` on every Flash call, thinking included; a reply cut off at it is 502 `upstream_error`. Not sent on TTS calls: Agent Platform's TTS refuses it (v0.5); TTS is bounded by the script's line limits |
| `SIB_DAILY_CALLS_PER_IP` | `100` | each client address's share of the daily cap, same costs; `0` = off. `deploy/config.sh` sets 300 |
| `SIB_TRUSTED_PROXY_HOPS` | `1` | which `X-Forwarded-For` entry, counted from the right, is the client address |
| `SIB_MAX_SOCKETS_PER_IP` | `4` | open Live sockets per client address on one instance |
| `SIB_API_DOCS` | `false` | serve `/api/docs` and `/api/openapi.json` (local development only) |
| `SIB_CALL_TIMEOUT_S` | `40` | v0.5.1: each Flash or Flash-Lite call attempt is cut off after this many seconds (never more than the phase timeout) and retried |
| `SIB_RETRY_ATTEMPTS` | `3` | attempts per model call on 429, 5xx or a cut-off attempt, with exponential backoff and jitter (range 1–5) |
| `SIB_REFUSAL_RETRIES` | `1` | extra calls after a reply the model's safety filter blocked (the block is not deterministic); 0 = never, at most 3 |
| `SIB_PHASE_TIMEOUT_S` / `SIB_REQUEST_TIMEOUT_S` | `110` / `120` | seconds per ADK phase and per chained `/api` call; the browser calls Cloud Run directly and waits 125 s |
| `SIB_IDEMPOTENCY_TTL_S` | `3600` | 2026-10-16, 0 to 86400: how long a check upload's `Idempotency-Key` keeps its judged round for a retry (`idempotency.py`, records `check_keys/{sha256}`); 0 ignores the header |
| `VITE_SW` (web build) | on | 2026-10-16: `0` builds the app without registering the offline shell's worker (`dist/sw.js` is still built) and removes one an earlier deploy installed |
| `SIB_DELIVERY_MIN_SIMILARITY` / `SIB_DELIVERY_MIN_SCRIPT_SHARE` | `0.8` / `0.7` | live mode: a segment below either is not `ok`, and its covered steps become `unclear` (guard rule 8) |
| `SIB_REPLY_MAX_CHARS` | `60` | live mode: a reply after an answer window longer than this is `reply_too_long` |
| `SIB_MAX_HAZARDS` | `5` | hazard reports per briefing |
| `VITE_API_BASE` (web build) | `/api` | API base URL; the Cloud Run service URL plus `/api` in production |
| `VITE_DEMO_VIDEO_URL` (web build) | empty | v0.5: an https link to the recorded demo video, shown on the landing page and once the daily limit is reached; empty shows nothing. A plain link, so the CSP is unchanged. `deploy/03` sets it from `DEMO_VIDEO_URL` |
| `SIB_KEEP_AUDIO` | `false` | keep answer and hazard-report audio (consented demos only) |
| `SIB_REQUIRE_CONSENT` | `true` | privacy (API.md Deviations 2026-10-16, build-notes/34-privacy.md): a round with no recorded choice is checked (13) only when `meta.sampleAnswers` lists every question, and gets a Live ticket (11) only with `{samplesOnly: true}`; else 409 `consent_required` (security fixes B, build-notes/36); a declined round is refused in both modes (`consent_declined`). The `Settings` dataclass default is `false` (tests, hand-built settings) |
| `SIB_RETENTION_DAYS` | `90` | privacy: each stored briefing carries `expireAt` (creation + this many days; a Firestore Timestamp, for the TTL policy on `briefings.expireAt`); the local store prunes expired records on read; `0` = keep; at most 3650 |
| `SIB_AUTH_MODE` | `device` | pilot accounts (API.md Deviations 2026-10-16, build-notes/34): `device` = anonymous device keys, as before; `firebase` = a Firebase ID token on every call, org records, roles per site |
| `SIB_AUTH_PROJECT` | `GOOGLE_CLOUD_PROJECT` | firebase mode: the Firebase project id the ID token's `aud` must name; required in that mode |
| `SIB_AUTH_ORG` | empty | firebase mode: the deployment's one org id (`[a-z0-9][a-z0-9_-]{0,39}`); required in that mode |
| `SIB_AUTH_ALLOWED_DOMAINS` | empty | firebase mode: comma list of email domains allowed to sign in (verified emails only); empty = any |
| `SIB_BOOTSTRAP_ADMINS` | empty | firebase mode: comma list of emails made org admin at a new member's first verified sign-in, only while the org has no org admin (build-notes/36) |
| `VITE_AUTH_MODE` (web build) | empty | `firebase` builds the sign-in gate, the token header and the Team screen, and widens the CSP for Firebase Auth; anything else is today's build |
| `VITE_FIREBASE_API_KEY` / `VITE_FIREBASE_AUTH_DOMAIN` / `VITE_FIREBASE_PROJECT_ID` (web build) | empty | firebase builds: the Firebase web config (public, not secrets); the auth domain also goes into the CSP's `frame-src` |

## Data regions: where each model and store processes or keeps data (17 Oct 2026)

Three things are kept apart here (review P0-13): what the deployment **configures** (`deploy/config.sh` and `deploy/02_deploy_backend.sh`, the source of truth), what Google **offers** for each model (its Agent Platform model page, read on 17 Oct 2026), and what the team **measured** (`findings.md`, 15 Oct). Every row is the judging deployment (device mode, `DATA_REGION=in`). Which personal data goes through each row, how long it stays and how it is deleted: `docs/PRIVACY_DATA_FLOW.md`.

**Models** (all through Agent Platform with the Cloud Run service account; the ids are pinned in `config.sh` and must be checked against the project at deploy).

| Model | Id · launch stage (Google) | Configured endpoint | What Google offers (model page, 17 Oct) | Measured by the team (15 Oct) | What it processes | Cross-border consequence |
|---|---|---|---|---|---|---|
| Gemini 3.8 Flash | `gemini-3.8-flash` · GA (released 2 Sep 2026) | `GOOGLE_CLOUD_LOCATION=global` | `global`, and the multi-regions `us` and `eu`; ML processing listed in `us` and `eu`; no Asia region listed. Google: the global endpoint "doesn't support data residency requirements" | `us-central1`, `asia-southeast1` and `asia-south1` answered 404 for this project; `global` answered | the supervisor's dictated instruction (audio), step extraction, the script and its back-translation, the worker's answer audio (blind transcriber, judge A), the re-explanation, a hazard report's audio | processed outside Singapore and India, in a location the global endpoint does not fix. Moving to `us` or `eu` would fix the location in the US or EU, not in Asia |
| Gemini 3.1 Flash-Lite (judge B) | `gemini-3.1-flash-lite` · GA (released 7 May 2026) | `global` (`SIB_JUDGE_B_MODEL`) | `global`, `us`, `eu`; ML processing in the US and Europe multi-regions | answered on `global` | the transcript and the steps only (no audio) | as Flash |
| Gemini 3.8 Live | `gemini-3.8-live` · GA (released 24 Sep 2026; retirement 25 Sep 2027 or later) | `SIB_LIVE_LOCATION=us-central1` | `us`, `eu` and `us-central1`; no `global`; ML processing in `us` and `eu` | answered in `us-central1` | live mode: the approved script spoken out, and the worker's microphone audio in each answer window, relayed by the backend | the worker's voice is processed in the United States. `eu` is offered and would keep it in the EU; neither is in Asia |
| Gemini 3.8 Flash TTS | `gemini-3.8-flash-tts` · **Preview** (released 28 Sep 2026; Pre-GA terms) | `SIB_TTS_LOCATION=global` | `global` only | `us-central1` does not serve it; `global` answers | turn mode: the approved script's text, turned into audio (no worker data) | script text only, outside Singapore and India. Preview: no GA commitment |

**Stores and services** (`REGION` is `asia-south1`, Mumbai, for `DATA_REGION=in`, or `asia-southeast1`, Singapore, for `sg`; the Firestore database's location is fixed when step 1 creates it).

| Store or service | Configured location | What it holds | Cross-border consequence |
|---|---|---|---|
| Cloud Run `say-it-back-api` | `REGION` | everything in a request, in memory: the answer audio is dropped after the check (`SIB_KEEP_AUDIO=false`), and ADK sessions are in memory | none at rest; the service is where the model calls above leave the region |
| Firestore `(default)` | `REGION` | briefing records (`briefings`, with `expireAt` for the TTL policy), the delivery outbox, the daily call counters (`gemini_calls`, and `gemini_calls_ip`: a SHA-256 of the day and the client address with its count), Live tickets, the SOP library, idempotency keys | at rest in `REGION` |
| Permit-to-work stub `say-it-back-ptw` (Cloud Run + Firestore) | `REGION` | from the signed decision record: the permit and slot, the open steps (id and text), the record hash, and the supervisor's optional `by` (kept, never shown or served); the reason arrives but is never stored; no transcript, no audio | none; a real e-permit system is wherever its vendor runs it |
| Google Chat (optional webhook) | the customer's Workspace | a text summary, the reason included | wherever the customer's Workspace keeps chat data |
| Cloud Logging, Error Reporting, Cloud Trace | Google's global location (defaults) | by design no transcript, audio, device key or client address in the app's own lines (tested); Cloud Run's platform request logs record the caller's address | log data may sit outside `REGION` |
| BigQuery (optional, off by default) | dataset created in `REGION` by step 1 | ADK analytics rows, content redacted | none at rest. Open: the backend's `SIB_BQ_LOCATION` defaults to `US` and step 2 does not set it |
| Firebase Hosting | Google's global CDN | the static web app; no user data | none |
| The supervisor's phone | the browser | the device key (`localStorage`), unsent answers (at most a day), the briefing draft (`sessionStorage`) | stays on the phone |

What follows for a deployer: Singapore's PDPA (section 26, the Transfer Limitation Obligation) allows a transfer abroad when the recipient is bound by legally enforceable obligations to a comparable standard of protection (law, contract or binding corporate rules); it does not require data to stay in Singapore. India's DPDP Act section 16 and Rule 15 restrict transfers only to countries the Central Government notifies, and are expected to apply from about May 2027. A site that uses Say It Back covers these transfers in its own review (`docs/PRIVACY_DATA_FLOW.md`); this table is not legal advice. Sources: Google's model pages for [3.8 Flash](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/3-8-flash), [3.1 Flash-Lite](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/3-1-flash-lite), [3.8 Live](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/3-8-live), [3.8 Flash TTS](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/3-8-flash-tts) and [locations](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/locations) (last updated 15 Oct 2026); [PDPC, the Transfer Limitation Obligation](https://www.pdpc.gov.sg/-/media/Files/PDPC/PDF-Files/Advisory-Guidelines/the-transfer-limitation-obligation---ch-19-(270717).pdf); [Bar & Bench on DPDP section 16 and Rule 15](https://www.barandbench.com/columns/the-dpdp-cross-border-transfer-rules-arent-live-yet-so-why-are-contracts-being-redrafted-as-if-they-are).

## Guardrails (enforced in code, not only in prompts)

- The tool never approves work; only the supervisor's POST records a decision. Go is refused while a worker's hazard report is unacknowledged.
- No prompt example comes from a tested domain: the judge and extractor examples are forklift traffic and chemical decanting, and a test fails if the prompts share a phrase with any eval answer or demo answer (v0.5).
- Nothing is spoken or judged before the supervisor approves the round's script: the live ticket, TTS, the Live socket and the check all refuse an unapproved round.
- `covered` is never emitted when the judges disagree, the quote isn't in the transcript, the answer is in the wrong language, there was no speech, or confidence is low, nor (rule 8, whenever Live spoke) when what Live said for the step's instruction, question or an earlier reply is not the approved script: a changed or moved negation, a changed number, low similarity, the wrong script, or a reply that is long or repeats the script's words. A step covered only by a stored sample answer is open at the decision (Go needs a reason), and the record and the webhook say which answers were samples.
- The briefer's context never contains steps, essentials or ratings (unit-tested). The browser can send only enumerated cues and audio, never instructions.
- No worker name, ID, score or history is stored. Audio, hazard reports included, is processed in memory and discarded unless `SIB_KEEP_AUDIO=true`. ADK sessions are in-memory, and analytics rows carry no transcript or audio. No hazard text or note reaches a log line, and the record chain holds only digests.
- The record is tamper-evident: every change appends a hash-chained event in the same atomic update, nothing else writes `events`, and verify recomputes the chain against the stored record, the transcripts, both judges' passes, the delivery check, `round.live` and the latest verdicts included. Webhook JSON posts are signed with a shared secret and carry the record hash; the URLs and the secret are never logged.
- Synthetic SOPs and tasks. The evaluation set is synthetic TTS unless marked `recorded` (consented volunteers only).

## Changes from v0.1

- Live moved from browser-direct (ephemeral Developer-API credential) to an ADK `run_live` relay on Cloud Run, so Live can run on Agent Platform. API.md endpoint 11 now returns a WebSocket ticket, and endpoint 20 is the WebSocket.
- Agent Platform is the cloud Gemini backend; ADK App plugins, Cloud Trace, BigQuery analytics and Google Chat were added (all env-gated); `adk web` works over the production agents.
