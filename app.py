import csv
import io
import json
import os
import re
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

from flask import Flask, Response, g, jsonify, render_template, request
from werkzeug.exceptions import HTTPException
from question_bank import QUESTION_BANK


app = Flask(__name__)
app.config["DATABASE"] = os.environ.get(
    "PREPARATOR_DATABASE", os.path.join(app.instance_path, "preparator.sqlite3")
)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024
if "PREPARATOR_DATABASE" not in os.environ:
    os.makedirs(app.instance_path, exist_ok=True)

ALLOWED_HOSTNAMES = {"127.0.0.1", "localhost"}


@app.before_request
def guard_localhost_requests():
    """ADR-002: Host allow-list, same-origin writes, JSON-only POSTs (in that order)."""
    is_api = request.path.startswith("/api/")
    try:
        hostname = urlparse("//" + request.host).hostname
    except ValueError:
        hostname = None
    if hostname not in ALLOWED_HOSTNAMES:
        if is_api:
            return jsonify({"error": "Unrecognized host."}), 400
        return Response("Unrecognized host.", status=400, mimetype="text/plain")
    if not is_api or request.method not in ("POST", "DELETE"):
        return None
    origin = request.headers.get("Origin")
    if origin is not None and origin != request.host_url.rstrip("/"):
        return jsonify({"error": "Cross-origin requests are not allowed."}), 403
    if request.method == "POST" and request.mimetype != "application/json":
        return jsonify({"error": "Send a JSON body with Content-Type: application/json."}), 415
    return None


MAX_ANSWER_LENGTH = 20000
SQLITE_MAX_INT = 2**63 - 1
API_ERROR_MESSAGES = {
    400: "Bad request.",
    404: "Not found.",
    405: "Method not allowed.",
    413: "Request is too large.",
    415: "Send a JSON body with Content-Type: application/json.",
}


@app.errorhandler(Exception)
def handle_error(error):
    """PLANNED-2: every /api/ error is JSON; other routes keep Flask's default pages."""
    is_api = request.path.startswith("/api/")
    if isinstance(error, HTTPException):
        if not is_api:
            return error
        status = error.code or 500
        if status >= 500:
            message = "Something went wrong. Try again."
        else:
            message = API_ERROR_MESSAGES.get(status, error.description or "Request failed.")
        response = jsonify({"error": message})
        response.status_code = status
        if status == 405 and error.get_response().headers.get("Allow"):
            response.headers["Allow"] = error.get_response().headers["Allow"]
        return response
    if not is_api:
        raise error  # Flask's own handler logs it and serves the HTML 500
    app.logger.exception("Unhandled error on %s %s", request.method, request.path)
    return jsonify({"error": "Something went wrong. Try again."}), 500


def read_json_object():
    """Return (body, None) for a JSON-object body, else (None, error response)."""
    try:
        data = request.get_json(silent=True)
    except RecursionError:  # absurdly nested JSON within the size cap
        data = None
    if not isinstance(data, dict):
        return None, (jsonify({"error": "The request body must be a JSON object."}), 400)
    return data, None


def is_int_id(value):
    return isinstance(value, int) and not isinstance(value, bool)


# Scores below this keep a question in the weak-spot queue.
WEAK_SCORE_THRESHOLD = 7
# Selects one row per prompt identity; older databases may hold duplicate seeds.
CANONICAL_QUESTION = (
    "q.id = (SELECT MIN(q2.id) FROM questions q2 WHERE q2.topic = q.topic "
    "AND q2.difficulty = q.difficulty AND q2.mode = q.mode AND q2.prompt = q.prompt)"
)
# ADR-005: rows whose identity left QUESTION_BANK are never served or listed.
# Use this where the table alias is q; queries without an alias inline `retired = 0`.
ACTIVE_QUESTION = "q.retired = 0"
_initialized_databases = set()
_init_lock = threading.Lock()


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        # Seed lazily so `flask run`, WSGI servers, and `python app.py` all work.
        path = app.config["DATABASE"]
        if path not in _initialized_databases:
            # ADR-003: one init per path; mark only after init_db() succeeds.
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


