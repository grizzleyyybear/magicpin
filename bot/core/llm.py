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
) -> Optional[dict]:
    """
    Call an LLM expecting strict JSON output. Returns parsed dict or None on failure.
    One retry with a corrective hint if the first response doesn't parse.
    """
    if litellm is None:
        logger.error("litellm not available")
        return None

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    async def _once(msgs):
        try:
            resp = await asyncio.wait_for(
                litellm.acompletion(
                    model=model,
                    messages=msgs,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                    num_retries=0,
                    max_retries=0,
                ),
                timeout=timeout_s,
            )
            return resp.choices[0].message.content or ""
        except asyncio.TimeoutError:
            logger.warning(f"LLM timeout after {timeout_s}s on {model}")
            return None
        except Exception as e:
            err_str = str(e).lower()
            # Some models reject response_format - try once without it.
            if "response_format" in err_str or "unsupported" in err_str:
                try:
                    resp = await asyncio.wait_for(
                        litellm.acompletion(
                            model=model,
                            messages=msgs,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            num_retries=0,
                        ),
                        timeout=timeout_s,
                    )
                    return resp.choices[0].message.content or ""
                except Exception as e2:
                    logger.warning(f"LLM call failed twice: {e2}")
                    return None
            logger.warning(f"LLM call failed: {type(e).__name__}: {str(e)[:200]}")
            return None

    raw = await _once(messages)
    if raw is None:
        return None
    try:
        return json.loads(_strip_to_json(raw))
    except json.JSONDecodeError:
        # Retry once with a corrective hint.
        retry_msgs = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": "Your previous response was not valid JSON. Reply with ONLY the JSON object, no prose, no code fences."},
        ]
        raw2 = await _once(retry_msgs)
        if raw2 is None:
            return None
        try:
            return json.loads(_strip_to_json(raw2))
        except json.JSONDecodeError as e:
            logger.warning(f"LLM JSON parse failed twice: {e}; raw='{raw2[:200]}'")
            return None
