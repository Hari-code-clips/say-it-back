# Say It Back: backend

Python 3.13, FastAPI, Google ADK 2.11 and Gemini 3.8. One service serves the 25 endpoints of
[`docs/API.md`](../docs/API.md) (v0.4): REST for the briefing flow and a WebSocket that relays the live
voice briefing. Every agent, including the live voice, runs through ADK; only turn-mode TTS is a plain
google-genai call, because it needs no agent. The same code runs on the
Gemini Developer API (a laptop with an API key) and on Gemini Enterprise Agent Platform (Cloud Run
with its service account). See [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) for the design.

## Run

```bash
cd backend
uv sync                                   # creates .venv from uv.lock
export GOOGLE_API_KEY=...                 # Developer API on a laptop. Never commit it.
uv run uvicorn sayitback.main:app --port 8080
curl localhost:8080/api/health
```

The web app's Vite proxy (`/api`, including the WebSocket) points at port 8080. Briefing records go to
`backend/.data/` (gitignored) with `SIB_STORE=local`, the default.

Every route except health needs a device key (API v0.3), which a browser makes for itself:
`curl -H "X-SIB-Device: $(openssl rand -hex 16)" localhost:8080/api/catalog`. Use one key for a whole session:
a briefing belongs to the key that created it.

## Test

```bash
uv run ruff check .
uv run pytest -q          # offline: fake models, temp store, and a guard that blocks the network
```

The suite covers every guard rule, the state machine and its 409 paths, the catalog's public view, the
check Workflow's graph and what each node is sent, the HTTP API with the model layer replaced by fakes,
the Live relay (tickets, Origin, enumerated cues, each cue and answer window once, `round.live`) over
both a fake runner and ADK's real `Runner.run_live` with a fake Gemini Live connection, backend selection
for both platforms, the Google Chat payload, the audit plugin and the BigQuery formatter, the daily
Gemini cap (what each endpoint costs, the script retry's reservation, refusals, the UTC day, bursts
against the local store and a Firestore fake), and the cost bounds (the script limits, the output ceiling
on every Flash agent and on the wire, replies cut off at it, the usage lines). Since API v0.3 it also covers
the device key and the ownership of every briefing route, the client address and its limiter, the per-address
daily allowance (over the Firestore fake, shown to break deliberately naive versions), TTS bound to a round's
script, the Live socket limits, and `deploy/01` and `deploy/02` under a stub `gcloud`. Since API v0.4
(`tests/test_v04_*.py`) it also covers the script approval gate, hazard reports and the Go they block,
the record chain and verify (edits to a stored rating, step or decision found at the right event, on
the local store and the Firestore fake), the delivery check v2 and guard rule 8 (the dropped Tamil
negation), judge B on its own model, the signed webhooks and the permit-to-work stub over ASGI, the
sample answers and the eval items' reference text, and `deploy/02` and `deploy/04`. Nothing in it
calls Google. Every request in the tests is one browser: `tests/helpers.py` `api_client` sends a
device key, and `drive_to_round` and `seed_round` approve round 1's script unless told not to.

## The check workflow

`check_answer` (`sayitback/agents/check_answer/agent.py`) is an ADK 2.x `Workflow`, a graph of nodes. It
replaces the `SequentialAgent` and `ParallelAgent` that ADK 2.11 deprecates.

```
START → blind_transcriber → (judge_a, judge_b) → join_judges → guard
```

- `blind_transcriber`: an `LlmAgent` that gets the clips and the languages, never the steps. It runs with
  `include_contents="none"`: its input already is the user's clips, so they are sent once, not twice.
- `judge_a` (the clips plus the blind transcript) and `judge_b` (the transcript only) run in parallel; a tuple
  in the edge chain is the fan-out. Judge B has `include_contents="none"` and a `before_model_callback` that
  strips media, so no audio part can reach it. Each judge's request also carries the blind transcript as its
  node input, which is how a Workflow hands data on.
- Judge B runs on a second model, `SIB_JUDGE_B_MODEL` (default `gemini-3.1-flash-lite`; empty means the Flash
  model), so the two judges' mistakes correlate less. A split between the judges is `unclear` (rule 1, v0.5.3:
  a contradiction in either stands), so a weaker second judge can never produce a pass, only "Ask again" or
  "Wrong". Its thinking level still applies (a 3.x model). `round.modelIds.judge_b` is the id that model's API
  returned, and health's `models.judgeB` names the setting.
- `join_judges`: a `JoinNode`, it waits for both judges.
- `guard`: a `FunctionNode` with no model. It reads the judges' outputs from session state, calls the pure
  `guards.run_guards` (rules 1-7) and writes the state key `final`, where `run_check` reads it.
- `SIB_JUDGE_PASSES=1` gives `START → blind_transcriber → judge_a → guard`.

`run_check`, the per-phase timeout, the audit plugin and the BigQuery plugin work as before:
`adk_run.run_phase` runs the Workflow in the same `Runner(app=App(...))`. Guard rule 8 (the delivery rule)
is not a node: the round's check (`rounds.check`) applies it after `run_check` returns, in live mode only,
so `run_check` and `eval/` are unchanged (see "API v0.4" below).

## ADK dev UI

`sayitback/agents/` is an ADK agents directory, one folder per phase, each exporting `root_agent`:
`extract_steps`, `write_script`, `back_translate`, `transcribe_instruction`, `check_answer`,
`re_explain`, `briefer_live` and (v0.4) `hazard_report`.

```bash
uv run adk web sayitback/agents           # http://127.0.0.1:8000, lists the eight apps
curl localhost:8000/list-apps
```

With an empty session every agent loads the catalog's lead demo task (`lifting-zone`, demo script `sg-lead`,
v0.5.1), so `check_answer` runs on an audio file you attach in the chat. The API runs the same agents, each in its own
`Runner(app=App(name, root_agent, plugins), session_service=InMemorySessionService())`. The dev UI draws
`check_answer` as the graph above (`GET /dev/apps/check_answer/build_graph_image` returns it as DOT).

## Layout