@app.teardown_appcontext
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
    """ADR-004: unsaving keeps the note. Existing rows are saved lessons (default 1)."""
    database.execute("ALTER TABLE saved_lessons ADD COLUMN saved INTEGER NOT NULL DEFAULT 1")


def _migration_3_retired_questions(database):
    """ADR-005: rows whose identity left QUESTION_BANK are retired, not deleted.

    Default 0 keeps every existing row active until seeding marks stale ones.
    """
    database.execute("ALTER TABLE questions ADD COLUMN retired INTEGER NOT NULL DEFAULT 0")
    database.execute(
        "CREATE INDEX IF NOT EXISTS questions_identity "
        "ON questions(topic, difficulty, mode, prompt)"
    )


# ADR-003: ordered (version, step) pairs. Steps must be additive only (new tables,
# new columns with defaults, new indexes); never rewrite or drop user data.
MIGRATIONS = [
    (1, _migration_1_baseline),
    (2, _migration_2_saved_flag),
    (3, _migration_3_retired_questions),
]


def run_migrations(database):
    """Apply pending steps; the caller owns the open transaction."""
    current = database.execute("PRAGMA user_version").fetchone()[0]
    latest = MIGRATIONS[-1][0]
    if current > latest:
        app.logger.warning(
            "Database user_version %s is newer than this app's schema version %s; "
            "continuing without migrating.", current, latest,
        )
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
    # ADR-005: retire everything, then re-activate identities still in the bank.
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


def keyword_pattern(keyword):
    # Anchor keywords that start with a letter or digit to a word start, so
    # "count" does not match "account" while "hash" still matches "hashable".
    escaped = re.escape(keyword.casefold())
    return rf"(?<!\w){escaped}" if re.match(r"\w", keyword) else escaped


def strip_starter_code(answer, starter_code):
    """Drop lines copied verbatim from the starter so the stub earns no credit."""
    starter_lines = {line.strip() for line in starter_code.splitlines() if line.strip()}
    return "\n".join(line for line in answer.splitlines() if line.strip() not in starter_lines)


def evaluate_answer(answer, criteria, starter_code=""):
    if starter_code:
        answer = strip_starter_code(answer, starter_code)
    normalized = re.sub(r"\s+", " ", answer.casefold())
    matched = []
    missing = []
    for item in criteria:
        if any(re.search(keyword_pattern(keyword), normalized) for keyword in item["keywords"]):
            matched.append(item["label"])
        else:
            missing.append(item["label"])
    score = round(10 * len(matched) / len(criteria)) if criteria else 0
    if answer.strip() and score == 0:
        score = 1
    return {"score": score, "matched": matched, "missing": missing}


CODING_PLACEHOLDER = "# Write your Python solution below.\n"


def effective_starter(row):
    """Starter shown to the user: stored code, else the Coding placeholder, else empty."""
    if row["starter_code"]:
        return row["starter_code"]
    return CODING_PLACEHOLDER if row["mode"] == "Coding" else ""


