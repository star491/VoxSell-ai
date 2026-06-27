# VoxSell AI Week 4 MVP Sprint

This folder is an isolated Week 4 package. It does not overwrite the existing
Week 3 build. To apply the sprint changes to the current single-folder app,
copy these files over the matching repo paths:

- `week 4/server.py` -> `server.py`
- `week 4/static/index.html` -> `static/index.html`
- `week 4/static/app.js` -> `static/app.js`
- `week 4/static/styles.css` -> `static/styles.css`

The two standalone sprint drills can be committed as Week 4 evidence:

- `week 4/barge_in.py`
- `week 4/custom_tool.py`

## Week 4 Requirements Covered

- Custom persona: `SYSTEM_INSTRUCTION` casts the agent as Nira, a concise
  consultative sales agent with a clear sales-only operating boundary.
- Two original tools:
  - `lookup_product_plan` queries a local SQLite catalog.
  - `save_lead_profile` writes a scored lead record to SQLite.
- Bonus tool:
  - `get_live_exchange_rate` calls a free public API when available, but the
    assignment demo can rely on the two SQLite-backed tools above.
- Barge-in:
  - The backend checks `serverContent.interrupted` before processing audio.
  - It sends `{ "type": "flush" }` to the browser immediately.
  - The frontend stops all scheduled audio sources and clears playback timing.
- Security:
  - The Gemini key remains backend-only through `.env`.
  - No frontend file contains an API key.

## Demo Script

1. Start the backend and connect the browser.
2. Click `Plan match` or ask: "Which plan fits a 12-person sales team?"
3. Click `Save lead` or say: "Save Acme as a hot lead, budget 6000 dollars,
   timeline this month, pain point missed follow ups."
4. During a spoken response, press `Hold to talk` and interrupt the agent.
   The console should log `Barge-in: Playback flushed immediately.`
