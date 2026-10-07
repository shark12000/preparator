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


ALT_PAIRS = "Checks all pairs (brute force)"

# TASK-092: one entry per row of the TASK-069 "Likely-too-strict rubrics" table.
# labels: every criterion label that carries the row (archetype plus hand-written twin);
# cases: (answer body, expected state, expected alternative label or None);
# added: every term this task added to that criterion (none may match the prompt).
STRICT_RUBRIC_ROWS = {
    1: {
        "labels": ["Uses remainder or parity"],
        "cases": [
            ("return number%2 == 0", "covered", None),
            ("return (number & 1) == 0", "covered", None),
        ],
        "added": ["%2", "& 1", "&1", "remainder"],
    },
    2: {
        "labels": ["Uses the multiplicative definition"],
        "cases": [
            ("result = 1\nfor i in range(2, number + 1):\n    result *= i\nreturn result", "covered", None),
            ("return reduce(operator.mul, range(1, number + 1), 1)", "covered", None),
            ("return math.prod(range(1, number + 1))", "covered", None),
        ],
        "added": ["*=", "* i", "*i", "reduce(", "prod("],
        "negative": "I would return 1 for zero and loop over the other values.",
    },
    3: {
        "labels": ["Squares each selected value"],
        "cases": [
            ("return [x**2 for x in values if x % 2 == 0]", "covered", None),
            ("return [pow(x, 2) for x in values if x % 2 == 0]", "covered", None),
            ("return [x * x for x in values if x % 2 == 0]", "partial", None),
        ],
        "added": ["**2", "pow(", "* x", "*x", "n * n", "n*n"],
        "negative": "I used a powerful approach with a loop.",
    },
    4: {
        "labels": ["Scans original order", "Preserves input order"],
        "cases": [
            ("for c in text:\n    if counts[c] == 1:\n        return c", "covered", None),
            ("for ch in text:\n    if counts[ch] == 1:\n        return ch", "covered", None),
        ],
        "added": ["for c in", "for ch in"],
    },
    5: {
        "labels": ["Initializes one way to make zero"],
        "cases": [
            ("table = [0] * (amount + 1)\ntable[0]=1", "covered", None),
            ("Start from the base case for the table.", "partial", None),
        ],
        "added": ["[0]=1", "[0] = 1", "[1] + [0]", "base case", "zero ways"],
    },
    6: {
        "labels": ["Uses a one-dimensional ways table"],
        "cases": [
            ("table = [0] * (amount+1)", "covered", None),
            ("dp=[0]*(amount+1)", "covered", None),
            ("Keep an array with one slot per amount.", "partial", None),
        ],
        "added": ["[0] * (amount", "[0]*(amount", "dp=", "ways=", "table =", "table=", "array", "list of size"],
        "negatives": [("Store the results in an array of strings.", "partial")],
    },
    7: {
        "labels": ["Returns exactly k values"],
        "cases": [
            ("return [v for v, _ in Counter(values).most_common(k)]", "covered",
             "Takes the top k with a library helper or slice"),
            ("return list(itertools.islice(ordered, k))", "covered",
             "Takes the top k with a library helper or slice"),
            ("Return the top k of the sorted values.", "partial", None),
        ],
        "added": ["most_common(", "islice(", "[0:k]", "nlargest(", "top k", "first k"],
    },
    8: {
        "labels": ["Checks candidate word boundaries"],
        "cases": [
            ("if reachable[i] and text[i:j] in words:", "covered", None),
            ("if reachable[i] and text.startswith(word, i):", "covered", None),
        ],
        "added": ["startswith(", "text[i:j]", "text[j:i]", "text[:", "split point", "word in words"],
    },
    9: {
        "labels": ["Uses two advancing indices"],
        "cases": [
            ("i = j = 0\nwhile i < len(left):\n    i += 1", "covered", None),
            ("return list(heapq.merge(left, right))", "covered",
             "Uses a library merge or sorts the concatenation"),
            ("return sorted(left + right)", "covered",
             "Uses a library merge or sorts the concatenation"),
        ],
        "added": ["i += 1", "j += 1", "i = j = 0", "i=j=0", "heapq.merge", "sorted(left + right)",
                  "sorted(left+right)"],
    },
    10: {
        "labels": ["Uses a map for prior values"],
        "cases": [
            ("by_value = dict()", "covered", None),
            ("lookup = {}", "covered", None),
            ("for i in range(len(values)):\n    for j in range(i + 1, len(values)):", "covered", ALT_PAIRS),
        ],
        "added": ["dict ", "dict(", "dict[", "dict.", "dict,", "hashmap", "lookup", "for j in range(i", "range(i + 1", "range(i+1"],
        "negatives": [("I would dictate the order of the pairs.", "not_detected")],
    },
    11: {
        "labels": ["Looks up complements"],
        "cases": [
            ("if values[i] + values[j] == target:", "covered",
             "Checks pairs directly against the target"),
            ("Compute the difference needed for each value.", "partial", None),
        ],
        "added": ["== target", "+ values[j]", "+ values[i]", "difference", "needed"],
        "negatives": [("The difference is large.", "partial")],
    },
    12: {
        "labels": ["Reduces rotation modulo list length"],
        "cases": [
            ("amount = amount % n", "covered", None),
            ("amount = amount % length", "covered", None),
            ("items = deque(values)\nitems.rotate(amount)", "covered", "Rotates with collections.deque"),
        ],
        "added": ["% n", "%n", "% length", "%len", "remainder", "rotate(", "deque("],
    },
    13: {
        "labels": ["Maintains search bounds", "Uses a bounded search interval"],
        "cases": [
            ("lo, hi = 0, len(values) - 1", "covered", None),
            ("start = 0\nend = len(values) - 1", "covered", None),
            ("return bisect.bisect_left(values, target)", "covered", "Uses the bisect module"),
        ],
        "added": ["lo =", "hi =", "lo, hi", "lo=", "hi=", "start =", "end =", "bisect"],
        "negative": "I begin at one end and keep starting over, ending soon.",
    },
    14: {
        "labels": ["Tracks previous character positions"],
        "cases": [
            ("seen = set()\nseen.add(char)", "covered", "Tracks the current window with a set"),
            ("seen.discard(text[left])", "covered", "Tracks the current window with a set"),
        ],
        "added": ["set(", ".remove(", ".discard("],
    },
    15: {
        "labels": ["Moves the left boundary past duplicates"],
        "cases": [
            ("while char in seen:\n    seen.remove(text[left])\n    left += 1", "covered",
             "Shrinks the window with a set"),
            ("then left += 1 for each step", "partial", None),
        ],
        "added": [".remove(", ".discard(", "shrink", "while char in", "while c in", "while ch in", "left += 1"],
    },
    16: {
        "labels": ["Handles all-negative arrays"],
        "cases": [
            ("best = float('-inf')", "covered", None),
            ("Start from the first element so one item is enough.", "covered", None),
            ("current = best = values[:1][0]", "covered", None),
            ("It must still work when every value is negative.", "covered", None),
        ],
        "added": ["-inf", "values[:1]", "first element", "first value", "all-negative", "only negative",
                  "every value is negative", "all values are negative"],
        "negatives": [
            ("current = best = 0\nfor v in values:\n    current = max(0, current + v)  # reset when negative\n"
             "    best = max(best, current)\nreturn best", "not_detected"),
            ("restart from zero when the running sum goes negative", "not_detected"),
        ],
    },
    17: {
        "labels": ["Compares with a reverse or two-pointer scan", "Compares against the reverse"],
        "cases": [
            ("while left < right:\n    left += 1", "covered", None),
            ("while i < j:", "covered", None),
            ("Compare the characters from both ends.", "partial", None),
        ],
        "added": ["left < right", "i < j", "from both ends"],
    },
    18: {
        "labels": ["Compares expected and actual totals", "Computes expected versus observed values"],
        "cases": [
            ("result = 0\nfor v in range(1, n + 1):\n    result ^= v", "covered", "Cancels pairs with XOR"),
            ("answer = a ^ b", "covered", "Cancels pairs with XOR"),
            ("Use the gauss formula for the full range.", "partial", None),
        ],
        "added": ["xor", "^=", " ^ ", "n * (n + 1)", "n*(n+1)", "gauss"],
    },
    19: {
        "labels": ["Tracks the lowest earlier price"],
        "cases": [
            ("min_so_far = prices[0]", "covered", None),
            ("cheapest = prices[0]", "covered", None),
            ("low = prices[0]\nhigh = 0", "covered", None),
        ],
        "added": ["min(", "min_so_far", "cheapest", "smallest", "low ="],
        "negative": "Keep a lower bound for the loop and keep the answer small.",
    },
    20: {
        "labels": ["Visits each decimal digit"],
        "cases": [
            ("number, digit = divmod(number, 10)", "covered", "Peels digits with divmod or integer division"),
            ("number //= 10", "covered", "Peels digits with divmod or integer division"),
            ("total += number%10", "covered", None),
        ],
        "added": ["%10", "divmod(", "// 10", "//10", "//= 10", "//=10", "for digit in"],
    },
    21: {
        "labels": ["Defaults evaluated once"],
        "cases": [
            ("The default is evaluated at def time.", "covered", None),
            ("It is evaluated when the function is created.", "covered", None),
            ("Only one list ever exists for that default.", "partial", None),
        ],
        "added": ["def time", "function is created", "function created", "function creation",
                  "creation", "only one", "single"],
        "negatives": [
            ("A new list is created on each call.", "not_detected"),
            ("Defaults are evaluated on every call, so a new list is created each time.", "not_detected"),
        ],
    },
    22: {
        "labels": ["Does not enforce types by default"],
        "cases": [
            ("They don't enforce them, they're just hints.", "covered", None),
            ("Python doesn’t enforce annotations.", "covered", None),
            ("They are hints only.", "covered", None),
        ],
        "added": ["doesn't enforce", "don't enforce", "doesn’t enforce", "don’t enforce",
                  "doesnt enforce", "dont enforce", "just hints", "only hints", "hints only"],
        "negative": "Annotations make the code easier to read and help each argument stand out.",
    },
    23: {
        "labels": ["Both create an outer copy"],
        "cases": [
            ("Each produces a separate copy of the list itself.", "covered", None),
            ("Both build a new list for the container.", "covered", None),
        ],
        "added": ["new list", "new container", "separate copy", "copy of the list", "copy of the dict",
                  "copy of the container", "copy of the outer", "copy of the top", "new outer"],
        "negatives": [
            ("A shallow copy shares nested references. A deep copy makes a copy of the nested objects.",
             "not_detected"),
        ],
    },
    24: {
        "labels": ["Cyclic collector supplements reference counting"],
        "cases": [
            ("A generational garbage collection pass finds the rest.", "covered", None),
            ("The GC runs periodically; gc.collect() forces it.", "covered", None),
            ("A collector handles those objects.", "partial", None),
        ],
        "added": ["garbage collection", "gc.collect", "the gc ", "the gc.", "the gc,", "generational",
                  "collector"],
        "negative": "Compute the gcd of the two counts.",
    },
    25: {
        "labels": ["Prefers scoped patches or dependency injection"],
        "cases": [
            ("Use pytest's monkeypatch fixture so each patch is undone.", "covered", None),
            ("Apply it inside a context manager.", "covered", None),
            ("Put a wrapper around it or use a subclass.", "partial", None),
        ],
        "added": ["monkeypatch.setattr", "pytest monkeypatch", "monkeypatch fixture", "pytest fixture",
                  "context manager", "wrapper", "subclass"],
        "negatives": [("It is like a test fixture gone global.", "not_detected")],
        "negative": "Monkeypatching changes classes at runtime.",
    },
}