```
sayitback/
  main.py            create_app(), error handlers, CORS; `app` for uvicorn
  api/               routes: briefings.py (4-11, 13, 14, 21-23, 25), misc.py (1-3, 12, 15),
                     evaluation.py (16-19, 24), live.py (20)
                     limits.py: request body caps enforced while the body streams (413)
                     uploads.py: the check's and the hazard report's multipart forms
                     device.py: the X-SIB-Device check (401), as middleware, before any body is read
  caller.py          Caller (owner hash and client address) and the device-key shape
  service.py rounds.py state_machine.py validators.py repo.py   use cases, 409 paths, input limits;
                     repo.py reads and writes only the owner's briefings
  agents/            ADK agents directory (one folder per phase, each with root_agent)
  guards.py guard_node.py delivery.py    guard rules 1-8 (pure), the guard node of the check Workflow, and
                     the delivery check (similarity, script, negations, numbers, replies)
  chain.py           the record's hash chain: canonical JSON, the events, verify (endpoint 25)
  pipeline.py        run_check(), the function eval/ imports
  phases.py          extract, script + back-translation, re-explain, supervisor speech-to-text,
                     a worker's spoken hazard report
  prompts.py         ALL prompt text, with PROMPT_VERSION
  backends.py        client kwargs per model kind: developer-api or agent-platform, from env
  live_relay.py live_frames.py live_order.py live_runner.py live_session.py live_transcripts.py   endpoint 20 and tickets
  live_idle.py       the Live socket's idle and first-cue clocks, and the open-sockets-per-address count
  observability.py   audit plugin, BigQuery plugin wiring and content formatter, Cloud Trace setup
  store/             local JSON store and Firestore store
  ratelimit.py       client_ip (the X-Forwarded-For rule) and the per-minute limiter
  tts.py webhook.py daily_cap.py wav.py catalog.py settings.py models.py evalset.py
  data/catalog.json
tests/               pytest; fakes.py (Gemini Flash incl. hazard_report and a second judge model, TTS),
                     fake_live.py (Live), fake_firestore.py,
                     wire_support.py (the real Gemini client over a mock transport), helpers.py
                     (api_client, seed_round), conftest.py
eval_data/           empty but for a placeholder; deploy/02_deploy_backend.sh stages the eval set here
Dockerfile .dockerignore .gcloudignore
```

## Configuration

Environment variables only. There are no dotenv files.

