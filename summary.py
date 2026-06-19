"""
Generates the post-call summary required by the spec ("Automatic call
summary generation"). Deliberately uses a plain REST call to
gemini-2.5-flash rather than the Live session - the call is already over,
so there's no need to keep paying for a live audio connection, and this
doubles as a callback to the Module 1 REST pattern from the curriculum.
"""

import os
import requests

from sales_engine import ConversationState

REST_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"


def generate_call_summary(state: ConversationState) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "[No GEMINI_API_KEY configured - skipping summary generation.]"

    transcript = state.full_transcript_text()
    if not transcript.strip():
        return "Call ended before any conversation was recorded."

    prompt = (
        "Summarize this sales call transcript in 3-4 sentences for a sales "
        "manager: what the customer needed, any objections raised, and the "
        "outcome (e.g. demo booked, follow-up needed, not interested). "
        "Be factual and concise.\n\n"
        f"Lead score at end of call: {state.scorer.score}/100 ({state.scorer.category})\n"
        f"Demo booked: {state.demo_booked}\n\n"
        f"Transcript:\n{transcript}"
    )

    headers = {"x-goog-api-key": api_key}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        response = requests.post(REST_URL, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as exc:  # noqa: BLE001 - this is a best-effort nicety, never crash the call on it
        return f"[Summary generation failed: {exc}]"
