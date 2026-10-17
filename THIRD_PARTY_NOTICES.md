# Third-party notices

Say It Back's own code and text are under the Apache License 2.0 (`LICENSE`). Everything below is someone else's work that the app, the evaluation set, the deck or the video uses. Items marked **check** are open questions for the team before submission (outside review, P0-23).

## In the web app

| What | Source | Licence |
| --- | --- | --- |
| Noto Sans and the Noto Sans script families (Tamil, Bengali, Devanagari, Oriya, Myanmar, Telugu, SC) | Google Fonts, loaded at run time | SIL Open Font License 1.1 |
| Material Symbols Outlined (the icons) | Google Fonts, a subset loaded at run time | Apache License 2.0 |
| React, Vite, Tailwind CSS, wouter and the other npm packages | `web/package.json`, `web/package-lock.json` | each package's own licence (MIT or Apache 2.0 for the direct dependencies; **check** the full tree with a licence report before the public push) |
| Firebase JavaScript SDK (sign-in builds only) | npm `firebase` | Apache License 2.0 |

## In the backend and the evaluation

| What | Source | Licence or terms |
| --- | --- | --- |
| FastAPI, Google ADK, google-genai, google-auth, google-cloud-firestore and the other Python packages | `backend/pyproject.toml`, `uv.lock` | each package's own licence (MIT or Apache 2.0 for the direct dependencies; **check** the full tree) |
| Gemini models (step extraction, scripts, the check, Live, TTS) | Google Cloud, Gemini Enterprise Agent Platform | Google Cloud terms of service |
| 58 synthetic evaluation clips (15 Oct) | Gemini TTS (`gemini-3.8-flash-tts`) | generated output under Google Cloud's terms |
| 30 synthetic sample-answer clips (16 and 17 Oct) | Sarvam Bulbul (`bulbul:v4-flash`, `bulbul:v3`), voices Vijay, Rahul, Roopa, Shubh, Tarun | Sarvam's terms of service; **check** that they allow use in a public demo and a competition entry |
| Safety procedures in the catalogue | written by the team from public guidance (Singapore MOM and WSH Council, UK HSE, US OSHA, WaterJet Technology Association and others; sources in `Google_BuilderCup/build-notes/37-domain-suites.md`) | the team's own text; quoted passages are short and attributed |

## In the deck and the video

| What | Source | Licence or terms |
| --- | --- | --- |
| Avenir Next, Tamil MN, Heiti SC, Bangla, Devanagari, Oriya and Myanmar Sangam MN, Telugu MN | macOS system fonts, embedded in the PDF by the export | Apple's font licence; **check** that embedding them in a published PDF is allowed (each font's embedding flag) |
| Screenshots | the team's own app | the team's |
| Video voice-over (`deck/narration/`) | ElevenLabs `eleven_v4`, premade voice "Lily", free plan | the free plan asks for attribution ("Voice-over: ElevenLabs") and is for non-commercial use, while the competition takes a perpetual marketing licence: **check**, or record the narration in a team member's voice |
| Quotations from codes, circulars and vendor pages | Singapore MOM, WSH Council, LTA, IMDA; vendors' own pages | short attributed quotations; every source is in the slide's speaker notes |