def questions_with_label(labels):
    found = []
    for question in QUESTION_BANK:
        for index, item in enumerate(question["criteria"]):
            if item["label"] in labels:
                found.append((question, index))
    return found


class StrictRubricFixTests(unittest.TestCase):
    """TASK-092: correct answers in other wordings or approaches are no longer missed."""

    def _state(self, question, index, answer):
        starter = question.get("starter_code", "")
        return preparator.evaluate_answer(answer, question["criteria"], starter)["concepts"][index]

    def test_every_row_finds_its_questions(self):
        self.assertEqual(sorted(STRICT_RUBRIC_ROWS), list(range(1, 26)))
        for number, row in STRICT_RUBRIC_ROWS.items():
            self.assertTrue(questions_with_label(row["labels"]), f"row {number}")

    def test_alternate_wordings_and_approaches_are_credited(self):
        for number, row in STRICT_RUBRIC_ROWS.items():
            for question, index in questions_with_label(row["labels"]):
                for answer, state, alternative in row["cases"]:
                    with self.subTest(row=number, answer=answer, prompt=question["prompt"][:40]):
                        concept = self._state(question, index, answer)
                        self.assertEqual(concept["state"], state, concept)
                        self.assertEqual(concept["alternative"], alternative, concept)

    def test_common_words_do_not_trigger_the_short_terms(self):
        for number, row in STRICT_RUBRIC_ROWS.items():
            negatives = list(row.get("negatives", []))
            if "negative" in row:
                negatives.append((row["negative"], "not_detected"))
            for question, index in questions_with_label(row["labels"]):
                for sentence, state in negatives:
                    with self.subTest(row=number, answer=sentence, prompt=question["prompt"][:40]):
                        concept = self._state(question, index, sentence)
                        self.assertEqual(concept["state"], state, concept)

    def test_the_prompt_as_an_answer_matches_none_of_the_added_terms(self):
        for number, row in STRICT_RUBRIC_ROWS.items():
            for question, index in questions_with_label(row["labels"]):
                with self.subTest(row=number, prompt=question["prompt"][:40]):
                    concept = self._state(question, index, question["prompt"])
                    self.assertEqual(
                        [term for term in concept["matched_terms"] if term in row["added"]], []
                    )

    def test_added_terms_exist_in_the_bank(self):
        for number, row in STRICT_RUBRIC_ROWS.items():
            for question, index in questions_with_label(row["labels"]):
                item = question["criteria"][index]
                terms = set(item["keywords"]) | set(item.get("related", []))
                for alternative in item.get("alternatives", []):
                    terms |= set(alternative["keywords"])
                with self.subTest(row=number, prompt=question["prompt"][:40]):
                    self.assertLessEqual(set(row["added"]), terms)

    def test_bare_except_does_not_cover_the_eafp_alternative(self):
        question = next(
            q for q in QUESTION_BANK
            if q["prompt"].startswith("What happens when a dictionary key is missing")
        )
        concept = self._state(question, 1, "It works except when the key is missing.")
        self.assertEqual(concept["state"], "not_detected")
        self.assertIsNone(concept["alternative"])
        self.assertEqual(concept["matched_terms"], [])


if __name__ == "__main__":
    unittest.main()
