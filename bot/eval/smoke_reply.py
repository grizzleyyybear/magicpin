"""Test /v1/reply behaviors that don't need LLM (deterministic FSM paths)."""
import json
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8080"
EXP = Path(__file__).resolve().parent.parent.parent / "expanded"


def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                  headers={"Content-Type": "application/json"})
    try:
        return 200, json.loads(urllib.request.urlopen(req, timeout=60).read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def push(scope, ctx_id, payload, version=1):
    return post("/v1/context", {"scope": scope, "context_id": ctx_id, "version": version,
                                  "payload": payload, "delivered_at": "2026-04-26T10:00:00Z"})


def main():
    # 1. Push contexts.
    push("category", "dentists", json.loads((EXP / "categories" / "dentists.json").read_text(encoding="utf-8")))
    push("merchant", "m_001_drmeera_dentist_delhi",
         json.loads((EXP / "merchants" / "m_001_drmeera_dentist_delhi.json").read_text(encoding="utf-8")))
    push("trigger", "trg_001_research_digest_dentists",
         json.loads((EXP / "triggers" / "trg_001_research_digest_dentists.json").read_text(encoding="utf-8")))

    # 2. Fire tick to create the conversation.
    s, r = post("/v1/tick", {"now": "2026-04-26T10:35:00Z",
                              "available_triggers": ["trg_001_research_digest_dentists"]})
    print(f"tick: HTTP {s}, actions={len(r.get('actions', []))}")
    if not r.get("actions"):
        print("  no action created — can't test reply (probably suppressed/rate-limited)")
        # Still test orphan conv handling.
        s2, r2 = post("/v1/reply", {"conversation_id": "conv_does_not_exist",
                                      "from_role": "merchant", "message": "yes",
                                      "received_at": "2026-04-26T10:42:00Z", "turn_number": 1})
        print(f"\n--- orphan reply: HTTP {s2} ---\n{json.dumps(r2, indent=2)}")
        return
    conv_id = r["actions"][0]["conversation_id"]

    cases = [
        ("hard_no",      "Not interested. Stop messaging me."),
        ("auto_reply_1", "Thank you for contacting Dr. Meera's Dental Clinic! Our team will respond shortly."),
        ("auto_reply_2", "Thank you for contacting Dr. Meera's Dental Clinic! Our team will respond shortly."),
        ("later",        "Call me later please, busy abhi."),
        ("explicit_yes", "yes please send it"),
    ]
    print(f"\n[Testing /v1/reply on {conv_id}]")
    for label, msg in cases:
        s, r = post("/v1/reply", {"conversation_id": conv_id, "from_role": "merchant",
                                    "message": msg, "received_at": "2026-04-26T10:42:00Z",
                                    "turn_number": 2})
        print(f"\n--- case '{label}' (msg={msg!r}) -> HTTP {s} ---")
        print(json.dumps(r, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    import urllib.error
    main()