def question_dict(row):
    return {
        "id": row["id"],
        "topic": row["topic"],
        "difficulty": row["difficulty"],
        "mode": row["mode"],
        "prompt": row["prompt"],
        "starter_code": effective_starter(row),
    }


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/dashboard")
def dashboard():
    database = get_db()
    totals = database.execute(
        "SELECT COUNT(*) AS attempts, ROUND(AVG(score)) AS average FROM attempts"
    ).fetchone()
    weak_count = database.execute(
        """SELECT COUNT(*) FROM weaknesses w JOIN questions q ON q.id = w.question_id
           WHERE """ + ACTIVE_QUESTION
    ).fetchone()[0]
    question_count = database.execute(
        """SELECT COUNT(*) FROM (
               SELECT 1 FROM questions WHERE retired = 0 GROUP BY topic, difficulty, mode, prompt
           )"""
    ).fetchone()[0]
    topics = database.execute(
        """SELECT q.topic, COUNT(a.id) AS attempts, ROUND(AVG(a.score)) AS average
           FROM questions q LEFT JOIN attempts a ON a.question_id = q.id
           GROUP BY q.topic HAVING SUM(q.retired = 0) > 0 ORDER BY q.topic"""
    ).fetchall()
    weak_questions = database.execute(
        """SELECT q.id, q.topic, q.difficulty, q.mode, q.prompt,
                  w.miss_count, w.last_score, w.pinned
           FROM weaknesses w JOIN questions q ON q.id = w.question_id
           WHERE """ + ACTIVE_QUESTION + """
           ORDER BY w.pinned DESC, w.updated_at ASC"""
    ).fetchall()
    recent = database.execute(
        """SELECT a.score, a.created_at, q.topic, q.prompt
           FROM attempts a JOIN questions q ON q.id = a.question_id
           ORDER BY a.id DESC LIMIT 5"""
    ).fetchall()
    matrix = database.execute(
        """SELECT q.topic, q.difficulty, COUNT(a.id) AS attempts, ROUND(AVG(a.score), 1) AS average
           FROM questions q LEFT JOIN attempts a ON a.question_id = q.id
           GROUP BY q.topic, q.difficulty HAVING SUM(q.retired = 0) > 0"""
    ).fetchall()
    # Day boundaries follow this computer's local time zone.
    daily = database.execute(
        """SELECT date(created_at, 'localtime') AS day, COUNT(*) AS attempts,
                  ROUND(AVG(score), 1) AS average
           FROM attempts GROUP BY day ORDER BY day DESC LIMIT 30"""
    ).fetchall()
    # The streak looks at every practice day, not just the 30 shown in the trend.
    practice_days = [
        row[0]
        for row in database.execute(
            "SELECT DISTINCT date(created_at, 'localtime') AS day FROM attempts"
        )
    ]
    return jsonify(
        {
            "attempts": totals["attempts"],
            "average": totals["average"] or 0,
            "weak_count": weak_count,
            "question_count": question_count,
            "topics": [dict(row) for row in topics],
            "matrix": [dict(row) for row in matrix],
            "trend": [dict(row) for row in reversed(daily)],
            "streak": practice_streak(practice_days),
            "weak_questions": [dict(row) for row in weak_questions],
            "recent": [dict(row) for row in recent],
        }
    )


def practice_streak(practice_days, today=None):
    """Count consecutive practice days ending today (or yesterday, if today is still open)."""
    today = today or date.today()
    practiced = {date.fromisoformat(day) for day in practice_days}
    cursor = today if today in practiced else today - timedelta(days=1)
    streak = 0
    while cursor in practiced:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


@app.get("/api/theory")
def theory_library():
    rows = get_db().execute(
        """SELECT q.id, q.topic, q.difficulty, q.prompt AS title, q.criteria,
              q.explanation, q.solution AS example, COALESCE(s.note, '') AS note,
                  (COALESCE(s.saved, 0) = 1) AS saved
           FROM questions q LEFT JOIN saved_lessons s ON s.question_id = q.id
           WHERE q.mode = 'Theory' AND """ + ACTIVE_QUESTION + " AND " + CANONICAL_QUESTION + """
           ORDER BY q.topic, q.difficulty, q.id"""
    ).fetchall()
    lessons = []
    for row in rows:
        lesson = dict(row)
        lesson["key_points"] = [item["label"] for item in json.loads(lesson.pop("criteria"))]
        lesson["saved"] = bool(lesson["saved"])
        lessons.append(lesson)
    return jsonify({"lessons": lessons, "saved_count": sum(lesson["saved"] for lesson in lessons)})


@app.post("/api/theory/<int:question_id>")
def save_theory_lesson(question_id):
    data, failure = read_json_object()
    if failure:
        return failure
    if "note" not in data:
        return jsonify({"error": "Include a note (it may be empty)."}), 400
    note = data["note"]
    if not isinstance(note, str) or len(note) > 4000:
        return jsonify({"error": "Notes must be text of 4,000 characters or fewer."}), 400
    database = get_db()
    lesson = database.execute(
        "SELECT id FROM questions WHERE id = ? AND mode = 'Theory'", (question_id,)
    ).fetchone()
    if lesson is None:
        return jsonify({"error": "Theory lesson not found."}), 404
    database.execute(
        """INSERT INTO saved_lessons (question_id, note, saved_at, saved) VALUES (?, ?, ?, 1)
           ON CONFLICT(question_id) DO UPDATE SET
               note = excluded.note,
               saved_at = CASE WHEN saved_lessons.saved = 0
                               THEN excluded.saved_at ELSE saved_lessons.saved_at END,
               saved = 1""",
        (question_id, note, utc_now()),
    )
    database.commit()
    return jsonify({"saved": True})


