"""ADR-017 / PLANNED-14: rubric states, partial credit and the bank shape check."""
import json
import os
import re
import tempfile
import unittest

import app as preparator
from question_bank import QUESTION_BANK


def crit(label, keywords, related=None, alternatives=None):
    item = {"label": label, "keywords": keywords}
    if related is not None:
        item["related"] = related
    if alternatives is not None:
        item["alternatives"] = alternatives
    return item


class EvaluateAnswerTests(unittest.TestCase):
    def test_without_extras_matches_the_old_rule(self):
        criteria = [crit("a", ["alpha"]), crit("b", ["beta"])]
        result = preparator.evaluate_answer("Alpha only", criteria)
        self.assertEqual(result["score"], 5)
        self.assertEqual(result["matched"], ["a"])
        self.assertEqual(result["missing"], ["b"])

    def test_each_state(self):
        criteria = [
            crit("kw", ["alpha"], related=["x1"]),
            crit("alt", ["nomatch"], alternatives=[{"label": "Other way", "keywords": ["gamma"]}]),
            crit("rel", ["nomatch2"], related=["delta"]),
            crit("none", ["nomatch3"], related=["nomatch4"]),
        ]
        concepts = preparator.evaluate_answer("alpha gamma delta", criteria)["concepts"]
        self.assertEqual(
            [c["state"] for c in concepts], ["covered", "covered", "partial", "not_detected"]
        )
        self.assertEqual([c["index"] for c in concepts], [0, 1, 2, 3])
        self.assertIsNone(concepts[0]["alternative"])
        self.assertEqual(concepts[1]["alternative"], "Other way")
        self.assertIsNone(concepts[2]["alternative"])
        self.assertEqual(concepts[3]["matched_terms"], [])
        self.assertEqual(concepts[0]["looked_for"], ["alpha"])

    def test_keyword_beats_alternative_beats_related(self):
        alt = [{"label": "Alt", "keywords": ["gamma"]}]
        item = crit("c", ["alpha"], related=["delta"], alternatives=alt)
        both = preparator.evaluate_answer("alpha gamma delta", [item])["concepts"][0]
        self.assertEqual(both["state"], "covered")
        self.assertIsNone(both["alternative"])
        self.assertEqual(both["matched_terms"], ["alpha", "gamma", "delta"])
        via_alt = preparator.evaluate_answer("gamma delta", [item])["concepts"][0]
        self.assertEqual(via_alt["alternative"], "Alt")
        self.assertEqual(via_alt["state"], "covered")

    def test_first_alternative_wins_and_terms_order_and_dedupe(self):
        item = crit(
            "c", ["nomatch"], related=["shared", "rel"],
            alternatives=[
                {"label": "First", "keywords": ["one", "shared"]},
                {"label": "Second", "keywords": ["two", "shared"]},
            ],
        )
        concept = preparator.evaluate_answer("two rel shared one", [item])["concepts"][0]
        self.assertEqual(concept["alternative"], "First")
        self.assertEqual(concept["matched_terms"], ["one", "shared", "two", "rel"])

    def test_second_alternative_covers_when_first_misses(self):
        item = crit("c", ["nomatch"], alternatives=[
            {"label": "First", "keywords": ["one"]},
            {"label": "Second", "keywords": ["two"]},
        ])
        concept = preparator.evaluate_answer("two", [item])["concepts"][0]
        self.assertEqual(concept["alternative"], "Second")

    def test_two_related_terms_do_not_cover(self):
        item = crit("c", ["nomatch"], related=["delta", "epsilon"])
        result = preparator.evaluate_answer("delta epsilon", [item])
        self.assertEqual(result["concepts"][0]["state"], "partial")
        self.assertEqual(result["matched"], [])
        self.assertEqual(result["missing"], ["c"])

    def test_partial_scoring_and_floor(self):
        three = [crit("a", ["alpha"]), crit("b", ["no"], related=["beta"]), crit("c", ["zz"])]
        self.assertEqual(preparator.evaluate_answer("alpha beta", three)["score"], 5)
        four = [
            crit("a", ["no1"]), crit("b", ["no2"], related=["beta"]),
            crit("c", ["no3"]), crit("d", ["no4"]),
        ]
        self.assertEqual(preparator.evaluate_answer("beta", four)["score"], 1)
        self.assertEqual(preparator.evaluate_answer("nothing", four)["score"], 1)
        self.assertEqual(preparator.PARTIAL_CREDIT, 0.5)

    def test_starter_lines_earn_nothing_for_related_or_alternatives(self):
        starter = "def f():\n    # delta gamma"
        item = crit(
            "c", ["no"], related=["delta"],
            alternatives=[{"label": "A", "keywords": ["gamma"]}],
        )
        answer = "def f():\n    # delta gamma\n    return 1"
        result = preparator.evaluate_answer(answer, [item], starter)
        self.assertEqual(result["concepts"][0]["state"], "not_detected")

    def test_related_term_with_spaces_and_anchor(self):
        item = crit("c", ["no"], related=[" in "])
        found = preparator.evaluate_answer("key in\n d", [item])["concepts"][0]["state"]
        self.assertEqual(found, "partial")
        absent = preparator.evaluate_answer("inside", [item])["concepts"][0]["state"]
        self.assertEqual(absent, "not_detected")


