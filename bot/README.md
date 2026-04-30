# Vera Bot - magicpin AI Challenge submission

**Team:** grizzleyyybear (Mrinal Sharma, mrinalsharmajune13@gmail.com)
**Bot URL:** https://vera-bot-l1rz.onrender.com
**Model:** Groq `llama-3.1-8b-instant` via litellm (provider-agnostic, swap with one env var)

## Approach

A two-step deterministic composer:

1. **Reasoner** (LLM, temp=0) reads all four contexts (category, merchant, trigger, customer) and emits a structured decision brief: `{best_signal, signal_source, lever, do_not_do, cta_shape, send_as, decision_rationale}`.
2. **Writer** (LLM, temp=0) takes the brief plus slim contexts and writes the message body.
3. **Guards** (pure Python) run hard checks on every output: no URLs, no taboo vocab, no fabricated prices/offers, must cite at least one context fact, valid CTA shape, no verbatim repeat, customer-facing messages address the customer not the merchant. On fail: one corrective retry, then deterministic template fallback.
4. **Template fallback** (pure Python, per trigger kind): when the LLM is unavailable or fails guards twice, ship a context-grounded message anchored on the same facts. Never returns empty actions.

Splitting reasoning from writing makes the lever choice auditable in `rationale` and lets the model spend tokens on picking the right signal. The writer focuses on voice and specificity.

## /v1/reply flow

A regex intent classifier handles deterministic paths in under a millisecond:

- `hard_no` ("not interested", "stop", "band karo") -> end and suppress
- `auto_reply` (canned WhatsApp Business templates, repeated identical bodies) -> one polite probe -> wait 4h -> quarantine merchant 6h
- `later` ("baad mein", "kal", "busy abhi") -> wait 30 min
- `off_topic` (GST, weather, etc.) -> one polite redirect -> end if persists
- `explicit_yes` (short affirmatives) -> ACTION mode: deliver the agreed artifact
- `engaged` (everything else) -> LLM responder grounded in conversation history and contexts

## TriggerRouter gates (run before any LLM call)

1. Expiry (`trigger.expires_at`)
2. Suppression-key dedup (48h, or 7d for `research_digest`)
3. Per-merchant outbound rate cap: 2 per 24h
4. Subscription gate: expired merchants only see winback/renewal kinds
5. Auto-reply quarantine (6h)
6. Open-conversation collision (route to /reply, not new send)
7. Customer-scope consent check (kind to required-scope mapping)

Triggers are prioritized by urgency desc, then expiry asc, capped at `MAX_ACTIONS_PER_TICK`.

## Operational guarantees

- All state in-process. Deterministic at temp=0.
- Contexts idempotent on (scope, context_id, version). Higher version replaces atomically; re-posting same version returns 409 to surface drift.
- No URLs ever leave the bot (regex check on every body).
- No fabricated prices: any Rs/₹ amount in the body must appear in the contexts JSON.
- Hard timeouts: LLM 10s, /tick budget 13s. Drop unfinished composes rather than block.

## Endpoints (all under /v1)

| Method | Path | Behavior |
|---|---|---|
| GET  | `/v1/healthz`  | uptime and per-scope context counts (no LLM) |
| GET  | `/v1/metadata` | team, model, approach |
| POST | `/v1/context`  | idempotent on (scope, context_id, version) |
| POST | `/v1/tick`     | gate triggers, parallel compose under budget, return Action[] |
| POST | `/v1/reply`    | classify intent, FSM route, LLM responder for engaged turns |

## Tradeoffs

- No retrieval or vector DB. Dataset is small (~50 merchants); slim minified context fits in the prompt.
- Free-tier Groq TPM constraints handled by per-model fallback chain (8b primary, gemma2 backup) plus template fallback to guarantee ship.
- Templates lose on creativity but always cite a real fact, so they never zero on Specificity.

## Local dev

```bash
cd bot
cp .env.example .env  # set GROQ_API_KEY
pip install -r requirements.txt
uvicorn bot.app:app --port 8080
```

Smoke tests in `bot/eval/`. Unit tests in `tests/`.
