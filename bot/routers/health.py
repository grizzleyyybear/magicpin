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
