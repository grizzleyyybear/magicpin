import os
import time
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
