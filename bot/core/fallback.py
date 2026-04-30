"""Deterministic template fallback for when the LLM is unavailable / rate-limited.

Goal: ALWAYS ship a context-grounded message rather than empty actions on /tick.
These won't win on creativity but they cite real facts and follow the rules
(no URLs, no fabrications, single CTA, Hindi tokens when needed).
"""
from __future__ import annotations

from typing import Optional


def _owner(merchant: dict) -> str:
    ident = merchant.get("identity") or {}
    return ident.get("owner_first_name") or ident.get("name", "").split()[0] or ""


def _is_hi(merchant: dict) -> bool:
    return "hi" in ((merchant.get("identity") or {}).get("languages") or [])


def _greet(merchant: dict, trigger: dict, customer: Optional[dict]) -> str:
    if trigger.get("scope") == "customer" and customer:
        cn = (customer.get("identity") or {}).get("name", "")
        first = cn.split()[0] if cn else ""
        return first or "Aapko"
    own = _owner(merchant)
    cat = (merchant.get("category_slug") or "").lower()
    if cat == "dentists" and own:
        return f"Dr. {own}"
    return own or "Hi"


def _digest_item(category: dict, top_item_id: str | None) -> Optional[dict]:
    digest = category.get("digest") or []
    if top_item_id:
        for d in digest:
            if d.get("id") == top_item_id:
                return d
    return digest[0] if digest else None


def _first_offer_title(merchant: dict) -> Optional[str]:
    for o in merchant.get("offers") or []:
        t = o.get("title")
        if t: return t
    return None


