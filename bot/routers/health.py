import time
from fastapi import APIRouter
from ..core.store import store

router = APIRouter()
START = time.time()


@router.get("/v1/healthz")
async def healthz():
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - START),
        "contexts_loaded": store.counts(),
    }
