import asyncio
import base64
import json
import os
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import uvicorn
import websockets
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DB_PATH = BASE_DIR / "voxsell_week4.db"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-2.5-flash-native-audio-preview-12-2025",
)
GEMINI_WS_URL = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
    f"?key={GEMINI_API_KEY}"
)

SYSTEM_INSTRUCTION = """
# IDENTITY
You are Nira, VoxSell AI's sharp, friendly sales copilot for small teams.
You sound human on voice: short sentences, no markdown, no long lists.

# OPERATIONAL BOUNDARY
You only help with VoxSell AI product questions, plan fit, pricing context,
lead qualification, objections, and next steps. If the user asks for something
unrelated, redirect in one sentence and offer to help with VoxSell.

# TONE
Warm, practical, and no-nonsense. If the buyer sounds rushed, be brief. If they
sound uncertain, slow down and ask one clear question.

# TOOL RULES
Use lookup_product_plan before recommending a plan. Use get_live_exchange_rate
when the buyer asks about pricing in another currency. Use save_lead_profile
when you have enough lead details to capture company, pain, budget, timeline,
or team size. Never invent catalog data.

# GUARDRAILS
Keep API keys private. If a tool fails, say so plainly and continue the call.
"""


app = FastAPI(title="VoxSell AI Week 4")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "message": "VoxSell AI Week 4 backend is running",
        "model": model_path(),
        "api_key_configured": bool(GEMINI_API_KEY),
        "database": str(DB_PATH),
    }


@app.websocket("/ws")
async def proxy_endpoint(client_ws: WebSocket):
    await client_ws.accept()

    if not GEMINI_API_KEY:
        await send_client_json(
            client_ws,
            {
                "type": "error",
                "message": "Missing GEMINI_API_KEY in .env on the backend.",
            },
        )
        await client_ws.close(code=1011)
        return

    try:
        async with websockets.connect(GEMINI_WS_URL, max_size=None) as gemini_ws:
            await gemini_ws.send(json.dumps(build_setup_message()))
            await send_client_json(client_ws, {"type": "status", "message": "Connected to Gemini"})

            client_to_gemini = asyncio.create_task(forward_client_to_gemini(client_ws, gemini_ws))
            gemini_to_client = asyncio.create_task(forward_gemini_to_client(gemini_ws, client_ws))

            done, pending = await asyncio.wait(
                {client_to_gemini, gemini_to_client},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            for task in done:
                task.result()
    except WebSocketDisconnect:
        return
    except Exception as exc:
        await send_client_json(client_ws, {"type": "error", "message": str(exc)})
        await client_ws.close(code=1011)


def model_path() -> str:
    return GEMINI_MODEL if GEMINI_MODEL.startswith("models/") else f"models/{GEMINI_MODEL}"


def build_setup_message() -> dict:
    return {
        "setup": {
            "model": model_path(),
            "generationConfig": {"responseModalities": ["AUDIO"]},
            "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION.strip()}]},
            "tools": [{"functionDeclarations": tool_declarations()}],
        }
    }


def tool_declarations() -> list[dict]:
    return [
        {
            "name": "lookup_product_plan",
            "description": "Searches the VoxSell AI product catalog in SQLite and returns matching plans.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "plan_name": {
                        "type": "STRING",
                        "description": "Optional plan name such as Starter, Growth, or Scale.",
                    },
                    "use_case": {
                        "type": "STRING",
                        "description": "The buyer's use case or need, such as lead scoring or follow ups.",
                    },
                },
                "required": [],
            },
        },
        {
            "name": "save_lead_profile",
            "description": "Stores a qualified lead in SQLite and returns a computed lead score.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "company_name": {"type": "STRING"},
                    "contact_name": {"type": "STRING"},
                    "pain_point": {"type": "STRING"},
                    "budget_usd": {"type": "NUMBER"},
                    "timeline": {"type": "STRING"},
                    "team_size": {"type": "NUMBER"},
                },
                "required": ["company_name", "pain_point"],
            },
        },
        {
            "name": "get_live_exchange_rate",
            "description": "Converts an amount between currencies using the free Frankfurter public API.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "base_currency": {"type": "STRING"},
                    "quote_currency": {"type": "STRING"},
                    "amount": {"type": "NUMBER"},
                },
                "required": ["base_currency", "quote_currency"],
            },
        },
        {
            "name": "get_current_time",
            "description": "Returns the current local time for the requested IANA timezone.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "timezone": {
                        "type": "STRING",
                        "description": "Optional IANA timezone, for example Asia/Kolkata or America/New_York.",
                    }
                },
                "required": [],
            },
        },
    ]


