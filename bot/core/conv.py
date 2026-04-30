"""Conversation FSM + per-merchant rate ledger + suppression ledger."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Optional


@dataclass
class Turn:
    from_role: str           # "vera" | "merchant_on_behalf" | "merchant" | "customer"
    body: str
    ts: str
    turn_number: int = 0


@dataclass
class Conversation:
    conv_id: str
    merchant_id: str
    customer_id: Optional[str]
    trigger_id: str
    send_as: str
    state: str = "SENT"           # SENT | ENGAGED | QUALIFYING | ACTION | AUTO_REPLY_PROBED | WAITING | ENDED
    turns: list[Turn] = field(default_factory=list)
    sent_bodies: set[str] = field(default_factory=set)
    auto_reply_count: int = 0
    received_bodies_seen: dict[str, int] = field(default_factory=dict)
    last_outbound_ts: Optional[str] = None
    ended_at: Optional[str] = None


class ConversationStore:
    def __init__(self) -> None:
        self._convs: dict[str, Conversation] = {}
        self._open_by_trigger: dict[str, str] = {}    # trigger_id -> conv_id
        self._sent_suppression: dict[str, datetime] = {}
        self._outbound_log: dict[str, list[datetime]] = {}   # merchant_id -> timestamps
        self._quarantined_until: dict[str, datetime] = {}    # merchant_id -> dt
        self._lock = RLock()

    # ---- conversation lifecycle ----
    def get(self, conv_id: str) -> Optional[Conversation]:
        with self._lock:
            return self._convs.get(conv_id)

    def create(self, conv_id: str, merchant_id: str, customer_id: Optional[str],
               trigger_id: str, send_as: str) -> Conversation:
        with self._lock:
            c = Conversation(conv_id=conv_id, merchant_id=merchant_id,
                             customer_id=customer_id, trigger_id=trigger_id, send_as=send_as)
            self._convs[conv_id] = c
            self._open_by_trigger[trigger_id] = conv_id
            return c

    def record_outbound(self, conv: Conversation, body: str, ts: str) -> None:
        with self._lock:
            conv.turns.append(Turn(from_role=conv.send_as, body=body, ts=ts,
                                    turn_number=len(conv.turns) + 1))
            conv.sent_bodies.add(body.strip())
            conv.last_outbound_ts = ts
            now = datetime.now(timezone.utc)
            self._outbound_log.setdefault(conv.merchant_id, []).append(now)

    def record_inbound(self, conv: Conversation, from_role: str, body: str,
                       ts: str, turn_number: int) -> None:
        with self._lock:
            conv.turns.append(Turn(from_role=from_role, body=body, ts=ts, turn_number=turn_number))
            norm = body.strip().lower()
            conv.received_bodies_seen[norm] = conv.received_bodies_seen.get(norm, 0) + 1

    def end(self, conv: Conversation, reason: str = "") -> None:
        with self._lock:
            conv.state = "ENDED"
            conv.ended_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            self._open_by_trigger.pop(conv.trigger_id, None)

    def open_conv_for_trigger(self, trigger_id: str) -> Optional[str]:
        with self._lock:
            cid = self._open_by_trigger.get(trigger_id)
            if cid is None:
                return None
            c = self._convs.get(cid)
            if c is None or c.state == "ENDED":
                self._open_by_trigger.pop(trigger_id, None)
                return None
            return cid

    # ---- suppression / rate / quarantine ----
    def sent_recently(self, suppression_key: str, hours: int = 48) -> bool:
        if not suppression_key:
            return False
        with self._lock:
            ts = self._sent_suppression.get(suppression_key)
            if ts is None:
                return False
            return (datetime.now(timezone.utc) - ts) < timedelta(hours=hours)

    def mark_sent(self, suppression_key: str) -> None:
        if not suppression_key:
            return
        with self._lock:
            self._sent_suppression[suppression_key] = datetime.now(timezone.utc)

    def outbound_count_24h(self, merchant_id: str) -> int:
        with self._lock:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            entries = [t for t in self._outbound_log.get(merchant_id, []) if t >= cutoff]
            self._outbound_log[merchant_id] = entries
            return len(entries)

    def quarantine(self, merchant_id: str, hours: int) -> None:
        with self._lock:
            self._quarantined_until[merchant_id] = datetime.now(timezone.utc) + timedelta(hours=hours)

    def is_quarantined(self, merchant_id: str) -> bool:
        with self._lock:
            until = self._quarantined_until.get(merchant_id)
            if until is None:
                return False
            if datetime.now(timezone.utc) >= until:
                self._quarantined_until.pop(merchant_id, None)
                return False
            return True

    def clear(self) -> None:
        with self._lock:
            self._convs.clear()
            self._open_by_trigger.clear()
            self._sent_suppression.clear()
            self._outbound_log.clear()
            self._quarantined_until.clear()


conv_store = ConversationStore()
