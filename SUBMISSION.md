# Submission: VoxSell AI

## Data flow architecture

VoxSell AI has three legs. The browser captures microphone audio with
`getUserMedia`, downsamples it from the browser's native sample rate to
16kHz PCM16 using a `ScriptProcessorNode`, and streams it as raw binary
WebSocket frames to our FastAPI backend. The backend is a pure proxy: it
holds the only Gemini API key (loaded from `.env`, never sent to the
client) and maintains a second WebSocket connection to Gemini's
`BidiGenerateContent` Live API endpoint. Audio chunks arriving from the
browser are base64-wrapped into Gemini's `realtimeInput` JSON message and
forwarded upstream; audio coming back from Gemini is unwrapped and sent to
the browser as raw binary frames, which a second `AudioContext` queues
gap-free for 24kHz playback. The browser never talks to Google directly,
satisfying the security requirement, and the two audio legs use different
wire formats (binary-on-the-wire to the browser, base64-in-JSON to
Gemini) - that translation is the proxy's actual job, not just pass-through.

On top of that pipe sits the Sales Intelligence Layer. We turned on
Gemini's `inputAudioTranscription`/`outputAudioTranscription` in the setup
message so the backend gets a live text transcript alongside the audio,
with no second model call needed. A small regex-based `ObjectionDetector`
and `IntentAnalyzer` (`sales_engine.py`) scan the customer's transcript as
it streams in, updating a running 0-100 lead score and, when an objection
is detected, sending a text-only `clientContent` turn back to Gemini with
`turnComplete: false`. That note is never spoken - it rides along inside
the *same* turn as the customer's audio and steers Gemini's eventual
spoken reply (e.g. acknowledge a price objection, then weave in the
trial-period talking point from the product KB) without the customer ever
hearing it. This is the "hybrid" design: detection is deterministic
Python, but Gemini still composes the actual sentence.

Two further tools (`get_product_info`, `schedule_demo`) plus the
curriculum's required `get_current_time` are declared in the setup
message; when Gemini emits a `toolCall`, the backend dispatches to
`tools.py`, runs the Python function, and sends a `toolResponse` back so
Gemini can speak the result. At call end, the full transcript is sent to
`gemini-2.5-flash` via a plain REST call (reusing the Module 1 pattern) to
generate a 3-4 sentence manager-facing summary.

## Handling the dual WebSocket connections

Each connection runs its own `asyncio` task -
`client_to_gemini` forwards mic audio/control messages, `gemini_to_client`
forwards audio/transcripts/tool calls back - joined with `asyncio.gather`
inside an `async with websockets.connect(...)` block, so closing either
socket tears both tasks down via a shared `asyncio.Event`.

## Challenges

The trickiest part was deciding how to inject the objection-handling note
without it sounding like the customer said it or interrupting their turn
mid-sentence - using `turnComplete: false` to append context inside the
live turn, rather than as a separate user message, was the cleanest fit
within the protocol. The Live API being a preview surface also meant
double-checking field names against the docs rather than memory.