| Variable | Default | Meaning |
|---|---|---|
| `GOOGLE_GENAI_USE_ENTERPRISE` (legacy `GOOGLE_GENAI_USE_VERTEXAI`) | unset | `true`: Gemini through Agent Platform |
| `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` | unset, `global` | Agent Platform project and location for Flash and TTS |
| `SIB_LIVE_LOCATION` | `us-central1` | Agent Platform location for Live (US or EU endpoints only) |
| `SIB_LIVE_BACKEND`, `SIB_TTS_BACKEND` | follow the switch | `developer-api` or `agent-platform` for that model kind |
| `GOOGLE_API_KEY` | unset | Developer API key. Read by the SDK only, never sent to the browser or logged |
| `SIB_FLASH_MODEL`, `SIB_LIVE_MODEL`, `SIB_TTS_MODEL` | `gemini-3.8-flash`, `gemini-3.8-live`, `gemini-3.8-flash-tts` | model ids |
| `SIB_JUDGE_B_MODEL` | `gemini-3.1-flash-lite` | judge B's model, on the Flash backend; empty means `SIB_FLASH_MODEL`. Must be a Gemini 3.x model (thinking level) |
| `SIB_LIVE_VOICE`, `SIB_TTS_VOICE` | `Kore`, `Kore` | prebuilt voices |
| `SIB_JUDGE_PASSES` | `2` | 1 drops judge B |
| `SIB_COVERED_MIN_CONFIDENCE` | `0.75` | below this a `covered` becomes `unclear` |
| `SIB_THINKING_<AGENT>` | see `settings.py` | `low`, `medium` or `high` (Gemini 3.8 Flash has no `minimal`), for `EXTRACT_STEPS`, `WRITE_SCRIPT`, `BACK_TRANSLATE`, `TRANSCRIBE_INSTRUCTION`, `RE_EXPLAIN`, `BLIND_TRANSCRIBER`, `JUDGE_A`, `JUDGE_B`, `HAZARD_REPORT` (default `low`) |
| `SIB_STORE` | `local` | `local` or `firestore` |
| `SIB_ALLOWED_ORIGINS` | `http://localhost:5173` | CORS and the WebSocket Origin check |
| `SIB_PUBLIC_WS_BASE` | empty | for example `wss://say-it-back-api-xxxx.a.run.app`; empty gives a same-origin path |
| `SIB_LIVE_TURN_TAKING` | `manual` | `manual` (activity start and end) or `auto` (server VAD). `manual` falls back to `auto` if Live rejects it |
| `SIB_TRACE_TO_CLOUD` | `false` | export ADK OpenTelemetry spans to Cloud Trace (extra `trace`) |
| `SIB_BQ_DATASET`, `SIB_BQ_LOCATION` | empty, `US` | `project.dataset` for ADK's BigQuery Agent Analytics plugin (extra `bigquery`) |
| `SIB_WEBHOOK_URL` | empty | up to 3 comma-separated http(s) URLs; each decision is POSTed to all of them. `chat.googleapis.com` gets `{"text": ...}`, anything else the JSON record. More than 3, or an entry that is not a URL, and the service does not start (the error names the entry's position, never its text) |
| `SIB_WEBHOOK_SECRET` | empty | HMAC-SHA256 key: each JSON post carries `X-SIB-Timestamp` and `X-SIB-Signature`. Empty sends them unsigned. Never logged, not in the settings' repr |
| `SIB_WEBHOOK_TIMEOUT_S` | `5.0` | v0.5: the decision endpoint awaits every webhook, all at once, for at most this many seconds in total, then answers; a slow or failing receiver is logged (exception class only) and never fails the decision. Above 0 and at most 10 (the browser waits 20 s for a decision) |
| `SIB_TTS_LOCATION` | empty | v0.5: the Agent Platform location of the TTS client only; empty means `GOOGLE_CLOUD_LOCATION`. Set `us-central1` if `deploy/probe_models.sh` finds TTS missing on `global` |
| `SIB_EVAL_DIR` | `../eval` | test set and reports for `/api/eval/*`. The image sets `/app/eval`, where `deploy/02` stages `eval/testset` and `eval/reports/latest.json` |
| `SIB_RATE_LIMIT_PER_MIN` | `30` | per-client-address limit on the Gemini-backed endpoints (3, 8, 10, 11, 12, 13, 19, and 21 with audio) and on the free writes (4, 7, 21 as a tap, 22, 23), per instance. See Callers and ownership |
| `SIB_DAILY_GEMINI_CALLS` | `300` | global cap on Gemini calls per UTC day for those same endpoints, counted in the store so every instance shares it; an integer, 0 or more. Over it: 429 `daily_limit`. `0` refuses every call (a kill switch). See Daily cap |
| `SIB_DAILY_CALLS_PER_IP` | `100` | each client address's share of the day's cap, with the same costs, kept in the store under a SHA-256 of the day and the address. An integer, 0 or more; `0` turns it off. Over it: 429 `daily_limit`. See Daily cap |
| `SIB_TRUSTED_PROXY_HOPS` | `1` | which `X-Forwarded-For` entry, counted from the right, is the client address: `1` is the one Cloud Run's front end appends. An integer from 0 to 8; `0` means no proxy, so the header is not read. The service does not start with any other value. See Callers and ownership |
| `SIB_MAX_SOCKETS_PER_IP` | `4` | open Live sockets per client address on one instance. An integer, 1 or more. Over it: `error` `limit` and close 4429 |
| `SIB_API_DOCS` | `false` | `true` serves `/api/docs` and `/api/openapi.json` (local development; they need no device key). Off, both are 404 |
| `SIB_MAX_SENTENCES_PER_STEP` | `3` | most instruction sentences that may deliver one step in a round's scope, and 3 times the steps in the round in all. An integer, 1 or more. A script over it is retried once, then 502 `script_incomplete`. See Daily cap |
| `SIB_MAX_LINE_CHARS` | `160` | most characters in any spoken line: a sentence, a question or the closing. An integer, 1 or more. Same retry and 502 |
| `SIB_MAX_OUTPUT_TOKENS` | `8192` | output ceiling (`max_output_tokens`) on every Flash call and every TTS call, thinking tokens included; a reply that hits it is a 502 `upstream_error`. An integer, 1024 or more (the model's own limit is 65,536). Not applied to Live |
| `SIB_PHASE_TIMEOUT_S`, `SIB_REQUEST_TIMEOUT_S` | `110`, `120` | seconds allowed per ADK phase and per `/api` call that chains phases (then 503 `upstream_busy`). The browser calls Cloud Run directly, so Hosting's 60 s cut does not apply; the browser waits 125 s. Both above 0 |
| `SIB_DELIVERY_MIN_SIMILARITY` | `0.8` | live mode: a segment whose normalised similarity to the approved text is under this is `low_similarity`. Between 0 and 1 |
| `SIB_DELIVERY_MIN_SCRIPT_SHARE` | `0.7` | live mode: under this share of the speech's letters in the worker language's script is `wrong_script`. Between 0 and 1 |
| `SIB_REPLY_MAX_CHARS` | `60` | live mode: a `"<qid>.reply"` longer than this (normalised) is `reply_too_long`. At least 1 |
| `SIB_MAX_HAZARDS` | `5` | hazard reports per briefing; one more is 422 `too_many_hazards`. At least 1 |
| `SIB_KEEP_AUDIO` | `false` | write answer clips and hazard-report clips under `.data/audio/` (consented demos only) |

Request bodies are capped as they stream (`api/limits.py`): 3 MB + 64 KB for `/api/transcribe` and for a
hazard report (`/api/briefings/{id}/hazards`), 3 files of 3 MB + 64 KB for a check, 256 KB for every other
write. Over the cap is `413 payload_too_large`.

Gemini 3.x guidance is followed: no `temperature`, `top_p` or `top_k` is sent, and effort is set with
`thinking_level`. A 429 or 5xx from Gemini is retried once with a 2 s backoff, then the API answers
`503 upstream_busy` (an `error` frame on the socket).

### Choosing the Gemini backend

```bash
# Laptop: Developer API
export GOOGLE_API_KEY=...

# Cloud Run: Agent Platform on the service account, Live in a US region
export GOOGLE_GENAI_USE_ENTERPRISE=true GOOGLE_CLOUD_PROJECT=my-project
export GOOGLE_CLOUD_LOCATION=global SIB_LIVE_LOCATION=us-central1

# Mixed: everything on Agent Platform except TTS (needs GOOGLE_API_KEY in the cloud)
export SIB_TTS_BACKEND=developer-api
```

`GET /api/health` reports the backend each model kind uses, but it does not call any model, so a wrong model id
still reads healthy. Before a deploy, check every pinned id with one real call each (v0.5):

```bash
# Same environment as the service; prints OK or FAIL per model and exits 1 on any FAIL
uv run python -m sayitback.probe --also-location us-central1
```

`deploy/probe_models.sh` runs it with the values from `deploy/config.sh`.

## Callers and ownership

There are no accounts. Each browser makes a random device key once (22 to 64 characters of `[A-Za-z0-9_-]`, at
least 128 bits) and sends it as `X-SIB-Device` on every request except `GET /api/health` and the WebSocket. The
check is middleware (`api/device.py`), so no route can forget it: it runs before any body is read, and its 401
carries the CORS headers a cross-origin page needs to read it. A missing or malformed key (or two of them) is
401 `device_required`.

- **Ownership.** A briefing is stored with the SHA-256 of its creator's key as its owner, beside the record and
  outside the `Briefing` type, so it cannot appear in a response, and `Caller` prints as nothing, so it cannot
  reach a log. `repo.py` takes the owner on every read and write. Another key gets the 404 `not_found` an unknown
  id gets, with the same body, and the check runs inside the store's atomic update, so a write for another owner
  never happens. The list (5) and the CSV export (15) ask the store for the owner's briefings only (Firestore
  needs the composite index in Cloud Run below). A briefing with no owner, made before v0.3, belongs to no one.
  TTS (12) is the caller's own as well: it needs a briefing of the caller's and speaks only lines of that
  round's script.
- **WebSocket.** It takes no key. Its ticket, which only the briefing's owner can get (endpoint 11), is the
  capability: the ticket's record names the owner, and the relay reads and writes the briefing as that owner.
- **Client address.** `client_ip` (`ratelimit.py`) is the `X-Forwarded-For` entry `SIB_TRUSTED_PROXY_HOPS` from
  the right, else the socket peer. Cloud Run's front end appends the connecting address there, so the entries to
  its left are the caller's own words and are never read. An IPv6 address stands for its /64, since its owner can
  use any address in it; an IPv4-mapped one is the IPv4 address. The per-minute limit (`SIB_RATE_LIMIT_PER_MIN`,
  which also covers the free writes: create (4), edit (7), a hazard tap (21), a hazard
  acknowledgement (22) and a script approval (23)), the daily allowance and the Live socket count all
  key on it. The limiter keeps at most 10,000 addresses (idle ones are dropped as time passes, and the least
  recently used goes when the table is full), so a flood of addresses costs each request the same.
- **From where a browser may call.** The browser calls the Cloud Run URL directly. CORS allows `Content-Type` and
  `X-SIB-Device` from `SIB_ALLOWED_ORIGINS`, caches the preflight for 7200 s and exposes `Retry-After`. A
  cross-site form post cannot carry the custom header, so it is refused before its upload is parsed.
- **Smaller exposure.** `/api/docs` and `/api/openapi.json` exist only with `SIB_API_DOCS=true`. A 422 or upload
  error quotes at most 40 characters of a submitted value, and shows anything unprintable as `?`. The judge
  prompt fences the transcripts as untrusted evidence (`PROMPT_VERSION` 2026-10-14.6).
- **Not here.** There is still no login: anyone can make a key, and a key owns only what it creates. The
  production path is Firebase Authentication or Identity Platform plus App Check (docs/ARCHITECTURE.md). The
  deny-all Firestore client rules and the CSP headers belong to the web side (`firebase.json`).

## Daily cap

The service is public (`--allow-unauthenticated`), and the per-minute limit is in memory and per instance, so it
cannot bound total spend. `SIB_DAILY_GEMINI_CALLS` does: one global count of Gemini calls per UTC day, kept
in the store (the Firestore document `gemini_calls/<YYYYMMDD>`, or `.data/gemini_calls/` locally), so every
instance shares it and neither a restart nor scale-to-zero resets it. The code is `daily_cap.py`. The model
probe (`python -m sayitback.probe`) runs on a laptop with your own credentials and makes 4 or more real calls
outside this cap.

- A Gemini-backed request reserves its calls in one atomic step (a Firestore transaction; under the lock in
  the local store) after its validation and state checks and just before its first model call. A request that
  does not fit is refused whole: 429 `daily_limit`, `Retry-After` set to the seconds until 00:00 UTC, no model
  call. The per-minute limit answers first. Nothing is refunded.
- Each client address also has its own daily allowance, `SIB_DAILY_CALLS_PER_IP` (default 100, `0` is off), so
  one client cannot spend the count every visitor needs. It has the same costs and the same UTC day, and it is
  kept under a SHA-256 of the day and the address, never the address: the Firestore document
  `gemini_calls_ip/<digest>` (`.data/gemini_calls_ip/` locally), at most as many a day as the shared cap allows
  calls. It is reserved in the same step as the shared count, in one transaction over both documents (under the
  same lock locally). Either count refusing is a 429 `daily_limit`, and then neither moves. The address's own
  count is read and checked first, so a client over its allowance is refused without reading or locking the
  shared document that every other caller contends on. Only the shared cap's refusal logs the one WARNING a
  day; a client over its own allowance is routine and logs nothing. Everyone behind one NAT shares one address,
  so 100 calls (about ten briefings) a day is that room's share: raise it for an event.
- Costs, counted from the code: transcribe 1, extract 1 (0 for a briefing from a library version, `sopRef`,
  which reserves nothing; the SOP library routes make no model call), round 2 (script, back-translation) or 3 for a
  re-explain round with no supervisor note (its re-explain call comes first), plus 1 for each script retry,
  live ticket 4 (a weight for one Live session, not a call count; charged when the ticket is issued, not per
  socket), TTS 1 (0 on a cache hit), check and eval try 1 plus `SIB_JUDGE_PASSES`, a voice hazard report 1
  (the `hazard_report` agent; a tap is free). Approving a script (23), acknowledging a hazard (22), verify
  (25) and the sample answers (24) make no model call. `run_check` and
  `Tts.speak` take an optional `before_call` hook, and `phases.make_script` an optional `before_retry` one:
  that is where the API reserves.
- A script retry (the second `write_script` call, made when the first script fails a check) reserves 1 call
  just before it runs. If the cap refuses, the round is 429 `daily_limit` and no retry call is made, even when
  the first script was acceptable apart from having too few questions. The back-translation call already
  reserved for a round that then fails is not refunded.
- The live ticket's 4 prices a session that two rules keep small: each cue and each answer window can be
  used once per session (see Live relay), and the script's length is bounded in code (next bullet). A
  session is then the script read once, each question asked once, the closing, and at most 35 s of answer
  per question.
- Script limits, checked in code (`script_checks.py`, read from settings), as hard problems:
  - at most `SIB_MAX_SENTENCES_PER_STEP` sentences deliver any one step (counted from the step map), and the
    instruction has at most that many times the steps in the round's scope in all, so a sentence that
    delivers no step cannot lengthen the read-out;
  - at most `SIB_MAX_LINE_CHARS` characters in any sentence, question or the closing (characters, after
    whitespace is collapsed, not bytes);
  - at most 3 questions in a first round and 2 in a re-explain round. Fewer than the range (2 to 3, or 1 to
    2) stays a soft problem: the draft is accepted after the retry.

  A script that breaks a hard limit is retried once with a fix note that names the exact limit, then refused
  with 502 `script_incomplete`. The script prompt states the same limits, so a first draft usually passes.
- Output ceiling: every Flash agent is built with `max_output_tokens=SIB_MAX_OUTPUT_TOKENS` (`adk_common.py`).
  Thinking tokens count toward it, and a call that hits it is still billed for them. The default thinking
  levels are `medium` for `extract_steps`, `judge_a` and `judge_b` and `low` for `write_script`,
  `back_translate`, `transcribe_instruction`, `re_explain` and `blind_transcriber`. A reply whose finish
  reason is `MAX_TOKENS` is never used: it is 502 `upstream_error` ("The model's reply was cut off at its
  length limit"), without a retry, with nothing the model wrote in the error or the logs. This is read from
  the finish reason by the audit plugin, because ADK alone does not catch it: a judge or the transcriber cut
  off with no content lets the check finish with ordinary-looking ratings (`unclear` where a verdict was
  missing) instead of failing. A complete reply that happens to end exactly at the ceiling is refused too.
  Every TTS call has the same ceiling (`tts.py`): a reply cut off at it is the same 502, never played back and
  never cached. At about 25 audio tokens a second 8192 is about 5.5 minutes of speech, far more than the 600
  characters a TTS request may carry, so it is a backstop, not a tight bound. Live has no ceiling.
- Each Flash call logs one `usage` line with its token counts (see Privacy and observability), so the cost
  per call can be read from a real run.
- Not counted: the SDK's one retry after a Gemini 429 or 5xx. A day can overshoot the cap by those few
  uncounted calls.
- TTS (12) is spoken only from a round's own script (`tts.part_of_script`): the text, with whitespace
  collapsed, must lie inside that round's instruction or equal one of its questions or its closing, else 422
  `tts_text_not_in_script`. The briefing must be the caller's, and the text goes through `clean_text` (a lone
  surrogate is a 422 `invalid_text`, not a 500). A cache hit is free and needs no reservation.
- `0` is a kill switch: the eight Gemini-backed endpoints (a voice hazard report included) answer 429 and
  the rest of the API keeps working (cached TTS clips are still served, and a hazard can still be reported
  by tap). On Cloud Run:
  `gcloud run services update say-it-back-api --region asia-south1 --update-env-vars SIB_DAILY_GEMINI_CALLS=0`.
  `deploy/02_deploy_backend.sh` sets the variable on every deploy from `DAILY_CALLS` in `deploy/config.sh`,
  so edit its value there too.
- The first refusal each UTC day on an instance logs one WARNING (`daily Gemini call cap reached: limit N,
  UTC day YYYYMMDD`, no request content), for a log-based alert.
- If the store cannot be reached the request fails with 500 rather than run uncounted.
- `eval/` is not capped: `eval/check_adapter.py` calls `pipeline.run_check` directly, and that reserves
  nothing unless it is given a `before_call` hook.

## API v0.4: approval, hazards, the record chain, delivery, samples

**Script approval (23).** `POST /api/briefings/{id}/rounds/{n}/approve` with an optional `{by}` (at most 80
characters) sets the round's `approvedAt` and `approvedBy` and returns the round. Until then the live ticket
(11), TTS (12) and the check (13) answer 409 `script_not_approved`, before any model call, any upload or any
ticket slot is used; the Live relay checks it again when a socket claims the round. A second approval is a
no-op that returns the round unchanged (its first `approvedAt` and `approvedBy`), in any state; a first
approval needs the round unjudged (else 409 `invalid_state`). It is a free write under the per-minute limit.
Re-explain rounds need their own approval.

**Hazards (21, 22).** `POST /api/briefings/{id}/hazards` is multipart: an optional `audio` (16-bit PCM WAV,
at most 30 s and 3 MB) and an optional `round` (one of the briefing's round numbers). No body at all, or no
`audio`, is a tap: a `Hazard` with `kind: "tap"` and no text, free. With audio, one Flash call (the
`hazard_report` agent, thinking `SIB_THINKING_HAZARD_REPORT`, default low) transcribes it verbatim in the
worker's own script and translates it into the supervisor's language; it costs 1 against the daily cap,
reserved just before the call, and the clip is then dropped (kept under `.data/audio/<id>/hazard-<hid>.wav`
only with `SIB_KEEP_AUDIO`). Ids are `h1`, `h2`... A report is allowed in `steps_confirmed`, `briefing` and
`judged` (else 409), at most `SIB_MAX_HAZARDS` (5) a briefing (else 422 `too_many_hazards`); both are checked
before the upload is read. A JSON body is 415. `POST .../hazards/{hid}/ack` `{note, by?}` records what the
supervisor did: a note under 5 characters is 422 `note_required`, an unknown hazard 404 `hazard_not_found`,
a second ack 409 `invalid_state`. Go while a hazard is unacknowledged is 409 `hazard_open` (whatever the
reason); No-go is always allowed and lists them in `decision.openHazardIds`. No hazard text, translation or
note is ever logged (a test searches the logs for them).

**The record chain (25).** Every state change appends one `ChainEvent` to `events` in the same atomic
`repo.mutate` update (`chain.py`): `created`, `instruction_edited`, `steps_proposed`, `steps_confirmed`,
`round_created`, `script_approved`, `round_judged`, `hazard_raised`, `hazard_acknowledged`, `decided`.
`hash = sha256_hex(prevHash + "\n" + canonical({seq, type, at, data}))`, canonical being JSON with sorted keys,
no whitespace and UTF-8 unescaped; the first `prevHash` is 64 zeros and `recordHash` is the last `hash`.
Content is bound by `sha256_hex(canonical(<wire form>))`; a string's wire form is its JSON string, quotes
included. The data of each event:

| Event | `data` |
|---|---|
| `created` | `instructionSha256`, `siteId`, `taskId`, `supervisorLang`, `workerLang`, `sopId`, `sopVersion`, `sopSha256` |
| `instruction_edited` | `instructionSha256` |
| `steps_proposed` | `stepIds`, `stepsSha256` |
| `steps_confirmed` | `stepsVersion`, `stepIds`, `stepsSha256` |
| `round_created` | `n`, `kind`, `stepIds`, `scriptSha256` |
| `script_approved` | `n`, `scriptSha256`, `by` |
| `round_judged` | `n`, `mode`, `verdicts`, `ratingsSha256`, `deliveryOk`, `sampleAnswers`, `evidenceSha256` (transcripts, both passes, delivery, nextAction, sampleAnswers), `liveSha256` (`round.live`, or null) |
| `hazard_raised` | `hazardId`, `kind`, `round`, `reportSha256` (of `{original, translation, lang}`) |
| `hazard_acknowledged` | `hazardId`, `kind`, `noteSha256`, `by` |
| `decided` | `value`, `openStepIds`, `openHazardIds`, `reasonSha256` (or null), `by`; `inPerson: true` only for a Go after an in-person check (2026-10-17: the worker declined the recording) |

No event carries a transcript, an answer, a note, audio, a device key or its hash (tested). `repo.mutate`
refuses (500) a change that alters or drops an earlier event, and the request body cannot carry `events`.
`GET /api/briefings/{id}/verify` recomputes every link and re-derives what the latest event of each kind
binds from the record as stored now: the briefing's site, task and languages, the instruction and SOP, the
steps, each round's script and approver, ratings, verdicts, mode, evidence, `round.live` and sample answers,
`latestVerdicts` (re-derived from the rounds' ratings), each hazard's report and acknowledgement, and the
decision (and that the status is `decided`). It answers `{ok, events, recordHash}`, or `ok: false` with `brokenAt`
(the `seq` of the first event whose link, hash or bound content no longer matches) and a `reason`
(`seq_mismatch`, `prev_hash_mismatch`, `hash_mismatch`, `created_mismatch`, `instruction_mismatch`,
`sop_mismatch`, `steps_mismatch`, `script_mismatch`, `approval_mismatch`, `ratings_mismatch`,
`evidence_mismatch`, `live_mismatch`, `verdicts_mismatch`, `round_missing`, `hazard_mismatch`,
`hazard_missing`, `decision_mismatch`; or, at the last event, `record_hash_mismatch` and
`unrecorded_change` for content no event records). A briefing from before v0.4 has no events: it verifies
as `{ok: false, events: 0, recordHash: "", reason: "no_chain"}` and never starts a chain part-way. Someone
who can rewrite the whole store can rebuild the chain; the decision's `recordHash` goes to every webhook,
outside the store, for that.

**Delivery check v2 and guard rule 8.** Whenever the round has a `round.live` record, whatever `meta.mode`
says, each segment of the approved script (`instruction`, each question, `closing`) gets `similarity`,
`scriptOk`, `issues` (`not_spoken`, `wrong_script`, `low_similarity` under `SIB_DELIVERY_MIN_SIMILARITY`,
`negation_changed`, `number_changed`), `said` (what Live said) and `ok` (spoken, in the worker's script,
similar enough, no issue). In turn mode a segment Live never spoke is dropped (the TTS read it), and
anything Live did say still counts.
- **Negations** are the catalog's `negationMarkers` for the worker language, counted per sentence: the
  approved text and what was said are split on `. ! ? । ॥ ။ 。` and line breaks, each approved sentence is
  aligned with the said sentence that holds most of it (at least 60 %; a said sentence two approved ones
  share is compared with their sum), and the counts must agree pair by pair and in total. A sentence that
  cannot be aligned fails `negation_changed`, as does a "not" moved from one sentence to another.
- **Numbers** are compared in order, as a sequence: digit runs (every script's own digits mapped to ASCII;
  "1,000" is 1000, "1.5" stays 1.5) and the language's `numberWords`, each where it starts, so `十五米` against
  `五十米` is `number_changed`.
- Markers and words are normalised like the text (`guards.normalise`) and matched as whole words for a
  `match: "word"` language, as substrings otherwise.
- Each question's `"<qid>.reply"` (what Live said after the answer window) follows it, when Live said one:
  similarity 1, `said` always, `reply_too_long` past `SIB_REPLY_MAX_CHARS`, and `reply_not_neutral` when a
  normalised word of 3+ letters of the reply is also a word of the round's approved instruction or
  questions and is not one of the language's catalog `thanksWords` (in a script written without spaces,
  Chinese, any 3-character run left once the thanks words are taken out). The Tamil hint
  `நன்றி. சிக்னல்மேன் சொல்வதை மட்டும் கேளுங்கள்.` is short but not neutral.

Then rule 8 (`guards.apply_delivery`), in `rounds.check` after `run_check`: a segment that is not `ok` turns
every `covered` step it delivers into `unclear` with flag `delivery_mismatch`: the instruction, all steps in
scope; a question, the steps it checks; a question's reply, the steps of that question and of every later
question in the round (a hint said after q1's answer is heard before q2); the closing, none. `nextAction` is
recomputed, and the judges' own passes are kept as they were. The proof is the Tamil case: approved
`கரண்ட் இல்லை என்று டெஸ்டரில் சரிபார்த்த பிறகுதான் பேனலைத் திறங்கள்.`, said without `இல்லை`, scores 0.95 and is
`negation_changed`, and every covered step becomes "Ask again".

**Sample answers (24).** `GET /api/demo-answers` lists `{taskId, workerLang, round, questionId, stepIds,
gloss}` for each catalog demo answer that has a current clip: each `demoScripts[].rounds[]` answer and, since
16 Oct, its `followUps` (one per further reference question; `catalog.round_answers`), so an evaluator's stored
samples can answer every question of a demo round. `stepIds` are the reference question's steps, and a round's
answers are listed in reference question order. The clip is an eval item of pattern `demo` keyed by
`(taskId, workerLang, demo.round + 1, questionId)`, its `audio` on disk and `"audio"` not in its `pending` list.
`GET /api/demo-answers/{taskId}/{workerLang}/{round}/{questionId}/audio` returns that question's WAV, and the
older `GET /api/demo-answers/{taskId}/{workerLang}/{round}/audio` the round's own first answer (never a
follow-up); round 2 serves every later round, and anything else is 404 `no_demo_answer`. No model call. The web
pairs each question of the round's script with the stored answer it shares the most steps with
(`web/src/screens/brief/sample.ts`). A check's `meta.sampleAnswers` (question ids of the round,
each with a clip in the request; else 422) is stored as `round.sampleAnswers` in question order and recorded
in the `round_judged` event. **A sample answer never counts as the worker's.** `Briefing.sampleCoveredStepIds`
is derived on every read, never stored and never taken from a request: the steps whose latest `covered`
rating came only from sample answers, that is, every question asking about the step in that round
(`questions[].stepIds`) was a sample, or the worker's own answers to it do not hold the rating's quote. The
verdict stays as rated; a decision counts those steps as open (Go needs a reason, 422 `reason_required`, and
`decision.openStepIds` lists them), while a re-explain round's scope (`open_step_ids`) is unchanged. The
webhook record lists `sampleAnswers: [{round, questionId}]`, the Chat text says so, and the permit-to-work
stub marks the permit "Demo: synthetic sample answers". With the eval set as it is now (16 Oct), the six
rounds' own answers have current clips (rendered 15 Oct) and the six follow-ups have Sarvam-voiced clips (16 Oct,
`eval/vendor_tts.py`), so every question of both demo rounds has a sample once `deploy/02` copies `eval/testset`.

