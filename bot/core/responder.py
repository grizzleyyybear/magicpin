"""LLM responder for /v1/reply — used when intent is 'engaged' or 'off_topic'."""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

from .. import config
from .llm import call_json
from .reasoner import _slim_category, _slim_customer, _slim_merchant, _slim_trigger

logger = logging.getLogger("vera.responder")

PROMPT_DIR = Path(__file__).parent / "prompts"


@lru_cache(maxsize=1)
def _system_prompt() -> str:
    return (PROMPT_DIR / "system_responder.md").read_text(encoding="utf-8")


def _slim_conv(conv) -> dict:
    return {
        "state": conv.state,
        "send_as": conv.send_as,
        "turns": [
            {"from_role": t.from_role, "body": t.body, "turn_number": t.turn_number}
            for t in conv.turns[-6:]   # last 6 turns max
        ],
        "sent_bodies": list(conv.sent_bodies)[-3:],   # for anti-repeat
    }


async def respond(
    conv,
    intent: str,
    last_inbound: str,
    category: dict,
    merchant: dict,
    trigger: dict,
    customer: Optional[dict] = None,
) -> Optional[dict]:
    payload = {
        "conversation": _slim_conv(conv),
        "intent": intent,
        "last_inbound": last_inbound,
        "category": _slim_category(category),
        "merchant": _slim_merchant(merchant),
        "trigger": _slim_trigger(trigger),
        "customer": _slim_customer(customer) if customer else None,
    }
    sys = _system_prompt()
    user = json.dumps(payload, ensure_ascii=False)
    out = await call_json(
        model=config.LLM_MODEL_RESPONDER,
        system=sys,
        user=user,
        timeout_s=config.LLM_TIMEOUT_S,
        max_tokens=500,
        temperature=0.0,
    )
    if not out:
        logger.warning("responder LLM returned None")
        return None
    out.setdefault("cta", "open_ended")
    out.setdefault("body", "")
    out.setdefault("rationale", "")
    return out
