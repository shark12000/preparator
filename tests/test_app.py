import contextlib
import csv
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import date, datetime, time, timedelta, timezone
from unittest import mock
import app as preparator

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bank_identities  # noqa: E402


class PreparatorTests(unittest.TestCase):
    def setUp(self):
        self.database = tempfile.NamedTemporaryFile(delete=False)
        self.database.close()
        preparator.app.config.update(TESTING=True, DATABASE=self.database.name)
        with preparator.app.app_context():
            preparator.init_db()
        self.client = preparator.app.test_client()

    def tearDown(self):
        os.unlink(self.database.name)

    def test_answer_evaluation_reports_missing_concepts(self):
        criteria = [
            {"label": "mutability", "keywords": ["mutable", "immutable"]},
            {"label": "hashing", "keywords": ["hashable", "hash"]},
        ]
        result = preparator.evaluate_answer("A list is mutable.", criteria)
        self.assertEqual(result["score"], 5)
        self.assertEqual(result["matched"], ["mutability"])
        self.assertEqual(result["missing"], ["hashing"])

    def test_keywords_match_at_word_starts_only(self):
        criteria = [{"label": "counting", "keywords": ["count"]}]
        self.assertEqual(preparator.evaluate_answer("Check the account.", criteria)["matched"], [])
        self.assertEqual(preparator.evaluate_answer("Use counts.", criteria)["matched"], ["counting"])

    def test_untouched_starter_lines_earn_no_credit(self):
        starter = "def is_even(number: int) -> bool:\n    pass"
        criteria = [{"label": "boolean", "keywords": ["bool"]}]
        self.assertEqual(preparator.evaluate_answer(starter + "\n    # todo", criteria, starter)["score"], 1)

    def test_submitting_unchanged_starter_is_rejected(self):
        with preparator.app.app_context():
            row = preparator.get_db().execute(
                "SELECT id, starter_code FROM questions WHERE starter_code != '' LIMIT 1"
            ).fetchone()
        response = self.client.post(
            "/api/answer", json={"question_id": row["id"], "answer": row["starter_code"]}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get("/api/dashboard").get_json()["attempts"], 0)

    def test_seeding_refreshes_edited_question_content(self):
        with preparator.app.app_context():
            database = preparator.get_db()
            database.execute("UPDATE questions SET explanation = 'stale'")
            database.commit()
            preparator.init_db()
            stale = database.execute(
                "SELECT COUNT(*) FROM questions WHERE explanation = 'stale'"
            ).fetchone()[0]
        self.assertEqual(stale, 0)

    def test_practice_streak_counts_consecutive_days(self):
        from datetime import date
        today = date(2026, 10, 3)
        self.assertEqual(preparator.practice_streak(["2026-10-03", "2026-10-02", "2026-09-30"], today), 2)
        self.assertEqual(preparator.practice_streak(["2026-10-02", "2026-10-01"], today), 2)
        self.assertEqual(preparator.practice_streak(["2026-09-29"], today), 0)

    def _insert_attempts_on_days_ago(self, offsets, at=None):
        with preparator.app.app_context():
            database = preparator.get_db()
            qid = database.execute("SELECT id FROM questions WHERE retired = 0 LIMIT 1").fetchone()[0]
            for offset in offsets:
                local_noon = datetime.combine(date.today() - timedelta(days=offset), at or time(12)).astimezone()
                database.execute(
                    "INSERT INTO attempts (question_id, answer, score, created_at) VALUES (?, 'x', 5, ?)",
                    (qid, local_noon.astimezone(timezone.utc).isoformat(timespec="seconds")),
                )
            database.commit()

    def test_dashboard_streak_is_not_capped_at_thirty_days(self):
        self._insert_attempts_on_days_ago(range(45))
        dashboard = self.client.get("/api/dashboard").get_json()
        self.assertEqual(dashboard["streak"], 45)
        self.assertEqual(len(dashboard["trend"]), 30)

    @unittest.skipUnless(
        timedelta(0) < datetime.now().astimezone().utcoffset() <= timedelta(hours=12),
        "needs a local zone 0 to 12h ahead of UTC: only there does 00:30 local fall on the previous UTC day "
        "and yesterday noon fall on yesterday in UTC (UTC+13/+14 would put yesterday noon on the day before)",
    )
    def test_dashboard_streak_uses_local_day_for_attempts_just_after_midnight(self):
        # Today 00:30 local is yesterday in UTC, so without 'localtime' it merges with yesterday noon
        # (also yesterday in UTC) and the streak drops to 1. On UTC or behind-UTC machines the test cannot
        # tell the difference, so it is skipped there instead of giving false assurance. At UTC+13/+14 yesterday
        # noon is itself on the day before in UTC, so the two rows no longer collide and the test is skipped too.
        self._insert_attempts_on_days_ago([0], at=time(0, 30))
        self._insert_attempts_on_days_ago([1])
        self.assertEqual(self.client.get("/api/dashboard").get_json()["streak"], 2)

    def test_dashboard_streak_anchors_on_yesterday_and_breaks_on_gap(self):
        self._insert_attempts_on_days_ago([1, 2, 3, 5])
        self.assertEqual(self.client.get("/api/dashboard").get_json()["streak"], 3)

    def test_dashboard_reports_trend_matrix_and_streak(self):
        with preparator.app.app_context():
            question_id = preparator.get_db().execute("SELECT id FROM questions LIMIT 1").fetchone()[0]
        self.client.post("/api/answer", json={"question_id": question_id, "answer": "mutable"})
        dashboard = self.client.get("/api/dashboard").get_json()
        self.assertEqual(len(dashboard["trend"]), 1)
        self.assertEqual(dashboard["trend"][0]["attempts"], 1)
        self.assertEqual(dashboard["streak"], 1)
        levels = {row["difficulty"] for row in dashboard["matrix"]}
        self.assertEqual(levels, {"Foundations", "Intermediate", "Advanced"})

    def test_specific_question_can_be_requested(self):
        with preparator.app.app_context():
            question_id = preparator.get_db().execute(
                "SELECT id FROM questions WHERE mode = 'Coding' LIMIT 1"
            ).fetchone()[0]
        response = self.client.post(
            "/api/question",
            json={
                "question_id": question_id,
                "mode": "Theory",
                "source_confirmed": True,
                "source_url": "https://www.google.com/search?q=python",
                "search_query": "Python interview questions",
            },
        )
        self.assertEqual(response.get_json()["question"]["id"], question_id)

    def test_question_is_served_without_any_search_fields(self):
        response = self.client.post("/api/question", json={"topic": "Python Core"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["question"]["topic"], "Python Core")
        self.assertEqual(self.client.post("/api/question", json={}).status_code, 200)

    def test_question_bank_covers_every_level_and_filters_correctly(self):
        levels = {question["difficulty"] for question in preparator.QUESTION_BANK}
        self.assertEqual(levels, {"Foundations", "Intermediate", "Advanced"})
        for level in levels:
            response = self.client.post(
                "/api/question",
                json={
                    "difficulty": level,
                    "source_confirmed": True,
                    "source_url": "https://www.google.com/search?q=Python+interview+questions",
                    "search_query": "Python interview questions",
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["question"]["difficulty"], level)

    def test_bank_has_over_300_unique_prompts_across_all_levels(self):
        prompts = [question["prompt"] for question in preparator.QUESTION_BANK]
        self.assertGreaterEqual(len(prompts), 300)
        self.assertEqual(len(prompts), len(set(prompts)))
        counts = {
            level: sum(question["difficulty"] == level for question in preparator.QUESTION_BANK)
            for level in ("Foundations", "Intermediate", "Advanced")
        }
        self.assertTrue(all(count >= 100 for count in counts.values()), counts)

    def test_coding_question_includes_a_python_starter(self):
        # Deterministic: check every Foundations Coding question the endpoint could serve.
        with preparator.app.app_context():
            rows = preparator.get_db().execute(
                "SELECT * FROM questions WHERE difficulty = 'Foundations' AND mode = 'Coding' AND retired = 0"
            ).fetchall()
            served = [preparator.question_dict(row) for row in rows]
        self.assertGreater(len(served), 0)
        for question in served:
            with self.subTest(prompt=question["prompt"]):
                self.assertTrue(question["starter_code"].startswith("def "))
        response = self.client.post(
            "/api/question",
            json={
                "difficulty": "Foundations",
                "mode": "Coding",
                "source_confirmed": True,
                "source_url": "https://www.google.com/search?q=Python+coding+questions",
                "search_query": "Python coding questions",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["question"]["mode"], "Coding")
        self.assertTrue(response.get_json()["question"]["starter_code"].startswith("def "))

    def _placeholder_question(self, criteria=None):
        """A Coding row with no stored starter (relies on the placeholder).

        Optionally replaces its criteria. Targets the exact row it blanked.
        """
        with preparator.app.app_context():
            database = preparator.get_db()
            question_id = database.execute(
                "SELECT id FROM questions WHERE mode = 'Coding' AND retired = 0 LIMIT 1"
            ).fetchone()["id"]
            database.execute("UPDATE questions SET starter_code = '' WHERE id = ?", (question_id,))
            if criteria is not None:
                database.execute(
                    "UPDATE questions SET criteria = ? WHERE id = ?",
                    (json.dumps(criteria), question_id),
                )
            database.commit()
            return database.execute(
                "SELECT id, criteria FROM questions WHERE id = ?", (question_id,)
            ).fetchone()

    def test_unchanged_placeholder_is_rejected_and_records_nothing(self):
        row = self._placeholder_question()
        for answer in (
            "# Write your Python solution below.",
            "# Write your Python solution below.\n",
            "  \n# Write your Python solution below.\n\n  ",
        ):
            with self.subTest(answer=answer):
                response = self.client.post(
                    "/api/answer", json={"question_id": row["id"], "answer": answer}
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.get_json()["error"],
                    "Replace the starter stub with your solution before submitting.",
                )
        with preparator.app.app_context():
            database = preparator.get_db()
            self.assertEqual(database.execute("SELECT COUNT(*) FROM attempts").fetchone()[0], 0)
            self.assertEqual(database.execute("SELECT COUNT(*) FROM weaknesses").fetchone()[0], 0)

    def test_placeholder_line_earns_no_credit_alongside_real_code(self):
        criteria = [{"label": "placeholder words", "keywords": ["write", "python", "solution"]}]
        row = self._placeholder_question(criteria)
        placeholder = "# Write your Python solution below."
        self.assertEqual(
            preparator.evaluate_answer(placeholder + "\nx = 1", criteria)["matched"],
            ["placeholder words"],
        )
        response = self.client.post(
            "/api/answer",
            json={"question_id": row["id"], "answer": placeholder + "\nx = 1"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["matched"], [])
        self.assertEqual(body["missing"], ["placeholder words"])
        self.assertEqual(body["score"], 1)

    def test_question_endpoint_still_returns_placeholder_starter(self):
        row = self._placeholder_question()
        response = self.client.post(
            "/api/question",
            json={
                "question_id": row["id"],
                "source_confirmed": True,
                "source_url": "https://www.google.com/search?q=Python+coding+questions",
                "search_query": "Python coding questions",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["question"]["starter_code"], "# Write your Python solution below.\n"
        )

    def test_every_coding_item_has_starter_code(self):
        coding = [question for question in preparator.QUESTION_BANK if question["mode"] == "Coding"]
        self.assertGreater(len(coding), 0)
        for question in coding:
            with self.subTest(prompt=question["prompt"]):
                self.assertTrue(question.get("starter_code", "").strip())
                self.assertNotEqual(question["starter_code"].strip(), question["solution"].strip())

    def test_coding_starters_are_bare_stubs_matching_the_solution(self):
        import ast

        def signature_names(source, check_bare):
            """Top-level def/class names plus class method names, in order. Optionally assert stub shape."""
            tree = ast.parse(source)
            names = []
            for node in tree.body:
                if check_bare:
                    self.assertIsInstance(node, (ast.FunctionDef, ast.ClassDef))
                elif not isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    continue  # solutions may import or define constants; only starters must be bare
                names.append(node.name)
                if isinstance(node, ast.FunctionDef):
                    if check_bare:
                        self.assertEqual(len(node.body), 1)
                        self.assertIsInstance(node.body[0], ast.Pass)
                    continue
                for member in node.body:
                    if check_bare:
                        self.assertIsInstance(member, ast.FunctionDef)
                    elif not isinstance(member, ast.FunctionDef):
                        continue
                    names.append(f"{node.name}.{member.name}")
                    if check_bare:
                        self.assertEqual(len(member.body), 1)
                        self.assertIsInstance(member.body[0], ast.Pass)
            return names

        for question in preparator.QUESTION_BANK:
            if question["mode"] != "Coding":
                continue
            with self.subTest(prompt=question["prompt"]):
                self.assertEqual(
                    signature_names(question["starter_code"], True),
                    signature_names(question["solution"], False),
                )

    def test_theory_model_answers_meet_their_own_rubric(self):
        theory = [question for question in preparator.QUESTION_BANK if question["mode"] == "Theory"]
        self.assertGreater(len(theory), 0)
        for question in theory:
            with self.subTest(prompt=question["prompt"]):
                result = preparator.evaluate_answer(question["solution"], question["criteria"])
                self.assertGreaterEqual(result["score"], 7, result["missing"])

    def test_bank_identities_baseline_is_still_present(self):
        # ADR-005: editing or removing a bank identity retires its row and orphans its history.
        # Additions are fine; a deliberate removal means regenerating the baseline in the same commit.
        baseline = {tuple(item) for item in bank_identities.load_baseline()}
        self.assertGreater(len(baseline), 0)
        missing = sorted(baseline - bank_identities.current_identities())
        if missing:
            self.fail(
                f"{len(missing)} baseline identities are missing from QUESTION_BANK (edited or removed prompts "
                "retire their rows per ADR-005 and orphan history): "
                + "; ".join(repr(item) for item in missing[:10])
                + ". If this is deliberate, regenerate the baseline with "
                "`.venv/Scripts/python.exe tests/bank_identities.py` and commit it with the change."
            )

    def test_coding_model_answers_meet_their_own_rubric(self):
        coding = [question for question in preparator.QUESTION_BANK if question["mode"] == "Coding"]
        self.assertGreater(len(coding), 0)
        for question in coding:
            with self.subTest(prompt=question["prompt"]):
                result = preparator.evaluate_answer(
                    question["solution"], question["criteria"], question["starter_code"]
                )
                self.assertGreaterEqual(result["score"], 7, result["missing"])

    def test_dashboard_reports_canonical_bank_count(self):
        response = self.client.get("/api/dashboard")
        self.assertEqual(response.get_json()["question_count"], len(preparator.QUESTION_BANK))

    def test_question_response_has_only_the_question_key(self):
        response = self.client.post("/api/question", json={"topic": "Python Core"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.get_json()), {"question"})

    def test_legacy_search_fields_are_ignored(self):
        legacy = (
            {"source_confirmed": False},
            {"source_url": "https://example.com/search?q=python"},
            {"source_url": 5},
            {"source_url": ["https://google.com"]},
            {"search_query": None},
            {"search_query": ""},
            {"source_confirmed": True, "source_url": "https://www.google.com/search?q=x", "search_query": "x"},
        )
        for payload in legacy:
            with self.subTest(payload=payload):
                response = self.client.post("/api/question", json=payload)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(set(response.get_json()), {"question"})

    def test_removed_confirmation_check_no_longer_runs_before_validation(self):
        response = self.client.post(
            "/api/question", json={"source_confirmed": False, "question_id": "1"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "question_id must be an integer."})

    def test_low_score_adds_question_to_weakness_queue(self):
        with preparator.app.app_context():
            question_id = preparator.get_db().execute("SELECT id FROM questions LIMIT 1").fetchone()[0]
        response = self.client.post("/api/answer", json={"question_id": question_id, "answer": "Not sure."})
        self.assertEqual(response.status_code, 200)
        dashboard = self.client.get("/api/dashboard").get_json()
        self.assertEqual(dashboard["weak_count"], 1)
        self.assertEqual(dashboard["attempts"], 1)

    def _answer_with_score(self, question_id, score):
        fake = {"score": score, "matched": [], "missing": []}
        with mock.patch.object(preparator, "evaluate_answer", return_value=fake):
            response = self.client.post(
                "/api/answer", json={"question_id": question_id, "answer": "anything"}
            )
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def _first_question_id(self):
        with preparator.app.app_context():
            return preparator.get_db().execute(
                "SELECT id FROM questions WHERE retired = 0 LIMIT 1"
            ).fetchone()[0]

    def test_weak_queue_added_then_still_weak_then_removed(self):
        qid = self._first_question_id()
        body = self._answer_with_score(qid, 3)
        self.assertEqual(body["weak_queue"], {"status": "added", "threshold": 7})
        body = self._answer_with_score(qid, 4)
        self.assertEqual(body["weak_queue"], {"status": "still_weak", "threshold": 7})
        body = self._answer_with_score(qid, 9)
        self.assertEqual(body["weak_queue"], {"status": "removed", "threshold": 7})
        self.assertEqual(self.client.get("/api/dashboard").get_json()["weak_count"], 0)

    def test_weak_queue_not_queued_on_pass_without_row(self):
        body = self._answer_with_score(self._first_question_id(), 10)
        self.assertEqual(body["weak_queue"], {"status": "not_queued", "threshold": 7})
        self.assertEqual(body["score"], 10)

    def test_pinned_question_keeps_row_and_updates_last_score_on_pass(self):
        qid = self._first_question_id()
        self.assertEqual(self.client.post(f"/api/weakness/{qid}", json={}).status_code, 200)
        body = self._answer_with_score(qid, 3)
        self.assertEqual(body["weak_queue"], {"status": "still_weak", "threshold": 7})
        body = self._answer_with_score(qid, 10)
        self.assertEqual(body["weak_queue"], {"status": "kept_pinned", "threshold": 7})
        weak = self.client.get("/api/dashboard").get_json()["weak_questions"]
        self.assertEqual(len(weak), 1)
        self.assertEqual(weak[0]["last_score"], 10)
        self.assertEqual(weak[0]["pinned"], 1)
        self.assertEqual(weak[0]["miss_count"], 1)

    def test_pinned_pass_updates_updated_at(self):
        qid = self._first_question_id()
        self.client.post(f"/api/weakness/{qid}", json={})
        with preparator.app.app_context():
            database = preparator.get_db()
            database.execute(
                "UPDATE weaknesses SET updated_at = '2000-01-01T00:00:00+00:00' WHERE question_id = ?",
                (qid,),
            )
            database.commit()
        self._answer_with_score(qid, 10)
        with preparator.app.app_context():
            updated = preparator.get_db().execute(
                "SELECT updated_at FROM weaknesses WHERE question_id = ?", (qid,)
            ).fetchone()[0]
        self.assertGreater(updated, "2000-01-01T00:00:00+00:00")

    def test_theory_lesson_and_note_are_saved_and_exported(self):
        lessons = self.client.get("/api/theory").get_json()["lessons"]
        expected_lessons = sum(question["mode"] == "Theory" for question in preparator.QUESTION_BANK)
        self.assertEqual(len(lessons), expected_lessons)
        lesson = lessons[0]
        self.assertEqual(lesson["note"], "")
        saved = self.client.post(
            f"/api/theory/{lesson['id']}", json={"note": "Review this before the interview."}
        )
        self.assertEqual(saved.status_code, 200)
        library = self.client.get("/api/theory").get_json()
        saved_lesson = next(item for item in library["lessons"] if item["id"] == lesson["id"])
        self.assertTrue(saved_lesson["saved"])
        self.assertEqual(saved_lesson["note"], "Review this before the interview.")
        self.client.post(
            f"/api/theory/{lesson['id']}", json={"note": "Updated note for review."}
        )
        export = self.client.get("/api/theory/export.csv")
        self.assertEqual(export.status_code, 200)
        self.assertIn(b"My notes", export.data)
        self.assertIn(b"Updated note for review.", export.data)

    def test_database_seeding_is_idempotent(self):
        with preparator.app.app_context():
            database = preparator.get_db()
            before = database.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
            preparator.init_db()
            after = database.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        self.assertEqual(after, before)

    def test_theory_export_neutralizes_spreadsheet_formulas(self):
        with preparator.app.app_context():
            question_id = preparator.get_db().execute(
                "SELECT id FROM questions WHERE mode = 'Theory' LIMIT 1"
            ).fetchone()[0]
        self.client.post(
            f"/api/theory/{question_id}",
            json={"note": '=HYPERLINK("https://example.com", "open")'},
        )
        export = self.client.get("/api/theory/export.csv")
        self.assertIn(b"'=HYPERLINK", export.data)

    def test_theory_save_rejects_non_theory_questions(self):
        with preparator.app.app_context():
            question_id = preparator.get_db().execute(
                "SELECT id FROM questions WHERE mode = 'Coding' LIMIT 1"
            ).fetchone()[0]
        response = self.client.post(f"/api/theory/{question_id}", json={"note": "not a theory lesson"})
        self.assertEqual(response.status_code, 404)

    def _theory_id(self):
        with preparator.app.app_context():
            return preparator.get_db().execute(
                "SELECT id FROM questions WHERE mode = 'Theory' LIMIT 1"
            ).fetchone()[0]

    def _note(self, question_id):
        lessons = self.client.get("/api/theory").get_json()["lessons"]
        return next(item for item in lessons if item["id"] == question_id)["note"]

    def test_text_plain_post_is_rejected_and_note_kept(self):
        qid = self._theory_id()
        self.client.post(f"/api/theory/{qid}", json={"note": "keep me"})
        response = self.client.post(f"/api/theory/{qid}", data="", content_type="text/plain")
        self.assertEqual(response.status_code, 415)
        self.assertEqual(self._note(qid), "keep me")

    def test_form_encoded_weakness_pin_is_rejected(self):
        qid = self._theory_id()
        response = self.client.post(f"/api/weakness/{qid}", data={"a": "b"})
        self.assertEqual(response.status_code, 415)
        with preparator.app.app_context():
            count = preparator.get_db().execute("SELECT COUNT(*) FROM weaknesses").fetchone()[0]
        self.assertEqual(count, 0)

    def test_foreign_host_is_rejected_everywhere(self):
        headers = {"Host": "attacker.example:5000"}
        self.assertEqual(self.client.get("/", headers=headers).status_code, 400)
        response = self.client.get("/api/dashboard", headers=headers)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "Unrecognized host."})
        self.assertEqual(
            self.client.post("/api/answer", json={"question_id": 1, "answer": "x"}, headers=headers).status_code,
            400,
        )

    def test_localhost_hosts_are_served(self):
        for host in ("127.0.0.1:5000", "localhost:5000"):
            self.assertEqual(self.client.get("/api/dashboard", headers={"Host": host}).status_code, 200)
            self.assertEqual(self.client.get("/", headers={"Host": host}).status_code, 200)

    def test_origin_check_on_answer(self):
        qid = self._theory_id()
        body = {"question_id": qid, "answer": "Not sure."}
        evil = self.client.post("/api/answer", json=body, headers={"Origin": "http://evil.example"})
        self.assertEqual(evil.status_code, 403)
        self.assertEqual(evil.get_json(), {"error": "Cross-origin requests are not allowed."})
        self.assertEqual(self.client.post("/api/answer", json=body, headers={"Origin": "null"}).status_code, 403)
        self.assertEqual(
            self.client.post("/api/answer", json=body, headers={"Origin": "http://localhost"}).status_code, 200
        )

    def test_delete_with_foreign_origin_is_rejected(self):
        qid = self._theory_id()
        self.client.post(f"/api/theory/{qid}", json={"note": "n"})
        response = self.client.delete(f"/api/theory/{qid}", headers={"Origin": "http://evil.example"})
        self.assertEqual(response.status_code, 403)
        lessons = self.client.get("/api/theory").get_json()["lessons"]
        self.assertTrue(next(item for item in lessons if item["id"] == qid)["saved"])

    def test_theory_post_requires_note_key(self):
        qid = self._theory_id()
        self.client.post(f"/api/theory/{qid}", json={"note": "keep me"})
        response = self.client.post(f"/api/theory/{qid}", json={})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "Include a note (it may be empty)."})
        self.assertEqual(self._note(qid), "keep me")
        self.assertEqual(self.client.post(f"/api/theory/{qid}", json={"note": ""}).status_code, 200)
        self.assertEqual(self._note(qid), "")

    def _fresh_database_path(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = os.path.join(directory.name, "fresh.sqlite3")
        self.addCleanup(preparator._initialized_databases.discard, path)
        return path

    def test_concurrent_first_requests_on_fresh_database_succeed(self):
        original = preparator.app.config["DATABASE"]
        self.addCleanup(preparator.app.config.__setitem__, "DATABASE", original)
        urls = ["/api/dashboard", "/api/theory", "/api/dashboard", "/api/theory", "/api/dashboard"]
        for _ in range(5):
            path = self._fresh_database_path()
            preparator.app.config["DATABASE"] = path
            self.assertNotIn(path, preparator._initialized_databases)
            barrier = threading.Barrier(len(urls))
            results = [None] * len(urls)

            def fire(index, url):
                client = preparator.app.test_client()
                barrier.wait(timeout=10)
                response = client.get(url)
                results[index] = (url, response.status_code, response.get_json())

            threads = [threading.Thread(target=fire, args=(i, u)) for i, u in enumerate(urls)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)
                self.assertFalse(thread.is_alive())
            for result in results:
                self.assertIsNotNone(result)
                self.assertEqual(result[1], 200, result)
                if result[0] == "/api/dashboard":
                    self.assertEqual(result[2]["question_count"], len(preparator.QUESTION_BANK))
            self.assertIn(path, preparator._initialized_databases)

    def test_failed_init_is_retried_on_next_request(self):
        original = preparator.app.config["DATABASE"]
        self.addCleanup(preparator.app.config.__setitem__, "DATABASE", original)
        path = self._fresh_database_path()
        preparator.app.config["DATABASE"] = path
        real_init = preparator.init_db
        calls = []

        def flaky_init():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("boom")
            return real_init()

        client = preparator.app.test_client()
        with mock.patch.dict(preparator.app.config, {"PROPAGATE_EXCEPTIONS": False}), \
                mock.patch.object(preparator, "init_db", flaky_init):
            self.assertEqual(client.get("/api/dashboard").status_code, 500)
            self.assertNotIn(path, preparator._initialized_databases)
            self.assertEqual(client.get("/api/dashboard").status_code, 200)
        self.assertIn(path, preparator._initialized_databases)
        self.assertEqual(len(calls), 2)
        connection = sqlite3.connect(path)
        try:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            connection.close()
        self.assertIn("questions", tables)


    OLD_QUESTIONS_SCHEMA = """CREATE TABLE questions (
        id INTEGER PRIMARY KEY, topic TEXT NOT NULL, difficulty TEXT NOT NULL,
        mode TEXT NOT NULL, prompt TEXT NOT NULL, criteria TEXT NOT NULL,
        explanation TEXT NOT NULL, solution TEXT NOT NULL)"""

    def _schema_snapshot(self, path):
        connection = sqlite3.connect(path)
        try:
            objects = connection.execute(
                "SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            columns = [r[1] for r in connection.execute("PRAGMA table_info(questions)")]
            version = connection.execute("PRAGMA user_version").fetchone()[0]
        finally:
            connection.close()
        return objects, columns, version

    def _table_columns(self, path, table):
        connection = sqlite3.connect(path)
        try:
            return [r[1] for r in connection.execute(f"PRAGMA table_info({table})")]
        finally:
            connection.close()

    def _run_init(self, path):
        original = preparator.app.config["DATABASE"]
        self.addCleanup(preparator.app.config.__setitem__, "DATABASE", original)
        preparator.app.config["DATABASE"] = path
        with preparator.app.app_context():
            preparator.init_db()

    def test_fresh_database_ends_at_latest_version_with_baseline_schema(self):
        path = self._fresh_database_path()
        self._run_init(path)
        objects, columns, version = self._schema_snapshot(path)
        self.assertEqual(version, preparator.MIGRATIONS[-1][0])
        names = {name for _, name in objects}
        self.assertTrue({"questions", "attempts", "weaknesses", "saved_lessons",
                         "attempts_question_id", "questions_identity"} <= names)
        self.assertIn("starter_code", columns)
        self.assertIn("retired", columns)
        self.assertIn("saved", self._table_columns(path, "saved_lessons"))

    def test_pre_starter_code_database_upgrades_and_keeps_data(self):
        path = self._fresh_database_path()
        connection = sqlite3.connect(path)
        connection.executescript(self.OLD_QUESTIONS_SCHEMA + """;
            CREATE TABLE attempts (id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER NOT NULL REFERENCES questions(id),
                answer TEXT NOT NULL, score INTEGER NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE weaknesses (question_id INTEGER PRIMARY KEY REFERENCES questions(id),
                miss_count INTEGER NOT NULL DEFAULT 1, last_score INTEGER NOT NULL DEFAULT 0,
                pinned INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL);
            CREATE TABLE saved_lessons (question_id INTEGER PRIMARY KEY REFERENCES questions(id),
                note TEXT NOT NULL DEFAULT '', saved_at TEXT NOT NULL);
            INSERT INTO questions VALUES (1, 'Custom', 'Easy', 'Theory', 'Old prompt', '[]', 'e', 's');
            INSERT INTO attempts (question_id, answer, score, created_at)
                VALUES (1, 'my answer', 4, '2026-01-01T00:00:00+00:00');
        """)
        connection.commit()
        self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 0)
        connection.close()
        self._run_init(path)
        _, columns, version = self._schema_snapshot(path)
        self.assertEqual(version, preparator.MIGRATIONS[-1][0])
        self.assertIn("starter_code", columns)
        self.assertIn("retired", columns)
        self.assertIn("saved", self._table_columns(path, "saved_lessons"))
        connection = sqlite3.connect(path)
        try:
            self.assertEqual(
                connection.execute("SELECT prompt FROM questions WHERE id = 1").fetchone()[0],
                "Old prompt")
            self.assertEqual(
                connection.execute("SELECT answer, score FROM attempts WHERE question_id = 1").fetchall(),
                [("my answer", 4)])
            seeded_with_starter = connection.execute(
                "SELECT COUNT(*) FROM questions WHERE starter_code != ''").fetchone()[0]
        finally:
            connection.close()
        self.assertGreater(seeded_with_starter, 0)

    def test_init_db_twice_is_a_noop_the_second_time(self):
        path = self._fresh_database_path()
        self._run_init(path)

        def counts():
            connection = sqlite3.connect(path)
            try:
                return [connection.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                        for t in ("questions", "attempts", "weaknesses", "saved_lessons")]
            finally:
                connection.close()

        before = (counts(), self._schema_snapshot(path))
        self._run_init(path)
        self.assertEqual((counts(), self._schema_snapshot(path)), before)

    def test_failing_migration_step_rolls_back_schema_and_version(self):
        path = self._fresh_database_path()
        self._run_init(path)
        before = self._schema_snapshot(path)

        def step_3(database):
            database.execute("CREATE TABLE step3_partial (id INTEGER)")
            database.execute("ALTER TABLE questions ADD COLUMN extra TEXT NOT NULL DEFAULT ''")
            raise RuntimeError("boom")

        migrations = preparator.MIGRATIONS + [(len(preparator.MIGRATIONS) + 1, step_3)]
        with mock.patch.object(preparator, "MIGRATIONS", migrations):
            with self.assertRaises(RuntimeError):
                self._run_init(path)
        self.assertEqual(self._schema_snapshot(path), before)

    def test_failing_step_on_old_database_leaves_it_untouched(self):
        path = self._fresh_database_path()
        connection = sqlite3.connect(path)
        connection.execute(self.OLD_QUESTIONS_SCHEMA)
        connection.commit()
        connection.close()
        before = self._schema_snapshot(path)

        def broken(database):
            database.execute("CREATE TABLE attempts (id INTEGER)")
            raise RuntimeError("boom")

        with mock.patch.object(preparator, "MIGRATIONS", [(1, broken)]):
            with self.assertRaises(RuntimeError):
                self._run_init(path)
        self.assertEqual(self._schema_snapshot(path), before)
        self.assertEqual(before[2], 0)

    def test_migration_versions_are_consecutive_from_one(self):
        versions = [version for version, _ in preparator.MIGRATIONS]
        self.assertEqual(versions, list(range(1, len(versions) + 1)))

    def test_failing_later_step_rolls_back_earlier_version_write_on_fresh_database(self):
        path = self._fresh_database_path()

        def boom(database):
            raise RuntimeError("boom")

        migrations = preparator.MIGRATIONS + [(len(preparator.MIGRATIONS) + 1, boom)]
        with mock.patch.object(preparator, "MIGRATIONS", migrations):
            with self.assertRaises(RuntimeError):
                self._run_init(path)
        connection = sqlite3.connect(path)
        try:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 0)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0], 0)
        finally:
            connection.close()

    def test_rollback_failure_does_not_mask_original_init_error(self):
        path = self._fresh_database_path()

        class FailingRollback:
            def __init__(self, inner):
                self.inner = inner

            def __getattr__(self, name):
                return getattr(self.inner, name)

            def rollback(self):
                raise sqlite3.OperationalError("rollback failed")

        def boom(database):
            raise RuntimeError("original")

        original = preparator.app.config["DATABASE"]
        self.addCleanup(preparator.app.config.__setitem__, "DATABASE", original)
        preparator.app.config["DATABASE"] = path
        with preparator.app.app_context():
            real = preparator.get_db()
            with mock.patch.object(preparator, "run_migrations", boom), \
                    mock.patch.object(preparator, "get_db", lambda: FailingRollback(real)):
                with self.assertRaises(RuntimeError) as caught:
                    preparator.init_db()
        self.assertEqual(str(caught.exception), "original")

    def _newer_database(self):
        """Seeded scratch database at latest + 1, with an edited explanation."""
        path = self._fresh_database_path()
        self._run_init(path)
        connection = sqlite3.connect(path)
        connection.execute("UPDATE questions SET explanation = 'edited' WHERE id = 1")
        connection.execute(f"PRAGMA user_version = {preparator.MIGRATIONS[-1][0] + 1}")
        connection.commit()
        connection.close()
        preparator._initialized_databases.discard(path)
        return path

    def _db_state(self, path):
        connection = sqlite3.connect(path)
        try:
            return (
                connection.execute("PRAGMA user_version").fetchone()[0],
                connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0],
                connection.execute("SELECT explanation FROM questions WHERE id = 1").fetchone()[0],
            )
        finally:
            connection.close()

    def _newer_message(self):
        latest = preparator.MIGRATIONS[-1][0]
        return (f"This database (schema version {latest + 1}) was created by a newer version "
                f"of Preparator; this version supports up to {latest}. Update Preparator, "
                "or set PREPARATOR_DATABASE to a different file.")

    def test_newer_database_version_is_refused_without_writes(self):
        path = self._newer_database()
        before = self._db_state(path)
        with self.assertRaises(preparator.SchemaTooNewError) as caught:
            self._run_init(path)
        self.assertEqual(str(caught.exception), self._newer_message())
        self.assertEqual(self._db_state(path), before)
        self.assertEqual(before[2], "edited")

    def test_newer_database_gives_500_and_retries_after_fix(self):
        path = self._newer_database()
        original = preparator.app.config["DATABASE"]
        self.addCleanup(preparator.app.config.__setitem__, "DATABASE", original)
        preparator.app.config["DATABASE"] = path
        client = preparator.app.test_client()
        with mock.patch.dict(preparator.app.config, {"PROPAGATE_EXCEPTIONS": False}):
            with self.assertLogs(preparator.app.logger, level="ERROR") as logs:
                response = client.get("/api/dashboard")
            self.assertIn(self._newer_message(), " ".join(logs.output))
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.get_json(), {"error": "Something went wrong. Try again."})
            self.assertNotIn(path, preparator._initialized_databases)
            connection = sqlite3.connect(path)
            connection.execute(f"PRAGMA user_version = {preparator.MIGRATIONS[-1][0]}")
            connection.commit()
            connection.close()
            self.assertEqual(client.get("/api/dashboard").status_code, 200)
        self.assertIn(path, preparator._initialized_databases)

    def test_prepare_database_lets_other_exceptions_propagate(self):
        original = preparator.app.config["DATABASE"]
        self.addCleanup(preparator.app.config.__setitem__, "DATABASE", original)
        preparator.app.config["DATABASE"] = self._fresh_database_path()
        stderr = io.StringIO()
        with mock.patch.object(preparator, "init_db", side_effect=RuntimeError("boom")),                 contextlib.redirect_stderr(stderr), self.assertRaises(RuntimeError) as caught:
            preparator.prepare_database()
        self.assertEqual(str(caught.exception), "boom")
        self.assertEqual(stderr.getvalue(), "")

    def test_newer_version_check_runs_before_any_write(self):
        path = self._newer_database()
        statements = []
        real_connect = sqlite3.connect

        def traced_connect(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            connection.set_trace_callback(statements.append)
            return connection

        with mock.patch.object(preparator.sqlite3, "connect", traced_connect):
            with self.assertRaises(preparator.SchemaTooNewError):
                self._run_init(path)
        self.assertIn("PRAGMA user_version", statements)
        writes = ("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "REPLACE",
                  "PRAGMA USER_VERSION =")
        for statement in statements:
            self.assertFalse(statement.strip().upper().startswith(writes), statement)

    def test_prepare_database_exits_on_newer_database_only(self):
        original = preparator.app.config["DATABASE"]
        self.addCleanup(preparator.app.config.__setitem__, "DATABASE", original)
        preparator.app.config["DATABASE"] = self._newer_database()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as caught:
            preparator.prepare_database()
        self.assertEqual(caught.exception.code, 1)
        self.assertEqual(stderr.getvalue().strip(), self._newer_message())
        preparator.app.config["DATABASE"] = self._fresh_database_path()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            preparator.prepare_database()
        self.assertEqual(stderr.getvalue(), "")

    def test_version_1_database_with_saved_lessons_upgrades_to_latest(self):
        path = self._fresh_database_path()
        self._run_init(path)
        connection = sqlite3.connect(path)
        qid = connection.execute(
            "SELECT id FROM questions WHERE mode = 'Theory' LIMIT 1").fetchone()[0]
        # Rebuild saved_lessons as it looked at version 1 (no `saved` column).
        connection.executescript("""
            DROP TABLE saved_lessons;
            CREATE TABLE saved_lessons (question_id INTEGER PRIMARY KEY REFERENCES questions(id),
                note TEXT NOT NULL DEFAULT '', saved_at TEXT NOT NULL);
            DROP INDEX questions_identity;
            ALTER TABLE questions DROP COLUMN retired;
            PRAGMA user_version = 1;
        """)
        connection.execute(
            "INSERT INTO saved_lessons (question_id, note, saved_at) VALUES (?, ?, ?)",
            (qid, "old note", "2026-01-01T00:00:00+00:00"))
        connection.commit()
        connection.close()
        self._run_init(path)  # points the app at `path` for the rest of the test
        self.assertEqual(self._schema_snapshot(path)[2], preparator.MIGRATIONS[-1][0])
        lesson, saved_count = self._lesson(qid)
        self.assertTrue(lesson["saved"])
        self.assertEqual(lesson["note"], "old note")
        self.assertEqual(saved_count, 1)
        self.assertIn("old note", self.client.get("/api/theory/export.csv").get_data(as_text=True))
        # New semantics apply to the upgraded row: unsaving keeps the note.
        self.assertEqual(self.client.delete(f"/api/theory/{qid}").get_json(), {"saved": False})
        lesson, _ = self._lesson(qid)
        self.assertFalse(lesson["saved"])
        self.assertEqual(lesson["note"], "old note")

    def _lesson(self, qid):
        data = self.client.get("/api/theory").get_json()
        return next(item for item in data["lessons"] if item["id"] == qid), data["saved_count"]

    def _saved_at(self, qid):
        with preparator.app.app_context():
            return preparator.get_db().execute(
                "SELECT saved_at FROM saved_lessons WHERE question_id = ?", (qid,)).fetchone()[0]

    def _set_saved_at(self, qid, value):
        with preparator.app.app_context():
            database = preparator.get_db()
            database.execute("UPDATE saved_lessons SET saved_at = ? WHERE question_id = ?", (value, qid))
            database.commit()

    def test_unsaving_keeps_note_and_excludes_it_from_export(self):
        qid = self._theory_id()
        self.client.post(f"/api/theory/{qid}", json={"note": "precious note"})
        response = self.client.delete(f"/api/theory/{qid}")
        self.assertEqual(response.get_json(), {"saved": False})
        lesson, saved_count = self._lesson(qid)
        self.assertFalse(lesson["saved"])
        self.assertEqual(lesson["note"], "precious note")
        self.assertEqual(saved_count, 0)
        self.assertNotIn("precious note",
                         self.client.get("/api/theory/export.csv").get_data(as_text=True))

    def test_resaving_sets_saved_keeps_posted_note_and_new_saved_at(self):
        qid = self._theory_id()
        self.client.post(f"/api/theory/{qid}", json={"note": "precious note"})
        self._set_saved_at(qid, "old")
        self.client.delete(f"/api/theory/{qid}")
        self.assertEqual(self.client.post(
            f"/api/theory/{qid}", json={"note": "second note"}).get_json(), {"saved": True})
        lesson, saved_count = self._lesson(qid)
        self.assertTrue(lesson["saved"])
        self.assertEqual(lesson["note"], "second note")
        self.assertEqual(saved_count, 1)
        self.assertNotEqual(self._saved_at(qid), "old")

    def test_updating_note_on_saved_lesson_keeps_saved_at(self):
        qid = self._theory_id()
        self.client.post(f"/api/theory/{qid}", json={"note": "one"})
        self._set_saved_at(qid, "old")
        self.client.post(f"/api/theory/{qid}", json={"note": "two"})
        self.assertEqual(self._saved_at(qid), "old")

    def test_unsaving_a_lesson_with_empty_note_removes_the_row(self):
        qid = self._theory_id()
        self.client.post(f"/api/theory/{qid}", json={"note": ""})
        self.assertEqual(self.client.delete(f"/api/theory/{qid}").get_json(), {"saved": False})
        with preparator.app.app_context():
            count = preparator.get_db().execute(
                "SELECT COUNT(*) FROM saved_lessons WHERE question_id = ?", (qid,)).fetchone()[0]
        self.assertEqual(count, 0)
        lesson, _ = self._lesson(qid)
        self.assertFalse(lesson["saved"])

    def _saved_row_count(self, qid):
        with preparator.app.app_context():
            return preparator.get_db().execute(
                "SELECT COUNT(*) FROM saved_lessons WHERE question_id = ?", (qid,)).fetchone()[0]

    def test_unsaving_a_whitespace_only_note_removes_the_row(self):
        qid = self._theory_id()
        blank = "  \n\t "
        self.client.post(f"/api/theory/{qid}", json={"note": blank})
        self.assertEqual(self._lesson(qid)[0]["note"], blank)  # POST stores it as sent
        self.assertEqual(self.client.delete(f"/api/theory/{qid}").get_json(), {"saved": False})
        self.assertEqual(self._saved_row_count(qid), 0)
        lesson, _ = self._lesson(qid)
        self.assertEqual((lesson["note"], lesson["saved"]), ("", False))

    def test_unsaving_keeps_a_note_with_text_and_whitespace_exactly(self):
        qid = self._theory_id()
        self.client.post(f"/api/theory/{qid}", json={"note": "  keep me \n"})
        self.client.delete(f"/api/theory/{qid}")
        lesson, _ = self._lesson(qid)
        self.assertEqual((lesson["note"], lesson["saved"]), ("  keep me \n", False))

    def test_unsaving_a_never_saved_lesson_is_harmless(self):
        qid = self._theory_id()
        self.assertEqual(self.client.delete(f"/api/theory/{qid}").get_json(), {"saved": False})

    # ---- TASK-012 / ADR-005: retired rows ----
    SEARCH = {
        "source_confirmed": True,
        "source_url": "https://www.google.com/search?q=python",
        "search_query": "Python interview questions",
    }

    def _edited_bank(self):
        bank = [dict(item) for item in preparator.QUESTION_BANK]
        old = {}
        for mode in ("Theory", "Coding"):
            item = next(q for q in bank if q["mode"] == mode)
            old[mode] = item["prompt"]
            item["prompt"] += " (edited)"
        return bank, old

    def _ids(self, prompts):
        with preparator.app.app_context():
            database = preparator.get_db()
            return {p: database.execute(
                "SELECT id FROM questions WHERE prompt = ?", (p,)).fetchone()[0] for p in prompts}

    def _retire_edited(self):
        bank, old = self._edited_bank()
        ids = self._ids(old.values())
        with mock.patch.object(preparator, "QUESTION_BANK", bank):
            with preparator.app.app_context():
                preparator.init_db()
        return bank, old, ids

    def test_edited_prompts_retire_old_rows(self):
        bank, old, ids = self._retire_edited()
        identities = {(q["topic"], q["difficulty"], q["mode"], q["prompt"]) for q in bank}
        dashboard = self.client.get("/api/dashboard").get_json()
        self.assertEqual(dashboard["question_count"], len(identities))
        titles = [lesson["title"] for lesson in self.client.get("/api/theory").get_json()["lessons"]]
        self.assertIn(old["Theory"] + " (edited)", titles)
        self.assertNotIn(old["Theory"], titles)
        with preparator.app.app_context():
            database = preparator.get_db()
            retired = {r[0] for r in database.execute("SELECT id FROM questions WHERE retired = 1")}
            self.assertEqual(retired, set(ids.values()))
            # Give every active row one attempt so least-practiced ordering would
            # pick a retired row first if the retired filter regressed.
            database.execute(
                "INSERT INTO attempts (question_id, answer, score, created_at) "
                "SELECT id, 'x', 5, '2026-01-01T00:00:00+00:00' FROM questions WHERE retired = 0")
            database.commit()
            for _ in range(5):
                self.assertNotIn(preparator.pick_question(database, {})["id"], retired)
                self.assertNotIn(
                    preparator.pick_question(database, {"mode": "Coding"})["id"], retired)
                self.assertNotIn(
                    preparator.pick_question(database, {"mode": "Theory"})["id"], retired)
            # The only weakness is on a retired row, so weak_only has nothing to serve.
            database.execute(
                "INSERT INTO weaknesses (question_id, miss_count, last_score, updated_at) "
                "VALUES (?, 1, 1, '2026-01-01T00:00:00+00:00')", (min(retired),))
            database.commit()
            self.assertIsNone(preparator.pick_question(database, {"weak_only": True}))

    def test_attempt_on_retired_row_still_counts(self):
        old = self._edited_bank()[1]["Theory"]
        qid = self._ids([old])[old]
        self.assertEqual(self.client.post(
            "/api/answer", json={"question_id": qid, "answer": "x"}).status_code, 200)
        self._retire_edited()
        dashboard = self.client.get("/api/dashboard").get_json()
        self.assertEqual(dashboard["attempts"], 1)
        self.assertEqual(len(dashboard["recent"]), 1)
        self.assertEqual(sum(t["attempts"] for t in dashboard["topics"]), 1)
        self.assertEqual(sum(m["attempts"] for m in dashboard["matrix"]), 1)

    def test_retired_id_is_not_served_or_pinned_but_answerable(self):
        _, old, ids = self._retire_edited()
        qid = ids[old["Coding"]]
        response = self.client.post("/api/question", json={**self.SEARCH, "question_id": qid})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json(), {"error": "Question not found."})
        response = self.client.post(f"/api/weakness/{qid}", json={})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json(), {"error": "Question not found."})
        self.assertEqual(self.client.post(
            "/api/answer", json={"question_id": qid, "answer": "something else"}).status_code, 200)

    def test_weakness_on_retired_row_is_hidden_but_row_kept(self):
        old = self._edited_bank()[1]["Theory"]
        qid = self._ids([old])[old]
        self.assertEqual(self.client.post(f"/api/weakness/{qid}", json={}).status_code, 200)
        self.assertEqual(self.client.get("/api/dashboard").get_json()["weak_count"], 1)
        self._retire_edited()
        after = self.client.get("/api/dashboard").get_json()
        self.assertEqual(after["weak_count"], 0)
        self.assertEqual(after["weak_questions"], [])
        with preparator.app.app_context():
            self.assertEqual(preparator.get_db().execute(
                "SELECT COUNT(*) FROM weaknesses").fetchone()[0], 1)

    def test_topics_and_matrix_omit_groups_with_only_retired_questions(self):
        gone = preparator.QUESTION_BANK[0]["topic"]
        bank = [q for q in preparator.QUESTION_BANK if q["topic"] != gone]
        with mock.patch.object(preparator, "QUESTION_BANK", bank):
            with preparator.app.app_context():
                preparator.init_db()
        dashboard = self.client.get("/api/dashboard").get_json()
        self.assertNotIn(gone, [t["topic"] for t in dashboard["topics"]])
        self.assertNotIn(gone, [m["topic"] for m in dashboard["matrix"]])

    def test_retired_saved_lesson_stays_in_csv_export(self):
        old = self._edited_bank()[1]["Theory"]
        qid = self._ids([old])[old]
        self.client.post(f"/api/theory/{qid}", json={"note": "kept note"})
        self._retire_edited()
        csv_text = self.client.get("/api/theory/export.csv").get_data(as_text=True)
        self.assertIn("kept note", csv_text)
        self.assertIn(old, csv_text)

    def test_reseeding_reactivates_a_retired_identity(self):
        _, old, ids = self._retire_edited()
        with preparator.app.app_context():
            preparator.init_db()  # original bank again
            row = preparator.get_db().execute(
                "SELECT retired FROM questions WHERE id = ?", (ids[old["Theory"]],)).fetchone()
        self.assertEqual(row[0], 0)

    def test_failed_seed_leaves_no_rows_retired(self):
        with preparator.app.app_context():
            database = preparator.get_db()
            total = database.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        bank = [{"topic": "Python"}] + [dict(q) for q in preparator.QUESTION_BANK]
        with mock.patch.object(preparator, "QUESTION_BANK", bank):
            with preparator.app.app_context():
                with self.assertRaises(KeyError):
                    preparator.init_db()
        with preparator.app.app_context():
            database = preparator.get_db()
            self.assertEqual(database.execute(
                "SELECT COALESCE(SUM(retired), 0), COUNT(*) FROM questions").fetchone()[:], (0, total))

    def test_version_2_database_with_stale_row_upgrades_to_retired(self):
        path = self._fresh_database_path()
        self._run_init(path)
        connection = sqlite3.connect(path)
        connection.executescript("""
            DROP INDEX questions_identity;
            ALTER TABLE questions DROP COLUMN retired;
            PRAGMA user_version = 2;
        """)
        total = connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        stale = connection.execute(
            "INSERT INTO questions (topic, difficulty, mode, prompt, criteria, explanation, "
            "solution) VALUES ('Python', 'Easy', 'Theory', 'Stale prompt', '[]', 'e', 's')"
        ).lastrowid
        connection.execute(
            "INSERT INTO attempts (question_id, answer, score, created_at) "
            "VALUES (?, 'a', 3, '2026-01-01T00:00:00+00:00')", (stale,))
        connection.execute(
            "INSERT INTO weaknesses (question_id, miss_count, last_score, updated_at) "
            "VALUES (?, 1, 3, '2026-01-01T00:00:00+00:00')", (stale,))
        connection.execute(
            "INSERT INTO saved_lessons (question_id, note, saved_at, saved) "
            "VALUES (?, 'stale note', '2026-01-01T00:00:00+00:00', 1)", (stale,))
        connection.commit()
        connection.close()
        self._run_init(path)
        self.assertEqual(self._schema_snapshot(path)[2], preparator.MIGRATIONS[-1][0])
        self.assertIn("questions_identity", {n for _, n in self._schema_snapshot(path)[0]})
        connection = sqlite3.connect(path)
        try:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM questions").fetchone()[0], total + 1)
            self.assertEqual(connection.execute(
                "SELECT retired FROM questions WHERE id = ?", (stale,)).fetchone()[0], 1)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM questions WHERE retired = 0").fetchone()[0], total)
            joined = connection.execute(
                """SELECT COUNT(*) FROM attempts a JOIN questions q ON q.id = a.question_id
                   JOIN weaknesses w ON w.question_id = q.id
                   JOIN saved_lessons s ON s.question_id = q.id WHERE q.id = ?""",
                (stale,)).fetchone()[0]
            self.assertEqual(joined, 1)
        finally:
            connection.close()
        dashboard = self.client.get("/api/dashboard").get_json()
        self.assertEqual(dashboard["attempts"], 1)
        self.assertEqual(dashboard["weak_count"], 0)
        identities = {(q["topic"], q["difficulty"], q["mode"], q["prompt"])
                      for q in preparator.QUESTION_BANK}
        self.assertEqual(dashboard["question_count"], len(identities))
        titles = [x["title"] for x in self.client.get("/api/theory").get_json()["lessons"]]
        self.assertNotIn("Stale prompt", titles)
        self.assertIn("stale note", self.client.get("/api/theory/export.csv").get_data(as_text=True))

    # ---- TASK-010: JSON errors and input validation ----
    def _search(self, **extra):
        return {**self.SEARCH, **extra}

    def _assert_error(self, response, status, message=None):
        self.assertEqual(response.status_code, status)
        self.assertTrue(response.is_json)
        body = response.get_json()
        self.assertEqual(list(body), ["error"])
        if message is not None:
            self.assertEqual(body["error"], message)

    BODY_MSG = "The request body must be a JSON object."
    ID_MSG = "question_id must be an integer."

    def test_non_object_bodies_are_400_everywhere(self):
        qid = self._theory_id()
        for path in ("/api/question", "/api/answer", f"/api/theory/{qid}"):
            for payload in ([1], "str", 5, "null"):
                response = self.client.post(path, json=payload) if payload != "null" else self.client.post(path, data="null", content_type="application/json")
                self._assert_error(response, 400, self.BODY_MSG)
            invalid = self.client.post(path, data="{not json", content_type="application/json")
            self._assert_error(invalid, 400, self.BODY_MSG)
            empty = self.client.post(path, data="", content_type="application/json")
            self._assert_error(empty, 400, self.BODY_MSG)

    def test_bad_question_id_types_are_400(self):
        for bad in ([1], {}, True, False, "1", 1.5):
            response = self.client.post("/api/question", json=self._search(question_id=bad))
            self._assert_error(response, 400, self.ID_MSG)
            response = self.client.post("/api/answer", json={"question_id": bad, "answer": "x"})
            self._assert_error(response, 400, self.ID_MSG)

    def test_question_id_missing_null_or_huge(self):
        qid = self._theory_id()
        self.assertEqual(self.client.post("/api/question", json=self._search(question_id=None)).status_code, 200)
        for body in ({"answer": "x"}, {"answer": "x", "question_id": None}, {"answer": "x", "question_id": 10**30}):
            self._assert_error(self.client.post("/api/answer", json=body), 404, "Question not found.")
        self._assert_error(
            self.client.post("/api/question", json=self._search(question_id=10**30)), 404, "Question not found.")
        self.assertEqual(self.client.post("/api/question", json=self._search(question_id=qid)).status_code, 200)

    def test_filters_must_be_text(self):
        for field in ("topic", "difficulty", "mode"):
            for bad in (None, 5, ["Python Core"], {}):
                response = self.client.post("/api/question", json=self._search(**{field: bad}))
                self._assert_error(response, 400, "Filters must be text.")

    # ---- TASK-049 / PLANNED-10: previous_score ----
    def test_previous_score_null_then_last_attempt_score(self):
        qid = self._first_question_id()
        first = self._answer_with_score(qid, 3)
        self.assertIn("previous_score", first)
        self.assertIsNone(first["previous_score"])
        self.assertEqual(self._answer_with_score(qid, 9)["previous_score"], 3)
        self.assertEqual(self._answer_with_score(qid, 5)["previous_score"], 9)

    def test_submit_inserts_attempt_before_reading_previous_score(self):
        # Guards the ordering that makes the previous_score read race-free (TASK-049 NIT 1).
        qid = self._first_question_id()
        statements = []
        real_connect = sqlite3.connect

        def tracing_connect(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            connection.set_trace_callback(statements.append)
            return connection

        with mock.patch.object(preparator.sqlite3, "connect", tracing_connect):
            self._answer_with_score(qid, 5)
        insert = next(i for i, s in enumerate(statements) if "INSERT INTO attempts" in s)
        select = next(i for i, s in enumerate(statements)
                      if "SELECT score FROM attempts" in s and "id <" in s)
        self.assertLess(insert, select)

    def test_previous_score_is_per_question_id(self):
        with preparator.app.app_context():
            a, b = [r[0] for r in preparator.get_db().execute(
                "SELECT id FROM questions WHERE retired = 0 LIMIT 2")]
        self.assertIsNone(self._answer_with_score(a, 2)["previous_score"])
        self.assertIsNone(self._answer_with_score(b, 8)["previous_score"])
        self.assertEqual(self._answer_with_score(a, 6)["previous_score"], 2)
        self.assertEqual(self._answer_with_score(b, 1)["previous_score"], 8)
        self.assertEqual(self._answer_with_score(a, 4)["previous_score"], 6)

    def test_rejected_requests_do_not_change_previous_score(self):
        with preparator.app.app_context():
            row = preparator.get_db().execute(
                "SELECT id, starter_code FROM questions WHERE mode = 'Coding' AND retired = 0 "
                "AND starter_code != '' LIMIT 1").fetchone()
        qid = row["id"]
        self._answer_with_score(qid, 4)
        self.assertEqual(self.client.post(
            "/api/answer", json={"question_id": qid, "answer": row["starter_code"]}).status_code, 400)
        self.assertEqual(self.client.post(
            "/api/answer", json={"question_id": qid, "answer": "  "}).status_code, 400)
        self.assertEqual(self.client.post(
            "/api/answer", json={"question_id": 10**9, "answer": "x"}).status_code, 404)
        self.assertEqual(self._answer_with_score(qid, 8)["previous_score"], 4)

    def test_previous_score_on_retired_id_and_its_successor(self):
        _, old, ids = self._retire_edited()
        retired_id = ids[old["Theory"]]
        self.assertIsNone(self._answer_with_score(retired_id, 3)["previous_score"])
        self.assertEqual(self._answer_with_score(retired_id, 6)["previous_score"], 3)
        with preparator.app.app_context():
            successor = preparator.get_db().execute(
                "SELECT id FROM questions WHERE retired = 0 AND prompt = ?",
                (old["Theory"] + " (edited)",)).fetchone()[0]
        self.assertIsNone(self._answer_with_score(successor, 5)["previous_score"])

    def test_non_string_answer_is_rejected(self):
        qid = self._theory_id()
        for bad in (5, None, ["a"], {"a": 1}, True):
            response = self.client.post("/api/answer", json={"question_id": qid, "answer": bad})
            self._assert_error(response, 400, "Write an answer before submitting.")

    def test_answer_length_limit(self):
        qid = self._theory_id()
        too_long = self.client.post("/api/answer", json={"question_id": qid, "answer": "a" * 20001})
        self._assert_error(too_long, 400, "Answers must be 20,000 characters or fewer.")
        padded = self.client.post("/api/answer", json={"question_id": qid, "answer": "  " + "a" * 20000 + "  "})
        self.assertEqual(padded.status_code, 200)

    def test_api_framework_errors_are_json(self):
        self._assert_error(self.client.get("/api/nope"), 404)
        method = self.client.get("/api/answer")
        self._assert_error(method, 405)
        self.assertIn("POST", method.headers.get("Allow", ""))
        self._assert_error(self.client.post("/api/answer", data="x", content_type="text/plain"), 415,
                           "Send a JSON body with Content-Type: application/json.")

    def test_oversize_body_is_413_json(self):
        big = '{"answer": "' + "a" * (1024 * 1024) + '"}'
        response = self.client.post("/api/answer", data=big, content_type="application/json")
        self._assert_error(response, 413, "Request is too large.")

    def test_unhandled_exception_is_json_500_without_traceback(self):
        qid = self._theory_id()
        with mock.patch.object(preparator, "evaluate_answer", side_effect=RuntimeError("secret-detail")):
            with self.assertLogs(preparator.app.logger, level="ERROR"):
                response = self.client.post("/api/answer", json={"question_id": qid, "answer": "x"})
        self._assert_error(response, 500, "Something went wrong. Try again.")
        text = response.get_data(as_text=True)
        self.assertNotIn("Traceback", text)
        self.assertNotIn("secret-detail", text)

    def test_non_api_404_stays_html(self):
        response = self.client.get("/nope")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.is_json)

    def test_non_api_500_stays_html_and_is_logged_once(self):
        # TESTING would re-raise; switch propagation off to see the served response.
        with mock.patch.dict(preparator.app.config, {"PROPAGATE_EXCEPTIONS": False, "TESTING": False}):
            with mock.patch.object(preparator, "render_template", side_effect=RuntimeError("boom")):
                with self.assertLogs(preparator.app.logger, level="ERROR") as logs:
                    response = self.client.get("/")
        self.assertEqual(response.status_code, 500)
        self.assertFalse(response.is_json)
        self.assertEqual(len(logs.records), 1)

    def test_deeply_nested_json_is_400(self):
        body = "[" * 100000 + "]" * 100000
        response = self.client.post("/api/question", data=body, content_type="application/json")
        self._assert_error(response, 400, self.BODY_MSG)

    def test_debug_is_off_unless_flask_debug_set(self):
        with open(preparator.__file__, encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn('debug=os.environ.get("FLASK_DEBUG") == "1"', source)
        self.assertNotIn("debug=True", source)

    # ---- TASK-002 review NITs ----
    def test_theory_post_non_object_body_gets_generic_message(self):
        qid = self._theory_id()
        self._assert_error(self.client.post(f"/api/theory/{qid}", json=["note"]), 400, self.BODY_MSG)
        self._assert_error(self.client.post(f"/api/theory/{qid}", data="oops", content_type="application/json"),
                           400, self.BODY_MSG)

    def test_exact_415_message(self):
        qid = self._theory_id()
        response = self.client.post(f"/api/theory/{qid}", data="", content_type="text/plain")
        self.assertEqual(response.get_json(),
                         {"error": "Send a JSON body with Content-Type: application/json."})

    def test_origin_with_different_port_is_rejected(self):
        body = {"question_id": self._theory_id(), "answer": "Not sure."}
        response = self.client.post("/api/answer", json=body, headers={"Origin": "http://localhost:6000"})
        self._assert_error(response, 403, "Cross-origin requests are not allowed.")

    def test_origin_is_checked_before_content_type(self):
        response = self.client.post("/api/answer", data="x", content_type="text/plain",
                                    headers={"Origin": "http://evil.example"})
        self._assert_error(response, 403, "Cross-origin requests are not allowed.")

    def test_host_check_applies_to_csv_export(self):
        response = self.client.get("/api/theory/export.csv", headers={"Host": "attacker.example"})
        self._assert_error(response, 400, "Unrecognized host.")

    # ---- TASK-018: guardrails, weak spots, lessons, CSV, 404s, selection ----
    def _question_row(self, mode):
        with preparator.app.app_context():
            return preparator.get_db().execute(
                "SELECT * FROM questions WHERE mode = ? AND retired = 0 LIMIT 1", (mode,)
            ).fetchone()["id"]

    def _weakness_row(self, qid):
        with preparator.app.app_context():
            row = preparator.get_db().execute(
                "SELECT miss_count, pinned FROM weaknesses WHERE question_id = ?", (qid,)
            ).fetchone()
            return None if row is None else (row["miss_count"], row["pinned"])

    def test_question_response_never_includes_solution_explanation_or_criteria(self):
        # ARCHITECTURE.md guardrail: no solution before submission, for both modes and for the
        # specific-id path as well as the picker path.
        forbidden = {"solution", "explanation", "criteria", "key_points", "example"}
        for mode in ("Theory", "Coding"):
            qid = self._question_row(mode)
            for extra in ({"mode": mode}, {"question_id": qid}):
                with self.subTest(mode=mode, extra=extra):
                    response = self.client.post("/api/question", json=self._search(**extra))
                    self.assertEqual(response.status_code, 200)
                    body = response.get_json()
                    self.assertFalse(forbidden & set(body["question"]), body["question"].keys())
                    self.assertFalse(forbidden & set(body), body.keys())
                    with preparator.app.app_context():
                        row = preparator.get_db().execute(
                            "SELECT solution, explanation FROM questions WHERE id = ?",
                            (body["question"]["id"],),
                        ).fetchone()
                    text = response.get_data(as_text=True)
                    self.assertNotIn(row["solution"], text)
                    self.assertNotIn(row["explanation"], text)

    def test_answer_response_has_heuristic_feedback_note_and_the_solution(self):
        for mode in ("Theory", "Coding"):
            qid = self._question_row(mode)
            with self.subTest(mode=mode):
                response = self.client.post(
                    "/api/answer", json={"question_id": qid, "answer": "my attempt number one"}
                )
                self.assertEqual(response.status_code, 200)
                body = response.get_json()
                self.assertIn("keyword rubric", body["feedback_note"])
                self.assertIn("not an AI judgment", body["feedback_note"])
                with preparator.app.app_context():
                    row = preparator.get_db().execute(
                        "SELECT solution, explanation FROM questions WHERE id = ?", (qid,)
                    ).fetchone()
                self.assertEqual(body["solution"], row["solution"])
                self.assertEqual(body["explanation"], row["explanation"])
                self.assertTrue({"score", "matched", "missing", "weak_queue"} <= set(body))

    def test_pin_creates_unmissed_pinned_row(self):
        qid = self._first_question_id()
        self.assertEqual(self.client.post(f"/api/weakness/{qid}", json={}).get_json(), {"saved": True})
        self.assertEqual(self._weakness_row(qid), (0, 1))

    def test_pin_on_existing_missed_row_keeps_miss_count(self):
        qid = self._first_question_id()
        self._answer_with_score(qid, 2)
        self._answer_with_score(qid, 3)
        self.assertEqual(self._weakness_row(qid), (2, 0))
        self.assertEqual(self.client.post(f"/api/weakness/{qid}", json={}).status_code, 200)
        self.assertEqual(self._weakness_row(qid), (2, 1))

    def test_delete_weakness_removes_pinned_and_unpinned_rows(self):
        pinned = self._first_question_id()
        with preparator.app.app_context():
            missed = preparator.get_db().execute(
                "SELECT id FROM questions WHERE retired = 0 AND id != ? LIMIT 1", (pinned,)
            ).fetchone()[0]
        self.client.post(f"/api/weakness/{pinned}", json={})
        self._answer_with_score(missed, 2)
        self.assertIsNotNone(self._weakness_row(pinned))
        self.assertIsNotNone(self._weakness_row(missed))
        for qid in (pinned, missed):
            response = self.client.delete(f"/api/weakness/{qid}")
            self.assertEqual(response.get_json(), {"removed": True})
            self.assertIsNone(self._weakness_row(qid))
        self.assertEqual(self.client.get("/api/dashboard").get_json()["weak_count"], 0)

    def test_weak_only_serves_only_weak_questions(self):
        with preparator.app.app_context():
            ids = [r[0] for r in preparator.get_db().execute(
                "SELECT id FROM questions WHERE retired = 0 ORDER BY id LIMIT 3")]
        weak = ids[1]
        self._answer_with_score(weak, 2)
        for _ in range(15):
            response = self.client.post("/api/question", json={"weak_only": True})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["question"]["id"], weak)

    def test_weak_only_with_empty_queue_is_404(self):
        response = self.client.post("/api/question", json={"weak_only": True})
        self._assert_error(response, 404, "No questions match those filters yet.")

    def test_note_length_limit_is_4000_characters(self):
        qid = self._theory_id()
        ok = self.client.post(f"/api/theory/{qid}", json={"note": "n" * 4000})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(len(self._note(qid)), 4000)
        too_long = self.client.post(f"/api/theory/{qid}", json={"note": "m" * 4001})
        self._assert_error(too_long, 400, "Notes must be text of 4,000 characters or fewer.")
        self.assertEqual(self._note(qid), "n" * 4000)

    def test_importing_app_with_database_env_does_not_create_instance_dir(self):
        # Spy on os.makedirs in a fresh interpreter before importing app; with
        # PREPARATOR_DATABASE set, app must not create any directory at import.
        with tempfile.TemporaryDirectory() as work:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            env = dict(os.environ, PREPARATOR_DATABASE=os.path.join(work, "x.sqlite3"))
            code = (
                "import os, sys\n"
                "calls = []\n"
                "real = os.makedirs\n"
                "os.makedirs = lambda *a, **k: (calls.append(a[0]), real(*a, **k))[1]\n"
                f"sys.path.insert(0, {root!r})\n"
                "import app\n"
                "assert not calls, calls\n"
            )
            result = subprocess.run(
                [sys.executable, "-c", code], cwd=work, env=env, capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_csv_export_header_bom_and_filename(self):
        qid = self._theory_id()
        self.client.post(f"/api/theory/{qid}", json={"note": "plain note"})
        response = self.client.get("/api/theory/export.csv")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["Content-Type"].startswith("text/csv"))
        self.assertEqual(
            response.headers["Content-Disposition"], "attachment; filename=preparator-theory.csv"
        )
        self.assertTrue(response.data.startswith(b"\xef\xbb\xbf"))
        lines = response.data.decode("utf-8-sig").splitlines()
        self.assertEqual(lines[0], "Topic,Level,Theory,Explanation,Example,My notes,Saved at")

    def test_csv_export_neutralizes_every_formula_prefix(self):
        qid = self._theory_id()
        for prefix in ("=", "+", "-", "@", "\t", "\r"):
            with self.subTest(prefix=repr(prefix)):
                note = prefix + "cmd|' /C calc'!A0"
                self.client.post(f"/api/theory/{qid}", json={"note": note})
                text = self.client.get("/api/theory/export.csv").data.decode("utf-8-sig")
                rows = list(csv.reader(io.StringIO(text, newline="")))
                self.assertEqual(len(rows), 2)
                self.assertEqual(rows[1][5], "'" + note)
        self.client.post(f"/api/theory/{qid}", json={"note": "safe text"})
        text = self.client.get("/api/theory/export.csv").data.decode("utf-8-sig")
        self.assertEqual(list(csv.reader(io.StringIO(text, newline="")))[1][5], "safe text")

    def test_unknown_question_id_is_404_on_question_and_answer(self):
        with preparator.app.app_context():
            missing = preparator.get_db().execute("SELECT MAX(id) FROM questions").fetchone()[0] + 1000
        self._assert_error(
            self.client.post("/api/question", json=self._search(question_id=missing)), 404, "Question not found."
        )
        self._assert_error(
            self.client.post("/api/answer", json={"question_id": missing, "answer": "x"}), 404, "Question not found."
        )
        self.assertEqual(self.client.get("/api/dashboard").get_json()["attempts"], 0)

    def test_filters_with_no_match_are_404(self):
        for filters in ({"topic": "No Such Topic"}, {"difficulty": "Impossible"}, {"mode": "Oral"}):
            with self.subTest(filters=filters):
                response = self.client.post("/api/question", json=self._search(**filters))
                self._assert_error(response, 404, "No questions match those filters yet.")

    def test_least_practiced_question_is_served_first(self):
        with preparator.app.app_context():
            database = preparator.get_db()
            group = database.execute(
                "SELECT topic, difficulty, mode FROM questions WHERE retired = 0 "
                "GROUP BY topic, difficulty, mode HAVING COUNT(*) BETWEEN 2 AND 6 LIMIT 1"
            ).fetchone()
            self.assertIsNotNone(group)
            ids = [r[0] for r in database.execute(
                "SELECT id FROM questions WHERE retired = 0 AND topic = ? AND difficulty = ? AND mode = ? "
                "ORDER BY id", tuple(group))]
        self.assertGreaterEqual(len(ids), 2)
        filters = dict(group)
        left_out = ids[-1]
        for qid in ids[:-1]:
            self._answer_with_score(qid, 10)
        for _ in range(10):
            response = self.client.post("/api/question", json=self._search(**filters))
            self.assertEqual(response.get_json()["question"]["id"], left_out)
        # Once the left-out one is practiced twice, an id practiced once is preferred again.
        self._answer_with_score(left_out, 10)
        self._answer_with_score(left_out, 10)
        for _ in range(10):
            response = self.client.post("/api/question", json=self._search(**filters))
            self.assertNotEqual(response.get_json()["question"]["id"], left_out)


if __name__ == "__main__":
    unittest.main()
