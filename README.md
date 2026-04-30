# Vera - magicpin AI Challenge submission

**Team:** grizzleyyybear
**Contact:** Mrinal Sharma (mrinalsharmajune13@gmail.com)
**Live bot URL:** https://vera-bot-l1rz.onrender.com

## Endpoints

| Method | Path | |
|---|---|---|
| GET  | `/v1/healthz`  | health + per-scope context counts |
| GET  | `/v1/metadata` | team, model, approach |
| POST | `/v1/context`  | idempotent on (scope, context_id, version) |
| POST | `/v1/tick`     | gate triggers, parallel compose, return Action[] |
| POST | `/v1/reply`    | classify intent, FSM route, LLM responder |

## What this submission contains

- `bot/` - FastAPI service (Reasoner -> Writer -> Guards -> Template fallback). See `bot/README.md` for design notes.
- `tests/` - unit tests (18 passing).
- `dataset/`, `expanded/`, `examples/` - provided challenge data + generator output.
- `render.yaml` - Render blueprint used to deploy the live bot.
- `judge_simulator.py` - local-only (gitignored), runs the official harness against the deployed URL.

## Quick local run

```bash
cd bot
cp .env.example .env   # set GROQ_API_KEY
pip install -r requirements.txt
uvicorn bot.app:app --port 8080
```

Full design notes, trade-offs, and per-route behavior are in [`bot/README.md`](bot/README.md).
