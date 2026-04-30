"""Push contexts then call /v1/tick with ONE trigger to verify single-shot perf."""
import json, time, urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8080"
EXP = Path(__file__).resolve().parent.parent.parent / "expanded"

def post(p, b):
    req = urllib.request.Request(BASE + p, data=json.dumps(b).encode(),
                                  headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())

# Push minimum needed for trg_001.
post("/v1/context", {"scope":"category","context_id":"dentists","version":1,
                      "payload":json.loads((EXP/"categories/dentists.json").read_text(encoding="utf-8")),
                      "delivered_at":"2026-04-26T10:00:00Z"})
post("/v1/context", {"scope":"merchant","context_id":"m_001_drmeera_dentist_delhi","version":1,
                      "payload":json.loads((EXP/"merchants/m_001_drmeera_dentist_delhi.json").read_text(encoding="utf-8")),
                      "delivered_at":"2026-04-26T10:00:00Z"})
post("/v1/context", {"scope":"trigger","context_id":"trg_001_research_digest_dentists","version":1,
                      "payload":json.loads((EXP/"triggers/trg_001_research_digest_dentists.json").read_text(encoding="utf-8")),
                      "delivered_at":"2026-04-26T10:00:00Z"})

t = time.time()
r = post("/v1/tick", {"now":"2026-04-26T10:35:00Z",
                       "available_triggers":["trg_001_research_digest_dentists"]})
print(f"\n=== /v1/tick (1 trigger) -> {time.time()-t:.2f}s ===")
print(json.dumps(r, indent=2))
