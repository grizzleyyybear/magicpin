"""POST /v1/reply — intent classifier + FSM router + LLM responder for engaged turns."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

from .. import config
from ..core import intent as intent_mod
from ..core.conv import conv_store
from ..core.guards import GuardContext, validate
from ..core.responder import respond
from ..core.schemas import ReplyBody, ReplyEndResponse, ReplySendResponse, ReplyWaitResponse
from ..core.store import store

router = APIRouter()
logger = logging.getLogger("vera.reply")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _ctx_for_conv(conv) -> tuple[Any, Any, Any, Any]:
    trigger = store.get("trigger", conv.trigger_id) or {}
    if "id" not in trigger:
        trigger = {**trigger, "id": conv.trigger_id}
    merchant = store.get("merchant", conv.merchant_id) or {}
    cat_slug = (trigger.get("payload") or {}).get("category") or merchant.get("category_slug")
    category = store.get("category", cat_slug) if cat_slug else {}
    customer = store.get("customer", conv.customer_id) if conv.customer_id else None
    return category, merchant, trigger, customer


@router.post("/v1/reply")
async def reply(body: ReplyBody):
    cid = body.conversation_id
    conv = conv_store.get(cid)

    # If we never sent on this conv, treat as orphan inbound — wait briefly and ignore.
    if not conv:
        logger.info(f"reply on unknown conversation_id={cid}; waiting")
        return ReplyWaitResponse(wait_seconds=3600,
                                  rationale=f"No record of conversation {cid}; deferring 1h.").model_dump()

    if conv.state == "ENDED":
        return ReplyEndResponse(rationale="Conversation already ended; ignoring further inbound.").model_dump()

    repeat_count = conv.received_bodies_seen.get(body.message.strip().lower(), 0)
    intent, why = intent_mod.classify(body.message, repeat_count=repeat_count)

    # Record the inbound BEFORE branching.
    conv_store.record_inbound(conv, body.from_role, body.message, body.received_at, body.turn_number)

    # ---- HARD NO ----
    if intent == "hard_no":
        conv_store.end(conv, reason="hard_no")
        return ReplyEndResponse(
            rationale="Merchant explicitly opted out. Closing conversation; suppressing this conversation_id."
        ).model_dump()

    # ---- LATER ----
    if intent == "later":
        conv.state = "WAITING"
        return ReplyWaitResponse(
            wait_seconds=1800,
            rationale="Merchant asked to talk later. Backing off 30 minutes."
        ).model_dump()

    # ---- AUTO-REPLY ----
    if intent == "auto_reply":
        conv.auto_reply_count += 1
        if conv.auto_reply_count == 1:
            # Probe ONCE.
            owner = (((store.get("merchant", conv.merchant_id) or {}).get("identity") or {}).get("owner_first_name")) or ""
            sal = f"{owner}, " if owner else ""
            probe = (f"{sal}looks like that was an auto-reply. When you read this yourself, "
                     "reply YES and I will send the one-minute version directly.")
            conv.state = "AUTO_REPLY_PROBED"
            conv_store.record_outbound(conv, probe, _now_iso())
            return ReplySendResponse(
                body=probe, cta="yes_no",
                rationale="First canned auto-reply detected; sending one human-eyes probe before backing off."
            ).model_dump()
        if conv.auto_reply_count == 2:
            return ReplyWaitResponse(
                wait_seconds=14400,
                rationale="Auto-reply observed twice. Backing off 4 hours to wait for owner."
            ).model_dump()
        # 3rd+ time: end and quarantine.
        conv_store.quarantine(conv.merchant_id, hours=config.AUTO_REPLY_QUARANTINE_HOURS)
        conv_store.end(conv, reason="repeated_auto_reply")
        return ReplyEndResponse(
            rationale="Repeated auto-reply with no owner engagement; closing and quarantining merchant for 6h."
        ).model_dump()

    # ---- OFF-TOPIC ----
    # Single redirect; if they go off-topic again, end politely.
    if intent == "off_topic":
        if getattr(conv, "_off_topic_redirected", False):
            conv_store.end(conv, reason="off_topic_persistent")
            return ReplyEndResponse(
                rationale="Merchant persistently off-topic after a redirect; closing thread."
            ).model_dump()
        conv._off_topic_redirected = True
        conv.state = "ENGAGED"
        category, merchant, trigger, customer = _ctx_for_conv(conv)
        # Try LLM responder; on failure, send a deterministic redirect line.
        msg = await respond(conv, "off_topic", body.message, category, merchant, trigger, customer)
        if msg and msg.get("body"):
            _maybe_record(conv, msg)
            return ReplySendResponse(body=msg["body"], cta=msg.get("cta", "open_ended"),
                                     rationale=msg.get("rationale", "Off-topic; one redirect.")).model_dump()
        # Fallback redirect.
        owner = ((merchant.get("identity") or {}).get("owner_first_name")) or ""
        redirect = (f"{owner + ', ' if owner else ''}that question is outside my scope, "
                    "your CA can help there. Should we go back and finish what we started?")
        conv_store.record_outbound(conv, redirect, _now_iso())
        return ReplySendResponse(body=redirect, cta="yes_no",
                                  rationale="Off-topic ask declined; one-line redirect to original trigger.").model_dump()

    # ---- EXPLICIT YES → ACTION mode ----
    if intent == "explicit_yes":
        conv.state = "ACTION"
        category, merchant, trigger, customer = _ctx_for_conv(conv)
        msg = await respond(conv, "explicit_yes", body.message, category, merchant, trigger, customer)
        if msg and msg.get("body"):
            _maybe_record(conv, msg)
            return ReplySendResponse(body=msg["body"], cta=msg.get("cta", "yes_no"),
                                     rationale=msg.get("rationale", "Explicit yes; delivering next step.")).model_dump()
        # Fallback acknowledgement.
        ack = "Done. Preparing the next step now, you'll have an update in 1 to 2 minutes."
        conv_store.record_outbound(conv, ack, _now_iso())
        return ReplySendResponse(body=ack, cta="none",
                                  rationale="LLM unavailable; sending action-mode acknowledgement.").model_dump()

    # ---- ENGAGED FREEFORM ----
    conv.state = "ENGAGED"
    category, merchant, trigger, customer = _ctx_for_conv(conv)
    msg = await respond(conv, "engaged", body.message, category, merchant, trigger, customer)
    if msg and msg.get("body"):
        _maybe_record(conv, msg)
        return ReplySendResponse(body=msg["body"], cta=msg.get("cta", "open_ended"),
                                  rationale=msg.get("rationale", "Engaged freeform; staying on mission.")).model_dump()

    # Last-resort wait if LLM is rate-limited.
    return ReplyWaitResponse(wait_seconds=300,
                              rationale="LLM unavailable for engaged reply; brief 5-min wait then re-engage.").model_dump()


def _maybe_record(conv, msg: dict) -> None:
    """Validate via guards (best-effort), record outbound, advance turn."""
    body = msg.get("body", "")
    cta = msg.get("cta", "open_ended")
    if not body:
        return
    category, merchant, trigger, customer = _ctx_for_conv(conv)
    gctx = GuardContext(
        body=body, cta=cta, suppression_key="", rationale=msg.get("rationale", ""),
        category=category, merchant=merchant, trigger=trigger, customer=customer,
        previous_sent_bodies=list(conv.sent_bodies),
        decision_brief={},
    )
    result = validate(gctx)
    if not result.ok:
        # Log but still send — guards on /reply are advisory; we'd rather respond than freeze.
        logger.info(f"reply guard issues (sent anyway): {result.issues}")
    conv_store.record_outbound(conv, body, _now_iso())
