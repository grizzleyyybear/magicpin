"""Smoke test for the Reasoner: run it against 3 known-good triggers and print briefs."""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from bot.core import reasoner


ROOT = Path(__file__).resolve().parent.parent.parent
EXP = ROOT / "expanded"


def load(scope: str, ctx_id: str):
    p = EXP / scope / f"{ctx_id}.json"
    return json.loads(p.read_text(encoding="utf-8"))


def find_trigger(trigger_id: str):
    return load("triggers", trigger_id)


async def main():
    if not os.getenv("GEMINI_API_KEY"):
        print("ERROR: GEMINI_API_KEY env var not set.")
        sys.exit(1)

    cases = [
        ("trg_001_research_digest_dentists",   "dentists"),
        ("trg_004_perf_dip_bharat",            "dentists"),
        ("trg_010_ipl_match_delhi",            "restaurants"),
    ]
    for trg_id, cat_slug in cases:
        trg = find_trigger(trg_id)
        merchant_id = trg.get("merchant_id")
        merchant = load("merchants", merchant_id)
        category = load("categories", cat_slug)
        customer = None
        if trg.get("customer_id"):
            try:
                customer = load("customers", trg["customer_id"])
            except FileNotFoundError:
                customer = None
        print(f"\n=== {trg_id} ({trg.get('kind')}) → {merchant_id} ===")
        brief = await reasoner.reason(category, merchant, trg, customer)
        if brief is None:
            print("  REASONER RETURNED NONE")
            continue
        print(json.dumps(brief, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