**Eval items (17).** Each item gains `steps` (gold step id → the catalog reference step text), `questionText`
(the catalog reference question) and `hasAudio` (its clip is on the server and not pending). A pending clip is
not served by 18, 19 or 24 either. Endpoint 19's `unsafe` counts gold `unclear` as a gold miss.

**Webhooks.** `SIB_WEBHOOK_URL` takes up to 3 URLs, posted to at once; one failing does not stop the others.
The JSON record adds `recordHash`, `events` (the count), `hazards` (`[{id, kind, acknowledged}]`, no text),
`sampleAnswers` (`[{round, questionId}]`) and `decidedAt`. With `SIB_WEBHOOK_SECRET`, each JSON post is signed over its exact bytes: `X-SIB-Timestamp` (Unix
seconds) and `X-SIB-Signature: sha256=<hex HMAC-SHA256 of "<timestamp>.<raw body>">`. Chat posts are unchanged
and unsigned. Only a URL's host is logged; the secret never is. `integrations/ptw-stub/` is the receiver that
checks it (a test posts the backend's real webhook to it over ASGI).

## Privacy and observability

- **Audit plugin, always on.** One `audit` line per run: phase, model id as the API returned it, latency and
  call count per agent. No content. The same ids and timings fill `round.modelIds` and `timingsMs`.
- **Usage lines.** One `usage` line per Flash model call, logged by the audit plugin when the response
  arrives, so a call that is then cut off or refused still shows what it used. Counts and ids only:
  ```
  usage {"agent": "judge_a", "event": "usage", "finish_reason": "STOP", "model": "gemini-3.8-flash-001",
         "output_tokens": 210, "phase": "check_answer", "prompt_tokens": 1830, "thinking_tokens": 412,
         "total_tokens": 2452}
  ```
  (one line in the log; keys sorted). The counts are the response's `usage_metadata`: `prompt_token_count`,
  `candidates_token_count` (what the model wrote; its thinking is billed as output too),
  `thoughts_token_count` and `total_token_count`, or `null` when the API sent none. `finish_reason` is
  `MAX_TOKENS` for a call that hit the output ceiling. Only integers and the finish reason's name can appear.
  TTS and Live sessions log no usage line.
- **BigQuery** (`SIB_BQ_DATASET`): Google's `BigQueryAgentAnalyticsPlugin` with a content formatter that
  keeps only token counts, drops `STATE_DELTA` and `NODE_OUTPUT` rows (they carry transcripts and ratings)
  and no multimodal content.
- **Logs.** The output schemas hide the rejected input in their validation errors (`hide_input_in_errors`).
  ADK's Workflow logs a failed node with the exception text, and without this a malformed model reply, which
  holds the worker's transcript, would be echoed into the service logs.
- **Cloud Trace** (`SIB_TRACE_TO_CLOUD`): `get_gcp_exporters` and `maybe_set_otel_providers`, with
  `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false` unless you set it, so spans carry no prompts or transcripts.
- **Webhooks** (`SIB_WEBHOOK_URL`): a short text summary of the decision for Google Chat, the JSON record
  (ids, verdicts, the decision, the record hash; no transcript, answer or hazard text) for anything else,
  signed with `SIB_WEBHOOK_SECRET`. A webhook URL can hold a key and a secret, so only its host is ever logged,
  `httpx` request logging is silenced, and neither the URLs nor the secret are in the settings' repr.
- ADK sessions are in memory. Audio (answers and hazard reports) is not stored unless `SIB_KEEP_AUDIO=true`.
- A hazard report's text and translation and the supervisor's note are stored in the briefing, never logged;
  the record chain holds only their digests.
- No log line and no response carries a device key, its hash or a client address (a test drives a whole
  briefing, the WebSocket included, and searches both). The store holds the owner hash with each briefing and
  in each ticket's record, and a per-address count under a hash of the day and the address.

## Live relay

`POST /api/briefings/{id}/rounds/{n}/live-session` returns a single-use ticket (random, 120 s, only its
SHA-256 is stored in the store, at most 2 per round) for a round whose script the supervisor has approved
(else 409 `script_not_approved`; the relay checks it again when the socket claims the round). `WS /api/live/{id}/{n}` then takes
`{"type":"start","ticket":...}`, checks the `Origin` header against `SIB_ALLOWED_ORIGINS`, and runs the
ADK `briefer_live` agent with `Runner.run_live`. The briefer's instruction is built on the server from
the round's script and the language lock; it never contains steps, essentials or ratings. Only the
enumerated cues `READ_INSTRUCTION`, `ASK <qid>` and `CLOSE` reach the model, as text built on the server,
and mic audio only inside an answer window. Each cue and each question's answer window can be used once per
session (`live_order.py`): a repeat is `invalid_state` (close 4409) and is never forwarded, so a client cannot
loop them to keep the model speaking and listening until the session limit. What Live said and heard is
written to `round.live` when the socket closes: speech after an answer window is kept apart under
`"<qid>.reply"` so the neutral thanks can be audited. Limits: first frame within 5 s, a first cue within 30 s of
`ready`, 10 min per session, 35 s per answer, 60 s idle, binary frames of at most 8 KB, and at most
`SIB_MAX_SOCKETS_PER_IP` (4) open sockets per client address on one instance. Idle means no frame the relay
accepts (a cue, an answer marker, or audio forwarded inside an answer window), no event from the model and no
model speech still playing: Live sends a turn's audio well ahead of real time and ends the turn when the speech
would end, so queued playback is not idleness (`live_idle.py`). Audio the relay drops outside a window is not
activity, which stops a socket being held open for the whole session limit with nothing for the model. A
socket over the per-address cap is accepted only to be sent `error` `limit` and closed with 4429, before any
frame is read, so its ticket is not spent and no Live connection is opened. The slot is released before the
close frame goes out. The first-message and first-cue times are settings (`ws_first_message_s`,
`ws_first_cue_s`), not environment variables. `round.live` is written before the ADK runner is closed, so a
`check` with `mode: "live"` posted right after `stop` finds it (it waits up to 5 s, then 409
`live_not_recorded`).

## Cloud Run

- Request timeout of at least 900 s (`--timeout=900`): a live socket lasts up to 10 minutes. Use
  `--session-affinity`. The browser calls the service URL directly, for the API (`VITE_API_BASE`) and for the
  WebSocket: Firebase Hosting cannot proxy WebSockets, and a Hosting rewrite would put another proxy in front of
  the client address. Set `SIB_PUBLIC_WS_BASE` to the service's `wss://` address and `SIB_ALLOWED_ORIGINS` to the
  web origins (CORS and the WebSocket Origin check both read it).
- The runtime service account needs `roles/aiplatform.user` (Gemini on Agent Platform) and
  `roles/datastore.user` (Firestore), plus `roles/cloudtrace.agent` when `SIB_TRACE_TO_CLOUD` is on
  (it includes `telemetry.traces.write`; ADK exports over OTLP to `telemetry.googleapis.com`) and
  `roles/bigquery.dataEditor` when `SIB_BQ_DATASET` is set. `deploy/01_setup_project.sh` grants the BigQuery
  role only when `BQ_DATASET` is set. A project set up by an earlier version of the script still holds it:
  remove it with `gcloud projects remove-iam-policy-binding` if BigQuery is not used.
- Enable the `aiplatform`, `firestore`, `telemetry` and `bigquery` APIs as needed. Optionally add a Firestore
  TTL policy on `live_tickets.expiresAt` and `live_locks.expiresAt`.
- **Firestore index.** A caller's list of briefings (`GET /api/briefings` and the CSV export) is the query
  `briefings` where `owner ==` the caller's hash, ordered by `createdAt` descending. Firestore refuses it
  without a composite index on `briefings(owner ascending, createdAt descending)`, and the two endpoints then
  answer 500. `deploy/01_setup_project.sh` creates it if no index with those fields exists (it asks
  `gcloud firestore indexes composite list` first, so the script can run again), and waits until it is built. By
  hand:
  `gcloud firestore indexes composite create --database="(default)" --collection-group=briefings --query-scope=collection --field-config=field-path=owner,order=ascending --field-config=field-path=createdAt,order=descending --project "$PROJECT_ID"`.
  Check it with `gcloud firestore indexes composite list --database="(default)"`: its state must be `READY`
  before the first list. A test ties the query the store runs to the index the script creates
  (`tests/test_deploy_scripts.py`).
- **The client address.** Per-address limits, the daily allowance and the socket cap read the `X-Forwarded-For`
  entry `SIB_TRUSTED_PROXY_HOPS` (default 1) from the right, the one Cloud Run's front end appends. This is
  assumed from the documentation, never observed on a real deployment: check it after the first deploy. From
  one machine send 31 `POST $SERVICE_URL/api/briefings` (a valid body and a device key), each with a new made-up
  leftmost entry, `-H "X-Forwarded-For: 10.0.0.N"`. With the right setting the 31st is 429 `rate_limited`
  (all 31 came from one real address, and the default limit is 30 a minute). If all pass, the rightmost entry is
  not the client's address (nothing is appended, or the entry is a proxy's): look at what the service receives
  and set `SIB_TRUSTED_PROXY_HOPS`. Then confirm from two networks (a laptop and a phone on mobile data) that
  each gets its own allowance. Behind a load balancer the client is one entry further left, so the value is 2.
  Per-address state is per instance for the minute limit and the socket cap (`--max-instances=3` allows up to
  three times `SIB_MAX_SOCKETS_PER_IP` open sockets per address), and shared through Firestore for the daily
  allowance.
