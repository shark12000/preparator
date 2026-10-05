# Preparator Architecture

## Overview

Preparator is a local, single-process Flask application. Flask serves one HTML page and JSON endpoints; browser JavaScript switches views and calls those endpoints. SQLite stores practice history, review items, and saved theory notes. There is no frontend build step, account system, LLM, or direct Google Sheets connection.

## Project Map

- `app.py` contains Flask configuration, SQLite setup, request handlers, rubric scoring, and CSV export.
- `question_bank.py` holds the hand-written prompts and appends the generated coding variants into `QUESTION_BANK`.
- `coding_variants.py` generates 312 deterministic coding prompts from 24 original problem types and varied sample inputs.
- `templates/index.html` defines the single-page shell and its Practice, Learn, Weak spots, and Progress views.
- `static/app.js` (ES module) owns view state, hash routing, keyboard shortcuts, API requests, and rendering of questions, lessons, weak spots, and progress charts (inline SVG).
- `static/editor.js` wraps CodeMirror for coding answers; `app.js` imports it lazily and falls back to a textarea if it fails.
- `static/vendor/codemirror.js` is a prebuilt CodeMirror 6 bundle (see README to rebuild). Do not edit by hand.
- `static/style.css` defines design tokens (colors, type scale) for light and dark themes, then components and responsive layouts. Use tokens rather than raw hex values.
- `tests/test_app.py` exercises API behavior with an isolated temporary SQLite database. `tests/test_bank_determinism.py` checks that bank identities do not depend on the hash seed, and `tests/bank_identities.json` (written by `tests/bank_identities.py`) pins the current identities (ADR-005 addendum).
- `instance/preparator.sqlite3` is the local persistent database. Do not use it as a test database.
- `requirements.txt` lists the Python runtime dependency; `requirements-dev.txt` lists development-only tools (Playwright for the browser checks in `tools/qa/`). `.vscode/tasks.json` provides the local run task.

## Data Model

- `questions` stores prompts, topic, difficulty, mode, answer criteria, explanations, examples, optional starter code, and a `retired` flag. `init_db()` runs once per database file per process, on the first connection (ADR-003). In one transaction it applies pending schema migrations and then seeds: it inserts new prompts from `QUESTION_BANK` and refreshes criteria, explanation, solution, and starter code on existing rows (matched by topic, difficulty, mode, and prompt), so editing a prompt's text creates a new row while editing its content updates in place. Rows whose identity is no longer in the bank are marked `retired` (ADR-005): they are never served for practice or listed in Learn or Weak spots, and not counted in the bank size, but they are kept so user history stays attached (their attempts still count in the progress aggregates, and saved lessons on them stay in the CSV export). Because the prompt is part of the identity, bank prompts must be byte-identical across processes, and a changed prompt retires its row with no merge migration (ADR-005 addendum).
  A rubric criterion is `{label, keywords}` with optional `related` terms (partial credit, half weight) and `alternatives` (`{label, keywords}`, full credit, shown as "Also valid") (ADR-017, TASK-067). These live in the `criteria` JSON, so they need no schema change.
- `attempts` stores each submitted answer, rubric score, and timestamp. The score is always the rubric's; nothing the user marks afterwards changes it.
- `rubric_overrides` (ADR-017, migration step 4, TASK-068) records "I covered this" per attempt and criterion (index plus a label snapshot). It is kept apart from the score, the weak queue and the aggregates, and exists to show the user's mark and to find rubrics that miss real answers.
- `weaknesses` tracks questions to revisit, including misses and user-pinned items.
- `review_schedule` (planned, ADR-008, migration step 5, TASK-083) holds one spaced-repetition row per answered question (`interval_days`, local `due_date`). It is separate from `weaknesses`: neither reads or writes the other.
- `saved_lessons` stores theory question IDs with a personal note, a `saved` flag, and a save timestamp. Unsaving a lesson clears the flag and keeps a non-empty note (ADR-004).

Schema changes go through the versioned migrations in `app.py` (`MIGRATIONS`, tracked in `PRAGMA user_version`, ADR-003). Steps are additive only: new tables, new columns with defaults, new indexes; they never rewrite or drop user data. A database whose version is newer than the code is refused rather than used (ADR-014, TASK-050): `python app.py` exits with a message, and other runners fail every database route with the generic 500 and write nothing.

