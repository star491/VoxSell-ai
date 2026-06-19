"""
Tool implementations for VoxSell AI.

These are the Python functions that actually run when Gemini emits a
`toolCall`. Each function's signature matches the matching entry in
gemini_session.TOOL_DECLARATIONS. Keep these side-effect-light and fast -
the call is live, so the customer is waiting on the result.
"""

import datetime
from typing import Any

from product_kb import find_relevant_info


def get_current_time(args: dict[str, Any]) -> dict[str, Any]:
    """
    The 'guided tool' required by Module 4 / the assignment baseline.
    Kept even though VoxSell AI's real tools are business tools below,
    so the curriculum's explicit "what time is it" requirement is met.
    """
    now = datetime.datetime.now().strftime("%I:%M %p on %A, %B %d")
    return {"current_time": now}


def get_product_info(args: dict[str, Any]) -> dict[str, Any]:
    """Looks up a factual answer in the Product Knowledge Base."""
    query = args.get("query", "")
    return {"answer": find_relevant_info(query)}


def schedule_demo(args: dict[str, Any]) -> dict[str, Any]:
    """
    Simulates booking a demo / desired next action. In production this
    would call a real calendar API (e.g. Calendly, Google Calendar) -
    swapping the body of this function is the only change needed.
    """
    name = args.get("customer_name", "the customer")
    preferred_time = args.get("preferred_time", "a time to be confirmed")
    return {
        "status": "booked",
        "confirmation": f"Demo tentatively booked for {name} at {preferred_time}. "
        f"A confirmation email/calendar invite will follow.",
    }


# Dispatch table used by server.py when a toolCall arrives.
TOOL_REGISTRY = {
    "get_current_time": get_current_time,
    "get_product_info": get_product_info,
    "schedule_demo": schedule_demo,
}
