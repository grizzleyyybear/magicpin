"""FastAPI entry point."""
import logging
from fastapi import FastAPI
from .routers import context, tick, reply, health, meta
from . import config

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)

app = FastAPI(title="grizzleyyybear · vera-bot", version=config.BOT_VERSION)

app.include_router(health.router)
app.include_router(meta.router)
app.include_router(context.router)
app.include_router(tick.router)
app.include_router(reply.router)


@app.get("/")
async def root():
    return {"ok": True, "service": "vera-bot", "team": config.TEAM_NAME}