Progress backup (ADR-010, planned: TASK-086 export, TASK-087 import) is a JSON file that refers to questions by identity, never by row id. Import is the only path where outside data enters the database, so it is validated all-or-nothing and merges without deleting.

The question bank is currently the source of truth for lesson and interview content. Duplicate question rows from older development reloads are filtered by canonical prompt identity when selecting or listing questions.

## Client-side state

Browser `localStorage` holds volatile UI state only; SQLite holds all durable progress (attempts, weak spots, saved lessons and notes). Anything in `localStorage` may disappear when the user clears browser data, and the app must keep working when storage is unavailable (all access is best effort, errors ignored).

- Today: `preparator-theme` (light/dark) and `preparator-filters` (Practice filters).
- Planned (ADR-011, TASK-033): `preparator-draft:<question_id>` answer drafts.
- Planned (ADR-012, amended by ADR-016; design TASK-093): `preparator-open-question`, a pointer to the revealed but unsubmitted question so it can be resumed after a reload with one click (a targeted question request; no search step).

`localStorage` never holds solutions, explanations or criteria, and it is not part of the progress backup (ADR-010). Moving any of this into SQLite needs a write endpoint (ADR-002) and is only worth it if drafts must survive a browser data wipe.

## Main Flows

1. `GET /` serves the application shell.
2. Practice opens on an intro with the filters and one primary button; pressing it serves the question (nothing is requested on page load; ADR-016 decision 7). `POST /api/question` returns one question chosen by the filters (least practiced first), or the weak-spot queue in review mode. An optional `question_id` serves that specific question (used by "Practice this one" in Weak spots). There is no search or confirmation step (ADR-016); legacy `source_confirmed`, `source_url` and `search_query` fields are ignored if sent.
   Status: implemented (server TASK-061, intro TASK-063). Planned: `due_only` serves questions due for review today, with no fallback when none are due (ADR-008, PLANNED-17, TASK-084).
3. `POST /api/answer` applies a keyword rubric, stores the attempt, updates the weakness queue, and returns per-concept states (covered, partly covered, not detected; no "wrong" state) with matched terms, the attempt id, `previous_score`, theory, and the example solution (ADR-017, TASK-067). `POST`/`DELETE /api/attempts/<id>/overrides` record "I covered this" without changing the score (TASK-068). The feedback UI for concept states and overrides is TASK-075 to 077. Planned: `schedule` (next review date) in the response (PLANNED-16, TASK-083).
4. `GET /api/dashboard` returns totals, per-topic and topic × level averages, a daily trend (local dates), the practice streak, weak spots, and recent attempts.
5. `GET /api/theory` lists theory-mode questions as lessons. `POST` and `DELETE /api/theory/<id>` save or remove a lesson; saved notes are updated through the same `POST` endpoint. Planned (ADR-001 option A, accepted 2026-10-05; PLANNED-8, TASK-004 to 006): a lesson's explanation, model answer and key points stay locked until its question has at least one attempt.
6. `GET /api/theory/export.csv` exports saved lessons and notes as formula-neutralized CSV for import into Google Sheets. There is no OAuth or automatic spreadsheet sync.
7. Planned: `GET /api/questions/<id>/attempts` returns the user's own earlier answers to one question, never the solution (ADR-011, PLANNED-18, TASK-089). `GET /api/backup.json` and `POST /api/backup/import` back up and merge all progress (ADR-010, PLANNED-19/20, TASK-086/087).

## Local Development

```powershell
python app.py
python -m unittest discover -s tests
```

The default URL is `http://127.0.0.1:5000`. `PORT` changes the listen port; `PREPARATOR_DATABASE` changes the SQLite file path. The Flask development server is intended for local practice only. Debug mode (reloader and interactive debugger) is off unless `FLASK_DEBUG=1` is set (TASK-010); never enable it when anything other than you can reach the port.

## Agent Guardrails

- Preserve one-question-at-a-time behavior. Do not include a solution in the question response; reveal it only after answer submission.
- The practice flow has no search or source-confirmation step before a question (human decision 2026-10-04, ADR-016). This replaces the former guardrail "Keep source confirmation before question delivery" (removed from the code by TASK-061 and TASK-063).
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