@app.delete("/api/theory/<int:question_id>")
def unsave_theory_lesson(question_id):
    database = get_db()
    # ADR-004: keep the note; only clear the flag. Empty notes have nothing to keep.
    database.execute("UPDATE saved_lessons SET saved = 0 WHERE question_id = ?", (question_id,))
    database.execute(
        "DELETE FROM saved_lessons WHERE question_id = ? AND note = ''", (question_id,)
    )
    database.commit()
    return jsonify({"saved": False})


def spreadsheet_safe(value):
    text = str(value or "")
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


@app.get("/api/theory/export.csv")
def export_saved_theory():
    rows = get_db().execute(
        """SELECT q.topic, q.difficulty, q.prompt, q.explanation, q.solution,
                  s.note, s.saved_at
           FROM saved_lessons s JOIN questions q ON q.id = s.question_id
           WHERE s.saved = 1
           ORDER BY q.topic, q.prompt"""
    ).fetchall()
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["Topic", "Level", "Theory", "Explanation", "Example", "My notes", "Saved at"])
    for row in rows:
        writer.writerow([spreadsheet_safe(value) for value in row])
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=preparator-theory.csv"},
    )


@app.post("/api/question")
def next_question():
    preferences, failure = read_json_object()
    if failure:
        return failure
    if not preferences.get("source_confirmed"):
        return jsonify({"error": "Search recent interview coverage in your browser before continuing."}), 428
    source_url = preferences.get("source_url", "")
    source_query = preferences.get("search_query", "")
    allowed_hosts = {"google.com", "www.google.com", "bing.com", "www.bing.com", "duckduckgo.com"}
    source_ok = isinstance(source_url, str) and isinstance(source_query, str) and source_query.strip()
    if source_ok:
        try:
            parsed_source = urlparse(source_url)
            source_ok = parsed_source.scheme == "https" and parsed_source.hostname in allowed_hosts
        except ValueError:
            source_ok = False
    if not source_ok:
        return jsonify({"error": "A valid public search link is required before a question can be served."}), 400
    source_query = source_query.strip()
    requested_id = preferences.get("question_id")
    if requested_id is not None and not is_int_id(requested_id):
        return jsonify({"error": "question_id must be an integer."}), 400
    for field in ("topic", "difficulty", "mode"):
        if field in preferences and not isinstance(preferences[field], str):
            return jsonify({"error": "Filters must be text."}), 400
    database = get_db()
    if requested_id is not None:
        if abs(requested_id) > SQLITE_MAX_INT:
            return jsonify({"error": "Question not found."}), 404
        # A specific question (e.g. "Practice this one" from Weak spots) overrides the filters.
        row = database.execute("SELECT * FROM questions WHERE id = ? AND retired = 0", (requested_id,)).fetchone()
        if row is None:
            return jsonify({"error": "Question not found."}), 404
    else:
        row = pick_question(database, preferences)
        if row is None:
            return jsonify({"error": "No questions match those filters yet."}), 404
    return jsonify(
        {
            "question": question_dict(row),
            "sources": [{"title": f"Web search: {source_query}", "url": source_url}],
        }
    )


def pick_question(database, preferences):
    conditions = [ACTIVE_QUESTION, CANONICAL_QUESTION]
    parameters = []
    for field, any_value in (("topic", "All topics"), ("difficulty", "Any level"), ("mode", "Any mode")):
        value = preferences.get(field, any_value)
        if value != any_value:
            conditions.append(f"q.{field} = ?")
            parameters.append(value)
    if preferences.get("weak_only"):
        query = "SELECT q.* FROM questions q JOIN weaknesses w ON w.question_id = q.id"
    else:
        query = "SELECT q.* FROM questions q"
    query += " WHERE " + " AND ".join(conditions)
    # Least-practiced prompts first, randomized within each tier.
    query += " ORDER BY (SELECT COUNT(*) FROM attempts a WHERE a.question_id = q.id), RANDOM() LIMIT 1"
    return database.execute(query, parameters).fetchone()


