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
- `tests/test_app.py` exercises API behavior with an isolated temporary SQLite database.
- `instance/preparator.sqlite3` is the local persistent database. Do not use it as a test database.
- `requirements.txt` lists the Python runtime dependency; `requirements-dev.txt` lists development-only tools (Playwright for the browser checks in `tools/qa/`). `.vscode/tasks.json` provides the local run task.

## Data Model

- `questions` stores prompts, topic, difficulty, mode, answer criteria, explanations, examples, optional starter code, and a `retired` flag. `init_db()` runs once per database file per process, on the first connection (ADR-003). In one transaction it applies pending schema migrations and then seeds: it inserts new prompts from `QUESTION_BANK` and refreshes criteria, explanation, solution, and starter code on existing rows (matched by topic, difficulty, mode, and prompt), so editing a prompt's text creates a new row while editing its content updates in place. Rows whose identity is no longer in the bank are marked `retired` (ADR-005): they are never served or listed, but they are kept so user history stays attached.
- `attempts` stores each submitted answer, rubric score, and timestamp.
- `weaknesses` tracks questions to revisit, including misses and user-pinned items.
- `saved_lessons` stores theory question IDs with a personal note, a `saved` flag, and a save timestamp. Unsaving a lesson clears the flag and keeps a non-empty note (ADR-004).

Schema changes go through the versioned migrations in `app.py` (`MIGRATIONS`, tracked in `PRAGMA user_version`, ADR-003). Steps are additive only: new tables, new columns with defaults, new indexes; they never rewrite or drop user data.

The question bank is currently the source of truth for lesson and interview content. Duplicate question rows from older development reloads are filtered by canonical prompt identity when selecting or listing questions.

## Client-side state

Browser `localStorage` holds volatile UI state only; SQLite holds all durable progress (attempts, weak spots, saved lessons and notes). Anything in `localStorage` may disappear when the user clears browser data, and the app must keep working when storage is unavailable (all access is best effort, errors ignored).

- Today: `preparator-theme` (light/dark) and `preparator-filters` (Practice filters).
- Planned (ADR-011, TASK-033): `preparator-draft:<question_id>` answer drafts.
- Planned (ADR-012): `preparator-open-question`, a pointer to the revealed but unsubmitted question so it can be resumed after a reload, through the search gate.

`localStorage` never holds solutions, explanations or criteria, and it is not part of the progress backup (ADR-010). Moving any of this into SQLite needs a write endpoint (ADR-002) and is only worth it if drafts must survive a browser data wipe.

## Main Flows

1. `GET /` serves the application shell.
2. Starting a question opens a Google search in a browser tab. The user confirms they reviewed it; `POST /api/question` checks the confirmation flag and allowed search host before returning one question. The server does not independently verify browser activity or search-result contents.
   An optional `question_id` serves that specific question (used by "Practice this one" in Weak spots); the search confirmation is still required.
3. `POST /api/answer` applies a keyword rubric, stores the attempt, updates the weakness queue, and returns matched/missing criteria, theory, and the example solution.
4. `GET /api/dashboard` returns totals, per-topic and topic × level averages, a daily trend (local dates), the practice streak, weak spots, and recent attempts.
5. `GET /api/theory` lists theory-mode questions as lessons. `POST` and `DELETE /api/theory/<id>` save or remove a lesson; saved notes are updated through the same `POST` endpoint.
6. `GET /api/theory/export.csv` exports saved lessons and notes as formula-neutralized CSV for import into Google Sheets. There is no OAuth or automatic spreadsheet sync.

## Local Development

```powershell
python app.py
python -m unittest discover -s tests
```

The default URL is `http://127.0.0.1:5000`. `PORT` changes the listen port; `PREPARATOR_DATABASE` changes the SQLite file path. The Flask development server is intended for local practice only. Debug mode (reloader and interactive debugger) is off unless `FLASK_DEBUG=1` is set (TASK-010); never enable it when anything other than you can reach the port.

## Agent Guardrails

- Preserve one-question-at-a-time behavior. Do not include a solution in the question response; reveal it only after answer submission.
- Keep source confirmation before question delivery. It is a user confirmation, not proof that a search was completed.
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

Status of step 1 (ADR-003): the versioned migration mechanism (`PRAGMA user_version`) is implemented inside `app.py` (TASK-007; schema version 3 after TASK-008 and TASK-012). Moving the database code into its own module was deferred until `app.py` passes about 600 lines; it is now about 630 lines, so the trigger is reached and the move is on the lead's open-items list. That move needs the agent ownership table in `CLAUDE.md` updated first.

## Architecture Decisions

Decisions are recorded in `docs/architecture/adr/`. Planned API changes are in `docs/architecture/api-contract.md` under "Planned changes".

| ADR | Title | Status |
|---|---|---|
| ADR-001 | Learn view exposes Theory answers before submission | Proposed (awaiting human approval) |
| ADR-002 | Protect the localhost API from cross-site requests and DNS rebinding | Accepted |
| ADR-003 | Safe one-time DB initialization and versioned schema migrations | Accepted |
| ADR-004 | Lesson notes survive "Remove from saved" | Accepted |
| ADR-005 | Retire question rows that are no longer in the bank | Accepted |
| ADR-006 | Python lint tooling, and how frontend fixes are verified | Accepted |
| ADR-007 | Practice flow product decisions | Accepted |
| ADR-008 | Spaced-repetition review schedule, separate from the weak-spot queue | Accepted (not yet implemented) |
| ADR-009 | Source confirmation once per mock-interview session | Proposed (awaiting human approval) |
| ADR-010 | Progress backup format and import validation rules | Accepted (not yet implemented) |
| ADR-011 | Answer drafts in localStorage; read-only, solution-free attempt history | Accepted (not yet implemented) |
| ADR-012 | Resume an unfinished question after reload, through the search gate | Accepted (not yet implemented; needs a design addendum) |