def _build(trigger: dict, merchant: dict, category: dict, customer: Optional[dict] = None) -> Optional[dict]:
    kind = trigger.get("kind", "")
    payload = trigger.get("payload") or {}
    g = _greet(merchant, trigger, customer)
    hi = _is_hi(merchant)
    sup = trigger.get("suppression_key", "")

    if kind == "research_digest":
        d = _digest_item(category, payload.get("top_item_id"))
        if not d: return None
        title = d.get("title", "")
        src = d.get("source", "")
        if hi:
            body = f"{g}, {src} mein ek study aayi hai: {title}. Kya main aapke liye iska 2-min abstract draft karu?"
        else:
            body = f"{g}, new from {src}: {title}. Want me to pull the 2-min abstract?"
        return dict(body=body, cta="open_ended", suppression_key=sup,
                    rationale=f"Lever: reciprocity. Anchor: category.digest[{d.get('id','?')}].title (template fallback).")

    if kind == "perf_dip":
        metric = payload.get("metric", "calls")
        delta = payload.get("delta_pct", 0) or 0
        pct = abs(int(round(delta * 100)))
        sign = "neeche" if delta < 0 else "upar"
        if hi:
            body = (f"{g}, aapke {metric} pichle 7 din mein {pct}% {sign} hain. "
                    f"Ek root-cause check + ek fix sujha doon? Reply YES.")
        else:
            body = (f"{g}, your {metric} are {pct}% {'down' if delta<0 else 'up'} over 7 days. "
                    f"Want me to flag the likely cause + one fix? Reply YES.")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale=f"Lever: specificity. Anchor: merchant.performance.delta_7d.{metric} (template fallback).")

    if kind == "perf_spike":
        metric = payload.get("metric", "views")
        delta = payload.get("delta_pct", 0) or 0
        pct = abs(int(round(delta * 100)))
        offer = _first_offer_title(merchant) or ""
        anchor = f' Aapka "{offer}" boost karu kya?' if offer else " Boost campaign chalu karu?"
        if hi:
            body = f"{g}, {metric} +{pct}% pichle 7 din mein.{anchor}"
        else:
            body = f"{g}, {metric} are up {pct}% in 7 days.{anchor.strip().replace('Aapka','Your').replace('boost karu kya','— want to push it further').replace('chalu karu','— want me to start')}"
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale=f"Lever: reciprocity. Anchor: merchant.performance.delta_7d (template fallback).")

    if kind == "supply_alert":
        batches = payload.get("batches") or payload.get("batch_ids") or []
        molecule = payload.get("molecule") or payload.get("medicine") or "the affected batch"
        bstr = ", ".join(batches[:3]) if isinstance(batches, list) else str(batches)
        if hi:
            body = (f"{g}, {molecule} ({bstr}) ka recall / replacement aaya hai — "
                    f"affected customers ki list nikaal du? Reply YES.")
        else:
            body = (f"{g}, {molecule} batches {bstr} need replacement. "
                    f"Want me to pull affected customers? Reply YES.")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: loss_aversion. Anchor: trigger.payload.batches (template fallback).")

    if kind == "ipl_match_today":
        opps = payload.get("teams") or payload.get("opponents") or "today's match"
        is_weekend = bool(payload.get("is_weekend"))
        if is_weekend:
            offer = _first_offer_title(merchant) or "delivery special"
            base = (f"{g}, {opps} aaj — Saturday/Sunday pe log ghar pe dekhte hain. "
                    f'"{offer}" ko delivery push karein? Reply YES.')
        else:
            offer = _first_offer_title(merchant) or "match-night offer"
            base = (f"{g}, {opps} aaj — weeknight crowd dine-in mein aata hai. "
                    f'"{offer}" pe match-night promo chalu karu? Reply YES.')
        return dict(body=base, cta="yes_no", suppression_key=sup,
                    rationale="Lever: specificity (counter-intuitive day-check). Anchor: trigger.payload (template fallback).")

    if kind == "festival_upcoming":
        fest = payload.get("festival") or payload.get("name") or "the festival"
        days = payload.get("days_away")
        offer = _first_offer_title(merchant) or "your top offer"
        when = f" ({days} din baad)" if days else ""
        if hi:
            body = f'{g}, {fest}{when} aane wala hai. "{offer}" pe festival creative banaa du? Reply YES.'
        else:
            body = f'{g}, {fest}{when} approaching. Want a festival creative for "{offer}"? Reply YES.'
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale=f"Lever: loss_aversion. Anchor: trigger.payload.festival (template fallback).")

    if kind in ("recall_due", "customer_lapsed_soft", "wedding_package_followup", "chronic_refill_due", "post_visit_followup"):
        # Customer-facing.
        cn = (customer or {}).get("identity", {}).get("name", "").split()[0] if customer else ""
        own = _owner(merchant)
        clinic = (merchant.get("identity") or {}).get("name", "")
        offer = _first_offer_title(merchant) or "ek slot"
        if kind == "recall_due":
            line = "6 mahine ka cleaning recall due hai" if hi else "your 6-month cleaning is due"
            cta_q = f'"{offer}" ke liye Wed 6pm slot chahiye?' if hi else f'Want a Wed 6pm slot for "{offer}"?'
        elif kind == "wedding_package_followup":
            days = (payload.get("days_to_wedding") or payload.get("days_remaining") or "kuch")
            line = f"shaadi mein {days} din baaki hain" if hi else f"{days} days to your wedding"
            cta_q = "skin-prep slot abhi book karu kya?" if hi else "Shall I lock a skin-prep slot now?"
        elif kind == "chronic_refill_due":
            line = "aapki refill window aa gayi hai" if hi else "your refill window is here"
            cta_q = "ghar pe deliver karu — confirm?" if hi else "Confirm and I'll dispatch?"
        else:  # customer_lapsed_soft, post_visit_followup
            line = "kaafi din ho gaye" if hi else "it has been a while"
            cta_q = f'"{offer}" pe slot chahiye?' if hi else f'Want a slot for "{offer}"?'
        body = f"Hi {cn or ''}, {own or clinic} se. {line}. {cta_q}".strip()
        return dict(body=body, cta="open_ended" if kind in ("recall_due","customer_lapsed_soft") else "yes_no",
                    suppression_key=sup,
                    rationale=f"Lever: reciprocity. Anchor: customer.last_visit + merchant.offers (template fallback for {kind}).")

    # Generic fallback: cite the merchant + trigger kind without inventing.
    own = _owner(merchant)
    if hi:
        body = f"{g or own}, ek update aapke business ke liye — abhi 1 min de sakte hain? haan ya nahi?"
    else:
        body = f"{g or own}, quick update on your business — got 1 min? Reply YES."
    return dict(body=body, cta="yes_no", suppression_key=sup,
                rationale=f"Generic template fallback for kind={kind}.")


def fallback_message(category: dict, merchant: dict, trigger: dict,
                     customer: Optional[dict] = None) -> Optional[dict]:
    """Return a deterministic message dict, or None if we can't assemble one."""
    try:
        return _build(trigger, merchant, category, customer)
    except Exception:
        return None