Status of step 1 (ADR-003): the versioned migration mechanism (`PRAGMA user_version`) is implemented inside `app.py` (TASK-007; schema version 4 after TASK-008, TASK-012 and TASK-068). Moving the database code into its own module was deferred until `app.py` passes about 600 lines; it is now about 800. ADR-015 decides the move: connection, migration and seeding code goes to a new `db.py`, behavior unchanged (TASK-051; unblocked 2026-10-05, `db.py` is in the `CLAUDE.md` write areas). Every new schema step (5 onward) and the review-schedule replay go into `db.py`, so TASK-051 runs before TASK-083.

Step 2 was to be revisited when the backup import was designed. Decision 2026-10-05: not yet. The import (TASK-087) is one handler plus a validator and a merge function in `app.py`; splitting services for it alone adds structure before there is a second consumer. Revisit step 2 when `app.py` passes about 1,000 lines after TASK-051 and the backup tasks, or when a second feature needs the same merge or validation code. Step 3 is not started.

## Architecture Decisions

Decisions are recorded in `docs/architecture/adr/`. Planned API changes are in `docs/architecture/api-contract.md` under "Planned changes".

| ADR | Title | Status |
|---|---|---|
| ADR-001 | Learn view exposes Theory answers before submission | Accepted, option A: lock until the first attempt (human decision 2026-10-05; not yet implemented: TASK-004, 005, 006) |
| ADR-002 | Protect the localhost API from cross-site requests and DNS rebinding | Accepted |
| ADR-003 | Safe one-time DB initialization and versioned schema migrations | Accepted |
| ADR-004 | Lesson notes survive "Remove from saved" | Accepted |
| ADR-005 | Retire question rows that are no longer in the bank | Accepted |
| ADR-006 | Python lint tooling, and how frontend fixes are verified | Accepted |
| ADR-007 | Practice flow product decisions | Accepted (decisions 1 and 6 superseded, decision 4 reworded by ADR-016) |
| ADR-008 | Spaced-repetition review schedule, separate from the weak-spot queue | Accepted (not yet implemented: TASK-083, 084 backend, TASK-085 design) |
| ADR-009 | Source confirmation once per mock-interview session | Superseded by ADR-016 |
| ADR-010 | Progress backup format and import validation rules | Accepted, amended 2026-10-05 (self-assessments included; not yet implemented: TASK-086, 087 backend, TASK-088 design) |
| ADR-011 | Answer drafts in localStorage; read-only, solution-free attempt history | Accepted (`previous_score` done by TASK-049; not yet implemented: drafts TASK-033, history TASK-089, 090, 091) |
| ADR-012 | Resume an unfinished question after reload, through the search gate | Accepted, amended by ADR-016 (resume is one click, no search; not yet implemented: design TASK-093, after TASK-033) |
| ADR-013 | Open items from the Learn and Practice designs (notes, weak-spot removal, export, copy) | Accepted (decisions 7 and 9 implemented by TASK-050 and TASK-049; the frontend items are in the Learn and Practice task backlog) |
| ADR-014 | Refuse to open a database whose schema is newer than the code | Accepted (implemented by TASK-050) |
| ADR-015 | Move the database code out of `app.py` into `db.py` | Accepted (not yet implemented; TASK-051, unblocked 2026-10-05) |
| ADR-016 | Remove the search and source-confirmation step before a question | Accepted (human approval 2026-10-04; changes a guardrail; implemented by TASK-061 and TASK-063; TASK-064 to 066 refine the flow) |
| ADR-017 | Graded rubric feedback (partial matches, accepted alternatives) and recorded self-assessment | Accepted (no guardrail change; backend implemented by TASK-067, 068, 069; design TASK-070; frontend TASK-075 to 077 and the rubric fixes in TASK-092 not yet done) |

Notes: ADR-008 (2026-10-05) gives the review schedule migration step 5 in `db.py`, replays by `created_at` then `id`, and moves `WEAK_SCORE_THRESHOLD` to `db.py`. ADR-010 (2026-10-05) adds self-assessments to backup format 1. ADR-011 (2026-10-05) keeps history solution-free after ADR-001. ADR-002 and ADR-005 carry 2026-10-04 clarifications (the `[::1]` rationale; the determinism addendum). ADR-001, ADR-007, ADR-009, ADR-011 and ADR-012 carry 2026-10-04 notes pointing to ADR-016.