- **Evaluation data in the image.** Endpoints 16 to 19 (the Sample page) read `SIB_EVAL_DIR`, which the image sets
  to `/app/eval`. `eval/` is outside the `backend/` folder that `gcloud run deploy --source` uploads, so
  `deploy/02_deploy_backend.sh` copies `eval/testset` and `eval/reports/latest.json` into `backend/eval_data/`
  before the build and removes the copy when it ends (a missing file is a warning, and that endpoint is 404, as
  without eval data). The `Dockerfile` copies `eval_data/` to `/app/eval`; built any other way (`docker build
  backend/`) the folder holds only its placeholder. Refresh `eval/reports/latest.json` before a deploy: the image
  carries what was there.
- The image installs the `trace` and `bigquery` extras by default (`--build-arg EXTRAS=""` for a smaller one).
  It runs `uvicorn sayitback.main:app` on `$PORT` (default 8080) as a non-root user. This repository does not
  build or push images; `deploy/` does.
- Gemini Live on Agent Platform serves from US and EU endpoints only (`SIB_LIVE_LOCATION`). The Live model id
  there may differ from the Developer API's: set `SIB_LIVE_MODEL` after checking.

## Verified and not verified

Run against the real Gemini Developer API on 13 Oct 2026 (call log in the build report):