async def forward_client_to_gemini(client_ws: WebSocket, gemini_ws):
    while True:
        message = await client_ws.receive()

        if "bytes" in message and message["bytes"]:
            await send_audio_chunk(gemini_ws, message["bytes"])
            continue

        if "text" not in message:
            continue

        try:
            payload = json.loads(message["text"])
        except json.JSONDecodeError:
            await send_text(gemini_ws, message["text"])
            continue

        message_type = payload.get("type")
        if message_type == "text":
            text = payload.get("text", "").strip()
            if text:
                await send_text(gemini_ws, text)
        elif message_type == "audio_end":
            await gemini_ws.send(json.dumps({"realtimeInput": {"audioStreamEnd": True}}))
        elif message_type == "ping":
            await send_client_json(client_ws, {"type": "status", "message": "Proxy is listening"})


async def forward_gemini_to_client(gemini_ws, client_ws: WebSocket):
    async for raw_message in gemini_ws:
        if isinstance(raw_message, bytes):
            await client_ws.send_bytes(raw_message)
            continue

        response = json.loads(raw_message)

        if "setupComplete" in response:
            await send_client_json(client_ws, {"type": "status", "message": "Gemini setup complete"})

        if "serverContent" in response:
            await handle_server_content(client_ws, response["serverContent"])

        if "toolCall" in response:
            await handle_tool_call(gemini_ws, client_ws, response["toolCall"])

        if "error" in response:
            await send_client_json(client_ws, {"type": "error", "message": response["error"]})


async def handle_server_content(client_ws: WebSocket, server_content: dict):
    if server_content.get("interrupted"):
        await send_client_json(client_ws, {"type": "flush", "reason": "interrupted"})
        return

    model_turn = server_content.get("modelTurn", {})
    for part in model_turn.get("parts", []):
        inline_data = part.get("inlineData")
        if inline_data and inline_data.get("data"):
            audio_bytes = base64.b64decode(inline_data["data"])
            await client_ws.send_bytes(audio_bytes)
        if "text" in part:
            await send_client_json(client_ws, {"type": "model_text", "text": part["text"]})

    if "inputTranscription" in server_content:
        await send_client_json(
            client_ws,
            {
                "type": "input_transcript",
                "text": server_content["inputTranscription"].get("text", ""),
            },
        )

    if "outputTranscription" in server_content:
        await send_client_json(
            client_ws,
            {
                "type": "output_transcript",
                "text": server_content["outputTranscription"].get("text", ""),
            },
        )

    if server_content.get("turnComplete"):
        await send_client_json(client_ws, {"type": "turn_complete"})


async def send_audio_chunk(gemini_ws, chunk_bytes: bytes):
    encoded = base64.b64encode(chunk_bytes).decode("utf-8")
    await gemini_ws.send(
        json.dumps(
            {
                "realtimeInput": {
                    "audio": {
                        "data": encoded,
                        "mimeType": "audio/pcm;rate=16000",
                    }
                }
            }
        )
    )


async def send_text(gemini_ws, text: str):
    await gemini_ws.send(
        json.dumps(
            {
                "clientContent": {
                    "turns": [{"role": "user", "parts": [{"text": text}]}],
                    "turnComplete": True,
                }
            }
        )
    )


async def handle_tool_call(gemini_ws, client_ws: WebSocket, tool_call: dict):
    function_responses = []

    for function_call in tool_call.get("functionCalls", []):
        name = function_call.get("name")
        call_id = function_call.get("id")
        args = function_call.get("args", {})

        try:
            result = run_tool(name, args)
            response = {"output": result}
            await send_client_json(client_ws, {"type": "tool", "name": name, "result": result})
        except Exception as exc:
            response = {"error": str(exc)}
            await send_client_json(client_ws, {"type": "error", "message": f"Tool {name} failed: {exc}"})

        function_responses.append({"name": name, "id": call_id, "response": response})

    await gemini_ws.send(json.dumps({"toolResponse": {"functionResponses": function_responses}}))


def run_tool(name: str, args: dict) -> dict:
    if name == "lookup_product_plan":
        return lookup_product_plan(args.get("plan_name", ""), args.get("use_case", ""))
    if name == "save_lead_profile":
        return save_lead_profile(**args)
    if name == "get_live_exchange_rate":
        return get_live_exchange_rate(
            args.get("base_currency", "USD"),
            args.get("quote_currency", "INR"),
            args.get("amount", 1),
        )
    if name == "get_current_time":
        return get_current_time(args.get("timezone") or "Asia/Kolkata")
    raise ValueError(f"Unknown tool: {name}")