@app.post("/api/answer")
def submit_answer():
    data, failure = read_json_object()
    if failure:
        return failure
    raw_answer = data.get("answer", "")
    answer = raw_answer.strip() if isinstance(raw_answer, str) else ""
    question_id = data.get("question_id")
    if not answer:
        return jsonify({"error": "Write an answer before submitting."}), 400
    if len(answer) > MAX_ANSWER_LENGTH:
        return jsonify({"error": "Answers must be 20,000 characters or fewer."}), 400
    if question_id is not None and not is_int_id(question_id):
        return jsonify({"error": "question_id must be an integer."}), 400
    database = get_db()
    if question_id is None or abs(question_id) > SQLITE_MAX_INT:
        row = None
    else:
        row = database.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
    if row is None:
        return jsonify({"error": "Question not found."}), 404
    starter = effective_starter(row)
    if starter and answer == starter.strip():
        return jsonify({"error": "Replace the starter stub with your solution before submitting."}), 400
    result = evaluate_answer(answer, json.loads(row["criteria"]), starter)
    now = utc_now()
    database.execute(
        "INSERT INTO attempts (question_id, answer, score, created_at) VALUES (?, ?, ?, ?)",
        (question_id, answer, result["score"], now),
    )
    existing = database.execute(
        "SELECT pinned FROM weaknesses WHERE question_id = ?", (question_id,)
    ).fetchone()
    if result["score"] < WEAK_SCORE_THRESHOLD:
        queue_status = "still_weak" if existing else "added"
        database.execute(
            """INSERT INTO weaknesses (question_id, miss_count, last_score, updated_at)
               VALUES (?, 1, ?, ?)
               ON CONFLICT(question_id) DO UPDATE SET
                   miss_count = miss_count + 1, last_score = excluded.last_score,
                   updated_at = excluded.updated_at""",
            (question_id, result["score"], now),
        )
    elif existing is None:
        queue_status = "not_queued"
    elif existing["pinned"]:
        queue_status = "kept_pinned"
        database.execute(
            "UPDATE weaknesses SET last_score = ?, updated_at = ? WHERE question_id = ?",
            (result["score"], now, question_id),
        )
    else:
        queue_status = "removed"
        database.execute(
            "DELETE FROM weaknesses WHERE question_id = ? AND pinned = 0", (question_id,)
        )
    database.commit()
    return jsonify(
        {
            **result,
            "explanation": row["explanation"],
            "solution": row["solution"],
            "feedback_note": "Concept-match score: a transparent keyword rubric, not an AI judgment. Review the missed concepts below.",
            "weak_queue": {"status": queue_status, "threshold": WEAK_SCORE_THRESHOLD},
        }
    )


@app.post("/api/weakness/<int:question_id>")
def pin_weakness(question_id):
    database = get_db()
    exists = database.execute(
        "SELECT id FROM questions WHERE id = ? AND retired = 0", (question_id,)
    ).fetchone()
    if exists is None:
        return jsonify({"error": "Question not found."}), 404
    now = utc_now()
    database.execute(
        """INSERT INTO weaknesses (question_id, miss_count, last_score, pinned, updated_at)
           VALUES (?, 0, 0, 1, ?)
           ON CONFLICT(question_id) DO UPDATE SET pinned = 1, updated_at = excluded.updated_at""",
        (question_id, now),
    )
    database.commit()
    return jsonify({"saved": True})


@app.delete("/api/weakness/<int:question_id>")
def remove_weakness(question_id):
    database = get_db()
    database.execute("DELETE FROM weaknesses WHERE question_id = ?", (question_id,))
    database.commit()
    return jsonify({"removed": True})


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=int(os.environ.get("PORT", "5000")))