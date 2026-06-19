"""
VoxSell AI backend - the "Middleman Proxy Server" from Module 3, extended
with the Sales Intelligence Layer and tool calling from Module 4/5.

Architecture (see SUBMISSION.md for the full writeup):

    Browser (mic)             This server                  Gemini Live API
    -------------             ------------                  ---------------
    raw PCM16 @16kHz  --(binary WS frame)-->  base64-wrap  --(JSON WS)-->
    raw PCM16 @24kHz  <--(binary WS frame)--  base64-decode <--(JSON WS)--
    JSON control msgs <-(text WS frames)->    orchestration

The frontend never talks to Gemini directly, and the Gemini API key never
leaves this process (Security requirement).
"""

import asyncio
import json
import os

import uvicorn
import websockets
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

import gemini_session as gs
from sales_engine import ConversationState, IntentAnalyzer, LeadScorer, ObjectionDetector, SalesStrategist
from summary import generate_call_summary
from tools import TOOL_REGISTRY

load_dotenv()

app = FastAPI(title="VoxSell AI Backend")

# Loosened for local dev against the Vite dev server. Tighten before shipping.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

objection_detector = ObjectionDetector()
intent_analyzer = IntentAnalyzer()
strategist = SalesStrategist()


@app.get("/health")
def health_check():
    return {"status": "ok", "message": "VoxSell AI proxy is running", "configured": bool(os.getenv("GEMINI_API_KEY"))}


async def _send_json(client_ws: WebSocket, payload: dict) -> None:
    try:
        await client_ws.send_text(json.dumps(payload))
    except Exception:
        pass  # client may already be gone; the outer loop will notice and stop


async def _handle_tool_call(gemini_ws, client_ws: WebSocket, function_calls: list[dict], state: ConversationState) -> None:
    for call in function_calls:
        name = call.get("name")
        call_id = call.get("id")
        args = call.get("args", {}) or {}

        handler = TOOL_REGISTRY.get(name)
        if handler is None:
            result = {"error": f"Unknown tool '{name}'"}
        else:
            result = handler(args)
            if name == "schedule_demo" and result.get("status") == "booked":
                state.demo_booked = True

        await _send_json(client_ws, {"type": "tool_call", "name": name, "args": args, "result": result})
        await gemini_ws.send(gs.build_tool_response(call_id, name, result))


async def client_to_gemini(client_ws: WebSocket, gemini_ws, state: ConversationState, stop_event: asyncio.Event) -> None:
    """Forwards mic audio + control messages from the browser into Gemini."""
    try:
        while not stop_event.is_set():
            message = await client_ws.receive()

            if message.get("type") == "websocket.disconnect":
                break

            if "bytes" in message and message["bytes"] is not None:
                await gemini_ws.send(gs.build_realtime_audio_chunk(message["bytes"]))

            elif "text" in message and message["text"] is not None:
                try:
                    control = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue
                if control.get("type") == "end_call":
                    stop_event.set()
                    break
    except WebSocketDisconnect:
        pass
    finally:
        stop_event.set()


async def gemini_to_client(client_ws: WebSocket, gemini_ws, state: ConversationState, stop_event: asyncio.Event) -> None:
    """Forwards Gemini's audio/text back to the browser and runs the Sales Intelligence Layer."""
    objection_already_flagged_this_turn = False

    try:
        async for raw in gemini_ws:
            if stop_event.is_set():
                break

            if isinstance(raw, bytes):
                # Some Live API responses arrive as raw binary frames rather
                # than JSON+base64 - forward untouched (per the curriculum's
                # own framing of how the proxy must handle this).
                await client_ws.send_bytes(raw)
                continue

            try:
                server_message = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if server_message.get("setupComplete") is not None:
                await _send_json(client_ws, {"type": "ready"})
                continue

            audio_bytes = gs.extract_audio_bytes(server_message)
            if audio_bytes:
                await client_ws.send_bytes(audio_bytes)

            input_text = gs.extract_input_transcript(server_message)
            if input_text:
                state.add_turn("customer", input_text)
                await _send_json(client_ws, {"type": "transcript", "role": "customer", "text": input_text})

                intent = intent_analyzer.classify(input_text)
                state.intents.append(intent)
                score = state.scorer.apply_intent(intent)
                await _send_json(client_ws, {"type": "lead_score", "score": score, "category": state.scorer.category})

                objection = objection_detector.detect(input_text)
                if objection and not objection_already_flagged_this_turn:
                    state.objections_raised.append(objection)
                    score = state.scorer.apply_objection(objection)
                    note = strategist.note_for(objection)
                    await gemini_ws.send(gs.build_steering_note(note))
                    await _send_json(client_ws, {
                        "type": "objection_detected",
                        "objection": objection.value,
                        "lead_score": score,
                        "category": state.scorer.category,
                    })
                    objection_already_flagged_this_turn = True

            output_text = gs.extract_output_transcript(server_message)
            if output_text:
                state.add_turn("agent", output_text)
                await _send_json(client_ws, {"type": "transcript", "role": "agent", "text": output_text})

            turn_complete = server_message.get("serverContent", {}).get("turnComplete")
            if turn_complete:
                objection_already_flagged_this_turn = False

            tool_calls = gs.extract_tool_calls(server_message)
            if tool_calls:
                await _handle_tool_call(gemini_ws, client_ws, tool_calls, state)

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        stop_event.set()


@app.websocket("/ws")
async def proxy_endpoint(client_ws: WebSocket):
    await client_ws.accept()
    state = ConversationState()
    stop_event = asyncio.Event()

    if not os.getenv("GEMINI_API_KEY"):
        await _send_json(client_ws, {"type": "error", "message": "Server is missing GEMINI_API_KEY. See backend/.env.example."})
        await client_ws.close()
        return

    try:
        async with websockets.connect(gs.GEMINI_WS_URL, max_size=None) as gemini_ws:
            # First message on a fresh session MUST be the setup message.
            await gemini_ws.send(gs.build_setup_message())

            await asyncio.gather(
                client_to_gemini(client_ws, gemini_ws, state, stop_event),
                gemini_to_client(client_ws, gemini_ws, state, stop_event),
            )
    except Exception as exc:  # noqa: BLE001 - surface to the UI instead of a silent 500
        await _send_json(client_ws, {"type": "error", "message": f"Upstream connection failed: {exc}"})

    # Call is over either way - generate the summary the spec asks for.
    summary = generate_call_summary(state)
    await _send_json(client_ws, {
        "type": "call_summary",
        "summary": summary,
        "final_score": state.scorer.score,
        "category": state.scorer.category,
        "objections_raised": [o.value for o in state.objections_raised],
        "demo_booked": state.demo_booked,
        "duration_seconds": round(state.duration_seconds(), 1),
    })

    try:
        await client_ws.close()
    except Exception:
        pass


if __name__ == "__main__":
    print("Starting VoxSell AI proxy on http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