def init_week4_database():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS product_plans (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                price_usd INTEGER NOT NULL,
                best_for TEXT NOT NULL,
                features TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                contact_name TEXT,
                pain_point TEXT NOT NULL,
                budget_usd REAL DEFAULT 0,
                timeline TEXT,
                team_size INTEGER DEFAULT 0,
                lead_score INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        existing = conn.execute("SELECT COUNT(*) FROM product_plans").fetchone()[0]
        if existing == 0:
            conn.executemany(
                """
                INSERT INTO product_plans (name, price_usd, best_for, features)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        "Starter",
                        99,
                        "solo founders and tiny sales teams",
                        "voice lead capture, basic objection handling, call notes",
                    ),
                    (
                        "Growth",
                        299,
                        "teams that need lead scoring and follow-up discipline",
                        "all Starter features, lead scoring, CRM-ready notes, pricing objection playbooks",
                    ),
                    (
                        "Scale",
                        799,
                        "multi-rep teams with repeatable sales motion",
                        "all Growth features, team analytics, custom playbooks, priority onboarding",
                    ),
                ],
            )


def lookup_product_plan(plan_name: str = "", use_case: str = "") -> dict:
    init_week4_database()
    plan_name = (plan_name or "").strip()
    use_case = (use_case or "").strip()

    query = "SELECT name, price_usd, best_for, features FROM product_plans"
    params: list[str] = []
    filters = []

    if plan_name:
        filters.append("LOWER(name) LIKE ?")
        params.append(f"%{plan_name.lower()}%")
    if use_case:
        filters.append("(LOWER(best_for) LIKE ? OR LOWER(features) LIKE ?)")
        params.extend([f"%{use_case.lower()}%", f"%{use_case.lower()}%"])
    if filters:
        query += " WHERE " + " OR ".join(filters)
    query += " ORDER BY price_usd"

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()

    if not rows and use_case:
        tokens = [token for token in use_case.lower().replace("-", " ").split() if len(token) > 3]
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            all_rows = conn.execute(
                "SELECT name, price_usd, best_for, features FROM product_plans ORDER BY price_usd"
            ).fetchall()
        rows = [
            row
            for row in all_rows
            if any(token in f"{row['best_for']} {row['features']}".lower().replace("-", " ") for token in tokens)
        ]

    plans = [dict(row) for row in rows]
    if not plans:
        return {"matches": [], "message": "No exact plan match. Ask one qualifying question."}
    return {"matches": plans}


def save_lead_profile(
    company_name: str,
    pain_point: str,
    contact_name: str = "",
    budget_usd: float = 0,
    timeline: str = "",
    team_size: int = 0,
) -> dict:
    init_week4_database()
    score = score_lead(float(budget_usd or 0), timeline or "", int(team_size or 0), pain_point)
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            """
            INSERT INTO leads (
                company_name, contact_name, pain_point, budget_usd,
                timeline, team_size, lead_score, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (company_name, contact_name, pain_point, budget_usd, timeline, team_size, score, created_at),
        )
        lead_id = cursor.lastrowid

    tier = "hot" if score >= 75 else "warm" if score >= 45 else "nurture"
    next_step = "book a demo now" if tier == "hot" else "send a focused follow-up"
    return {"lead_id": lead_id, "lead_score": score, "tier": tier, "next_step": next_step}


def score_lead(budget_usd: float, timeline: str, team_size: int, pain_point: str) -> int:
    score = 20
    if budget_usd >= 5000:
        score += 30
    elif budget_usd >= 1000:
        score += 18
    if any(word in timeline.lower() for word in ["now", "today", "week", "month", "urgent"]):
        score += 25
    if team_size >= 10:
        score += 15
    if any(word in pain_point.lower() for word in ["miss", "lost", "slow", "manual", "follow"]):
        score += 10
    return min(score, 100)


def get_live_exchange_rate(base_currency: str, quote_currency: str, amount: float = 1) -> dict:
    base = (base_currency or "USD").upper().strip()
    quote = (quote_currency or "INR").upper().strip()
    amount = float(amount or 1)

    if base == quote:
        return {"base_currency": base, "quote_currency": quote, "rate": 1, "converted_amount": amount}

    params = urllib.parse.urlencode({"from": base, "to": quote})
    url = f"https://api.frankfurter.app/latest?{params}"

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        rate = float(payload["rates"][quote])
        return {
            "base_currency": base,
            "quote_currency": quote,
            "rate": rate,
            "amount": amount,
            "converted_amount": round(amount * rate, 2),
            "source": "Frankfurter public API",
        }
    except Exception as exc:
        return {"error": f"Exchange-rate service unavailable: {exc}"}


def get_current_time(timezone: str) -> dict:
    try:
        now = datetime.now(ZoneInfo(timezone))
    except ZoneInfoNotFoundError:
        timezone = "Asia/Kolkata"
        now = datetime.now(ZoneInfo(timezone))

    return {
        "timezone": timezone,
        "iso_time": now.isoformat(timespec="seconds"),
        "spoken_time": now.strftime("%I:%M %p on %A, %d %B %Y"),
    }


async def send_client_json(client_ws: WebSocket, payload: dict):
    await client_ws.send_text(json.dumps(payload))


init_week4_database()


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
