# VoxSell AI

An AI-powered voice sales agent built on Gemini 2.5 Flash's native audio
Live API. This repo is the Week 3 assignment deliverable: a working local
voice client talking to Gemini through a securely configured backend proxy,
extended with the Sales Intelligence Layer, product knowledge base, and
lead scoring described in the VoxSell AI product spec.

See `SUBMISSION.md` for the architecture writeup required by the
assignment. This file is just setup/run instructions.

## What's here

```
backend/
  server.py          FastAPI proxy: frontend WS <-> Gemini Live API WS
  gemini_session.py  Setup message, tool declarations, wire-format helpers
  sales_engine.py    Rule-based objection/intent detection + lead scoring
  product_kb.py      Sample product data + objection rebuttal playbook
  tools.py           Python implementations of Gemini's function calls
  summary.py         End-of-call summary via a plain REST call (Module 1 pattern)
frontend/
  src/hooks/useAudioStreamer.js   Mic capture, downsampling, playback queue, WS lifecycle
  src/App.jsx + components/        Live call console UI
```

## 1. Get a free Gemini API key

## 2. Run the backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install -r requirements.txt
cp .env.example .env
# edit .env and paste your key into GEMINI_API_KEY=

python server.py
# -> Starting VoxSell AI proxy on http://localhost:8000
```

Sanity check: `curl http://localhost:8000/health` should return
`{"status":"ok", ...}`.

## 3. Run the frontend

```bash
cd frontend
npm install
cp .env.example .env   # default already points at ws://localhost:8000/ws
npm run dev
# -> open the printed http://localhost:5173 URL in Chrome or Firefox
```

Click **Start call**, allow microphone access, and talk. Say something
like *"What's the pricing?"* or *"This seems kind of expensive"* and watch
the transcript, lead score gauge, and live insights feed update in real
time. Click **End call** to get the auto-generated call summary.

## Notes / known limitations

- The Live API model name (`gemini-2.5-flash-native-audio-preview-12-2025`)
  and some wire-format field names are for a preview API and may shift -
  check the official docs linked in `gemini_session.py` if a field name
  has changed since this was written.
- `useAudioStreamer` uses `ScriptProcessorNode`, which is deprecated but
  still broadly supported; an `AudioWorklet` would be the production-grade
  upgrade.
- The Sales Intelligence Layer's objection/intent detection is intentionally
  rule-based (regex over the live transcript) rather than a second LLM
  call, per the project's design choice - see `sales_engine.py` to extend
  the patterns.
- This is a local development setup (no auth, no deployment config, `*`
  CORS) - harden before shipping anywhere public.
