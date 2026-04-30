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
            body = (f"{g}, {src} mein abhi ek interesting study aayi — \"{title}\". "
                    f"Soch raha tha aap dekhna chahenge. 2-min summary bhej du?")
        else:
            body = (f"{g}, {src} just published something I think you'd want to see — \"{title}\". "
                    f"Want me to drop the 2-min summary?")
        return dict(body=body, cta="open_ended", suppression_key=sup,
                    rationale=f"Lever: reciprocity. Anchor: category.digest[{d.get('id','?')}].title (template fallback).")

    if kind == "perf_dip":
        metric = payload.get("metric", "calls")
        delta = payload.get("delta_pct", 0) or 0
        pct = abs(int(round(delta * 100)))
        if hi:
            body = (f"{g}, ek baat notice hui — pichle 7 din mein {metric} {pct}% neeche hain. "
                    f"Tension wali baat nahi, par kaaran samajh lein? Main 1 likely reason + 1 fix bhej deta hoon — bolo?")
        else:
            body = (f"{g}, quick heads-up — {metric} are down {pct}% over the last 7 days. "
                    f"Nothing alarming, but worth a look. Want me to flag the likely cause + 1 fix?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale=f"Lever: specificity. Anchor: merchant.performance.delta_7d.{metric} (template fallback).")

    if kind == "perf_spike":
        metric = payload.get("metric", "views")
        delta = payload.get("delta_pct", 0) or 0
        pct = abs(int(round(delta * 100)))
        offer = _first_offer_title(merchant) or ""
        if hi:
            anchor = f' "{offer}" pe ek boost daal du?' if offer else " Ek boost campaign chala du?"
            body = f"{g}, zabardast — {metric} +{pct}% pichle 7 din mein!{anchor} Momentum hai abhi, lock kar lein."
        else:
            anchor = f' Want me to push "{offer}" while the wave is here?' if offer else " Want me to ride the wave with a quick boost?"
            body = f"{g}, big week — {metric} up {pct}% over 7 days.{anchor} Momentum's on — let's not waste it."
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale=f"Lever: reciprocity. Anchor: merchant.performance.delta_7d (template fallback).")

    if kind == "supply_alert":
        batches = (payload.get("affected_batches") or payload.get("batches")
                   or payload.get("batch_ids") or [])
        molecule = payload.get("molecule") or payload.get("medicine") or "the affected batch"
        bstr = ", ".join(batches[:3]) if isinstance(batches, list) else str(batches)
        bsuffix = f" ({bstr})" if bstr else ""
        if hi:
            body = (f"{g}, ek important update — {molecule}{bsuffix} ka recall aaya hai. "
                    f"Patient safety pehle. Affected customers ki list nikaal du, taaki aap aaj hi reach out kar sakein?")
        else:
            body = (f"{g}, important — {molecule}{(' batches ' + bstr) if bstr else ''} have been recalled. "
                    f"Patient safety first. Want me to pull the affected customer list so you can reach out today?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: loss_aversion. Anchor: trigger.payload.batches (template fallback).")

    if kind == "ipl_match_today":
        opps = payload.get("teams") or payload.get("opponents") or "today's match"
        is_weekend = bool(payload.get("is_weekend"))
        if is_weekend:
            offer = _first_offer_title(merchant) or "delivery special"
            if hi:
                base = (f"{g}, {opps} aaj — weekend hai toh log ghar pe baith ke dekhenge. "
                        f'Dine-in slow rahega; "{offer}" ko delivery pe push karein? Main banner ready kar deta hoon.')
            else:
                base = (f"{g}, {opps} tonight — it's a weekend so the crowd will watch from home. "
                        f'Dine-in will be slow; want to push "{offer}" on delivery? I can have the banner ready.')
        else:
            offer = _first_offer_title(merchant) or "match-night offer"
            if hi:
                base = (f"{g}, {opps} aaj — weeknight hai, log group mein dine-in karte hain. "
                        f'"{offer}" ko match-night offer banaa du? Bolo, kar deta hoon.')
            else:
                base = (f"{g}, {opps} tonight — weeknight crowd usually comes in for dine-in groups. "
                        f'Want me to spin "{offer}" into a match-night promo? Say the word.')
        return dict(body=base, cta="yes_no", suppression_key=sup,
                    rationale="Lever: specificity (counter-intuitive day-check). Anchor: trigger.payload (template fallback).")

    if kind == "festival_upcoming":
        fest = payload.get("festival") or payload.get("name") or "the festival"
        days = payload.get("days_away")
        offer = _first_offer_title(merchant) or "your top offer"
        when = f" ({days} din baad)" if days else ""
        if hi:
            body = (f"{g}, {fest}{when} aa raha hai. Pehle se ready ho jaayein toh better — "
                    f'"{offer}" pe ek festival creative banaa du?')
        else:
            body = (f"{g}, {fest}{when} is coming up. Better to be ready early — "
                    f'want a festival creative for "{offer}"?')
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale=f"Lever: loss_aversion. Anchor: trigger.payload.festival (template fallback).")

    if kind == "competitor_opened":
        comp = payload.get("competitor_name") or "a new competitor"
        dist = payload.get("distance_km")
        their = payload.get("their_offer") or ""
        anchor = f' Unka offer dekha — "{their}".' if their else ""
        dist_s = f" {dist} km dur" if dist else ""
        if hi:
            body = (f"{g}, {comp}{dist_s} pe naya open hua hai.{anchor} "
                    f"Ghabraane ki baat nahi — aapki USP strong hai. Ek 'why us' counter-message draft karu?")
        else:
            body = (f"{g}, {comp} just opened{(' ' + str(dist) + ' km away') if dist else ''}.{anchor} "
                    f"Nothing to worry about — your USP is solid. Want me to draft a 'why us' counter-message?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: loss_aversion. Anchor: trigger.payload.competitor (template).")

    if kind == "review_theme_emerged":
        theme = payload.get("theme", "a recurring concern")
        n = payload.get("occurrences_30d", "")
        quote = payload.get("common_quote", "")
        qstr = f' Ek customer ne likha: "{quote}".' if quote and hi else (f' One quote: "{quote}".' if quote else "")
        if hi:
            body = (f"{g}, pichle 30 din mein {n} reviews ne '{theme}' mention kiya hai.{qstr} "
                    f"Kabhi-kabhi yeh chhoti dikhti hai par compound hoti hai. Public reply + 1 ops fix sujhaaun?")
        else:
            body = (f"{g}, {n} reviews in the last 30d have flagged '{theme}'.{qstr} "
                    f"Small things compound. Want a public reply + 1 ops fix?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: loss_aversion. Anchor: trigger.payload.theme (template).")

    if kind == "milestone_reached":
        metric = payload.get("metric", "milestone")
        nv = payload.get("value_now", "")
        mv = payload.get("milestone_value", "")
        if hi:
            body = (f"{g}, badhaai ho — {metric} {nv} pe pahunch gaya, {mv} bas thoda dur! "
                    f'Yeh moment celebrate karna chahiye. "Thank you" creative + ek incentive post tayyar karu?')
        else:
            body = (f"{g}, congrats — your {metric} just hit {nv}, only {mv} away from the milestone! "
                    f'Worth celebrating publicly. Want me to draft a "thank you" creative + an incentive post?')
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: social_proof. Anchor: merchant.performance.metric (template).")

    if kind == "renewal_due":
        days = payload.get("days_remaining", "")
        plan = payload.get("plan", "Pro")
        amt = payload.get("renewal_amount", "")
        amt_s = f" (Rs {amt})" if amt else ""
        if hi:
            body = (f"{g}, sirf ek dosti reminder — aapka {plan} plan{amt_s} {days} din mein renew hoga. "
                    f"1-tap link bhej du, aaram se kar lijiyega?")
        else:
            body = (f"{g}, just a friendly reminder — your {plan} plan{amt_s} renews in {days} days. "
                    f"Want the 1-tap link so you can do it whenever's convenient?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: loss_aversion. Anchor: trigger.payload.days_remaining (template).")

    if kind == "winback_eligible":
        d = payload.get("days_since_expiry", "")
        dip = payload.get("perf_dip_pct")
        lapsed = payload.get("lapsed_customers_added_since_expiry", "")
        dipstr = ""
        if isinstance(dip, (int, float)):
            dipstr = f" calls bhi {abs(int(dip*100))}% neeche aaye hain" if hi else f" calls dropped {abs(int(dip*100))}%"
        if hi:
            body = (f"{g}, seedha bolun? Expiry ko {d} din ho gaye —{dipstr}, aur {lapsed} customers ne switch kiya. "
                    f"Wapas laana mushkil nahi — 50% off ek hafte ka winback push chala du?")
        else:
            body = (f"{g}, honest take? It's been {d} days since expiry —{dipstr}, and {lapsed} customers have lapsed. "
                    f"Not hard to recover — want me to run a 7-day 50%-off winback push?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: loss_aversion. Anchor: trigger.payload (template).")

    if kind == "dormant_with_vera":
        days = payload.get("days_since_last_merchant_message", "")
        topic = payload.get("last_topic", "")
        ts = f" (last baar '{topic}' pe baat hui thi)" if (topic and hi) else (f" (last we spoke about '{topic}')" if topic else "")
        if hi:
            body = (f"{g}, kaafi din ho gaye — {days} din se aapka koi message nahi aaya{ts}. "
                    f"Sab thik hai? Abhi sabse bada question kya hai, bata dijiye.")
        else:
            body = (f"{g}, it's been a while — {days} days since your last message{ts}. "
                    f"Everything ok? What's the biggest question on your mind right now?")
        return dict(body=body, cta="open_ended", suppression_key=sup,
                    rationale="Lever: reciprocity. Anchor: merchant.conversation_history (template).")

    if kind == "curious_ask_due":
        if hi:
            body = (f"{g}, ek mast trend dekha aapke area mein — "
                    f"share karu? Ya batayiye kis topic pe sabse zyada interest hai aaj kal.")
        else:
            body = (f"{g}, spotted an interesting trend in your area this week — "
                    f"want me to share? Or tell me what topic you're most curious about.")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: curiosity. Anchor: category.trend_signals (template).")

    if kind == "active_planning_intent":
        topic = payload.get("intent_topic", "your idea")
        last_msg = payload.get("merchant_last_message", "")
        ms = f' Aapne kaha tha: "{last_msg[:80]}".' if (last_msg and hi) else (f' You said: "{last_msg[:80]}".' if last_msg else "")
        if hi:
            body = (f"{g}, '{topic}' wali baat aage badhaate hain.{ms} "
                    f"Main 3 bullet plan + ek sample creative draft kar deta hoon — bhej du?")
        else:
            body = (f"{g}, let's pick up '{topic}' where we left off.{ms} "
                    f"I'll draft a 3-bullet plan + sample creative — want it?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: reciprocity. Anchor: trigger.payload.intent_topic (template).")

    if kind == "regulation_change":
        deadline = payload.get("deadline_iso", "")[:10]
        d_id = payload.get("top_item_id", "")
        if hi:
            body = (f"{g}, ek compliance update aaya hai — deadline {deadline}. "
                    f"Bhaag-daud nahi karni padegi, bas ek 2-min checklist follow karni hai. Bhej du?")
        else:
            body = (f"{g}, a compliance update is out — deadline {deadline}. "
                    f"No scramble needed, just a 2-min checklist to follow. Should I send it?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale=f"Lever: loss_aversion. Anchor: category.digest[{d_id}] (template).")

    if kind == "seasonal_perf_dip":
        metric = payload.get("metric", "views")
        d = payload.get("delta_pct", 0) or 0
        pct = abs(int(round(d * 100)))
        note = payload.get("season_note", "seasonal pattern")
        if hi:
            body = (f"{g}, {metric} {pct}% neeche dikh rahe hain — par ghabraayein nahi, "
                    f"yeh expected hai ({note}). Off-season mein retention pe focus karte hain — ek play sujhaaun?")
        else:
            body = (f"{g}, {metric} are down {pct}% — but no panic, "
                    f"this is expected ({note}). Off-season is the right time to focus on retention — want a play?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: reciprocity. Anchor: trigger.payload.is_expected_seasonal (template).")

    if kind == "category_seasonal":
        season = payload.get("season", "this season")
        trends = payload.get("trends") or []
        top = trends[0] if trends else ""
        if hi:
            body = (f"{g}, {season} mein '{top}' jaise items pe demand kaafi badh rahi hai. "
                    f"Shelf thoda adjust kar lein, ek promo bhi banaa du — saath mein chala dein?")
        else:
            body = (f"{g}, {season} is bringing demand spikes on items like '{top}'. "
                    f"Worth tweaking the shelf — want me to send a quick adjustment + 1 promo plan?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: specificity. Anchor: trigger.payload.trends (template).")

    if kind == "gbp_unverified":
        uplift = payload.get("estimated_uplift_pct")
        upstr = f" (~{int(uplift*100)}% extra discovery milti hai)" if (isinstance(uplift, (int, float)) and hi) else (f" (~{int(uplift*100)}% extra discovery)" if isinstance(uplift, (int, float)) else "")
        path = payload.get("verification_path", "")
        if hi:
            body = (f"{g}, ek chhoti si baat — aapka Google Business Profile ab tak verify nahi hua{upstr}. "
                    f"{path} se ho jaata hai, 5 minute ka kaam. Main steps bhej du?")
        else:
            body = (f"{g}, small thing — your Google Business Profile isn't verified yet{upstr}. "
                    f"Takes 5 minutes via {path}. Want me to send the steps?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: loss_aversion. Anchor: trigger.payload.verified=false (template).")

    if kind == "cde_opportunity":
        d_id = payload.get("digest_item_id", "")
        cred = payload.get("credits", "")
        fee = payload.get("fee", "")
        fee_s = " (members ke liye free)" if ("free" in str(fee) and hi) else (" (free for members)" if "free" in str(fee) else (f" ({fee})" if fee else ""))
        if hi:
            body = (f"{g}, ek webinar dekha — {cred} CDE credits milenge{fee_s}. "
                    f"Aapke kaam ki lagi. Calendar invite bhej du?")
        else:
            body = (f"{g}, spotted a webinar — {cred} CDE credits{fee_s}. "
                    f"Looked relevant for you. Want the calendar invite?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale=f"Lever: reciprocity. Anchor: category.digest[{d_id}] (template).")

    if kind == "appointment_tomorrow":
        cn = (customer or {}).get("identity", {}).get("name", "").split()[0] if customer else ""
        own = _owner(merchant); clinic = (merchant.get("identity") or {}).get("name", "")
        sender = own or clinic
        if hi:
            body = (f"Namaste {cn}, {sender} ki taraf se ek reminder — kal aapka appointment hai. "
                    f"Aa rahe hain na? Ek 'haan' kaafi hai.")
        else:
            body = (f"Hi {cn}, quick reminder from {sender} — you have your appointment tomorrow. "
                    f"Are you still on? A quick 'yes' is all I need.")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: specificity. Anchor: trigger.kind=appointment_tomorrow (template).")

    if kind == "trial_followup":
        cn = (customer or {}).get("identity", {}).get("name", "").split()[0] if customer else ""
        own = _owner(merchant); clinic = (merchant.get("identity") or {}).get("name", "")
        sender = own or clinic
        nxt = payload.get("next_session_options") or []
        slot_label = nxt[0].get("label", "") if nxt and isinstance(nxt[0], dict) else ""
        if hi:
            slot_s = f' Aapke liye {slot_label} hold kar raha hoon.' if slot_label else ''
            body = (f"Namaste {cn}, {sender} se. Trial kaisa laga? "
                    f"Agar accha laga toh next session lock kar dete hain.{slot_s} Bolo?")
        else:
            slot_s = f' I can hold {slot_label} for you.' if slot_label else ''
            body = (f"Hi {cn}, {sender} here. How was the trial? "
                    f"If it worked for you, let's lock the next session.{slot_s} Want to?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: reciprocity. Anchor: trigger.payload.next_session_options (template).")

    if kind == "customer_lapsed_hard":
        cn = (customer or {}).get("identity", {}).get("name", "").split()[0] if customer else ""
        own = _owner(merchant); clinic = (merchant.get("identity") or {}).get("name", "")
        sender = own or clinic
        days = payload.get("days_since_last_visit", "")
        prev = payload.get("previous_focus", "")
        if hi:
            body = (f"Namaste {cn}, {sender} se. {days} din baad yaad aaya — "
                    f"pichli baar '{prev}' pe humne saath kaam kiya tha. Ek free re-assessment rakh dete hain, "
                    f"dekhein kahan tak aaye? Bolo, slot bhej du?")
        else:
            body = (f"Hi {cn}, {sender} here. Reaching out after {days} days — "
                    f"last time we worked on '{prev}' together. Let's do a free re-assessment to see where you are now. "
                    f"Want me to send a slot?")
        return dict(body=body, cta="yes_no", suppression_key=sup,
                    rationale="Lever: reciprocity. Anchor: customer.last_visit (template).")

    if kind in ("recall_due", "customer_lapsed_soft", "wedding_package_followup", "chronic_refill_due", "post_visit_followup"):
        cn = (customer or {}).get("identity", {}).get("name", "").split()[0] if customer else ""
        own = _owner(merchant)
        clinic = (merchant.get("identity") or {}).get("name", "")
        sender = own or clinic
        offer = _first_offer_title(merchant) or "ek slot"
        if kind == "recall_due":
            if hi:
                line = "aapka 6-mahine ka cleaning recall due hai"
                cta_q = "Wed 6pm slot rakh du, ya koi aur time prefer karenge?"
            else:
                line = "your 6-month cleaning is due"
                cta_q = "I can hold Wed 6pm — does that work, or another time?"
        elif kind == "wedding_package_followup":
            days = (payload.get("days_to_wedding") or payload.get("days_remaining") or "kuch")
            if hi:
                line = f"shaadi mein bas {days} din baaki hain"
                cta_q = "Skin-prep ka slot abhi lock kar lein? Bolo, kar deta hoon."
            else:
                line = f"only {days} days to your wedding now"
                cta_q = "Shall I lock a skin-prep slot now? Just say the word."
        elif kind == "chronic_refill_due":
            if hi:
                line = "aapki refill ki time aa gayi hai"
                cta_q = "Ghar pe bhej du, ya store se pick karenge? Confirm kar dein."
            else:
                line = "your refill window is here"
                cta_q = "Want home delivery, or you'll pick up? Just confirm."
        else:
            if hi:
                line = "kaafi din ho gaye, yaad aaya"
                cta_q = f'"{offer}" ke liye ek slot bhej du?'
            else:
                line = "it's been a while — thought of reaching out"
                cta_q = f'Want me to send a slot for "{offer}"?'
        prefix = ("Namaste" if hi else "Hi")
        body = f"{prefix} {cn or ''}, {sender} se. {line}. {cta_q}".strip()
        return dict(body=body, cta="open_ended" if kind in ("recall_due","customer_lapsed_soft") else "yes_no",
                    suppression_key=sup,
                    rationale=f"Lever: reciprocity. Anchor: customer.last_visit + merchant.offers (template fallback for {kind}).")

    own = _owner(merchant)
    if hi:
        body = (f"{g or own}, ek chhota update share karna chahta tha aapke business ke baare mein. "
                f"Abhi 1 min hai? Bolo, bhej du?")
    else:
        body = (f"{g or own}, wanted to share a small update about your business. "
                f"Got a minute? Should I send it?")
    return dict(body=body, cta="yes_no", suppression_key=sup,
                rationale=f"Generic template fallback for kind={kind}.")


def fallback_message(category: dict, merchant: dict, trigger: dict,
                     customer: Optional[dict] = None) -> Optional[dict]:
    """Return a deterministic message dict, or None if we can't assemble one."""
    try:
        return _build(trigger, merchant, category, customer)
    except Exception:
        return None