class AnswerEndpointTests(unittest.TestCase):
    def setUp(self):
        self.database = tempfile.NamedTemporaryFile(delete=False)
        self.database.close()
        preparator.app.config.update(TESTING=True, DATABASE=self.database.name)
        with preparator.app.app_context():
            preparator.init_db()
        self.client = preparator.app.test_client()

    def tearDown(self):
        os.unlink(self.database.name)

    def test_response_has_attempt_id_and_concepts(self):
        with preparator.app.app_context():
            row = preparator.get_db().execute(
                "SELECT id, criteria FROM questions WHERE mode = 'Theory' AND retired = 0 LIMIT 1"
            ).fetchone()
        response = self.client.post(
            "/api/answer", json={"question_id": row["id"], "answer": "some answer text"}
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        with preparator.app.app_context():
            stored = preparator.get_db().execute(
                "SELECT MAX(id) FROM attempts WHERE question_id = ?", (row["id"],)
            ).fetchone()[0]
        self.assertEqual(body["attempt_id"], stored)
        labels = [c["label"] for c in json.loads(row["criteria"])]
        self.assertEqual([c["label"] for c in body["concepts"]], labels)
        for concept in body["concepts"]:
            self.assertEqual(
                set(concept),
                {"index", "label", "state", "matched_terms", "looked_for", "alternative"},
            )
            self.assertIn(concept["state"], {"covered", "partial", "not_detected"})
        states = {c["label"]: c["state"] for c in body["concepts"]}
        self.assertEqual(body["matched"], [k for k, v in states.items() if v == "covered"])
        self.assertEqual(body["missing"], [k for k, v in states.items() if v != "covered"])


class BankShapeTests(unittest.TestCase):
    def _check_terms(self, terms, where):
        self.assertIsInstance(terms, list, where)
        self.assertTrue(terms, where)
        for term in terms:
            self.assertIsInstance(term, str, where)
            self.assertTrue(term.strip(), where)
            self.assertIsNone(re.search(r"\s{2,}|[^\S ]", term), f"{where}: {term!r}")

    def test_every_criterion_has_the_documented_shape(self):
        allowed = {"label", "keywords", "related", "alternatives"}
        for question in QUESTION_BANK:
            for number, item in enumerate(question["criteria"]):
                where = f"{question['prompt'][:40]!r} criterion {number}"
                self.assertLessEqual(set(item), allowed, where)
                self.assertTrue(isinstance(item.get("label"), str) and item["label"].strip(), where)
                self._check_terms(item.get("keywords"), where)
                if "related" in item:
                    self._check_terms(item["related"], where)
                if "alternatives" in item:
                    self.assertIsInstance(item["alternatives"], list, where)
                    self.assertTrue(item["alternatives"], where)
                    for alternative in item["alternatives"]:
                        self.assertEqual(set(alternative), {"label", "keywords"}, where)
                        label = alternative["label"]
                        self.assertTrue(isinstance(label, str) and label.strip(), where)
                        self._check_terms(alternative["keywords"], where)


if __name__ == "__main__":
    unittest.main()
