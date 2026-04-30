"""Deterministic per-trigger templates used when the LLM is unavailable.

English-first. If merchant.identity.languages includes "hi", we add a single
light Hindi token (addressing or sign-off) to honour the language preference
without sounding like a Hinglish gimmick.
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
        return first or "Hi"
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
        if t:
            return t
    return None


def _build(trigger: dict, merchant: dict, category: dict,
           customer: Optional[dict] = None) -> Optional[dict]:
    kind = trigger.get("kind", "")
    payload = trigger.get("payload") or {}
    g = _greet(merchant, trigger, customer)
    hi = _is_hi(merchant)
    sup = trigger.get("suppression_key", "")

    if kind == "research_digest":
        d = _digest_item(category, payload.get("top_item_id"))
        if not d:
            return None
        title = d.get("title", "")
        src = d.get("source", "")
        body = (f'{g}, new from {src}: "{title}". '
                f"Want me to pull a 2-minute summary?")
        return dict(body=body, cta="open_ended", suppression_key=sup,
                    rationale=f"Lever: reciprocity. Anchor: category.digest[{d.get('id','?')}].title.")

    if kind == "perf_dip":
        metric = payload.get("metric", "calls")
        delta = payload.get("delta_pct", 0) or 0
        pct = abs(int(round(delta * 100)))
        body = (f"{g}, your {metric} are {pct}% down over the last 7 days. "
                f"Want me to flag the likely cause and one fix?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale=f"Lever: specificity. Anchor: merchant.performance.delta_7d.{metric}.")

    if kind == "perf_spike":
        metric = payload.get("metric", "views")
        delta = payload.get("delta_pct", 0) or 0
        pct = abs(int(round(delta * 100)))
        offer = _first_offer_title(merchant) or ""
        anchor = f' Want me to push "{offer}" while the wave is here?' if offer \
                 else " Want me to run a quick boost?"
        body = f"{g}, {metric} up {pct}% over 7 days.{anchor}"
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: reciprocity. Anchor: merchant.performance.delta_7d.")

    if kind == "supply_alert":
        batches = (payload.get("affected_batches") or payload.get("batches")
                   or payload.get("batch_ids") or [])
        molecule = payload.get("molecule") or payload.get("medicine") or "the affected stock"
        bstr = ", ".join(batches[:3]) if isinstance(batches, list) else str(batches)
        bsuffix = f" (batches {bstr})" if bstr else ""
        body = (f"{g}, {molecule}{bsuffix} has a recall notice. "
                f"Want me to pull the affected customer list so you can reach out today?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: loss_aversion. Anchor: trigger.payload.batches.")

    if kind == "ipl_match_today":
        opps = payload.get("teams") or payload.get("opponents") or "today's match"
        is_weekend = bool(payload.get("is_weekend"))
        if is_weekend:
            offer = _first_offer_title(merchant) or "delivery special"
            body = (f"{g}, {opps} tonight. It is a weekend so most viewers stay in. "
                    f'Want to push "{offer}" on delivery?')
        else:
            offer = _first_offer_title(merchant) or "match-night offer"
            body = (f"{g}, {opps} tonight. Weeknight crowds usually come in for dine-in groups. "
                    f'Want me to spin "{offer}" into a match-night promo?')
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: specificity (day-check). Anchor: trigger.payload.")

    if kind == "festival_upcoming":
        fest = payload.get("festival") or payload.get("name") or "the festival"
        days = payload.get("days_away")
        offer = _first_offer_title(merchant) or "your top offer"
        when = f" ({days} days away)" if days else ""
        body = (f'{g}, {fest}{when} is coming up. '
                f'Want a festival creative for "{offer}"?')
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: loss_aversion. Anchor: trigger.payload.festival.")

    if kind == "competitor_opened":
        comp = payload.get("competitor_name") or "a new competitor"
        dist = payload.get("distance_km")
        their = payload.get("their_offer") or ""
        anchor = f' Their offer is "{their}".' if their else ""
        dist_s = f" {dist} km away" if dist else ""
        body = (f"{g}, {comp} just opened{dist_s}.{anchor} "
                f"Want me to draft a counter-offer and a 'why us' note?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: loss_aversion. Anchor: trigger.payload.competitor.")

    if kind == "review_theme_emerged":
        theme = payload.get("theme", "a recurring concern")
        n = payload.get("occurrences_30d", "")
        quote = payload.get("common_quote", "")
        qstr = f' One quote: "{quote}".' if quote else ""
        body = (f"{g}, {n} reviews in the last 30 days flagged '{theme}'.{qstr} "
                f"Want a public reply template and one ops fix?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: loss_aversion. Anchor: trigger.payload.theme.")

    if kind == "milestone_reached":
        metric = payload.get("metric", "milestone")
        nv = payload.get("value_now", "")
        mv = payload.get("milestone_value", "")
        body = (f"{g}, your {metric} just hit {nv}, only {mv} away from the milestone. "
                f'Want a "thank you" creative and an incentive post?')
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: social_proof. Anchor: merchant.performance.metric.")

    if kind == "renewal_due":
        days = payload.get("days_remaining", "")
        plan = payload.get("plan", "Pro")
        amt = payload.get("renewal_amount", "")
        amt_s = f" (Rs {amt})" if amt else ""
        body = (f"{g}, quick reminder: your {plan} plan{amt_s} renews in {days} days. "
                f"Want me to send the 1-tap renewal link?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: loss_aversion. Anchor: trigger.payload.days_remaining.")

    if kind == "winback_eligible":
        d = payload.get("days_since_expiry", "")
        dip = payload.get("perf_dip_pct")
        lapsed = payload.get("lapsed_customers_added_since_expiry", "")
        dipstr = ""
        if isinstance(dip, (int, float)):
            dipstr = f", calls down {abs(int(dip*100))}%"
        body = (f"{g}, {d} days since expiry{dipstr}, and {lapsed} customers have lapsed. "
                f"Want me to run a 7-day 50% off winback push?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: loss_aversion. Anchor: trigger.payload.")

    if kind == "dormant_with_vera":
        days = payload.get("days_since_last_merchant_message", "")
        topic = payload.get("last_topic", "")
        ts = f" (we last spoke about '{topic}')" if topic else ""
        body = (f"{g}, it has been {days} days since your last message{ts}. "
                f"What is the biggest question on your mind right now?")
        return dict(body=body, cta="open_ended", suppression_key=sup,
                    rationale="Lever: reciprocity. Anchor: merchant.conversation_history.")

    if kind == "curious_ask_due":
        body = (f"{g}, I spotted an interesting trend in your area this week. "
                f"Want me to share, or tell me which topic you're most curious about?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: curiosity. Anchor: category.trend_signals.")

    if kind == "active_planning_intent":
        topic = payload.get("intent_topic", "your idea")
        last_msg = payload.get("merchant_last_message", "")
        ms = f' You said: "{last_msg[:80]}".' if last_msg else ""
        body = (f"{g}, picking up '{topic}' from where we left off.{ms} "
                f"I can draft a 3-bullet plan and a sample creative, want it?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: reciprocity. Anchor: trigger.payload.intent_topic.")

    if kind == "regulation_change":
        deadline = payload.get("deadline_iso", "")[:10]
        d_id = payload.get("top_item_id", "")
        body = (f"{g}, a compliance update is out, deadline {deadline}. "
                f"Want the 2-minute checklist?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale=f"Lever: loss_aversion. Anchor: category.digest[{d_id}].")

    if kind == "seasonal_perf_dip":
        metric = payload.get("metric", "views")
        d = payload.get("delta_pct", 0) or 0
        pct = abs(int(round(d * 100)))
        note = payload.get("season_note", "seasonal pattern")
        body = (f"{g}, {metric} are down {pct}%, but this is expected ({note}). "
                f"Want an off-season retention play?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: reciprocity. Anchor: trigger.payload.is_expected_seasonal.")

    if kind == "category_seasonal":
        season = payload.get("season", "this season")
        trends = payload.get("trends") or []
        top = trends[0] if trends else ""
        body = (f"{g}, {season} demand is spiking on items like '{top}'. "
                f"Want a shelf adjustment and one promo plan?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: specificity. Anchor: trigger.payload.trends.")

    if kind == "gbp_unverified":
        uplift = payload.get("estimated_uplift_pct")
        upstr = f" (about {int(uplift*100)}% extra discovery)" if isinstance(uplift, (int, float)) else ""
        path = payload.get("verification_path", "")
        body = (f"{g}, your Google Business Profile is not verified yet{upstr}. "
                f"It takes 5 minutes via {path}. Want the steps?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: loss_aversion. Anchor: trigger.payload.verified.")

    if kind == "cde_opportunity":
        d_id = payload.get("digest_item_id", "")
        cred = payload.get("credits", "")
        fee = payload.get("fee", "")
        fee_s = " (free for members)" if "free" in str(fee) else (f" ({fee})" if fee else "")
        body = (f"{g}, a webinar is out: {cred} CDE credits{fee_s}. "
                f"Want the calendar invite?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale=f"Lever: reciprocity. Anchor: category.digest[{d_id}].")

    if kind == "appointment_tomorrow":
        cn = (customer or {}).get("identity", {}).get("name", "").split()[0] if customer else ""
        own = _owner(merchant)
        clinic = (merchant.get("identity") or {}).get("name", "")
        sender = own or clinic
        confirm = "Reply haan to confirm." if hi else "Reply yes to confirm."
        body = f"Hi {cn}, reminder from {sender}: your appointment is tomorrow. {confirm}"
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: specificity. Anchor: trigger.kind=appointment_tomorrow.")

    if kind == "trial_followup":
        cn = (customer or {}).get("identity", {}).get("name", "").split()[0] if customer else ""
        own = _owner(merchant)
        clinic = (merchant.get("identity") or {}).get("name", "")
        sender = own or clinic
        nxt = payload.get("next_session_options") or []
        slot_label = nxt[0].get("label", "") if nxt and isinstance(nxt[0], dict) else ""
        slot_s = f" I can hold {slot_label} for you." if slot_label else ""
        body = (f"Hi {cn}, {sender} here. How was the trial? "
                f"If it worked, let's lock the next session.{slot_s} Want to?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: reciprocity. Anchor: trigger.payload.next_session_options.")

    if kind == "customer_lapsed_hard":
        cn = (customer or {}).get("identity", {}).get("name", "").split()[0] if customer else ""
        own = _owner(merchant)
        clinic = (merchant.get("identity") or {}).get("name", "")
        sender = own or clinic
        days = payload.get("days_since_last_visit", "")
        prev = payload.get("previous_focus", "")
        body = (f"Hi {cn}, {sender} here. It has been {days} days. "
                f"Last time we worked on '{prev}'. Want a free re-assessment slot?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: reciprocity. Anchor: customer.last_visit.")

    if kind in ("recall_due", "customer_lapsed_soft", "wedding_package_followup",
                "chronic_refill_due", "post_visit_followup"):
        cn = (customer or {}).get("identity", {}).get("name", "").split()[0] if customer else ""
        own = _owner(merchant)
        clinic = (merchant.get("identity") or {}).get("name", "")
        sender = own or clinic
        offer = _first_offer_title(merchant) or "a slot"
        if kind == "recall_due":
            line = "Your 6-month cleaning is due"
            cta_q = "I can hold Wed 6pm. Does that work, or another time?"
        elif kind == "wedding_package_followup":
            days = (payload.get("days_to_wedding") or payload.get("days_remaining") or "a few")
            line = f"Only {days} days to your wedding now"
            cta_q = "Shall I lock a skin-prep slot?"
        elif kind == "chronic_refill_due":
            line = "Your refill window is here"
            cta_q = "Home delivery or store pickup? Just confirm."
        else:
            line = "It has been a while since your last visit"
            cta_q = f'Want a slot for "{offer}"?'
        body = f"Hi {cn or ''}, {sender} here. {line}. {cta_q}".strip()
        cta = "open_ended" if kind in ("recall_due", "customer_lapsed_soft") else "yes_no"
        return dict(body=body, cta=cta, suppression_key=sup,
                    rationale=f"Lever: reciprocity. Anchor: customer.last_visit + merchant.offers ({kind}).")

    own = _owner(merchant)
    body = (f"{g or own}, a quick update on your business. "
            f"Got a minute? Want me to send it?")
    return dict(body=body, cta="yes_no", suppression_key=sup,
                rationale=f"Generic template fallback for kind={kind}.")


def fallback_message(category: dict, merchant: dict, trigger: dict,
                     customer: Optional[dict] = None) -> Optional[dict]:
    try:
        return _build(trigger, merchant, category, customer)
    except Exception:
        return None
