"""LLM wrapper around litellm. Deterministic JSON output, single retry on parse failure."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Optional

from .. import config

logger = logging.getLogger("vera.llm")

# Surface API keys into env so litellm picks them up by provider prefix.
if config.GEMINI_API_KEY and "GEMINI_API_KEY" not in os.environ:
    os.environ["GEMINI_API_KEY"] = config.GEMINI_API_KEY
if config.GROQ_API_KEY and "GROQ_API_KEY" not in os.environ:
    os.environ["GROQ_API_KEY"] = config.GROQ_API_KEY

try:
    import litellm
    litellm.set_verbose = False
    litellm.suppress_debug_info = True
    litellm.drop_params = True   # quietly drop unsupported params per provider
    litellm.num_retries = 0
    litellm.request_timeout = 30
    # Kill the OpenAI SDK's built-in retries (the "Retrying request in 15s" lines).
    try:
        import openai
        # Older + newer SDKs both honor this attribute on the default client.
        openai.api_requestor = getattr(openai, "api_requestor", None)
    except Exception:
        pass
except Exception as e:  # pragma: no cover
    litellm = None
    logger.error(f"litellm not importable: {e}")


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _strip_to_json(text: str) -> str:
    """Pull the first JSON object out of a possibly-fenced model response."""
    if not text:
        return text
    m = _JSON_FENCE_RE.search(text)
    if m:
        return m.group(1)
    # Look for the first {...} block (greedy on outer braces).
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text


async def call_json(
    *,
    model: str,
    system: str,
    user: str,
    timeout_s: float = 8.0,
    max_tokens: int = 700,
    temperature: float = 0.0,
    fallback_models: Optional[list[str]] = None,
) -> Optional[dict]:
    """
    Call an LLM expecting strict JSON output. Returns parsed dict or None on failure.
    Tries `model` first; on rate-limit / 429 / failure, walks through `fallback_models`.
    One JSON-repair retry per model.
    """
    if litellm is None:
        logger.error("litellm not available")
        return None

    # Default fallback chain: if 70b 429s, drop to 8b.
    if fallback_models is None:
        if "70b" in model:
            fallback_models = ["groq/llama-3.1-8b-instant"]
        elif "8b" in model:
            fallback_models = ["groq/gemma2-9b-it"]
        else:
            fallback_models = []

    models_to_try = [model] + [m for m in fallback_models if m != model]

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    async def _once(mdl, msgs, use_json_format=True):
        try:
            kwargs = dict(
                model=mdl, messages=msgs,
                temperature=temperature, max_tokens=max_tokens,
                num_retries=0, max_retries=0,
            )
            if use_json_format:
                kwargs["response_format"] = {"type": "json_object"}
            resp = await asyncio.wait_for(
                litellm.acompletion(**kwargs), timeout=timeout_s,
            )
            return resp.choices[0].message.content or "", None
        except asyncio.TimeoutError:
            return None, "timeout"
        except Exception as e:
            return None, f"{type(e).__name__}:{str(e)[:160]}"

    for mdl in models_to_try:
        raw, err = await _once(mdl, messages, True)
        if raw is None and err and "response_format" in err.lower():
            raw, err = await _once(mdl, messages, False)
        if raw is None:
            logger.warning(f"LLM {mdl} failed: {err}")
            # Only fall over on rate limits / capacity errors
            if err and any(s in err.lower() for s in ("ratelimit", "429", "overloaded", "capacity", "timeout")):
                continue
            return None
        try:
            return json.loads(_strip_to_json(raw))
        except json.JSONDecodeError:
            retry_msgs = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": "Your previous response was not valid JSON. Reply with ONLY the JSON object, no prose, no code fences."},
            ]
            raw2, err2 = await _once(mdl, retry_msgs, True)
            if raw2 is None:
                logger.warning(f"LLM {mdl} JSON-repair failed: {err2}")
                continue
            try:
                return json.loads(_strip_to_json(raw2))
            except json.JSONDecodeError as e:
                logger.warning(f"LLM {mdl} JSON parse failed twice: {e}; raw='{raw2[:200]}'")
                continue
    return None
