"""End-to-end smoke test: Reasoner → Writer for 5 representative triggers."""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from bot.core import reasoner, writer
from bot.core.composer import compose
from bot.core.guards import GuardContext, validate

ROOT = Path(__file__).resolve().parent.parent.parent
EXP = ROOT / "expanded"


def load(scope: str, ctx_id: str):
    return json.loads((EXP / scope / f"{ctx_id}.json").read_text(encoding="utf-8"))


async def main():
    if not (os.getenv("GROQ_API_KEY") or os.getenv("GEMINI_API_KEY")):
        print("ERROR: set GROQ_API_KEY (preferred) or GEMINI_API_KEY in env.")
        sys.exit(1)

    cases = [
        ("trg_001_research_digest_dentists",   "dentists"),
        ("trg_004_perf_dip_bharat",            "dentists"),
        ("trg_010_ipl_match_delhi",            "restaurants"),
        ("trg_018_supply_atorvastatin_recall", "pharmacies"),
        ("trg_007_bridal_followup_kavya",      "salons"),
    ]
    for trg_id, cat_slug in cases:
        try:
            trg = load("triggers", trg_id)
        except FileNotFoundError:
            print(f"SKIP: trigger {trg_id} not found")
            continue
        merchant = load("merchants", trg["merchant_id"])
        category = load("categories", cat_slug)
        customer = None
        if trg.get("customer_id"):
            try:
                customer = load("customers", trg["customer_id"])
            except FileNotFoundError:
                customer = None

        print(f"\n========= {trg_id} ({trg.get('kind')}) -> {trg['merchant_id']} =========")
        msg = await compose(category, merchant, trg, customer, previous_sent_bodies=[])
        if not msg:
            print("  COMPOSE DROPPED (failed guards twice or reasoner skipped)"); continue
        brief = msg.get("_brief", {})
        print(f"  signal: {brief.get('best_signal')}")
        print(f"  lever:  {brief.get('lever')} | cta: {brief.get('cta_shape')} | send_as: {brief.get('send_as')}")
        print(f"\n  BODY:\n  {msg.get('body')}")
        print(f"\n  cta={msg.get('cta')} | suppression_key={msg.get('suppression_key')}")
        print(f"  rationale: {msg.get('rationale')}")


if __name__ == "__main__":
    asyncio.run(main())
