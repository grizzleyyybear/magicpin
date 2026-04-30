"""Deterministic post-LLM validators. Run AFTER every Writer/Responder output.

API:
    result = validate(message, ctx)        # returns ValidationResult
    if not result.ok and result.retry_hint:
        retry_with_hint(...)
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

URL_RE = re.compile(r"(https?://\S+|www\.\S+|\b[a-z0-9-]+\.(com|in|org|net|io|co|app|me)\b)", re.IGNORECASE)
DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
ROMAN_HINDI_TOKENS = {
    "aap", "aapko", "aapke", "aapki", "aapka", "kya", "kyun", "kyon", "kyu",
    "hai", "hain", "haan", "nahi", "nahin", "nai", "main", "mein", "mei",
    "kar", "karo", "karna", "karenge", "karein", "karein.", "karu", "karoon",
    "abhi", "kal", "aaj", "aur", "bhi", "ya", "ki", "ke", "ka", "ko", "se",
    "par", "ho", "hoga", "hogi", "hoon", "hun", "raha", "rahi", "rahe",
    "chahiye", "chahta", "chahti", "chalega", "chaliye", "chalo", "chal",
    "ji", "shukriya", "dhanyawad", "namaste", "swagat", "thik", "theek",
    "samjha", "samjhi", "samajh", "milte", "milegi", "milega", "milta",
    "baat", "baad", "phir", "saath", "ek", "do", "teen", "char", "paanch",
    "wala", "wali", "waale", "kuch", "sab", "sabhi", "yeh", "woh", "vo",
    "iska", "uska", "iski", "uski", "ismein", "usmein", "kyunki", "agar",
    "lekin", "magar", "fir", "iske", "uske", "saare",
}

CTA_QUESTION_HINTS = {
    "yes_no": [
        "?",
        "yes/no", "y/n", "haan ya nahi", "haan?", "nahi?",
        "shall i", "should i", "want me to", "would you like",
        "ready?", "confirm?", "reply yes", "reply y",
    ],
    "open_ended": ["?"],
}


@dataclass
class ValidationResult:
    ok: bool
    issues: list[str] = field(default_factory=list)
    retry_hint: Optional[str] = None
    auto_fixed: dict = field(default_factory=dict)


@dataclass
class GuardContext:
    """Bundles everything a guard needs to look at."""
    body: str
    cta: str
    suppression_key: str
    rationale: str

    category: dict
    merchant: dict
    trigger: dict
    customer: Optional[dict]

    previous_sent_bodies: list[str]
    decision_brief: dict


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s).strip().lower()


def _has_hindi(text: str) -> bool:
    if DEVANAGARI_RE.search(text):
        return True
    tokens = re.findall(r"[a-zA-Z']+", text.lower())
    return any(t in ROMAN_HINDI_TOKENS for t in tokens)


def _hindi_token_count(text: str) -> int:
    n = len(DEVANAGARI_RE.findall(text))
    tokens = re.findall(r"[a-zA-Z']+", text.lower())
    n += sum(1 for t in tokens if t in ROMAN_HINDI_TOKENS)
    return n


def _flatten_context_strings(ctx: GuardContext) -> str:
    """Concatenate every string we'd accept as 'a context fact' for substring checks."""
    bits: list[str] = []

    def push(x):
        if x is None: return
        if isinstance(x, (str, int, float)):
            bits.append(str(x))
        elif isinstance(x, dict):
            for v in x.values():
                push(v)
        elif isinstance(x, list):
            for v in x:
                push(v)

    push(ctx.category)
    push(ctx.merchant)
    push(ctx.trigger)
    push(ctx.customer)
    return " ".join(bits)


def _numbers_in(text: str) -> list[str]:
    return re.findall(r"\b\d[\d,./%-]*\b", text)


def _cta_matches_shape(body: str, cta: str) -> bool:
    if cta == "none":
        return True
    body_l = body.lower()
    hints = CTA_QUESTION_HINTS.get(cta, [])
    return any(h in body_l for h in hints)


# ---------- individual checks ----------

def check_url(ctx: GuardContext) -> Optional[str]:
    m = URL_RE.search(ctx.body)
    if m:
        return f"Body contains a URL ('{m.group(0)}'). Remove all URLs and links — Meta will reject the message."
    return None


def check_taboo_vocab(ctx: GuardContext) -> Optional[str]:
    voice = (ctx.category or {}).get("voice", {})
    taboo = voice.get("vocab_taboo", []) or []
    body_l = ctx.body.lower()
    for word in taboo:
        if not isinstance(word, str): continue
        w = word.lower().strip()
        if not w: continue
        if w in body_l:
            return f"Body contains a taboo word for this category: '{word}'. Rephrase without it."
    return None


def check_cta_value(ctx: GuardContext) -> Optional[str]:
    if ctx.cta not in ("yes_no", "open_ended", "none"):
        return f"cta must be one of: yes_no, open_ended, none (got '{ctx.cta}')."
    if not _cta_matches_shape(ctx.body, ctx.cta):
        return f"cta is '{ctx.cta}' but body doesn't end with a matching CTA. Add a clear question or YES/NO ask as the last sentence."
    return None


