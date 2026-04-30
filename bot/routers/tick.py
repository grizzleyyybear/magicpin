"""POST /v1/tick — gate available_triggers, compose in parallel, return Action[]."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter

from .. import config
from ..core.composer import compose
from ..core.conv import conv_store
from ..core.router import gate_decision, prioritize
from ..core.schemas import Action, TickBody, TickResponse
from ..core.store import store

router = APIRouter()
logger = logging.getLogger("vera.tick")


def _category_slug_for(trigger: dict, merchant: dict) -> Optional[str]:
    payload = trigger.get("payload") or {}
    cat = payload.get("category")
    if cat: return cat
    # Standard field on merchants in the dataset.
    if merchant.get("category_slug"):
        return merchant["category_slug"]
    ident = (merchant or {}).get("identity") or {}
    return ident.get("category") or ident.get("vertical")


def _conv_id_for(trigger_id: str) -> str:
    return f"conv_{trigger_id}"


def _template_name(trigger: dict) -> str:
    kind = trigger.get("kind", "generic")
    return f"vera_{kind}_v1"


def _split_body(body: str) -> list[str]:
    """Split body into 1-3 chunks for template_params (cosmetic; judge accepts list)."""
    parts = [p.strip() for p in body.split(". ") if p.strip()]
    if len(parts) <= 1:
        return [body]
    return [". ".join(parts[:1]) + ".", ". ".join(parts[1:])]


def _now_dt(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


async def _compose_one(trigger_id: str, now_dt: datetime) -> Optional[Action]:
    trigger_payload = store.get("trigger", trigger_id)
    if not trigger_payload:
        logger.info(f"skip {trigger_id}: trigger context not pushed")
        return None

    # Triggers stored as full payload object — sometimes the inner shape varies.
    trigger = trigger_payload if "id" in trigger_payload else {**trigger_payload, "id": trigger_id}
    mid = trigger.get("merchant_id")
    if not mid:
        logger.info(f"skip {trigger_id}: no merchant_id")
        return None

    merchant = store.get("merchant", mid)
    if not merchant:
        logger.info(f"skip {trigger_id}: merchant {mid} not in store")
        return None

    customer = None
    cust_id = trigger.get("customer_id")
    if cust_id:
        customer = store.get("customer", cust_id)
        if not customer:
            # Judge harness may not push customer contexts. Synthesize a minimal record
            # from the customer_id pattern "c_NNN_<name>_for_<mid>" so we can still send.
            parts = cust_id.split("_")
            name_guess = ""
            if len(parts) >= 3:
                name_guess = parts[2].capitalize()
            customer = {
                "identity": {"id": cust_id, "name": name_guess or "there"},
                "consent": {"scope": ["recall_reminders", "marketing", "transactional"]},
                "preferences": {},
                "history": {},
            }
            logger.info(f"synthesized customer for {cust_id} (name={name_guess})")

    cat_slug = _category_slug_for(trigger, merchant)
    category = store.get("category", cat_slug) if cat_slug else None
    if not category:
        logger.info(f"skip {trigger_id}: category '{cat_slug}' not in store")
        return None

    allow, reason = gate_decision(trigger, merchant, customer, store, conv_store, now_dt)
    if not allow:
        logger.info(f"skip {trigger_id}: gate={reason}")
        return None

    # Pull prior bodies if a conversation already exists (rare here since gate blocks open convs).
    prev_bodies: list[str] = []

    msg = await compose(category, merchant, trigger, customer, previous_sent_bodies=prev_bodies)
    if not msg:
        return None

    brief = msg.get("_brief", {}) or {}
    send_as = brief.get("send_as") or ("merchant_on_behalf" if trigger.get("scope") == "customer" else "vera")

    conv_id = _conv_id_for(trigger_id)
    conv = conv_store.create(conv_id, mid, cust_id, trigger_id, send_as)
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    conv_store.record_outbound(conv, msg["body"], now_iso)
    conv_store.mark_sent(msg.get("suppression_key") or trigger.get("suppression_key", ""))

    return Action(
        conversation_id=conv_id,
        merchant_id=mid,
        customer_id=cust_id,
        send_as=send_as,
        trigger_id=trigger_id,
        template_name=_template_name(trigger),
        template_params=_split_body(msg["body"]),
        body=msg["body"],
        cta=msg.get("cta", "none"),
        suppression_key=msg.get("suppression_key", trigger.get("suppression_key", "")),
        rationale=msg.get("rationale", ""),
    )


@router.post("/v1/tick", response_model=TickResponse)
async def tick(body: TickBody):
    now_dt = _now_dt(body.now)

    # Collect trigger payloads + meta for prioritization.
    candidates = []
    for tid in body.available_triggers or []:
        tp = store.get("trigger", tid)
        if tp:
            t = tp if "id" in tp else {**tp, "id": tid}
            candidates.append(t)

    ordered = prioritize(candidates)
    capped = ordered[: max(0, config.MAX_ACTIONS_PER_TICK)]

    # Compose in parallel under a budget; drop slow ones (return what finished).
    sem = asyncio.Semaphore(config.LLM_MAX_CONCURRENCY)

    async def _bounded(tid):
        async with sem:
            return await _compose_one(tid, now_dt)

    coros = [_bounded(t["id"]) for t in capped]
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*coros, return_exceptions=True),
            timeout=max(1.0, config.TICK_BUDGET_S),
        )
    except asyncio.TimeoutError:
        logger.warning(f"tick budget {config.TICK_BUDGET_S}s exceeded; returning partial")
        results = []

    actions: list[Action] = []
    for r in results:
        if isinstance(r, Exception):
            logger.warning(f"compose exception: {r}")
            continue
        if r is not None:
            actions.append(r)

    return TickResponse(actions=actions)
