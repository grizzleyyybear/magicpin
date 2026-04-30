"""Reasoner — picks the best signal/lever/CTA from the 4 contexts.
Outputs a structured decision brief that the Writer consumes.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

from .. import config
from . import llm

logger = logging.getLogger("vera.reasoner")

PROMPT_DIR = Path(__file__).parent / "prompts"


@lru_cache(maxsize=1)
def _system_prompt() -> str:
    return (PROMPT_DIR / "system_reasoner.md").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _framings() -> dict[str, str]:
    raw = (PROMPT_DIR / "trigger_framings.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    return {k: (v.strip() if isinstance(v, str) else str(v)) for k, v in data.items()}


def _slim_category(c: dict) -> dict:
    if not c:
        return {}
    return {
        "slug": c.get("slug"),
        "voice": c.get("voice", {}),
        "offer_catalog": c.get("offer_catalog", []),
        "peer_stats": c.get("peer_stats", {}),
        "digest": c.get("digest", []),
        "seasonal_beats": c.get("seasonal_beats", []),
        "trend_signals": c.get("trend_signals", []),
        "patient_content_library": [
            {"id": p.get("id"), "title": p.get("title")}
            for p in (c.get("patient_content_library") or [])
        ],
    }


def _slim_merchant(m: dict) -> dict:
    if not m:
        return {}
    return {
        "merchant_id": m.get("merchant_id"),
        "category_slug": m.get("category_slug"),
        "identity": m.get("identity", {}),
        "subscription": m.get("subscription", {}),
        "performance": m.get("performance", {}),
        "offers": m.get("offers", []),
        "conversation_history": (m.get("conversation_history") or [])[-6:],
        "customer_aggregate": m.get("customer_aggregate", {}),
        "signals": m.get("signals", []),
        "review_themes": m.get("review_themes", []),
    }


def _slim_trigger(t: dict) -> dict:
    if not t:
        return {}
    return {
        "id": t.get("id"),
        "scope": t.get("scope"),
        "kind": t.get("kind"),
        "source": t.get("source"),
        "merchant_id": t.get("merchant_id"),
        "customer_id": t.get("customer_id"),
        "payload": t.get("payload", {}),
        "urgency": t.get("urgency"),
        "suppression_key": t.get("suppression_key"),
        "expires_at": t.get("expires_at"),
    }


def _slim_customer(c: Optional[dict]) -> Optional[dict]:
    if not c:
        return None
    return {
        "customer_id": c.get("customer_id"),
        "merchant_id": c.get("merchant_id"),
        "identity": c.get("identity", {}),
        "relationship": c.get("relationship", {}),
        "state": c.get("state"),
        "preferences": c.get("preferences", {}),
        "consent": c.get("consent", {}),
    }


def build_user_prompt(category: dict, merchant: dict, trigger: dict,
                      customer: Optional[dict]) -> str:
    framings = _framings()
    framing = framings.get(trigger.get("kind", ""), framings.get("default", ""))
    payload = {
        "framing": framing,
        "category": _slim_category(category),
        "merchant": _slim_merchant(merchant),
        "trigger": _slim_trigger(trigger),
        "customer": _slim_customer(customer),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


REQUIRED_FIELDS = {
    "best_signal", "signal_source", "lever", "do_not_do",
    "cta_shape", "send_as", "decision_rationale",
}

VALID_LEVERS = {
    "specificity", "loss_aversion", "social_proof", "effort_externalization",
    "curiosity", "reciprocity", "asking_merchant", "loss_aversion_inverted",
}
VALID_CTA = {"yes_no", "open_ended", "none"}
VALID_SEND_AS = {"vera", "merchant_on_behalf"}


def _normalize_brief(brief: dict, trigger: dict) -> dict:
    """Mild auto-correction so downstream code can rely on the shape."""
    out = dict(brief)
    # Force send_as based on trigger.scope
    if trigger.get("scope") == "customer":
        out["send_as"] = "merchant_on_behalf"
    elif out.get("send_as") not in VALID_SEND_AS:
        out["send_as"] = "vera"
    if out.get("lever") not in VALID_LEVERS:
        out["lever"] = "specificity"
    if out.get("cta_shape") not in VALID_CTA:
        out["cta_shape"] = "open_ended"
    for k in REQUIRED_FIELDS:
        out.setdefault(k, "")
    return out


async def reason(
    category: dict, merchant: dict, trigger: dict,
    customer: Optional[dict] = None,
) -> Optional[dict]:
    """Produce a decision brief. Returns None if the LLM call fails entirely."""
    user = build_user_prompt(category, merchant, trigger, customer)
    brief = await llm.call_json(
        model=config.LLM_MODEL_REASONER,
        system=_system_prompt(),
        user=user,
        timeout_s=config.LLM_TIMEOUT_S,
        max_tokens=500,
        temperature=0.0,
    )
    if not brief:
        return None
    if not REQUIRED_FIELDS.issubset(set(brief.keys())):
        # Try to be forgiving — fill missing fields from defaults.
        logger.info(f"Reasoner missing fields: {set(REQUIRED_FIELDS) - set(brief.keys())}")
    return _normalize_brief(brief, trigger)
