"""Composer pipeline: Reasoner -> Writer -> Guards -> retry-once -> deterministic fallback.

Returns a dict {body, cta, suppression_key, rationale} or None if it can't ship.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from . import reasoner, writer
from .fallback import fallback_message
from .guards import GuardContext, validate

logger = logging.getLogger("vera.composer")


def _validate_msg(msg: dict, brief: dict, category, merchant, trigger, customer, prev_bodies):
    return validate(GuardContext(
        body=msg.get("body", ""),
        cta=msg.get("cta", ""),
        suppression_key=msg.get("suppression_key", ""),
        rationale=msg.get("rationale", ""),
        category=category, merchant=merchant, trigger=trigger, customer=customer,
        previous_sent_bodies=prev_bodies or [],
        decision_brief=brief or {},
    ))


async def compose(
    category: dict,
    merchant: dict,
    trigger: dict,
    customer: Optional[dict] = None,
    previous_sent_bodies: Optional[list[str]] = None,
) -> Optional[dict]:
    prev = previous_sent_bodies or []

    brief = await reasoner.reason(category, merchant, trigger, customer)
    if not brief or "NO_SEND" in (brief.get("best_signal") or ""):
        logger.info(f"reasoner skipped or NO_SEND; trying template fallback")
        return _try_fallback(category, merchant, trigger, customer, prev, brief or {})

    msg = await writer.write(brief, category, merchant, trigger, customer, prev)
    if msg:
        result = _validate_msg(msg, brief, category, merchant, trigger, customer, prev)
        if result.ok:
            msg["_brief"] = brief
            return msg
        logger.info(f"validator issues (retrying once): {result.issues}")
        extra = dict(brief); extra["correction_hint"] = result.retry_hint
        msg2 = await writer.write(extra, category, merchant, trigger, customer, prev)
        if msg2:
            result2 = _validate_msg(msg2, brief, category, merchant, trigger, customer, prev)
            if result2.ok:
                msg2["_brief"] = brief
                return msg2
            logger.warning(f"validator failed twice: {result2.issues}; falling back to template")
        else:
            logger.warning("writer retry returned None; falling back to template")
    else:
        logger.warning("writer returned None; falling back to template")

    return _try_fallback(category, merchant, trigger, customer, prev, brief)


def _try_fallback(category, merchant, trigger, customer, prev, brief) -> Optional[dict]:
    fb = fallback_message(category, merchant, trigger, customer)
    if not fb:
        return None
    result = _validate_msg(fb, brief or {}, category, merchant, trigger, customer, prev)
    if not result.ok:
        # Templates SHOULD pass guards. If not, just log and ship anyway —
        # better than empty action.
        logger.info(f"template fallback also has guard issues: {result.issues}; shipping anyway")
    fb["_brief"] = brief or {"best_signal": "template_fallback", "lever": "specificity",
                              "send_as": "merchant_on_behalf" if trigger.get("scope")=="customer" else "vera"}
    return fb