- `gemini-3.8-flash`: extract (the SOP-only shoring step is flagged `sop`), round-1 script en to ta with a
  back-translation and a complete `stepMap`.
- `gemini-3.8-flash-tts`: `generate_content` with the AUDIO modality returns 24 kHz PCM, wrapped as WAV.
- `gemini-3.8-live`: the relay end to end with **manual** activity detection, in Tamil: the read-out matches
  the script exactly, only a neutral thanks follows an answer, Live's own transcript of the answer is exact,
  and `round.live` is written on close.
- The check on real Tamil audio (blind transcript, two judges, guard) ran on `gemini-3.1-flash-lite`, because
  the shared key's free-tier quota for `gemini-3.8-flash` (20 requests a day) was spent. That was the earlier
  `SequentialAgent` version. Round 1: s1 covered, s2 and s3 missed. Round 2: all covered. Check latency 14 to
  36 s.
- The `Workflow` version of the check ran on real `gemini-3.8-flash` on 14 Oct (free-tier key, the hardened
  v0.3 code, `PROMPT_VERSION` 2026-10-14.6), round 1 of the then-lead panel demo only: the blind transcript was
  exactly the spoken Tamil, both judges rated s1 `unclear` (0.85; the line was vague, and the catalog line has
  changed since), s2 and s3 `missed`, nothing was falsely covered. Round 2 hit the free tier's daily limit.
  Usage per call: transcriber 383 prompt / 77 output tokens, judge A 1,091 / 154 / 328 thinking, judge B 806 /
  148 / 439; the free tier took 73 to 183 s a call. The lifting-zone lead demo has not run on a real model.

