import json
import os
import sqlite3
import tempfile
import threading
import unittest
from unittest import mock
import app as preparator


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

    def test_question_requires_search_confirmation_before_serving(self):
        response = self.client.post("/api/question", json={"topic": "Python Core"})
        self.assertEqual(response.status_code, 428)

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

    def test_every_foundations_coding_item_has_starter_code(self):
        coding = [
            question for question in preparator.QUESTION_BANK
            if question["difficulty"] == "Foundations" and question["mode"] == "Coding"
        ]
        self.assertGreater(len(coding), 0)
        for question in coding:
            with self.subTest(prompt=question["prompt"]):
                self.assertTrue(question.get("starter_code", "").strip())
                self.assertNotEqual(question["starter_code"].strip(), question["solution"].strip())

    def test_dashboard_reports_canonical_bank_count(self):
        response = self.client.get("/api/dashboard")
        self.assertEqual(response.get_json()["question_count"], len(preparator.QUESTION_BANK))

    def test_confirmed_search_serves_one_question_with_source_link(self):
        response = self.client.post(
            "/api/question",
            json={
                "topic": "Python Core",
                "source_confirmed": True,
                "source_url": "https://www.google.com/search?q=Python+interview+questions",
                "search_query": "Python interview questions",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("question", response.get_json())
        self.assertEqual(len(response.get_json()["sources"]), 1)

    def test_untrusted_search_link_is_rejected(self):
        response = self.client.post(
            "/api/question",
            json={
                "source_confirmed": True,
                "source_url": "https://example.com/search?q=python",
                "search_query": "Python interview questions",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_low_score_adds_question_to_weakness_queue(self):
        with preparator.app.app_context():
            question_id = preparator.get_db().execute("SELECT id FROM questions LIMIT 1").fetchone()[0]
        response = self.client.post("/api/answer", json={"question_id": question_id, "answer": "Not sure."})
        self.assertEqual(response.status_code, 200)
        dashboard = self.client.get("/api/dashboard").get_json()
        self.assertEqual(dashboard["weak_count"], 1)
        self.assertEqual(dashboard["attempts"], 1)

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

    def test_newer_database_version_logs_warning_and_continues(self):
        path = self._fresh_database_path()
        self._run_init(path)
        connection = sqlite3.connect(path)
        connection.execute("PRAGMA user_version = 99")
        connection.close()
        with self.assertLogs(preparator.app.logger, level="WARNING") as logs:
            self._run_init(path)
        self.assertTrue(any("99" in line for line in logs.output))
        self.assertEqual(self._schema_snapshot(path)[2], 99)

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
    SOURCE_MSG = "A valid public search link is required before a question can be served."

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

    def test_source_url_and_query_must_be_strings(self):
        for override in ({"source_url": 5}, {"source_url": ["https://google.com"]},
                         {"search_query": 5}, {"search_query": None}, {"source_url": None}):
            response = self.client.post("/api/question", json=self._search(**override))
            self._assert_error(response, 400, self.SOURCE_MSG)

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


if __name__ == "__main__":
    unittest.main()