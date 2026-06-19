"""
Everything specific to talking to the Gemini 2.5 Flash Native Audio
(Live API) protocol lives in this file, so server.py stays about
orchestration rather than wire-format details.

Reference docs (per Week 3 curriculum):
  - Get started with Gemini Live API using WebSockets
  - Live API - WebSockets API Reference (tool use messages)
Double-check field names against the latest docs before a real demo -
this is a preview model and field names have moved before.
"""

import base64
import json
import os

MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025"

# v1beta is the standard, stable Live API endpoint. Swap for v1alpha only if
# you turn on experimental features like Affective Dialog or Proactive Audio.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_WS_URL = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
    f"?key={GEMINI_API_KEY}"
)

SYSTEM_INSTRUCTION = (
    "You are Alex, a warm, confident voice sales agent for PulseMetrics, a "
    "real-time analytics dashboard. Your job is to understand the "
    "customer's needs, answer questions accurately using the "
    "get_product_info tool rather than guessing, handle objections with "
    "empathy first and facts second, and move genuinely interested "
    "customers toward booking a demo with the schedule_demo tool. Never "
    "be pushy with someone who has said no. Keep responses conversational "
    "and brief, like a real phone call, not a monologue. If you receive an "
    "internal coach note in the conversation, follow its guidance silently "
    "and never mention that a note exists."
)

TOOL_DECLARATIONS = [
    {
        "name": "get_current_time",
        "description": "Returns the current local time. Use only if the customer explicitly asks what time it is.",
        "parameters": {"type": "OBJECT", "properties": {}, "required": []},
    },
    {
        "name": "get_product_info",
        "description": (
            "Looks up a factual answer about PulseMetrics (pricing, features, "
            "setup, security, contracts, competitor comparisons) in the "
            "product knowledge base. Always use this instead of guessing "
            "facts about the product."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "What the customer wants to know, e.g. 'pricing' or 'is it secure'.",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "schedule_demo",
        "description": "Books a product demo once the customer has agreed to one.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "customer_name": {"type": "STRING", "description": "The customer's name, if known."},
                "preferred_time": {"type": "STRING", "description": "When the customer wants the demo."},
            },
            "required": ["preferred_time"],
        },
    },
]


def build_setup_message() -> str:
    """The BidiGenerateContentSetup message - must be the first message sent."""
    setup = {
        "setup": {
            "model": MODEL,
            "generationConfig": {"responseModalities": ["AUDIO"]},
            "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
            "tools": [{"functionDeclarations": TOOL_DECLARATIONS}],
            # Live transcripts are what let the rule-based Sales Intelligence
            # Layer "see" the conversation without running a second model.
            "inputAudioTranscription": {},
            "outputAudioTranscription": {},
        }
    }
    return json.dumps(setup)


def build_realtime_audio_chunk(raw_pcm16_16khz: bytes) -> str:
    """Wraps a raw mic chunk for Gemini's realtimeInput message."""
    encoded = base64.b64encode(raw_pcm16_16khz).decode("ascii")
    message = {
        "realtimeInput": {
            "audio": {"data": encoded, "mimeType": "audio/pcm;rate=16000"}
        }
    }
    return json.dumps(message)


def build_steering_note(note_text: str) -> str:
    """
    Injects a text-only turn into the *current* turn (turnComplete: False)
    so it influences the model's next spoken response without ever being
    heard by the customer. This is how the rule-based objection detector
    steers Gemini's natural-language reply.
    """
    message = {
        "clientContent": {
            "turns": [{"role": "user", "parts": [{"text": note_text}]}],
            "turnComplete": False,
        }
    }
    return json.dumps(message)


def build_tool_response(call_id: str, name: str, response: dict) -> str:
    message = {
        "toolResponse": {
            "functionResponses": [{"id": call_id, "name": name, "response": response}]
        }
    }
    return json.dumps(message)


def extract_audio_bytes(server_message: dict) -> bytes | None:
    """Pulls inline base64 PCM audio out of a serverContent message, if present."""
    try:
        parts = server_message["serverContent"]["modelTurn"]["parts"]
    except (KeyError, TypeError):
        return None
    for part in parts:
        inline = part.get("inlineData")
        if inline and inline.get("mimeType", "").startswith("audio/"):
            return base64.b64decode(inline["data"])
    return None


def extract_input_transcript(server_message: dict) -> str | None:
    """Customer's words, transcribed by Gemini, as they arrive."""
    transcript = server_message.get("inputTranscription")
    return transcript.get("text") if transcript else None


def extract_output_transcript(server_message: dict) -> str | None:
    """Agent's (Gemini's) spoken words, transcribed, as they arrive."""
    transcript = server_message.get("outputTranscription")
    return transcript.get("text") if transcript else None


def extract_tool_calls(server_message: dict) -> list[dict]:
    try:
        return server_message["toolCall"]["functionCalls"]
    except (KeyError, TypeError):
        return []