Added with API v0.4 and never run against Google: the `hazard_report` agent, judge B on
`gemini-3.1-flash-lite` inside the Workflow (thinking level included), the delivery check on real Live speech
(the negation and number markers are catalog drafts pending native-speaker review), the signed webhooks to a
deployed receiver, `deploy/02`'s new settings and `deploy/04` (stub `gcloud` only), and the permit-to-work
stub's image.

Added with API v0.5.3 and never run against Google: the judge prompt `2026-10-16.11` (`missed` only when the
answer says nothing about the step; everyday and site words count; a word that can also name an unsafe thing
does not) and guard rule 1 as a split-is-`unclear` rule. The unit tests pin the wording and the 16 verdict
pairs; whether Gemini rates a partial answer in site words `unclear` and a complete one `covered` is for the
next real eval run. `eval/reports/latest.json` was made with `2026-10-15.10` and the old rule 1. Prompt
`2026-10-16.12` (the script and re-explain prompts ask for the word a worker on site says, never an English
term spelled letter for letter in the worker's script) is likewise unit-tested only: whether Gemini follows it
in Tamil, Hindi, Bengali, Chinese, Odia and Burmese is for a native speaker to read in a real run.

Unit-tested only, never run against Google: the Agent Platform wiring (client kwargs, regional endpoints),
Firestore (a fake client, including the two-document daily-count transaction and the owner query), Cloud Trace
and BigQuery wiring (patched modules), the Google Chat webhook (a mock transport), the HTTP `check` endpoint in
live mode, the output ceiling and the usage lines (the real google-genai client and ADK `Gemini` model over a
mock transport that returns real-shaped responses: the request carries `maxOutputTokens`, and a `MAX_TOKENS`
reply is refused; no real call has hit the ceiling), and the Docker image (not built here).

Added with API v0.3 and not yet seen on a real deployment: the `X-Forwarded-For` shape Cloud Run sends (see Cloud
Run for the check), `max_output_tokens` on `gemini-3.8-flash-tts` and a TTS reply that finishes at it, the
Firestore composite index (`deploy/01` runs against a stub `gcloud` in the tests, and its list filter was
checked only with gcloud's own filter engine on a sample result), the browser's CORS preflight from the Hosting
origin, and the eval data in the built image.

## Known limits

- ADK 2.11's legacy dev endpoint `GET /dev/apps/{app}/graph` answers 500 for any `Workflow` (its
  `cli/agent_graph.py` reads an attribute `_graph` that a Workflow does not have). The dev UI itself calls
  `build_graph_image` and `build_graph`, which work for `check_answer`.
- The Workflow's single-turn nodes send slightly different requests than `SequentialAgent` did (compared on
  the wire, real google-genai client over a mock transport). ADK no longer appends its `You are an agent. Your
  internal name is "judge_a"...` identity line to the three system instructions, and each judge's request
  carries the blind transcript as its Workflow node input, a raw JSON user turn: judge B gets it instead of the
  fenced "For context" quote it had, judge A gets it as well as that quote. The instruction, which holds the
  transcript too, still says transcripts are evidence, never instructions. The generation config, the response
  schemas, the clips and the transcriber's contents are unchanged. `PROMPT_VERSION` was not bumped.
