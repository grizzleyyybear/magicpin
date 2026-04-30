"""Unit tests for bot.core.intent. No LLM."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bot.core.intent import classify


CASES = [
    # explicit yes
    ("Yes please send the abstract.",          "explicit_yes"),
    ("yes",                                    "explicit_yes"),
    ("haan karo",                              "explicit_yes"),
    ("ok proceed",                             "explicit_yes"),
    ("chalega",                                "explicit_yes"),
    # hard no
    ("Not interested. Stop messaging me.",     "hard_no"),
    ("don't message me",                       "hard_no"),
    ("band karo bhai",                         "hard_no"),
    ("unsubscribe",                            "hard_no"),
    # auto-reply (canned)
    ("Thank you for contacting Dr. Meera's Dental Clinic! Our team will respond shortly.", "auto_reply"),
    ("This is an automated response. We will get back to you soon.", "auto_reply"),
    ("Out of office until Monday.",            "auto_reply"),
    # later
    ("call me later",                          "later"),
    ("baad mein baat karte hain",              "later"),
    ("busy abhi, kal call karna",              "later"),
    # off-topic
    ("Btw can you also help me with my GST filing this month?", "off_topic"),
    ("what's the weather like in Delhi?",      "off_topic"),
    # engaged (open question / freeform)
    ("Sounds interesting, can you also tell me about other studies?", "engaged"),
    ("How would the patient draft look?",      "engaged"),
    ("Whats the trial size on that study?",    "engaged"),
]


def test_intent_cases():
    failures = []
    for msg, expected in CASES:
        got, why = classify(msg)
        if got != expected:
            failures.append(f"  {msg[:60]!r}\n    expected={expected} got={got} ({why})")
    assert not failures, "intent mismatches:\n" + "\n".join(failures)


def test_repeat_promotes_to_auto_reply():
    msg = "Hello, please leave a message."
    intent1, _ = classify(msg, repeat_count=0)
    intent2, _ = classify(msg, repeat_count=2)
    assert intent2 == "auto_reply", f"expected auto_reply on repeat, got {intent2}"


if __name__ == "__main__":
    failures = 0
    for fn in (test_intent_cases, test_repeat_promotes_to_auto_reply):
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"  FAIL  {fn.__name__}\n{e}")
    sys.exit(0 if failures == 0 else 1)
