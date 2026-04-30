# Vera Bot — magicpin AI Challenge submission

**Team:** grizzleyyybear · Mrinal Sharma · mrinalsharmajune13@gmail.com
**Bot URL:** https://vera-bot-l1rz.onrender.com
**Model:** Groq `llama-3.1-8b-instant` (provider-agnostic via litellm — swap with one env var)
**Local judge_simulator score:** 32–39/50 across runs (LLM-judge variance ±2/dim)

## Approach

A two-step deterministic composer:

1. **Reasoner** (LLM, temp=0) reads all 4 contexts (category, merchant, trigger, customer?) and emits a structured "decision brief": `{best_signal, signal_source, lever, do_not_do, cta_shape, send_as, decision_rationale}`.
2. **Writer** (LLM, temp=0) takes the brief + slim contexts and writes the actual message body.
3. **Guards** (pure Python) run 8 hard checks on every output: no URLs, no taboo category vocab, no fabricated prices/offers, must cite ≥1 context fact, valid CTA shape, ≥1 Hindi token if merchant.languages contains "hi", no verbatim repeat, customer-facing addresses customer not merchant. On fail: ONE corrective retry, then fall back to a deterministic template.
4. **Template fallback** (pure Python, per-trigger-kind): when the LLM is unavailable / rate-limited / fails guards twice, ship a context-grounded message anchored on the same facts. Never returns empty actions.

## Why Reasoner→Writer instead of one prompt

Decision quality is the #1 dimension. Splitting reasoning from writing makes the lever choice auditable in `rationale` and lets the model spend its tokens picking the *right* signal (e.g., for a Saturday IPL trigger at a restaurant, the reasoner correctly switches from "push dine-in promo" to "push delivery special — people watch at home on weekends" — Case Study 5). The writer can then focus purely on voice + specificity.

## /v1/reply flow

A regex intent classifier handles the deterministic paths in <1ms and zero LLM cost:

- `hard_no` ("not interested", "stop", "band karo") → end + suppress
- `auto_reply` (canned WhatsApp Business templates, repeated identical bodies) → 1 polite probe → wait 4h → quarantine merchant 6h
- `later` ("baad mein", "kal", "busy abhi") → wait 30 min
- `off_topic` (GST, weather, etc.) → one polite redirect → end if persists
- `explicit_yes` (short affirmatives) → ACTION mode: deliver the agreed artifact, no more qualifying
- `engaged` (everything else) → LLM responder grounded in conversation history + 4 contexts

## TriggerRouter — 7 gates before any LLM call

1. Expiry (`trigger.expires_at`)
2. Suppression-key dedup (48h, or 7d for research_digest)
3. Per-merchant outbound rate cap: 2 / 24h
4. Subscription gate: expired merchants → only winback/renewal kinds
5. Auto-reply quarantine (6h)
6. Open-conversation collision (route to /reply, not new send)
7. Customer-scope consent check (kind → required scope mapping)

Plus: `MAX_ACTIONS_PER_TICK=2`, prioritized by urgency desc, then expiry asc.

## Operational guarantees

- All state is in-process; deterministic at temp=0; idempotent contexts on (scope, context_id, version) — re-posts return 409 not no-op-200 to surface drift.
- No URLs ever leave the bot (regex check on every body).
- No fabricated prices: any ₹/Rs amount in body must substring-match the contexts JSON.
- Hard timeouts: LLM 25s, /tick budget 28s — drop unfinished composes rather than block.

## Endpoints (all under /v1)

| Method | Path | Behavior |
|---|---|---|
| GET  | `/v1/healthz`  | uptime + per-scope context counts (no LLM) |
| GET  | `/v1/metadata` | team + model + approach |
| POST | `/v1/context`  | idempotent on (scope, context_id, version); higher version replaces atomically |
| POST | `/v1/tick`     | gate available_triggers → cap 2 → parallel compose → return Action[] |
| POST | `/v1/reply`    | classify intent → FSM route → LLM responder for engaged turns |

## Tradeoffs

- **No retrieval / vector DB** — the dataset is small (~50 merchants); slim minified context fits in the prompt. Adding retrieval would cost more than it would save here.
- **Sequential composes (concurrency=1)** — Groq free-tier TPM (12k/min) penalizes parallel bursts; sequential is faster end-to-end with retries off.
- **Template fallback over LLM retry-storm** — when rate-limited, we ship a deterministic context-grounded message (loses on creativity, wins on shipping vs not-shipping).

## Local dev

```bash
cd bot
cp .env.example .env  # add your GROQ_API_KEY
pip install -r requirements.txt
uvicorn bot.app:app --port 8080
```

Smoke tests under `bot/eval/`. Unit tests under `tests/`.
