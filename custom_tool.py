"""Standalone Week 4 custom tool demo for VoxSell AI.

This demonstrates real tool logic without requiring Gemini:
- a local SQLite catalog query
- a local SQLite write for scored lead capture

Run with:
    python custom_tool.py
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DB_PATH = Path(__file__).with_name("voxsell_week4_demo.db")


plan_tool = {
    "name": "lookup_product_plan",
    "description": "Searches the VoxSell AI product catalog in SQLite and returns matching plans.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "plan_name": {"type": "STRING"},
            "use_case": {"type": "STRING"},
        },
        "required": [],
    },
}
lead_tool = {
    "name": "save_lead_profile",
    "description": "Stores a qualified sales lead in a local SQLite database and returns a lead score.",
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
}


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
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
                        "lead scoring, CRM-ready notes, pricing objection playbooks",
                    ),
                    (
                        "Scale",
                        799,
                        "multi-rep teams with repeatable sales motion",
                        "team analytics, custom playbooks, priority onboarding",
                    ),
                ],
            )


def lookup_product_plan(plan_name: str = "", use_case: str = "") -> dict:
    init_db()
    plan_name = (plan_name or "").strip()
    use_case = (use_case or "").strip()
    query = "SELECT name, price_usd, best_for, features FROM product_plans"
    params = []
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

    return {"matches": [dict(row) for row in rows]}


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


def save_lead_profile(
    company_name: str,
    pain_point: str,
    contact_name: str = "",
    budget_usd: float = 0,
    timeline: str = "",
    team_size: int = 0,
) -> dict:
    init_db()
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
    return {"lead_id": lead_id, "lead_score": score, "tier": tier, "stored_in": str(DB_PATH)}


fake_tool_call = {
    "toolCall": {
        "functionCalls": [
            {
                "id": "call-001",
                "name": "lookup_product_plan",
                "args": {"use_case": "lead scoring and follow ups"},
            },
            {
                "id": "call-002",
                "name": "save_lead_profile",
                "args": {
                    "company_name": "Acme Retail",
                    "contact_name": "Riya",
                    "pain_point": "Manual follow ups are causing missed demos",
                    "budget_usd": 6000,
                    "timeline": "this month",
                    "team_size": 14,
                },
            },
        ]
    }
}

tool_functions = {
    "lookup_product_plan": lookup_product_plan,
    "save_lead_profile": save_lead_profile,
}

function_responses = []

for call in fake_tool_call["toolCall"]["functionCalls"]:
    result = tool_functions[call["name"]](**call["args"])
    print(f"Executed {call['name']} -> {result}")
    function_responses.append(
        {"id": call["id"], "name": call["name"], "response": {"output": result}}
    )

tool_response = {"toolResponse": {"functionResponses": function_responses}}

print("\nSend this JSON back over the Live API WebSocket:")
print(json.dumps(tool_response, indent=2))
