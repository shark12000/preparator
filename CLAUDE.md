# Preparator

Local Python interview-practice app. See `README.md` for features and `ARCHITECTURE.md` (repo root) for the design and the agent guardrails.

## Project facts
- Backend: Python 3.14, Flask 3, SQLite (stdlib `sqlite3`) in `app.py`, `question_bank.py`, `coding_variants.py`; tests in `tests/` (unittest).
- Schema: versioned migrations in `app.py` (`MIGRATIONS`, `PRAGMA user_version`); add a new step for every schema change. Steps are additive only.
- Frontend: `templates/index.html`, `static/app.js`, `static/editor.js`, `static/style.css` (vanilla JS ES modules, CSS tokens, no build step). `static/vendor/codemirror.js` is a prebuilt bundle; do not hand-edit.
- API contract: `docs/architecture/api-contract.md` (current endpoints plus PLANNED changes). As-built description of the code: `docs/architecture/as-built.md` (the repo-root `ARCHITECTURE.md` is the normative one).
- Packages: pip + `requirements.txt` in `.venv/`.
- Version control: git, branch `main`.
- Real user data: `instance/preparator.sqlite3`. Never use it in tests or experiments; set `PREPARATOR_DATABASE` to a scratch file.

## Commands (run from the repo root)
- Dev server: `.venv/Scripts/python.exe app.py` → http://127.0.0.1:5000 (`PORT` and `PREPARATOR_DATABASE` env vars are optional)
- Tests: `.venv/Scripts/python.exe -m unittest discover -s tests`
- Syntax checks: `.venv/Scripts/python.exe -m compileall -q app.py question_bank.py coding_variants.py tests`, `node --check static/app.js`, `node --check static/editor.js`
- Lint / typecheck: none configured yet.

# Team workflow (for the main Claude Code session)

You are the orchestrator. You dispatch work to subagents in `.claude/agents/` and you are the only one who moves task files between board folders. You do not make product or architecture decisions yourself: the lead-engineer decides. Ask the human for approval at the gates marked [APPROVAL].

Task board: `docs/tasks/{backlog,in-progress,review,done}`. One file per task (see `docs/tasks/TEMPLATE.md`).

## Write areas

This table is the single source of truth for who may write where. Agent files point here instead of repeating it.

| Agent | May write to |
|---|---|
| orchestrator (main session) | moves task files between `docs/tasks/` folders; `docs/tasks/NEXT_ID`; `docs/HANDOFF.md`; git commits |
| ideator | `docs/ideas/` |
| lead-engineer | `ARCHITECTURE.md` (repo root), `README.md`, `docs/architecture/` (api-contract.md, as-built.md, adr/, agent-workflow.md), `docs/tasks/` (new task files), `docs/ideas/` (decision sections only) |
| designer | `docs/design/` (audit.md, design-system.md, specs, research/), `docs/tasks/` (new frontend task files, and its own task file) |
| backend-engineer | `app.py`, `question_bank.py`, `coding_variants.py`, `tests/`, `requirements.txt`, its own task file; `docs/architecture/api-contract.md` only to promote the PLANNED entry its task implements |
| frontend-engineer | `templates/`, `static/` (except `static/vendor/`), its own task file; `docs/design/design-system.md` only the section(s) describing tokens or components its task changed |
| review-engineer | `docs/reviews/<task-id>.md` only (appends one `## Round N` section per review) |

Nobody writes to `instance/` or `static/vendor/`.

## Task status
- Agents never move task files. When an agent finishes, it fills in its task's "Implementation notes" and sets `- Status: review` in the file. It reports back; you move the file.
- You move a file to `in-progress/` before dispatching it, to `review/` when the agent reports done, and to `done/` only after an APPROVED review.

## Feature flow
1. ideator writes proposals in `docs/ideas/`.
2. lead-engineer reviews proposals, records decisions, updates `ARCHITECTURE.md` / `docs/architecture/api-contract.md`,
   creates tasks. [APPROVAL: show the human the decisions and task list]
3. designer handles owner=designer tasks and writes owner=frontend tasks. The design itself goes through review (step 5)
   like code. [APPROVAL: show the human the frontend tasks the designer wrote before dispatching any of them]
4. backend-engineer and frontend-engineer implement their tasks. They may run in parallel
   once the API contract exists. Never let both edit the same files (backend: Python + `tests/`; frontend: `templates/` + `static/`).
5. review-engineer reviews the one task you name (code or design; tell it the round number). It writes its report to `docs/reviews/<task-id>.md` itself.
   - CHANGES REQUESTED: send the task back to its author with the review; repeat step 5.
   - APPROVED: move the task to `done/` and commit.
6. After a batch is done, ask lead-engineer whether `ARCHITECTURE.md` needs updating. (The API contract is kept current per task: backend promotes its PLANNED entry, and the reviewer flags a stale contract as SHOULD-FIX.)

## Lanes and dispatching
- Work runs in three lanes: **backend** (Python files + `tests/`), **frontend** (`templates/` + `static/`) and **design** (`docs/design/` + new task files). Lanes run in parallel; within a lane, run one task at a time, because its tasks share files (`app.py`, `tests/test_app.py`, `static/app.js`, `design-system.md`).
- Do not start the next task in a lane until the current task's review verdict is in: the reviewer reads the same files, and a changes-requested round needs them unchanged. While a task is held (for example approved but waiting for a human check), the lane may continue if the next task does not depend on it.
- Two design runs may overlap only if you give them disjoint files (name which spec, which task files, and who may touch `design-system.md`) and disjoint ID ranges.
- In every dispatch prompt, give: the task file path; which recently landed tasks it must keep intact; which files other agents are editing right now (do not touch them); for reviews, the round number; known flaky tests (currently `test_coding_question_includes_a_python_starter`, about 1 run in 27: re-run, do not count it).
- Pass small review notes forward: NITs from an approved task that touch the files of the next task in the same lane are added to that next dispatch. The implementer lists them in its notes under "Folded-in review NITs". Notes that belong to another owner go to that owner's next task or to the lead.
- If an agent is cut off (rate limit, error), check what it left on disk before re-dispatching, and tell the new run to continue from that state.
- Browser and screen-reader checks that no agent ran stay unticked and are marked "PENDING manual check" in the task file. A task may move to `done/` with PENDING checks only if its review approved the code; list it in the next status report. A task whose risk depends on such a check (for example TASK-002) stays in `review/` until the human runs it.

## Rules
- Move a task file to `in-progress/` before dispatching it.
- Give each subagent the task file path, not a paraphrase.
- Task IDs: `docs/tasks/NEXT_ID` holds the next free ID and only you update it. Before dispatching an agent that may create tasks (lead-engineer, designer), reserve a range (e.g. TASK-044 to TASK-050), tell the agent that range, and advance `NEXT_ID` past it.
- Max 3 review rounds per task, for code and design tasks alike; then escalate to the human.
- Commit after each approved task (one commit per task, message "TASK-NNN: <title>"), so reviewers can use `git diff`. Task "Implementation notes" still list every changed file.
- The guardrails in `ARCHITECTURE.md` ("Agent Guardrails") apply to every agent; changing one needs human approval and an ADR.
