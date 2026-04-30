"""Pure-regex intent classifier for inbound merchant/customer replies.

Returns one of:
  - 'auto_reply'   : canned WhatsApp Business autoresponse (or repeat)
  - 'hard_no'      : explicit opt-out / annoyance
  - 'explicit_yes' : strong commit ("yes", "go ahead", "haan")
  - 'later'        : asks for delay
  - 'off_topic'    : asks about something outside the trigger (GST, taxes, weather, etc.)
  - 'engaged'      : genuine question / freeform → falls back to LLM responder
"""
from __future__ import annotations

import re

CANNED_PATTERNS = [
    r"thank you for contacting",
    r"team will (respond|get back|revert)",
    r"automated (response|assistant|message|reply)",
    r"out of office",
    r"will (get back|respond) (to you )?(soon|shortly|asap)",
    r"office (hours|timings)",
    r"aapki jaankari ke liye.*shukriya",
    r"team tak pahuncha (denge|diya)",
    r"not currently available",
    r"away from",
    r"working hours",
]

YES_PATTERNS = [
    r"\byes\b", r"\byess+\b", r"\byep\b", r"\bsure\b",
    r"\bok(ay)?\b", r"\bgo ahead\b", r"\blet'?s do\b",
    r"\bproceed\b", r"\bconfirm(ed)?\b", r"\bdo it\b",
    r"\bsounds good\b", r"\bplease (send|share|draft|do)\b",
    r"\bhaan\b", r"\bha+n+\b", r"\bkaro\b", r"\bjaa+o?\b",
    r"\bchalega\b", r"\bbilkul\b", r"\bzaroor\b", r"\btheek hai\b",
]

HARD_NO_PATTERNS = [
    r"\bnot interested\b", r"\bdon'?t (message|contact|send|call)\b",
    r"\bstop\b", r"\bunsubscribe\b", r"\bopt.?out\b",
    r"\bremove me\b", r"\bdo not (message|contact)\b",
    r"\bband karo\b", r"\bband kar\b", r"\bmat bhejo\b", r"\bmat karo\b",
    r"\bbothering\b", r"\bspam(ming)?\b", r"\bannoying\b", r"\buseless\b",
    r"\bkoi (faayda|fayda) nahi\b",
]

LATER_PATTERNS = [
    r"\b(call|message|talk|connect|discuss)( me)? later\b",
    r"\bnext week\b", r"\bnext month\b",
    r"\bbusy (right now|today|abhi)\b",
    r"\bbaad mein\b", r"\bbaad me\b", r"\bkal\b", r"\babhi nahi\b",
    r"\bgive me (a|some )?(day|time|while)\b",
    r"\bremind me (later|tomorrow|next)\b",
]

# Off-topic keywords that don't relate to magicpin merchant growth.
OFF_TOPIC_PATTERNS = [
    r"\bgst\b", r"\bincome tax\b", r"\baccount(ing|ant)\b", r"\bca\b\s*(file|filing)",
    r"\bweather\b", r"\bcricket(?! match offer)\b",
    r"\binsurance\b", r"\brent(al)?\b",
    r"\bemployee (problem|issue)\b", r"\bsalary\b", r"\bhiring\b",
    r"\blegal (advice|notice)\b", r"\bcourt\b",
    r"\bloan\b", r"\bbank account\b",
]


def _norm(text: str) -> str:
    return (text or "").strip().lower()


def _matches_any(text: str, patterns: list[str]) -> bool:
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            return True
    return False


def classify(message: str, repeat_count: int = 0) -> tuple[str, str]:
    """Return (intent, brief_reason). Order matters — most decisive first."""
    text = _norm(message)
    if not text:
        return "engaged", "empty body"

    if _matches_any(text, HARD_NO_PATTERNS):
        return "hard_no", "matched hard-no pattern"

    if _matches_any(text, CANNED_PATTERNS):
        return "auto_reply", "matched canned auto-reply pattern"

    # If we've seen this exact body 2+ times → it's an auto-reply even if no canned pattern.
    if repeat_count >= 1:
        return "auto_reply", f"identical inbound body seen {repeat_count + 1} times"

    if _matches_any(text, LATER_PATTERNS):
        return "later", "matched later/defer pattern"

    if _matches_any(text, OFF_TOPIC_PATTERNS):
        return "off_topic", "matched off-topic pattern"

    if _matches_any(text, YES_PATTERNS) and len(text) <= 50:
        # Short affirmative is a clean yes; long messages with "yes" in them go to engaged.
        return "explicit_yes", "matched explicit-yes pattern (short)"

    return "engaged", "no decisive pattern; freeform engagement"
