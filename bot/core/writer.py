"""Writer — turns a decision brief + 4 contexts into the actual WhatsApp message body."""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

from .. import config
from . import llm
from .reasoner import _slim_category, _slim_merchant, _slim_trigger, _slim_customer

logger = logging.getLogger("vera.writer")

PROMPT_DIR = Path(__file__).parent / "prompts"


@lru_cache(maxsize=1)
def _system_prompt() -> str:
    return (PROMPT_DIR / "system_writer.md").read_text(encoding="utf-8")


REQUIRED_FIELDS = {"body", "cta", "suppression_key", "rationale"}
VALID_CTA = {"yes_no", "open_ended", "none"}


def build_user_prompt(
    decision_brief: dict,
    category: dict,
    merchant: dict,
    trigger: dict,
    customer: Optional[dict],
    previous_sent_bodies: Optional[list[str]] = None,
) -> str:
    payload = {
        "decision_brief": decision_brief,
        "category": _slim_category(category),
        "merchant": _slim_merchant(merchant),
        "trigger": _slim_trigger(trigger),
        "customer": _slim_customer(customer),
        "previous_sent_bodies": previous_sent_bodies or [],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _normalize(out: dict, decision_brief: dict, trigger: dict) -> dict:
    o = dict(out)
    o["suppression_key"] = trigger.get("suppression_key", "") or ""
    if o.get("cta") not in VALID_CTA:
        o["cta"] = decision_brief.get("cta_shape") if decision_brief.get("cta_shape") in VALID_CTA else "open_ended"
    o.setdefault("rationale", decision_brief.get("decision_rationale", ""))
    o.setdefault("body", "")
    return o


async def write(
    decision_brief: dict,
    category: dict,
    merchant: dict,
    trigger: dict,
    customer: Optional[dict] = None,
    previous_sent_bodies: Optional[list[str]] = None,
) -> Optional[dict]:
    """Produce a {body, cta, suppression_key, rationale} dict, or None on failure."""
    user = build_user_prompt(decision_brief, category, merchant, trigger,
                             customer, previous_sent_bodies)
    out = await llm.call_json(
        model=config.LLM_MODEL_WRITER,
        system=_system_prompt(),
        user=user,
        timeout_s=config.LLM_TIMEOUT_S,
        max_tokens=600,
        temperature=0.0,
    )
    if not out:
        return None
    if not REQUIRED_FIELDS.issubset(set(out.keys())):
        logger.info(f"Writer missing fields: {REQUIRED_FIELDS - set(out.keys())}")
    return _normalize(out, decision_brief, trigger)
