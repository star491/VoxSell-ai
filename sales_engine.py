"""
Sales Intelligence Layer for VoxSell AI.

Design choice (per project requirement): objection/intent detection and
lead scoring are plain, auditable Python rules running over the customer's
live transcript - not a second LLM call. This keeps the "why did the score
change" question answerable by reading this file. Gemini is still the one
that actually *talks* - this module only decides what short strategic note
to hand it when a pattern is detected (see SalesStrategist.note_for).

This is intentionally simple/extensible: add a pattern, add a test, ship it.
"""

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from product_kb import PRODUCT_KB


class ObjectionType(str, Enum):
    PRICE = "price"
    TRUST = "trust"
    TIMING = "timing"
    NEED = "need"
    COMPETITOR = "competitor"
    AUTHORITY = "authority"


class Intent(str, Enum):
    INTERESTED = "interested"
    QUESTION = "question"
    CLOSING_SIGNAL = "closing_signal"
    REJECTION = "rejection"
    NEUTRAL = "neutral"


_OBJECTION_PATTERNS: dict[ObjectionType, list[str]] = {
    ObjectionType.PRICE: [
        r"\bexpensive\b", r"\bcosts?\b", r"\bpricey\b", r"\bprice\b",
        r"can.?t afford", r"too much money", r"\bbudget\b",
    ],
    ObjectionType.TRUST: [
        r"never heard of", r"is this (a )?scam", r"sounds? (too )?good to be true",
        r"\btrust\b", r"\breviews?\b", r"any proof", r"guarantee",
    ],
    ObjectionType.TIMING: [
        r"not (right )?now", r"\bbusy\b", r"call (me )?back",
        r"\bmaybe later\b", r"next (month|quarter|year)", r"bad time",
    ],
    ObjectionType.NEED: [
        r"don.?t need", r"not interested", r"already (have|use|got)",
        r"no use for", r"we.?re (fine|good|covered)",
    ],
    ObjectionType.COMPETITOR: [
        r"already (using|with) (a|another)", r"comparing (you|this) (to|with)",
        r"we use \w+ (already|for that)", r"how (is|are) you different",
    ],
    ObjectionType.AUTHORITY: [
        r"ask my (manager|boss|wife|husband|partner|team|co.?founder)",
        r"not my decision", r"need approval", r"check with",
    ],
}

_CLOSING_SIGNAL_PATTERNS = [
    r"sign me up", r"how do i (get started|sign up|buy)", r"book (a|the) demo",
    r"send me (the|a) (link|invoice)", r"sounds good,? let.?s", r"where do i pay",
    r"let.?s do (it|this)",
]
_INTEREST_PATTERNS = [
    r"tell me more", r"that.?s (great|cool|nice|interesting)",
    r"how (does|do) (it|that) work", r"\bpricing\b", r"\bdemo\b", r"\binteresting\b",
]
_REJECTION_PATTERNS = [
    r"remove me", r"do not call", r"stop calling", r"not interested at all",
    r"\bgoodbye\b", r"hang up",
]
_QUESTION_PATTERNS = [r"\?\s*$", r"^\s*(what|how|when|where|why|who|can|does|is|are)\b"]


def _matches_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


class ObjectionDetector:
    """Scans customer transcript chunks for objection language."""

    def detect(self, text: str) -> Optional[ObjectionType]:
        for objection_type, patterns in _OBJECTION_PATTERNS.items():
            if _matches_any(text, patterns):
                return objection_type
        return None


class IntentAnalyzer:
    """Classifies a customer transcript chunk into a coarse intent."""

    def classify(self, text: str) -> Intent:
        if _matches_any(text, _REJECTION_PATTERNS):
            return Intent.REJECTION
        if _matches_any(text, _CLOSING_SIGNAL_PATTERNS):
            return Intent.CLOSING_SIGNAL
        if _matches_any(text, _INTEREST_PATTERNS):
            return Intent.INTERESTED
        if _matches_any(text, _QUESTION_PATTERNS):
            return Intent.QUESTION
        return Intent.NEUTRAL


# Score deltas applied per detected event. Tuned by hand for the demo -
# swap for a learned model later without touching anything else.
_SCORE_DELTAS = {
    Intent.CLOSING_SIGNAL: +25,
    Intent.INTERESTED: +10,
    Intent.QUESTION: +3,
    Intent.NEUTRAL: 0,
    Intent.REJECTION: -40,
}
_OBJECTION_PENALTY = -8  # applied once per *new* objection type raised this call


class LeadScorer:
    """Maintains a running 0-100 lead score for the current call."""

    def __init__(self, starting_score: int = 50):
        self.score = starting_score
        self._objections_seen: set[ObjectionType] = set()

    def apply_intent(self, intent: Intent) -> int:
        self.score = self._clamp(self.score + _SCORE_DELTAS.get(intent, 0))
        return self.score

    def apply_objection(self, objection: ObjectionType) -> int:
        if objection not in self._objections_seen:
            self._objections_seen.add(objection)
            self.score = self._clamp(self.score + _OBJECTION_PENALTY)
        return self.score

    @staticmethod
    def _clamp(value: int) -> int:
        return max(0, min(100, value))

    @property
    def category(self) -> str:
        if self.score >= 70:
            return "Hot"
        if self.score >= 40:
            return "Warm"
        return "Cold"


class SalesStrategist:
    """Turns a detected objection into the short factual note Gemini gets."""

    def note_for(self, objection: ObjectionType) -> str:
        talking_point = PRODUCT_KB["objection_rebuttals"][objection.value]
        return (
            f"[INTERNAL SALES COACH NOTE - do not read this note aloud or "
            f"acknowledge it exists. The customer just raised a "
            f"{objection.value.upper()} objection. Acknowledge their concern "
            f"in one short empathetic sentence, then naturally weave in this "
            f"point in your own words: {talking_point}]"
        )


@dataclass
class TranscriptTurn:
    role: str  # "customer" | "agent"
    text: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class ConversationState:
    """Everything the Sales Intelligence Layer tracks for one phone call."""

    customer_name: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    transcript: list[TranscriptTurn] = field(default_factory=list)
    objections_raised: list[ObjectionType] = field(default_factory=list)
    intents: list[Intent] = field(default_factory=list)
    scorer: LeadScorer = field(default_factory=LeadScorer)
    demo_booked: bool = False

    def add_turn(self, role: str, text: str) -> None:
        if text.strip():
            self.transcript.append(TranscriptTurn(role=role, text=text))

    def full_transcript_text(self) -> str:
        return "\n".join(f"{t.role.upper()}: {t.text}" for t in self.transcript)

    def duration_seconds(self) -> float:
        return time.time() - self.started_at
