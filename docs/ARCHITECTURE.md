# Say It Back — Architecture (v0.2, 13 Oct 2026, Google-native)

Before a migrant worker starts a new or changed task, the supervisor's instruction is spoken to them in their own language. The worker explains back, out loud, what they will do. Gemini checks the answer against the task's critical steps and shows the supervisor, in the supervisor's language, which step was missed. The supervisor decides whether work starts. The AI informs the decision; it never makes it.

v0.2 makes the build Google-native end to end. ADK runs every Gemini call, including the live voice briefing, and in the cloud all Gemini traffic goes through Gemini Enterprise Agent Platform (formerly Vertex AI). Changes from v0.1 are listed at the end.

## System

```
Supervisor's phone (React web app on Firebase Hosting)
 ├─ HTTPS /api/**  ──(straight to the Cloud Run URL, X-SIB-Device)──▶  Cloud Run "say-it-back-api"  (FastAPI + one ADK 2.11 agent package)
 └─ WSS  /api/live/... ──(straight to the Cloud Run URL)──▶ same service
                                             │
       ADK agents ───────────────────────────┤  extract steps · write script · back-translate · re-explain
       (one Runner + App per phase)          │  check (ADK Workflow): blind transcriber → (judge A ‖ judge B) → join → guard (code)
                                             │  briefer: run_live() bidi-streaming ⇄ Gemini Live API (gemini-3.8-live)
       google-genai (no agent needed) ───────┤  TTS for turn mode (gemini-3.8-flash-tts)
                                             ├─ Firestore: briefing records and the state machine
                                             ├─ Cloud Trace: ADK OpenTelemetry spans        (SIB_TRACE_TO_CLOUD)
                                             ├─ BigQuery: ADK Agent Analytics plugin, content redacted (SIB_BQ_DATASET)
                                             └─ Google Chat: decision posted to the site's space      (SIB_WEBHOOK_URL)

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
3. **Script.** The scripter agent writes the worker-language instruction (short sentences, explicit negations, site loanwords kept) and 2–3 open questions that don't contain the answer's key words. A **separate** back-translator agent renders both into the site language, so the supervisor sees what the worker will hear. Code checks that every confirmed step is delivered (`stepMap`) and asked about.
4. **Briefing.** Live mode: the browser opens a WebSocket to the backend with a single-use ticket. The backend runs the ADK **briefer** agent with `Runner.run_live()`. Its instruction is built on the server from the round's script and the language lock, so the browser can't change it. The browser streams mic audio only during answer windows and plays the model's audio. The briefer reads and asks; it never sees the steps, never judges, never hints. The backend keeps what Live said and heard per segment. Turn mode (fallback): TTS audio for each segment. In both modes the browser records each answer locally as a 16 kHz WAV.
5. **Check.** One request runs the ADK check workflow:
   - a **blind transcriber** (steps withheld) writes verbatim transcripts in the original script, with a site-language translation;
   - two judges run in parallel (a fan-out in the ADK 2 `Workflow` graph, then a `JoinNode`): judge A on the audio plus the transcript, judge B on the transcript only;
   - a **guard** `FunctionNode` (pure code, no model) applies the guard rules (API.md) and writes the final ratings.

   A step is `covered` only if both judges agree, the quote is really in the transcript, the language is right and confidence is high. Everything uncertain becomes `unclear`: ask again.
6. **Re-explain.** For open steps the supervisor re-explains, in their own words or with a generated focused re-explanation. The app then asks new questions about those steps only. After 3 rounds it suggests "verify by demonstration".
7. **Decision.** The supervisor taps Go or No-go (human gate 2). Go with open steps requires a typed reason. The record says what was checked and what was decided, and it never scores the worker. The decision can be posted to the site's Google Chat space.

## ADK structure

- `backend/sayitback/agents/` is an ADK agents directory. Each phase is a folder exporting `root_agent`: `extract_steps`, `write_script`, `back_translate`, `transcribe_instruction`, `check_answer`, `re_explain` and `briefer_live`. `uv run adk web sayitback/agents` opens Google's dev UI over the same agents. Event traces, the agent graph and live voice there are useful for development and for the demo video. If state is empty, `check_answer` loads the catalog's `sg-lead` demo task.
- The API runs each phase with `Runner(app=App(name, root_agent, plugins), session_service=InMemorySessionService())`. The Runner exists only for the request, and the briefing state lives in the store. Audio stays out of any persistent ADK session (privacy), so ADK sessions are deliberately in-memory.
- Instructions are callables (InstructionProvider) that read session state, so JSON braces in prompts are never template-substituted. Output schemas give typed results, and judge B uses `include_contents="none"` so audio never reaches it.
- Plugins: an always-on audit plugin (model ids, timings and call counts per phase, no content), and Google's BigQuery Agent Analytics plugin when `SIB_BQ_DATASET` is set, with a content formatter that drops transcripts and audio.
- The production path for the human gates is an ADK 2.x `Workflow` with `RequestInput` nodes on Agent Engine Sessions (verified offline in probes). The prototype enforces the gates with the store's state machine instead, because a paused workflow on in-memory sessions dies when the instance is recycled.

## Design decisions

| Decision | Why |
|---|---|
| ADK runs every Gemini call, including Live, through `run_live` | One agent framework end to end, as Google's own guidance recommends; one place for instructions, schemas, callbacks, plugins and tracing; the dev UI shows the real agents. |
| Live is relayed by the backend, not opened from the browser | In the cloud all Gemini traffic, Live included, runs on Agent Platform with the service account and the trial credit. No API key is deployed, and no free-tier rate limit hits the judged demo. The lock is server-side by construction, and the server keeps the transcripts. The cost is one extra hop and a WebSocket that goes straight to the Cloud Run URL (Hosting can't proxy it). Browser-direct Live with config-locked ephemeral credentials was verified in probes, but those credentials exist only on the Developer API, so it isn't built. |
| No accounts: each browser holds a random device key that owns its briefings | A public demo needs visitors kept apart without a sign-up step. The key scopes reads, writes, the list and the export to one browser; its ticket alone opens the Live socket. The production path is Firebase Authentication or Identity Platform for the org's users, plus App Check against scripted clients. |
| The browser calls Cloud Run directly, not through a Hosting rewrite | Per-address limits read `X-Forwarded-For` from the right, so every request must arrive through the same hops; the WebSocket already goes direct. It also removes Hosting's 60 s cut on long requests. |
| Live is voice only; judging is a separate Flash workflow | Live has no response schema. Separating the judge keeps it auditable and lets it run twice. |
| Blind transcription before judging | A transcriber that knows the expected steps can "hear" them. Withholding the steps keeps the evidence independent of the rubric. |
| Two judge passes, worse verdict wins, plus a code guard node | Asymmetric safety: a false "covered" is the one error that matters, so agreement is required to pass and any doubt abstains. The guard is a `FunctionNode` in the same ADK 2 `Workflow` graph as the judges, so it appears in traces and in the `adk web` graph like the model steps. |
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
| `SIB_LIVE_VOICE` / `SIB_TTS_VOICE` | `Kore` / `Kore` | prebuilt voices |
| `SIB_JUDGE_PASSES` | `2` | 1 = judge A only |
| `SIB_COVERED_MIN_CONFIDENCE` | `0.75` | below this, `covered` becomes `unclear` |
| `SIB_STORE` | `local` | `local` (JSON files in `backend/.data/`) or `firestore` |
| `SIB_ALLOWED_ORIGINS` | `http://localhost:5173` | CORS and WebSocket Origin check, comma-separated |
| `SIB_PUBLIC_WS_BASE` | empty | e.g. `wss://say-it-back-api-xxxx.a.run.app`; empty = same origin (local dev through the Vite proxy) |
| `SIB_TRACE_TO_CLOUD` | `false` | export ADK OpenTelemetry spans to Cloud Trace |
| `SIB_BQ_DATASET` | empty | `project.dataset` for the ADK BigQuery Agent Analytics plugin (content redacted) |
| `SIB_WEBHOOK_URL` | empty | each decided briefing is POSTed here; a `chat.googleapis.com` URL gets a Google Chat message |
| `SIB_EVAL_DIR` | `../eval` | test set and reports for `/api/eval/*` |
| `SIB_RATE_LIMIT_PER_MIN` | `30` | per-IP limit on Gemini-backed endpoints |
| `SIB_DAILY_GEMINI_CALLS` | `300` | global Gemini calls per UTC day, shared by all instances through the store; over it, 429 `daily_limit` |
| `SIB_MAX_SENTENCES_PER_STEP` | `3` | most script sentences per step, and 3 times the round's steps in all; a script over it is retried once, then 502 `script_incomplete` |
| `SIB_MAX_LINE_CHARS` | `160` | most characters in any spoken line (sentence, question, closing); same retry, then 502 |
| `SIB_MAX_OUTPUT_TOKENS` | `8192` | `max_output_tokens` on every Flash and TTS call, thinking included; a reply cut off at it is 502 `upstream_error` |
| `SIB_DAILY_CALLS_PER_IP` | `100` | each client address's share of the daily cap, same costs; `0` = off |
| `SIB_TRUSTED_PROXY_HOPS` | `1` | which `X-Forwarded-For` entry, counted from the right, is the client address |
| `SIB_MAX_SOCKETS_PER_IP` | `4` | open Live sockets per client address on one instance |
| `SIB_API_DOCS` | `false` | serve `/api/docs` and `/api/openapi.json` (local development only) |
| `VITE_API_BASE` (web build) | `/api` | API base URL; the Cloud Run service URL plus `/api` in production |
| `SIB_KEEP_AUDIO` | `false` | keep answer audio (consented demos only) |

## Guardrails (enforced in code, not only in prompts)

- The tool never approves work; only the supervisor's POST records a decision.
- `covered` is never emitted when the judges disagree, the quote isn't in the transcript, the answer is in the wrong language, there was no speech, or confidence is low.
- The briefer's context never contains steps, essentials or ratings (unit-tested). The browser can send only enumerated cues and audio, never instructions.
- No worker name, ID, score or history is stored. Audio is processed in memory and discarded unless `SIB_KEEP_AUDIO=true`. ADK sessions are in-memory, and analytics rows carry no transcript or audio.
- Synthetic SOPs and tasks. The evaluation set is synthetic TTS unless marked `recorded` (consented volunteers only).

## Changes from v0.1

- Live moved from browser-direct (ephemeral Developer-API credential) to an ADK `run_live` relay on Cloud Run, so Live can run on Agent Platform. API.md endpoint 11 now returns a WebSocket ticket, and endpoint 20 is the WebSocket.
- Agent Platform is the cloud Gemini backend; ADK App plugins, Cloud Trace, BigQuery analytics and Google Chat were added (all env-gated); `adk web` works over the production agents.
