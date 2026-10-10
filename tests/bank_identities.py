"""Baseline of question identities (topic, difficulty, mode, prompt).

Editing or removing a prompt retires its row and orphans its history, so
`bank_identities.json` pins every identity. The test only requires the baseline to be a
subset of the current bank: additions never break it.

Regenerate deliberately (after an intentional edit or removal), from the repo root:
    .venv/Scripts/python.exe tests/bank_identities.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BASELINE_PATH = os.path.join(HERE, "bank_identities.json")


def current_identities():
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from question_bank import QUESTION_BANK

    return {(q["topic"], q["difficulty"], q["mode"], q["prompt"]) for q in QUESTION_BANK}


def load_baseline():
    with open(BASELINE_PATH, encoding="utf-8") as handle:
        return json.load(handle)


if __name__ == "__main__":
    with open(BASELINE_PATH, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(sorted(current_identities()), handle, indent=1, ensure_ascii=False)
        handle.write("\n")
    print(f"wrote {len(current_identities())} identities to {BASELINE_PATH}")