def check_hindi_when_required(ctx: GuardContext) -> Optional[str]:
    langs = ((ctx.merchant or {}).get("identity") or {}).get("languages", []) or []
    if "hi" not in langs:
        return None
    if _hindi_token_count(ctx.body) < 1:
        return ("Merchant language preference includes 'hi'. Rewrite as natural Hindi-English code-mix "
                "(e.g., use words like 'aapke', 'kya', 'chalega', 'haan', 'karu').")
    return None


def check_no_repeat(ctx: GuardContext) -> Optional[str]:
    body_norm = _norm(ctx.body)
    for prev in ctx.previous_sent_bodies or []:
        if _norm(prev) == body_norm:
            return "Body is a verbatim repeat of a previously sent message. Reword with a fresh angle."
    return None


def check_must_cite_fact(ctx: GuardContext) -> Optional[str]:
    """At least one number/date/source/offer-title from contexts must appear in body."""
    body = ctx.body or ""
    flat = _flatten_context_strings(ctx).lower()
    body_l = body.lower()

    # Pass if the body contains any number that also appears in the contexts.
    nums = _numbers_in(body)
    for n in nums:
        if n.strip(",.%-/") and n.lower() in flat:
            return None

    # Pass if any offer title from offer_catalog or merchant.offers appears in body.
    titles = []
    for o in (ctx.category or {}).get("offer_catalog", []) or []:
        t = o.get("title")
        if t: titles.append(t)
    for o in (ctx.merchant or {}).get("offers", []) or []:
        t = o.get("title")
        if t: titles.append(t)
    for t in titles:
        if t and t.lower() in body_l:
            return None

    # Pass if any digest title or source string appears.
    for d in (ctx.category or {}).get("digest", []) or []:
        for f in ("title", "source"):
            v = d.get(f)
            if v and isinstance(v, str) and v.lower() in body_l:
                return None
            # Loose: cite any meaningful 4+ word substring from title.
            if v and isinstance(v, str):
                words = v.split()
                if len(words) >= 4:
                    snippet = " ".join(words[:4]).lower()
                    if snippet in body_l:
                        return None

    return ("Body does not cite any verifiable fact from the contexts (no matching number, no offer title, no digest source). "
            "Anchor on a specific fact present in category/merchant/trigger/customer.")


def check_offer_provenance(ctx: GuardContext) -> Optional[str]:
    """If the body mentions ₹/Rs prices that don't appear in the contexts, flag it."""
    price_re = re.compile(r"(?:₹|Rs\.?\s?|INR\s?)\s?\d[\d,]*", re.IGNORECASE)
    prices_in_body = price_re.findall(ctx.body)
    if not prices_in_body:
        return None
    flat = _flatten_context_strings(ctx).lower()
    for p in prices_in_body:
        digits = re.sub(r"[^\d]", "", p)
        if digits and digits in flat:
            continue
        return (f"Body mentions a price '{p.strip()}' that does not appear in any context "
                f"(merchant.offers, category.offer_catalog, trigger.payload). Use only real prices.")
    return None


def check_send_as(ctx: GuardContext) -> Optional[str]:
    """Soft check — addresses the merchant when a customer message was expected, or vice versa."""
    if (ctx.trigger or {}).get("scope") != "customer":
        return None
    cust_name = ((ctx.customer or {}).get("identity") or {}).get("name", "")
    if cust_name and cust_name.lower() not in ctx.body.lower():
        return (f"This is a customer-facing message (trigger.scope=customer). Address the customer by name "
                f"('{cust_name}'), not the merchant.")
    return None


# Hard-fail checks (ship-blocker if they trip): URL, taboo, CTA, repeat, send_as,
# offer_provenance. Soft checks (warn but ship): hindi, cite_fact — better to ship
# a slightly off message than fall back to template.
HARD_CHECKS = [
    ("url", check_url),
    ("taboo", check_taboo_vocab),
    ("cta", check_cta_value),
    ("repeat", check_no_repeat),
    ("offer_provenance", check_offer_provenance),
    ("send_as", check_send_as),
]
SOFT_CHECKS = [
    ("hindi", check_hindi_when_required),
    ("cite_fact", check_must_cite_fact),
]
CHECKS = HARD_CHECKS + SOFT_CHECKS  # backwards-compat for tests


def validate(ctx: GuardContext) -> ValidationResult:
    hard_issues, soft_issues, hints = [], [], []
    for name, fn in HARD_CHECKS:
        msg = fn(ctx)
        if msg:
            hard_issues.append(f"{name}: {msg}")
            hints.append(msg)
    for name, fn in SOFT_CHECKS:
        msg = fn(ctx)
        if msg:
            soft_issues.append(f"{name}: {msg}")
            hints.append(msg)
    if not hard_issues and not soft_issues:
        return ValidationResult(ok=True)
    retry_hint = "Fix these issues ALL in your next attempt:\n- " + "\n- ".join(hints)
    if hard_issues:
        return ValidationResult(ok=False, issues=hard_issues + soft_issues, retry_hint=retry_hint)
    # Soft-only: ship anyway, attach hints for observability.
    return ValidationResult(ok=True, issues=soft_issues, retry_hint=retry_hint)
