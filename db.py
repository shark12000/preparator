import json
import sqlite3
import threading
from datetime import datetime, timezone

from flask import current_app, g

from question_bank import QUESTION_BANK

# Selects one row per prompt identity; older databases may hold duplicate seeds.
CANONICAL_QUESTION = (
    "q.id = (SELECT MIN(q2.id) FROM questions q2 WHERE q2.topic = q.topic "
    "AND q2.difficulty = q.difficulty AND q2.mode = q.mode AND q2.prompt = q.prompt)"
)
# Rows whose identity left QUESTION_BANK are never served or listed.
# Use this where the table alias is q; queries without an alias inline `retired = 0`.
ACTIVE_QUESTION = "q.retired = 0"
_initialized_databases = set()
_init_lock = threading.Lock()


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        # Seed lazily so `flask run`, WSGI servers, and `python app.py` all work.
        path = current_app.config["DATABASE"]
        if path not in _initialized_databases:
            # One init per path; mark only after init_db() succeeds.
            # init_db() calls get_db() again, which returns g.db without the lock.
            with _init_lock:
                if path not in _initialized_databases:
                    try:
                        init_db()
                    except Exception:
                        try:
                            g.db.rollback()
                        except sqlite3.Error:
                            pass  # never mask the original init error
                        raise
                    _initialized_databases.add(path)
    return g.db


def close_db(_error=None):
    database = g.pop("db", None)
    if database is not None:
        database.close()


def _migration_1_baseline(database):
    """Baseline schema; also upgrades databases created before `starter_code`."""
    # One execute() per statement: executescript() would commit the open transaction.
    statements = (
        """CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY,
            topic TEXT NOT NULL,
            difficulty TEXT NOT NULL,
            mode TEXT NOT NULL,
            prompt TEXT NOT NULL,
            criteria TEXT NOT NULL,
            explanation TEXT NOT NULL,
            solution TEXT NOT NULL,
            starter_code TEXT NOT NULL DEFAULT ''
        )""",
        """CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL REFERENCES questions(id),
            answer TEXT NOT NULL,
            score INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS weaknesses (
            question_id INTEGER PRIMARY KEY REFERENCES questions(id),
            miss_count INTEGER NOT NULL DEFAULT 1,
            last_score INTEGER NOT NULL DEFAULT 0,
            pinned INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS saved_lessons (
            question_id INTEGER PRIMARY KEY REFERENCES questions(id),
            note TEXT NOT NULL DEFAULT '',
            saved_at TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS attempts_question_id ON attempts(question_id)",
    )
    for statement in statements:
        database.execute(statement)
    question_columns = {
        column["name"] for column in database.execute("PRAGMA table_info(questions)")
    }
    if "starter_code" not in question_columns:
        database.execute(
            "ALTER TABLE questions ADD COLUMN starter_code TEXT NOT NULL DEFAULT ''"
        )


def _migration_2_saved_flag(database):
    """Unsaving keeps the note. Existing rows are saved lessons (default 1)."""
    database.execute("ALTER TABLE saved_lessons ADD COLUMN saved INTEGER NOT NULL DEFAULT 1")


def _migration_3_retired_questions(database):
    """Rows whose identity left QUESTION_BANK are retired, not deleted.

    Default 0 keeps every existing row active until seeding marks stale ones.
    """
    database.execute("ALTER TABLE questions ADD COLUMN retired INTEGER NOT NULL DEFAULT 0")
    database.execute(
        "CREATE INDEX IF NOT EXISTS questions_identity "
        "ON questions(topic, difficulty, mode, prompt)"
    )


def _migration_4_rubric_overrides(database):
    """Recorded "I covered this" marks. Never read by scoring or the dashboard."""
    database.execute(
        """CREATE TABLE IF NOT EXISTS rubric_overrides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_id INTEGER NOT NULL REFERENCES attempts(id),
            question_id INTEGER NOT NULL REFERENCES questions(id),
            criterion_index INTEGER NOT NULL,
            criterion_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(attempt_id, criterion_index)
        )"""
    )
    database.execute(
        "CREATE INDEX IF NOT EXISTS rubric_overrides_question_id "
        "ON rubric_overrides(question_id)"
    )


# Ordered (version, step) pairs. Steps must be additive only (new tables,
# new columns with defaults, new indexes); never rewrite or drop user data.
MIGRATIONS = [
    (1, _migration_1_baseline),
    (2, _migration_2_saved_flag),
    (3, _migration_3_retired_questions),
    (4, _migration_4_rubric_overrides),
]


class SchemaTooNewError(RuntimeError):
    """The database was created by a newer version of Preparator.

    Refuse to open it rather than risk damaging it.
    """

    def __init__(self, database_version, latest_version):
        self.database_version = database_version
        self.latest_version = latest_version
        super().__init__(
            f"This database (schema version {database_version}) was created by a newer "
            f"version of Preparator; this version supports up to {latest_version}. "
            "Update Preparator, or set PREPARATOR_DATABASE to a different file."
        )


def run_migrations(database):
    """Apply pending steps; the caller owns the open transaction."""
    current = database.execute("PRAGMA user_version").fetchone()[0]
    latest = MIGRATIONS[-1][0]
    if current > latest:
        raise SchemaTooNewError(current, latest)  # before any write
    for version, step in MIGRATIONS:
        if current < version:
            step(database)
            # PRAGMA does not take bound parameters; version is an int from MIGRATIONS.
            database.execute(f"PRAGMA user_version = {int(version)}")
            current = version


def init_db():
    database = get_db()
    database.commit()  # close any implicit transaction before the explicit BEGIN
    # Migrations and seed share one transaction so a failure rolls both back.
    database.execute("BEGIN IMMEDIATE")
    try:
        run_migrations(database)
        seed_questions(database)
        database.commit()
    except BaseException:
        try:
            database.rollback()
        except sqlite3.Error:
            pass  # never mask the original init error
        raise


def seed_questions(database):
    # Retire everything, then re-activate identities still in the bank.
    database.execute("UPDATE questions SET retired = 1")
    for question in QUESTION_BANK:
        identity = (question["topic"], question["difficulty"], question["mode"], question["prompt"])
        content = (
            json.dumps(question["criteria"]),
            question["explanation"],
            question["solution"],
            question.get("starter_code", ""),
        )
        # Refresh content on existing rows so edits to the bank reach old databases.
        updated = database.execute(
            """UPDATE questions SET criteria = ?, explanation = ?, solution = ?, starter_code = ?,
                   retired = 0
               WHERE topic = ? AND difficulty = ? AND mode = ? AND prompt = ?""",
            content + identity,
        )
        if updated.rowcount:
            continue
        database.execute(
            """INSERT INTO questions
               (topic, difficulty, mode, prompt, criteria, explanation, solution, starter_code, retired)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            identity + content,
        )


def init_app(app):
    app.teardown_appcontext(close_db)
