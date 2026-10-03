# Preparator

Local Python interview-practice app. See `README.md` for features and `ARCHITECTURE.md` for the design and the agent guardrails.

## Project facts
- Backend: Python 3.14, Flask 3, SQLite (stdlib `sqlite3`) in `app.py`, `question_bank.py`, `coding_variants.py`; tests in `tests/` (unittest).
- Frontend: `templates/index.html`, `static/app.js`, `static/editor.js`, `static/style.css` (vanilla JS ES modules, CSS tokens, no build step). `static/vendor/codemirror.js` is a prebuilt bundle; do not hand-edit.
- Packages: pip + `requirements.txt` in `.venv/`.
- Real user data: `instance/preparator.sqlite3`. Never use it in tests or experiments; set `PREPARATOR_DATABASE` to a scratch file.

## Commands (run from the repo root)
- Dev server: `.venv/Scripts/python.exe app.py` → http://127.0.0.1:5000 (`PORT` and `PREPARATOR_DATABASE` env vars are optional)
- Tests: `.venv/Scripts/python.exe -m unittest discover -s tests`
- Syntax checks: `.venv/Scripts/python.exe -m compileall -q app.py question_bank.py coding_variants.py tests`, `node --check static/app.js`, `node --check static/editor.js`
- Lint / typecheck: none configured yet.

# Team workflow (for the main Claude Code session)

You are the orchestrator. You dispatch work to subagents in `.claude/agents/` and move tasks
between folders. You do not make product or architecture decisions yourself: the
lead-engineer decides. Ask the human for approval at the gates marked [APPROVAL].

Task board: `docs/tasks/{backlog,in-progress,review,done}`. One file per task (see `docs/tasks/TEMPLATE.md`).

Agents and what they may edit:
| Agent | Writes to |
|---|---|
| ideator | `docs/ideas/` |
| lead-engineer | `ARCHITECTURE.md` (repo root), `docs/architecture/` (api-contract.md, adr/), `docs/tasks/` |
| designer | `docs/design/` (audit.md, design-system.md, research/), `docs/tasks/` |
| backend-engineer | `app.py`, `question_bank.py`, `coding_variants.py`, `tests/`, `requirements.txt` |
| frontend-engineer | `templates/`, `static/` (except `static/vendor/`) |
| review-engineer | nothing (reports only; you save its output) |

## Feature flow
1. ideator writes proposals in `docs/ideas/`.
2. lead-engineer reviews proposals, records decisions, updates `ARCHITECTURE.md` / `docs/architecture/api-contract.md`,
   creates tasks. [APPROVAL: show the human the decisions and task list]
3. designer handles owner=designer tasks and writes owner=frontend tasks.
4. backend-engineer and frontend-engineer implement their tasks. They may run in parallel
   once the API contract exists. Never let both edit the same files (backend: Python + `tests/`; frontend: `templates/` + `static/`).
5. review-engineer reviews everything in `docs/tasks/review/`. Save its output to `docs/reviews/<task-id>.md`.
   - CHANGES REQUESTED: send the task back to its author with the review; repeat step 5.
   - APPROVED: move the task to `done/`.
6. After a batch is done, ask lead-engineer whether `ARCHITECTURE.md` needs updating.

## Rules
- Move a task file to `in-progress/` before dispatching it.
- Give each subagent the task file path, not a paraphrase.
- Max 3 review rounds per task; then escalate to the human.
- Commit after each approved task. The project is not a git repo yet: until the human runs `git init`, skip commits and make sure the task's "Implementation notes" list every changed file, because the reviewer has no diff.
- The guardrails in `ARCHITECTURE.md` ("Agent Guardrails") apply to every agent; changing one needs human approval and an ADR.
