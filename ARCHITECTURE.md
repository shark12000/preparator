# Preparator Architecture

This is the normative design document: what the system is, how it is divided, and the rules every change must keep. It is deliberately high level. The reasoning behind these rules is kept in architecture decision records in the team's private process record, which is not part of this repository; the rule stated here is the one that applies.

## Overview

Preparator is a local, single-user, single-process Flask application. Flask serves one HTML page and a small JSON API; browser JavaScript switches views and calls those endpoints. SQLite stores practice history, review items and saved theory notes. It runs on localhost only. There is no frontend build step, account system, LLM, or direct Google Sheets connection.

## Stack

- Python 3.14, Flask 3 (exact pins in `requirements.txt`), SQLite through the standard-library `sqlite3` module.
- Vanilla JavaScript ES modules and plain CSS with design tokens. A prebuilt CodeMirror 6 bundle is vendored; nothing is compiled at install or run time.
- Tests: `unittest`. Lint: ruff, default rule set, no config file. JavaScript is checked with `node --check`. There is no type checker.

## Project Map

- `app.py`: the web side. Flask configuration, the localhost guard and error handler, request handlers (HTTP validation and responses), rubric scoring, question selection, the practice streak and the CSV export. It reaches the database only through `db` (`import db` and qualified names such as `db.get_db()`).
- `db.py`: the database side. Connection lifecycle, versioned schema migrations, one-time initialization and seeding from the question bank, and the shared SQL predicates for canonical and active questions. It never imports `app`. Tests patch database names on `db`, never on `app`.
- `question_bank.py`: the hand-written prompts, extended with the generated coding variants into `QUESTION_BANK`, the single content source.
- `coding_variants.py`: 312 deterministic coding prompts generated from 24 problem types.
- `templates/index.html`: the single-page shell with the Practice, Learn, Weak spots and Progress views.
- `static/app.js`: view state, hash routing, keyboard shortcuts, API requests, and rendering (including inline-SVG progress charts).
- `static/editor.js`: a thin CodeMirror wrapper; `app.js` loads it lazily and falls back to a textarea if it fails.
- `static/vendor/codemirror.js`: the prebuilt CodeMirror bundle. Never edited by hand.
- `tools/editor-bundle/`: the recipe that builds the CodeMirror bundle (`entry.js`, `package.json` with pinned versions, rebuild notes). Development only; nothing in it runs with the app.
- `static/style.css`: light and dark design tokens, then components and responsive layouts. Components use tokens, not raw colors.
- `tests/`: API and behavior tests, each on its own temporary SQLite database; rubric tests; bank-determinism tests and a committed baseline of question identities.
- `tools/qa/`: headless-browser check helpers (Playwright) used during development; the app does not import them.
- `assets/screenshots/`: the README screenshots, taken from a scratch database that holds demo data only.
- `.github/workflows/ci.yml`: lint, syntax checks and the test suite on Linux and Windows, on every push and pull request, with a temporary database.
- `requirements.txt` (exact runtime pins) and `requirements-dev.txt` (the runtime pins plus pinned ruff and Playwright).
- `CLAUDE.md` and `.claude/agents/`: the AI-agent team setup that builds the project. The Agent Guardrails below apply to it.
- `instance/preparator.sqlite3`: the user's local database. Not in the repository, and never used by tests.

## Data Model

- `questions` holds the content copied from `QUESTION_BANK`: prompt, topic, difficulty, mode, rubric criteria, explanation, solution, optional starter code, and a `retired` flag.
  - A question's identity is (topic, difficulty, mode, prompt). Seeding inserts new identities and refreshes the content of existing ones in place, so editing a prompt's text creates a new row while editing its rubric or explanation does not.
  - Rows whose identity left the bank are marked retired, never deleted: they are not served, listed or counted, but the user's history on them is kept.
  - Selection and listing filter out retired rows and old duplicate rows (identical identities left by earlier seeding) through the shared canonical and active predicates in `db.py`.
  - Because the prompt is part of the identity, bank prompts must be byte-identical across processes (no hash-order dependence).
  - A rubric criterion is `{label, keywords}` with optional `related` terms (half credit) and `alternatives` (full credit). These live in the criteria JSON and need no schema change.
- `attempts` stores each submitted answer, its rubric score and a timestamp. The score is always the rubric's.
- `rubric_overrides` records the user's "I covered this" marks per attempt and criterion. It is kept apart from the score, the weak-spot queue and the aggregates.
- `weaknesses` is the queue of questions to revisit: misses and user-pinned items.
- `saved_lessons` stores saved theory lessons with a personal note. Unsaving keeps a non-empty note.
- Planned: a `review_schedule` table for spaced repetition (one row per answered question), separate from `weaknesses`; neither reads or writes the other.

Rules for every schema change:
- Changes go through the versioned migrations in `db.py` (tracked in `PRAGMA user_version`). Steps are additive only: new tables, new columns with defaults, new indexes. They never rewrite or drop user data.
- Migrations and seeding run once per database file per process, in one transaction.
- A database whose schema is newer than the code is refused, not used: `python app.py` exits with a message, and other runners fail every database route with a generic 500 and write nothing.

Planned progress backup: a JSON file that refers to questions by identity, never by row id. Import is the only path where outside data enters the database, so it is validated all-or-nothing and merges without deleting.

## Client-side state

Browser `localStorage` holds volatile UI state only; SQLite holds all durable progress. Anything in `localStorage` may disappear when the user clears browser data, and the app must keep working when storage is unavailable (all access is best effort, errors ignored).

