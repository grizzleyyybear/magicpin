"""Push contexts then call /v1/tick. Validates the full P5 pipeline."""
import json
import sys
import time
from pathlib import Path

import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8080"
ROOT = Path(__file__).resolve().parent.parent.parent
EXP = ROOT / "expanded"


def post(path, body):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def push_ctx(scope, ctx_id, payload, version=1):
    return post("/v1/context", {
        "scope": scope, "context_id": ctx_id, "version": version,
        "payload": payload, "delivered_at": "2026-04-26T10:00:00Z",
    })


def main():
    # Push categories.
    for f in (EXP / "categories").glob("*.json"):
        s, _ = push_ctx("category", f.stem, json.loads(f.read_text(encoding="utf-8")))
        assert s == 200, f"category {f.stem}: {s}"

    # Push the 5 merchants we'll exercise.
    merchants = [
        "m_001_drmeera_dentist_delhi",
        "m_002_bharat_dentist_mumbai",
        "m_005_pizzajunction_restaurant_delhi",
        "m_009_apollo_pharmacy_jaipur",
        "m_003_studio11_salon_hyderabad",
    ]
    for mid in merchants:
        s, _ = push_ctx("merchant", mid, json.loads((EXP / "merchants" / f"{mid}.json").read_text(encoding="utf-8")))
        assert s == 200, f"merchant {mid}: {s}"

    # Push customers used by customer-scope triggers.
    triggers = [
        "trg_001_research_digest_dentists",
        "trg_004_perf_dip_bharat",
        "trg_010_ipl_match_delhi",
        "trg_018_supply_atorvastatin_recall",
        "trg_007_bridal_followup_kavya",
    ]
    for tid in triggers:
        tp = json.loads((EXP / "triggers" / f"{tid}.json").read_text(encoding="utf-8"))
        if tp.get("customer_id"):
            cf = EXP / "customers" / f"{tp['customer_id']}.json"
            if cf.exists():
                s, _ = push_ctx("customer", tp["customer_id"], json.loads(cf.read_text(encoding="utf-8")))
                assert s == 200, f"customer {tp['customer_id']}: {s}"
        s, _ = push_ctx("trigger", tid, tp)
        assert s == 200, f"trigger {tid}: {s}"

    print("=== contexts pushed ===")

    # Call /v1/tick.
    t = time.time()
    s, body = post("/v1/tick", {
        "now": "2026-04-26T10:35:00Z",
        "available_triggers": triggers,
    })
    dt = time.time() - t
    print(f"\n=== /v1/tick → HTTP {s} in {dt:.2f}s ===")
    print(f"actions returned: {len(body.get('actions', []))}\n")
    for i, a in enumerate(body.get("actions", []), 1):
        print(f"--- action {i}: trigger={a['trigger_id']} merchant={a['merchant_id']} ---")
        print(f"  conv_id     : {a['conversation_id']}")
        print(f"  send_as     : {a['send_as']}")
        print(f"  template    : {a['template_name']}")
        print(f"  cta         : {a['cta']} | suppression_key: {a['suppression_key']}")
        print(f"  body        : {a['body']}")
        print(f"  rationale   : {a['rationale']}\n")


if __name__ == "__main__":
    main()