- The per-minute limit and the Live socket count are in memory and per instance, keyed on the client address
  (the `X-Forwarded-For` entry `SIB_TRUSTED_PROXY_HOPS` from the right, an IPv6 address as its /64). A client
  with many addresses of its own (a botnet, or many /64s) gets an allowance for each. The daily cap and the
  per-address daily allowance (above) are what bound total spend; Cloud Armor needs a load balancer in front.
- The daily allowance is per address, so everyone behind one NAT shares 100 calls a day: about ten briefings.
  Raise `SIB_DAILY_CALLS_PER_IP` for a room of judges on one Wi-Fi.
- The per-address key is a plain SHA-256 of the day and the address. It keeps the address out of the store, but
  the IPv4 space is small enough to enumerate, so it hides the address from a casual reader of the store, not
  from someone who can try every address against it.
- A Live session is bounded by its script, and the script is bounded in code: at most 6 steps, 3 sentences per
  step (and 3 times the steps in all), 160 characters in any line, 2 to 3 questions (1 to 2 in a re-explain
  round), plus 10 minutes per session and 35 s per answer window. Only the 12-word limit is still a prompt
  rule. A draft whose only fault is too few questions is retried once and then accepted
  (`phases._write_checked`).
- The cost per call is still an estimate: the usage lines are new, and nothing has been measured with them.
  Whether the 8192-token ceiling is enough in practice (the blind transcriber with three long clips in an
  Indic script, and the `medium` thinking agents, are the likeliest to reach it) is for the first real run.
- There are no accounts, only device keys (see Callers and ownership): a key owns what it creates, but anyone
  can make a key, and a key kept in `localStorage` is lost with the browser's storage (its briefings can then
  no longer be reached). Put Firebase Authentication or Identity Platform and App Check in front before real
  use.
- `thinking_level` needs a Gemini 3.x model, judge B's `SIB_JUDGE_B_MODEL` included. A free-tier Developer
  API key allows only 20 `generate_content` requests a day per model, which is not enough for the eval runs.
- The delivery check counts markers, so it is only as good as the catalog's lists: in a `match: "word"`
  language a marker is a whole word after normalising, so English `n't` (normalised to `nt`) matches nothing,
  and only the listed contractions (`don't`, `won't`...) count. A paraphrase that keeps the count of negations
  but moves one ("do X, not Y" to "do not X, Y") is caught by similarity, not by the count.
- The record chain is tamper-evident, not tamper-proof: it finds an edit to the stored record, not a rewrite of
  the whole chain by someone who holds the store (the webhook's `recordHash` is the outside anchor). The live
  relay's `round.live` write is not an event of its own: the round's `round_judged` binds it by `liveSha256`,
  and the relay never writes into a judged round. A second Live session for a round appends its speech to the
  first's per segment, so the delivery check sees everything the worker heard.
- The webhook signature covers the timestamp and the body, not the URL path: a receiver with several paths
  cannot tell from the signature which one a post was meant for. A Google Chat URL (which carries its own key
  and token) is set as a plain environment variable from `deploy/config.sh`, not from Secret Manager; it is
  never printed or logged, but anyone who can read the service's configuration can read it. Both were left
  out of v0.4 on purpose.
- The delivery check's number words are the catalog's lists: a number word not in `numberWords` (Hindi
  `पंद्रह` for 15) is not seen, so 15 changed to 25 in words passes the number check (similarity may still
  catch it).
- Tickets, leases and `round.live` use the store, so they work across instances, but the audio relay itself
  is pinned to the instance that accepted the socket.