- Today: `preparator-theme` (light or dark) and `preparator-filters` (Practice filters).
- Planned: per-question answer drafts, and a pointer to a revealed but unsubmitted question so it can be resumed after a reload.

`localStorage` never holds solutions, explanations or criteria, and it is not part of the progress backup. Moving any of it into SQLite needs a write endpoint behind the localhost guard.

## Boundaries

- **Network.** The server binds to 127.0.0.1 and makes no outbound calls. A `before_request` guard rejects foreign `Host` headers on every route (DNS rebinding), and cross-origin writes and non-JSON POSTs under `/api/`. There are no sessions, cookies or CSRF tokens. The browser loads web fonts from Google Fonts; nothing else leaves the machine.
- **Errors.** Every `/api/` error is a JSON `{"error": "..."}` with a fixed message; tracebacks are logged, never sent.
- **Solutions.** The question response never contains the solution, explanation or criteria; they are returned only after an answer is submitted. A theory lesson's answer content stays locked, in Learn and in the CSV export, until its question has at least one attempt.
- **Submitted code** is stored as text and never executed.
- **Exports.** The CSV export neutralizes formula-like cells. Spreadsheet use is by file import; there are no credentials in the app.
- **Modules.** `db.py` does not import `app`. Frontend files never call SQLite or Python directly; they use the JSON API. Content changes go through `question_bank.py` / `coding_variants.py`, never through the database.

## Main Flows

1. `GET /` serves the application shell.
2. Practice opens on an intro with the filters and one primary button; pressing it requests a question (nothing is requested on page load). `POST /api/question` returns one question chosen by the filters (least practiced first), or from the weak-spot queue in review mode, or a specific question by `question_id`. There is no search or confirmation step. Planned: a "due today" mode driven by the review schedule.
3. `POST /api/answer` applies the keyword rubric, stores the attempt, updates the weak-spot queue, and returns per-concept states (covered, partly covered, not detected; no "wrong" state), the previous score, the theory and the example solution. The attempt-override endpoints record "I covered this" without changing the score.
4. `GET /api/dashboard` returns totals, per-topic and topic-by-level averages, a daily trend in local dates, the practice streak, weak spots and recent attempts.
5. `GET /api/theory` lists theory questions as lessons; `POST` and `DELETE /api/theory/<id>` save or remove a lesson and update its note.
6. `GET /api/theory/export.csv` exports saved lessons and notes as formula-neutralized CSV for import into Google Sheets.
7. Planned: a read-only history of the user's own earlier answers to one question (never the solution), and progress backup export and merge-import.

## Local Development

```powershell
python app.py
python -m unittest discover -s tests
python -m ruff check app.py db.py question_bank.py coding_variants.py tests
```

Install with `pip install -r requirements.txt` (runtime) or `pip install -r requirements-dev.txt` (runtime plus ruff and Playwright). Pins are exact; update them together and run the tests. ruff must exit 0; a finding is fixed, or suppressed inline with `# noqa: <code>` plus a short reason when the fix would change behavior. CI runs the same lint, syntax and test commands.

The default URL is `http://127.0.0.1:5000`. Environment variables: `PORT` changes the listen port; `PREPARATOR_DATABASE` changes the SQLite file path (tests and experiments must point it at a scratch file); `FLASK_DEBUG=1` turns on the reloader and interactive debugger, which are off otherwise. The Flask development server is intended for local practice only; never enable debug mode when anything other than you can reach the port.

## Agent Guardrails

- Preserve one-question-at-a-time behavior. Do not include a solution in the question response; reveal it only after answer submission.
- The practice flow has no search or source-confirmation step before a question (human decision 2026-10-04). This replaces the former guardrail "Keep source confirmation before question delivery", which has been removed from the code.
- Keep rubric scoring labeled as heuristic; it is not semantic or AI grading.
- Coding prompts provide a textarea starter and accept submitted source as text. Submitted Python is not executed by the app.
- Test database behavior with temporary databases. Avoid mutating `instance/preparator.sqlite3` in tests.
- CSV exports may be opened in spreadsheets: continue neutralizing formula-like cell values.
- Do not commit API keys, OAuth tokens, or spreadsheet credentials. Direct Google Sheets sync would need an explicit, user-configured authorization design.

## Recommended Evolution

Keep the current structure while the app remains small. As features grow, refactor in small steps:

1. Move SQLite connection/schema functions into a database module and add a versioned migration mechanism before further schema changes.
2. Separate interview, theory, and export operations into small services; keep Flask route handlers focused on HTTP validation and responses.
3. Move API groups into Flask blueprints and introduce an application factory when multiple configurations or deployments are needed.
4. Add direct Sheets sync only behind a dedicated integration boundary with explicit authorization; retain CSV export as a credential-free fallback.
5. Add authentication, CSRF protection, and a production WSGI server before exposing the app beyond localhost.

Status:
- Step 1 is **done**: versioned migrations exist, and the connection, migration and seeding code lives in `db.py` (`app.py` about 600 lines, `db.py` about 220). Every new schema step goes into `db.py`.
- Step 2 is **not yet**: planned features such as the backup import are one handler plus a validator and a merge function, and a service layer for one consumer adds structure too early. Revisit when `app.py` passes about 1,000 lines, or when a second feature needs the same merge or validation code.
- Step 3 is not started. Publishing the source code does not change the deployment model: the app is still local and single-user, so steps 3 and 5 remain unneeded until it must run anywhere other than the user's own machine.
