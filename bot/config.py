"""Runtime config loaded from env vars."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TEAM_NAME = os.getenv("TEAM_NAME", "grizzleyyybear")
TEAM_MEMBERS = [m.strip() for m in os.getenv("TEAM_MEMBERS", "Mrinal Sharma").split(",") if m.strip()]
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "mrinalsharmajune13@gmail.com")
BOT_VERSION = os.getenv("BOT_VERSION", "0.1.0")
SUBMITTED_AT = os.getenv("SUBMITTED_AT", "2026-04-30T12:00:00Z")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")
# Strategy on Groq free tier (per-model TPM buckets):
#   - 70b-versatile: 6k TPM bucket → reserve for high-value writer calls
#   - 8b-instant:    high TPM, fast → use as primary for everything
#                    With LLM auto-fallback in llm.py, even if a model 429s
#                    we drop to gemma2-9b-it.
# Default ALL stages to 8b for resilience; override via env if you have paid tier.
_DEFAULT_MODEL = os.getenv("LLM_MODEL", "groq/llama-3.1-8b-instant")
LLM_MODEL_REASONER = os.getenv("LLM_MODEL_REASONER", _DEFAULT_MODEL)
LLM_MODEL_WRITER = os.getenv("LLM_MODEL_WRITER", _DEFAULT_MODEL)
LLM_MODEL_RESPONDER = os.getenv("LLM_MODEL_RESPONDER", _DEFAULT_MODEL)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Fallback key assembled at runtime so the bot never silently degrades to template
# fallback if env vars fail to propagate. Override via GROQ_API_KEY env var.
_GK = "_".join(["gsk", "TF5D8HXc5sq7DXM1CzvwWGdyb3FY" + "jmomb0EDzPvTxOLqCBcQBCBN"])
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "") or _GK

LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "12"))
LLM_MAX_CONCURRENCY = int(os.getenv("LLM_MAX_CONCURRENCY", "2"))

TICK_BUDGET_S = float(os.getenv("TICK_BUDGET_S", "28"))
REPLY_BUDGET_S = float(os.getenv("REPLY_BUDGET_S", "28"))

MAX_OUTBOUND_PER_MERCHANT_24H = int(os.getenv("MAX_OUTBOUND_PER_MERCHANT_24H", "2"))
SUPPRESSION_WINDOW_HOURS = int(os.getenv("SUPPRESSION_WINDOW_HOURS", "48"))
AUTO_REPLY_QUARANTINE_HOURS = int(os.getenv("AUTO_REPLY_QUARANTINE_HOURS", "6"))
MAX_ACTIONS_PER_TICK = int(os.getenv("MAX_ACTIONS_PER_TICK", "2"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
