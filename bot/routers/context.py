from datetime import datetime, timezone
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from ..core.schemas import ContextBody
from ..core.store import store

router = APIRouter()


@router.post("/v1/context")
async def push_context(body: ContextBody):
    accepted, current_version, ack = store.upsert(
        body.scope, body.context_id, body.version, body.payload
    )
    if not accepted:
        return JSONResponse(
            status_code=409,
            content={
                "accepted": False,
                "reason": "stale_version",
                "current_version": current_version,
            },
        )
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {"accepted": True, "ack_id": ack, "stored_at": now}


@router.post("/v1/teardown")
async def teardown():
    from ..core.conv import conv_store
    store.clear()
    conv_store.clear()
    return {"ok": True}
