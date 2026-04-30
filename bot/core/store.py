"""In-memory ContextStore — versioned, idempotent on (scope, context_id)."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Optional


@dataclass
class StoredContext:
    scope: str
    context_id: str
    version: int
    payload: dict
    received_at: str


class ContextStore:
    def __init__(self) -> None:
        self._data: dict[tuple[str, str], StoredContext] = {}
        self._lock = RLock()

    def upsert(self, scope: str, context_id: str, version: int, payload: dict) -> tuple[bool, Optional[int], Optional[str]]:
        """Returns (accepted, current_version_if_rejected, ack_id_or_None)."""
        with self._lock:
            key = (scope, context_id)
            cur = self._data.get(key)
            if cur is not None and cur.version >= version:
                return (False, cur.version, None)
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            self._data[key] = StoredContext(
                scope=scope, context_id=context_id, version=version,
                payload=payload, received_at=now,
            )
            ack = f"ack_{context_id}_v{version}"
            return (True, version, ack)

    def get(self, scope: str, context_id: str) -> Optional[dict]:
        with self._lock:
            sc = self._data.get((scope, context_id))
            return sc.payload if sc else None

    def get_full(self, scope: str, context_id: str) -> Optional[StoredContext]:
        with self._lock:
            return self._data.get((scope, context_id))

    def counts(self) -> dict[str, int]:
        out = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
        with self._lock:
            for (scope, _), _ in self._data.items():
                out[scope] = out.get(scope, 0) + 1
        return out

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


store = ContextStore()
