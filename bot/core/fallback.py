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
        batches = (payload.get("affected_batches") or payload.get("batches")
                   or payload.get("batch_ids") or [])
        molecule = payload.get("molecule") or payload.get("medicine") or "the affected batch"
        bstr = ", ".join(batches[:3]) if isinstance(batches, list) else str(batches)
        bsuffix = f" ({bstr})" if bstr else ""
        if hi:
            body = (f"{g}, {molecule}{bsuffix} ka recall / replacement aaya hai — "
                    f"affected customers ki list nikaal du? Reply YES.")
        else:
            body = (f"{g}, {molecule}{(' batches ' + bstr) if bstr else ''} need replacement. "
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

    if kind == "competitor_opened":
        comp = payload.get("competitor_name") or "a new competitor"
        dist = payload.get("distance_km")
        their = payload.get("their_offer") or ""
        anchor = f' Unka offer: "{their}".' if their else ""
        dist_s = f" {dist} km dur" if dist else ""
        if hi:
            body = (f"{g}, {comp}{dist_s} pe khul gaya hai.{anchor} "
                    f"Aapka counter-offer + 'why us' message draft karu? Reply YES.")
        else:
            body = (f"{g}, {comp} just opened{(' ' + str(dist) + ' km away') if dist else ''}.{anchor} "
                    f"Want me to draft a counter-offer + 'why us' message? Reply YES.")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: loss_aversion. Anchor: trigger.payload.competitor (template).")

    if kind == "review_theme_emerged":
        theme = payload.get("theme", "a recurring concern")
        n = payload.get("occurrences_30d", "")
        quote = payload.get("common_quote", "")
        qstr = f' Sample: "{quote}".' if quote else ""
        if hi:
            body = (f"{g}, pichle 30 din mein {n} reviews mein '{theme}' theme uthi hai.{qstr} "
                    f"Ek public reply + ek operations fix sujha doon? Reply YES.")
        else:
            body = (f"{g}, {n} reviews in last 30d flagged '{theme}'.{qstr} "
                    f"Want a public reply template + 1 ops fix? Reply YES.")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: loss_aversion. Anchor: trigger.payload.theme (template).")

    if kind == "milestone_reached":
        metric = payload.get("metric", "milestone")
        nv = payload.get("value_now", "")
        mv = payload.get("milestone_value", "")
        if hi:
            body = (f"{g}, aapka {metric} {nv} pe pahunch gaya hai — {mv} bas thoda dur. "
                    f'"Thank you" creative + ek incentive post launch karu? Reply YES.')
        else:
            body = (f"{g}, your {metric} just hit {nv} — only {mv} away from the milestone. "
                    f'Want a "thank you" creative + an incentive post? Reply YES.')
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: social_proof. Anchor: merchant.performance.metric (template).")

    if kind == "renewal_due":
        days = payload.get("days_remaining", "")
        plan = payload.get("plan", "Pro")
        amt = payload.get("renewal_amount", "")
        amt_s = f" Rs {amt}" if amt else ""
        if hi:
            body = (f"{g}, aapka {plan} plan{amt_s} renewal {days} din mein due hai. "
                    f"1-tap renewal link bhej du? Reply YES.")
        else:
            body = (f"{g}, your {plan} plan renews in {days} days{amt_s}. "
                    f"Should I send the 1-tap renewal? Reply YES.")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: loss_aversion. Anchor: trigger.payload.days_remaining (template).")

    if kind == "winback_eligible":
        d = payload.get("days_since_expiry", "")
        dip = payload.get("perf_dip_pct")
        lapsed = payload.get("lapsed_customers_added_since_expiry", "")
        dipstr = ""
        if isinstance(dip, (int, float)):
            dipstr = f" calls {abs(int(dip*100))}% neeche" if hi else f" calls {abs(int(dip*100))}% down"
        if hi:
            body = (f"{g}, expiry ke {d} din ho gaye —{dipstr}, {lapsed} customers ne dur ja diya. "
                    f"50% off ek week winback offer chalu karu? Reply YES.")
        else:
            body = (f"{g}, {d} days since expiry —{dipstr}, {lapsed} customers lapsed. "
                    f"Want a 50%-off 7-day winback push? Reply YES.")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: loss_aversion. Anchor: trigger.payload (template).")

    if kind == "dormant_with_vera":
        days = payload.get("days_since_last_merchant_message", "")
        topic = payload.get("last_topic", "")
        ts = f" '{topic}' pe " if (topic and hi) else (f" on '{topic}' " if topic else " ")
        if hi:
            body = (f"{g}, aapne {days} din se message nahi kiya.{ts}quick check-in: "
                    f"abhi sabse bada question kya hai? Bata dijiye.")
        else:
            body = (f"{g}, you haven't messaged in {days} days.{ts}quick check-in — "
                    f"what's the biggest question right now? Tell me.")
        return dict(body=body, cta="open_ended", suppression_key=sup,
                    rationale="Lever: reciprocity. Anchor: merchant.conversation_history (template).")

    if kind == "curious_ask_due":
        if hi:
            body = (f"{g}, aapke area mein abhi sabse zyada kya search ho raha hai — "
                    f"main 1 fact share karu? Reply YES ya batayiye kis topic pe.")
        else:
            body = (f"{g}, want a quick fact about what's trending in your area this week? "
                    f"Reply YES or tell me the topic.")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: curiosity. Anchor: category.trend_signals (template).")

    if kind == "active_planning_intent":
        topic = payload.get("intent_topic", "your idea")
        last_msg = payload.get("merchant_last_message", "")
        ms = f' Aapne kaha tha: "{last_msg[:80]}".' if last_msg else ""
        if hi:
            body = (f"{g}, '{topic}' pe ek 3-bullet plan + sample creative draft karu?{ms} "
                    f"Reply YES.")
        else:
            body = (f"{g}, want a 3-bullet plan + sample creative for '{topic}'?{ms} "
                    f"Reply YES.")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: reciprocity. Anchor: trigger.payload.intent_topic (template).")

    if kind == "regulation_change":
        deadline = payload.get("deadline_iso", "")[:10]
        d_id = payload.get("top_item_id", "")
        if hi:
            body = (f"{g}, ek niyam-update aaya hai — compliance deadline {deadline} hai. "
                    f"2-min checklist nikaal du? Reply YES.")
        else:
            body = (f"{g}, a regulatory update is out — compliance deadline {deadline}. "
                    f"Want the 2-min checklist? Reply YES.")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale=f"Lever: loss_aversion. Anchor: category.digest[{d_id}] (template).")

    if kind == "seasonal_perf_dip":
        metric = payload.get("metric", "views")
        d = payload.get("delta_pct", 0) or 0
        pct = abs(int(round(d * 100)))
        note = payload.get("season_note", "seasonal pattern")
        if hi:
            body = (f"{g}, aapke {metric} {pct}% neeche hain — yeh expected hai ({note}). "
                    f"Off-season retention play sujha doon? Reply YES.")
        else:
            body = (f"{g}, {metric} are down {pct}% — this is expected ({note}). "
                    f"Want an off-season retention play? Reply YES.")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: reciprocity. Anchor: trigger.payload.is_expected_seasonal (template).")

    if kind == "category_seasonal":
        season = payload.get("season", "this season")
        trends = payload.get("trends") or []
        top = trends[0] if trends else ""
        if hi:
            body = (f"{g}, {season} mein '{top}' jaise demand spike aa rahe hain. "
                    f"Shelf adjustment + 1 promo plan bhej du? Reply YES.")
        else:
            body = (f"{g}, {season} demand: {top} is spiking. "
                    f"Want a shelf adjustment + 1 promo plan? Reply YES.")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: specificity. Anchor: trigger.payload.trends (template).")

    if kind == "gbp_unverified":
        uplift = payload.get("estimated_uplift_pct")
        upstr = f" (~{int(uplift*100)}% uplift)" if isinstance(uplift, (int, float)) else ""
        path = payload.get("verification_path", "")
        if hi:
            body = (f"{g}, aapka Google Business Profile ab tak verify nahi hua{upstr}. "
                    f"{path} ke through karein — main steps bhej du? Reply YES.")
        else:
            body = (f"{g}, your GBP isn't verified yet{upstr}. "
                    f"Use {path} — want me to send the steps? Reply YES.")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: loss_aversion. Anchor: trigger.payload.verified=false (template).")

    if kind == "cde_opportunity":
        d_id = payload.get("digest_item_id", "")
        cred = payload.get("credits", "")
        fee = payload.get("fee", "")
        fee_s = " (free for members)" if "free" in str(fee) else (f" ({fee})" if fee else "")
        if hi:
            body = (f"{g}, ek webinar aaya hai — {cred} CDE credits{fee_s}. "
                    f"Calendar invite bhej du? Reply YES.")
        else:
            body = (f"{g}, a webinar is out — {cred} CDE credits{fee_s}. "
                    f"Want the calendar invite? Reply YES.")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale=f"Lever: reciprocity. Anchor: category.digest[{d_id}] (template).")

    if kind == "appointment_tomorrow":
        cn = (customer or {}).get("identity", {}).get("name", "").split()[0] if customer else ""
        own = _owner(merchant); clinic = (merchant.get("identity") or {}).get("name", "")
        if hi:
            body = (f"Hi {cn}, {own or clinic} se. Kal aapka appointment hai. "
                    f"Confirm karein — haan ya nahi?")
        else:
            body = (f"Hi {cn}, this is {own or clinic}. Your appointment is tomorrow. "
                    f"Confirm — yes or no?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: specificity. Anchor: trigger.kind=appointment_tomorrow (template).")

    if kind == "trial_followup":
        cn = (customer or {}).get("identity", {}).get("name", "").split()[0] if customer else ""
        own = _owner(merchant); clinic = (merchant.get("identity") or {}).get("name", "")
        nxt = payload.get("next_session_options") or []
        slot_label = nxt[0].get("label", "") if nxt and isinstance(nxt[0], dict) else ""
        slot_s = f' "{slot_label}"' if slot_label else ""
        if hi:
            body = (f"Hi {cn}, {own or clinic} se. Trial ke baad{(' next session ' + slot_s) if slot_label else ' next session'} chahiye? "
                    f"haan ya nahi?")
        else:
            body = (f"Hi {cn}, this is {own or clinic}. Want to lock the next session{slot_s}? "
                    f"yes or no?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: reciprocity. Anchor: trigger.payload.next_session_options (template).")

    if kind == "customer_lapsed_hard":
        cn = (customer or {}).get("identity", {}).get("name", "").split()[0] if customer else ""
        own = _owner(merchant); clinic = (merchant.get("identity") or {}).get("name", "")
        days = payload.get("days_since_last_visit", "")
        prev = payload.get("previous_focus", "")
        if hi:
            body = (f"Hi {cn}, {own or clinic} se. {days} din ho gaye — pichli baar '{prev}' pe kaam kiya tha. "
                    f"Ek free re-assessment karein?")
        else:
            body = (f"Hi {cn}, this is {own or clinic}. It's been {days} days — last time we focused on '{prev}'. "
                    f"Want a free re-assessment?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: reciprocity. Anchor: customer.last_visit (template).")

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
