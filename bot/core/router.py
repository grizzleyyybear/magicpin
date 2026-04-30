"""TriggerRouter — gate every trigger before composing.

The seven gates from plan.md, plus a restraint heuristic that caps total sends.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from .. import config
from .conv import ConversationStore
from .store import ContextStore

logger = logging.getLogger("vera.router")

WINBACK_KINDS = {"winback", "renewal_reminder", "subscription_lapse"}


def _parse_iso(s: str) -> Optional[datetime]:
    if not s: return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def gate_decision(
    trigger: dict,
    merchant: Optional[dict],
    customer: Optional[dict],
    cstore: ContextStore,
    conv_store: ConversationStore,
    now: datetime,
) -> tuple[bool, str]:
    """Return (allow, reason)."""
    tid = trigger.get("id", "")
    mid = trigger.get("merchant_id", "")

    if not merchant:
        return False, "merchant_context_missing"

    # 1. Expiry
    exp = _parse_iso(trigger.get("expires_at", ""))
    if exp and now >= exp:
        return False, "expired"

    # 2. Suppression-key dedup
    sup_key = trigger.get("suppression_key", "")
    hours = 168 if (trigger.get("kind") == "research_digest") else config.SUPPRESSION_WINDOW_HOURS
    if conv_store.sent_recently(sup_key, hours=hours):
        return False, "suppressed"

    # 3. Per-merchant outbound rate (24h)
    if conv_store.outbound_count_24h(mid) >= config.MAX_OUTBOUND_PER_MERCHANT_24H:
        return False, "rate_capped_24h"

    # 4. Subscription gate
    sub_status = ((merchant.get("subscription") or {}).get("status") or "").lower()
    kind = trigger.get("kind", "")
    if sub_status == "expired" and kind not in WINBACK_KINDS:
        return False, "subscription_expired_non_winback"

    # 5. Auto-reply quarantine
    if conv_store.is_quarantined(mid):
        return False, "auto_reply_quarantined"

    # 6. Already an open conversation for this trigger -> handled via /reply
    if conv_store.open_conv_for_trigger(tid):
        return False, "open_conv_exists"

    # 7. Customer consent for customer-scope triggers
    if trigger.get("scope") == "customer":
        cid = trigger.get("customer_id")
        if not cid or not customer:
            return False, "customer_context_missing"
        consent = (customer.get("consent") or {})
        scopes = consent.get("scope") or []
        opted_in = consent.get("opted_in", True)
        if not opted_in:
            return False, "customer_opted_out"
        # Map trigger kind -> required consent scope.
        required = {
            "recall_due": "recall_reminders",
            "chronic_refill_due": "refill_reminders",
            "customer_lapsed_soft": "promotional",
            "wedding_package_followup": "bridal_package_followup",
            "post_visit_followup": "post_visit",
            "appointment_reminder": "appointment_reminders",
        }.get(kind)
        if required and required not in scopes and "all" not in scopes and "promotional" not in scopes:
            return False, f"missing_consent_scope:{required}"

    return True, "allow"


def prioritize(triggers_with_meta: list[dict]) -> list[dict]:
    """Sort by urgency desc, then expires_at asc (soonest first), then id for stability."""
    def key(t):
        urg = t.get("urgency", 0) or 0
        exp = _parse_iso(t.get("expires_at", "")) or datetime.max.replace(tzinfo=timezone.utc)
        return (-int(urg), exp, t.get("id", ""))
    return sorted(triggers_with_meta, key=key)
