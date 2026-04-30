"""Unit tests for bot.core.guards. No LLM calls."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.core.guards import GuardContext, validate, _has_hindi, _hindi_token_count


def make_ctx(**over):
    base = dict(
        body="Dr. Meera, JIDA Oct 2026 p.14 ka 2,100-patient trial — 3-month fluoride recall caries 38% better. Aap bhi consider karenge?",
        cta="open_ended",
        suppression_key="research:dentists:2026-W17",
        rationale="lever=reciprocity; anchor=category.digest.d_2026W17_jida_fluoride.title",
        category={
            "voice": {"vocab_taboo": ["guaranteed", "100% safe"]},
            "offer_catalog": [{"title": "Dental Cleaning @ Rs 299"}],
            "digest": [{"title": "3-month fluoride varnish recall outperforms 6-month",
                        "source": "JIDA Oct 2026, p.14"}],
            "peer_stats": {"avg_ctr": 0.030},
        },
        merchant={
            "identity": {"name": "Dr. Meera", "languages": ["en", "hi"]},
            "offers": [{"title": "Dental Cleaning @ Rs 299"}],
            "performance": {"views": 2410, "calls": 18},
        },
        trigger={"suppression_key": "research:dentists:2026-W17", "scope": "merchant"},
        customer=None,
        previous_sent_bodies=[],
        decision_brief={"cta_shape": "open_ended"},
    )
    base.update(over)
    return GuardContext(**base)


def test_clean_message_passes():
    r = validate(make_ctx())
    assert r.ok, f"expected pass, got: {r.issues}"


def test_url_blocks():
    r = validate(make_ctx(body="Read more at https://magicpin.com/blog. Want this?"))
    assert not r.ok and any("URL" in i or "url" in i for i in r.issues)


def test_www_url_blocks():
    r = validate(make_ctx(body="Visit www.magicpin.com for details. Reply YES."))
    assert not r.ok


def test_taboo_word_blocks():
    r = validate(make_ctx(body="Dr. Meera, this is 100% safe — guaranteed results. Want me to draft?"))
    assert not r.ok and any("taboo" in i for i in r.issues)


def test_invalid_cta_blocks():
    r = validate(make_ctx(cta="binary_yes_no"))
    assert not r.ok and any("cta" in i.lower() for i in r.issues)


def test_yes_no_without_question_blocks():
    r = validate(make_ctx(cta="yes_no", body="Dr. Meera, JIDA Oct 2026 p.14 stat is 38% better."))
    assert not r.ok and any("cta" in i for i in r.issues)


def test_yes_no_with_question_passes():
    r = validate(make_ctx(cta="yes_no",
                          body="Dr. Meera, JIDA Oct 2026 p.14 — 38% better outcomes. Should I draft a patient note? haan?"))
    assert r.ok, r.issues


def test_hindi_required_when_hi_in_languages():
    r = validate(make_ctx(body="Dr. Meera, JIDA Oct 2026 p.14 — 2100-patient trial showed 38% improvement. Want abstract?"))
    assert not r.ok and any("hindi" in i.lower() for i in r.issues)


def test_hindi_not_required_when_only_en():
    ctx = make_ctx(body="Dr. Meera, JIDA Oct 2026 p.14 — 2100-patient trial showed 38% improvement. Want abstract?")
    ctx.merchant["identity"]["languages"] = ["en"]
    r = validate(ctx)
    assert r.ok, r.issues


def test_repeat_blocks():
    body = "Dr. Meera, JIDA Oct 2026 p.14 — 38% better. Aap chahenge to draft karu?"
    ctx = make_ctx(body=body, previous_sent_bodies=[body])
    r = validate(ctx)
    assert not r.ok and any("repeat" in i for i in r.issues)


def test_must_cite_fact_blocks_generic():
    r = validate(make_ctx(body="Dr. Meera, kuch interesting research aaya hai. Chahenge?"))
    assert not r.ok and any("cite" in i.lower() for i in r.issues)


def test_must_cite_fact_passes_with_offer_title():
    r = validate(make_ctx(body="Dr. Meera, aapka Dental Cleaning @ Rs 299 abhi push karu kya?"))
    assert r.ok, r.issues


def test_offer_provenance_blocks_invented_price():
    r = validate(make_ctx(body="Dr. Meera, naya offer Rs 999 wala launch karenge? Chalega?"))
    assert not r.ok and any("price" in i.lower() or "provenance" in i.lower() for i in r.issues)


def test_send_as_blocks_when_customer_not_addressed():
    cust = {"identity": {"name": "Priya"}}
    ctx = make_ctx(customer=cust)
    ctx.trigger["scope"] = "customer"
    r = validate(ctx)
    assert not r.ok and any("customer" in i.lower() for i in r.issues)


def test_send_as_passes_when_customer_addressed():
    cust = {"identity": {"name": "Priya"}}
    ctx = make_ctx(
        body="Hi Priya, Dr. Meera ki clinic se. 5 mahine ho gaye — Dental Cleaning @ Rs 299 ke liye Wed 6pm slot chahiye?",
        customer=cust,
    )
    ctx.trigger["scope"] = "customer"
    r = validate(ctx)
    assert r.ok, r.issues


def test_hindi_token_helpers():
    assert _has_hindi("aap kya kar rahe ho")
    assert not _has_hindi("hello dear merchant please reply now")
    assert _hindi_token_count("aap chahenge to karu, haan?") >= 2


if __name__ == "__main__":
    import inspect
    funcs = [(n, f) for n, f in inspect.getmembers(sys.modules[__name__], inspect.isfunction) if n.startswith("test_")]
    failures = 0
    for n, f in funcs:
        try:
            f()
            print(f"  PASS  {n}")
        except AssertionError as e:
            failures += 1
            print(f"  FAIL  {n}: {e}")
        except Exception as e:
            failures += 1
            print(f"  ERROR {n}: {type(e).__name__}: {e}")
    print(f"\n{len(funcs) - failures}/{len(funcs)} passed")
    sys.exit(0 if failures == 0 else 1)
