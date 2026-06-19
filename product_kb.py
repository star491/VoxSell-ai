"""
Product Knowledge Base for VoxSell AI.

This is sample data for a fictional SaaS product ("PulseMetrics" - a
real-time analytics dashboard) so the assignment can be demoed end-to-end.
In a real deployment, a business would swap this dict for their own
catalogue, pricing, and rebuttal playbook - nothing else in the codebase
needs to change.
"""

PRODUCT_KB = {
    "company_name": "PulseMetrics",
    "tagline": "Real-time analytics for teams that hate waiting for reports.",
    "product_summary": (
        "PulseMetrics is a real-time analytics dashboard that connects to a "
        "business's existing data sources (Stripe, Shopify, Postgres, Google "
        "Analytics) and turns them into live, no-code dashboards in under "
        "10 minutes, with no engineering work required."
    ),
    "key_features": [
        "Live dashboards that update every 5 seconds, not once a day",
        "Pre-built connectors for Stripe, Shopify, Postgres, and Google Analytics",
        "No-code chart builder - drag a metric onto a canvas",
        "Slack and email alerts when a metric crosses a threshold",
        "Role-based sharing so any teammate can view without a seat license",
    ],
    "pricing_tiers": [
        {
            "name": "Starter",
            "price_per_month_usd": 49,
            "best_for": "Solo founders and small teams up to 3 users",
            "includes": ["3 dashboards", "1 data connector", "Email alerts"],
        },
        {
            "name": "Growth",
            "price_per_month_usd": 149,
            "best_for": "Growing teams up to 15 users",
            "includes": ["Unlimited dashboards", "5 data connectors", "Slack + email alerts", "Role-based sharing"],
        },
        {
            "name": "Scale",
            "price_per_month_usd": 399,
            "best_for": "Companies that need every connector and priority support",
            "includes": ["Everything in Growth", "Unlimited connectors", "Priority support", "Custom SLA"],
        },
    ],
    "free_trial_days": 14,
    "faqs": [
        {
            "topic": "setup time",
            "question": "How long does setup take?",
            "answer": "Most customers connect their first data source and see live data within 10 minutes, with no engineering work required.",
        },
        {
            "topic": "contract length",
            "question": "Is there a long-term contract?",
            "answer": "No. Every plan is month-to-month and can be cancelled anytime from the billing page.",
        },
        {
            "topic": "data security",
            "question": "Is my data secure?",
            "answer": "Yes. All connections use read-only, OAuth-scoped credentials, and data is encrypted in transit and at rest.",
        },
        {
            "topic": "competitor comparison",
            "question": "How is this different from a generic BI tool?",
            "answer": "Generic BI tools update dashboards on a schedule (often daily). PulseMetrics is built for live, second-by-second metrics, with no SQL or engineering setup required.",
        },
    ],
    # Used by sales_engine.SalesStrategist to build the short, factual talking
    # point that gets injected as a steering note when an objection is detected.
    # Gemini still composes the actual spoken sentence - this is the *content*
    # it should weave in, not a script to read verbatim.
    "objection_rebuttals": {
        "price": (
            "Reframe cost as ROI: Starter is $49/month, less than most teams "
            "spend on one wasted ad-hoc report. Mention the 14-day free trial "
            "so they can see value before paying anything."
        ),
        "trust": (
            "Build credibility: connections are read-only and OAuth-scoped, "
            "data is encrypted in transit and at rest, and there's a 14-day "
            "free trial so they can verify value themselves before committing."
        ),
        "timing": (
            "Lower the commitment, not the urgency: setup takes about 10 "
            "minutes and the trial is free, so there's no reason waiting "
            "helps them - offer to send a 2-minute setup link they can use "
            "whenever is convenient."
        ),
        "need": (
            "Re-qualify the need with a specific, low-effort question about "
            "how they currently track metrics today, and connect PulseMetrics "
            "to whatever gap that answer reveals rather than re-pitching "
            "generic features."
        ),
        "competitor": (
            "Differentiate on speed, not features: most BI tools refresh on "
            "a schedule (often daily); PulseMetrics updates every 5 seconds "
            "with no SQL or engineering work needed."
        ),
        "authority": (
            "Make it easy to bring someone else in: offer to send a short "
            "summary or join a 10-minute call with whoever else needs to "
            "weigh in, instead of pressing for a same-call decision."
        ),
    },
}


def find_relevant_info(query: str) -> str:
    """
    Very small keyword lookup over the KB, used by the get_product_info
    tool that Gemini can call mid-call. Returns a short, factual string -
    Gemini decides how to phrase it out loud.
    """
    q = query.lower()

    if any(k in q for k in ("price", "pricing", "cost", "plan", "tier", "month")):
        lines = [
            f"{t['name']}: ${t['price_per_month_usd']}/month - {t['best_for']}"
            for t in PRODUCT_KB["pricing_tiers"]
        ]
        return "Pricing tiers: " + "; ".join(lines) + f". There is a {PRODUCT_KB['free_trial_days']}-day free trial on every plan."

    if any(k in q for k in ("feature", "what does it do", "capability", "what is")):
        return PRODUCT_KB["product_summary"] + " Key features: " + ", ".join(PRODUCT_KB["key_features"]) + "."

    if any(k in q for k in ("setup", "install", "onboard", "implement")):
        return next(f["answer"] for f in PRODUCT_KB["faqs"] if f["topic"] == "setup time")

    if any(k in q for k in ("secur", "safe", "encrypt", "privacy")):
        return next(f["answer"] for f in PRODUCT_KB["faqs"] if f["topic"] == "data security")

    if any(k in q for k in ("contract", "commitment", "cancel")):
        return next(f["answer"] for f in PRODUCT_KB["faqs"] if f["topic"] == "contract length")

    if any(k in q for k in ("competitor", "compare", "versus", "vs", "alternative")):
        return next(f["answer"] for f in PRODUCT_KB["faqs"] if f["topic"] == "competitor comparison")

    if any(k in q for k in ("trial", "free")):
        return f"There is a {PRODUCT_KB['free_trial_days']}-day free trial with full access, no credit card surprises."

    # Fallback: hand back the general summary rather than an empty answer.
    return PRODUCT_KB["product_summary"]
