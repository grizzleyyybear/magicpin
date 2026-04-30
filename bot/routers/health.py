import os
import time
import traceback
from fastapi import APIRouter
from ..core.store import store
from .. import config

router = APIRouter()
START = time.time()


@router.get("/v1/healthz")
async def healthz():
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - START),
        "contexts_loaded": store.counts(),
        "llm": {
            "provider": config.LLM_PROVIDER,
            "model": config.LLM_MODEL_WRITER,
            "groq_key_loaded": bool(config.GROQ_API_KEY),
            "groq_key_len": len(config.GROQ_API_KEY) if config.GROQ_API_KEY else 0,
            "env_groq": bool(os.getenv("GROQ_API_KEY")),
        },
    }


@router.get("/v1/debug/llm")
async def debug_llm():
    """Diagnostic endpoint: round-trip one LLM call and return raw result + any error."""
    from ..core import llm as llm_mod
    out = {"model": config.LLM_MODEL_REASONER, "groq_key_len": len(config.GROQ_API_KEY)}
    try:
        t0 = time.time()
        result = await llm_mod.call_json(
            model=config.LLM_MODEL_REASONER,
            system="You are a JSON generator. Reply with only valid JSON.",
            user='Return: {"ok": true, "msg": "hello"}',
            timeout_s=15,
            max_tokens=50,
        )
        out["latency_s"] = round(time.time() - t0, 2)
        out["result"] = result
        out["ok"] = result is not None
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:500]}"
        out["traceback"] = traceback.format_exc()[-800:]
    return out


@router.post("/v1/debug/reset")
async def debug_reset():
    """Reset in-memory conv + suppression state so re-runs aren't blocked by dedup."""
    from ..core.conv import conv_store
    cleared = {
        "convs": len(getattr(conv_store, "_convs", {})),
        "suppression": len(getattr(conv_store, "_suppression", {})),
        "outbound_log": len(getattr(conv_store, "_outbound_log", [])),
    }
    if hasattr(conv_store, "_convs"): conv_store._convs.clear()
    if hasattr(conv_store, "_suppression"): conv_store._suppression.clear()
    if hasattr(conv_store, "_outbound_log"): conv_store._outbound_log.clear()
    return {"reset": True, "cleared": cleared}


@router.get("/v1/debug/state")
async def debug_state():
    from ..core.conv import conv_store
    return {
        "contexts": store.counts(),
        "convs": len(getattr(conv_store, "_convs", {})),
        "suppression_keys": len(getattr(conv_store, "_suppression", {})),
        "sample_suppression": list(getattr(conv_store, "_suppression", {}).keys())[:5],
    }


@router.get("/v1/debug/compose")
async def debug_compose(trigger_id: str):
    """Run compose end-to-end and return reasoner/writer/guard intermediate state."""
    from ..core import reasoner as r_mod
    from ..core import writer as w_mod
    from ..core.guards import GuardContext, validate
    out: dict = {"trigger_id": trigger_id}
    trig = store.get("trigger", trigger_id)
    if not trig:
        return {"error": "trigger not in store", "available": list(store._data.get("trigger", {}).keys())[:10]}
    trig = trig if "id" in trig else {**trig, "id": trigger_id}
    mid = trig.get("merchant_id")
    merchant = store.get("merchant", mid)
    cust_id = trig.get("customer_id")
    customer = store.get("customer", cust_id) if cust_id else None
    cat_slug = (trig.get("payload") or {}).get("category") or (merchant or {}).get("category_slug")
    category = store.get("category", cat_slug) if cat_slug else None
    out["loaded"] = {"merchant": bool(merchant), "category": bool(category), "customer": bool(customer), "cat_slug": cat_slug}
    if not (merchant and category):
        return out
    try:
        t0 = time.time()
        brief = await r_mod.reason(category, merchant, trig, customer)
        out["reasoner_ms"] = int((time.time() - t0) * 1000)
        out["brief"] = brief
        if not brief:
            out["fail"] = "reasoner returned None"; return out
        t1 = time.time()
        msg = await w_mod.write(brief, category, merchant, trig, customer, [])
        out["writer_ms"] = int((time.time() - t1) * 1000)
        out["msg"] = msg
        if not msg:
            out["fail"] = "writer returned None"; return out
        gres = validate(GuardContext(
            body=msg.get("body", ""), cta=msg.get("cta", ""),
            suppression_key=msg.get("suppression_key", ""),
            rationale=msg.get("rationale", ""),
            category=category, merchant=merchant, trigger=trig, customer=customer,
            previous_sent_bodies=[], decision_brief=brief,
        ))
        out["guards"] = {"ok": gres.ok, "issues": [str(i) for i in gres.issues]}
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:500]}"
        out["traceback"] = traceback.format_exc()[-1000:]
    return out
