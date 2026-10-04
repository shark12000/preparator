"""ADR-005: bank prompts are identity fields, so they must not depend on the hash seed."""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DIGEST_SCRIPT = """
import hashlib
from question_bank import QUESTION_BANK
identities = sorted(
    (q["topic"], q["difficulty"], q["mode"], q["prompt"]) for q in QUESTION_BANK
)
print(len(identities), len(set(identities)))
print(hashlib.sha256(repr(identities).encode("utf-8")).hexdigest())
"""

SEED_SCRIPT = """
import sqlite3
import app as preparator
with preparator.app.app_context():
    preparator.init_db()
connection = sqlite3.connect(preparator.app.config["DATABASE"])
total = connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
active = connection.execute("SELECT COUNT(*) FROM questions WHERE retired = 0").fetchone()[0]
print(total, active)
"""


def run_python(script, hash_seed, database=None):
    env = dict(os.environ, PYTHONHASHSEED=str(hash_seed))
    env.pop("PREPARATOR_DATABASE", None)
    if database:
        env["PREPARATOR_DATABASE"] = database
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return result.stdout.split("\n")[:-1]


class BankDeterminismTests(unittest.TestCase):
    def test_bank_identities_are_identical_across_hash_seeds(self):
        first = run_python(DIGEST_SCRIPT, 1)
        second = run_python(DIGEST_SCRIPT, 2)
        third = run_python(DIGEST_SCRIPT, 12345)
        self.assertEqual(first, second)
        self.assertEqual(first, third)
        self.assertEqual(first[0], "339 339")  # count, unique count

    def test_reseeding_under_another_hash_seed_adds_no_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "seed.sqlite3")
            first = run_python(SEED_SCRIPT, 1, database)
            second = run_python(SEED_SCRIPT, 2, database)
            third = run_python(SEED_SCRIPT, 3, database)
        self.assertEqual(first, second)
        self.assertEqual(first, third)
        self.assertEqual(first, ["339 339"])


if __name__ == "__main__":
    unittest.main()
