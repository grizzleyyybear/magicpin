from fastapi import APIRouter
from .. import config

router = APIRouter()


@router.get("/v1/metadata")
async def metadata():
    return {
        "team_name": config.TEAM_NAME,
        "team_members": config.TEAM_MEMBERS,
        "model": config.LLM_MODEL_WRITER,
        "approach": "Two-step composer: a Reasoner picks the best signal+lever from the 4 contexts, then a Writer drafts a single-CTA Hindi-English message. Deterministic guards (no URLs, no taboo vocab, no repeats, must cite a context fact) gate every output. /v1/reply uses a regex intent classifier (auto-reply / explicit-yes / hard-no / later / off-topic) before falling back to an LLM responder.",
        "contact_email": config.CONTACT_EMAIL,
        "version": config.BOT_VERSION,
        "submitted_at": config.SUBMITTED_AT,
    }
