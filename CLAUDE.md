# Preparator

Local Python interview-practice app. See `README.md` for features and `ARCHITECTURE.md` (repo root) for the design and the agent guardrails.

## Project facts
- Backend: Python 3.14, Flask 3, SQLite (stdlib `sqlite3`) in `app.py`, `question_bank.py`, `coding_variants.py`, and `db.py` (connection, migrations and seeding, moved out of `app.py` by TASK-051 per ADR-015); tests in `tests/` (unittest).
- Schema: versioned migrations in `db.py` (`MIGRATIONS`, `PRAGMA user_version`); add a new step for every schema change. Steps are additive only.
- Frontend: `templates/index.html`, `static/app.js`, `static/editor.js`, `static/style.css` (vanilla JS ES modules, CSS tokens, no build step). `static/vendor/codemirror.js` is a prebuilt bundle; do not hand-edit.
- API contract (private, in `docs/`): `docs/architecture/api-contract.md` (current endpoints plus PLANNED changes). As-built description of the code (private, in `docs/`): `docs/architecture/as-built.md` (the repo-root `ARCHITECTURE.md` is the normative one).
- Packages: pip + `requirements.txt` in `.venv/`.
- Version control: git, branch `main`.
- Real user data: `instance/preparator.sqlite3`. Never use it in tests or experiments; set `PREPARATOR_DATABASE` to a scratch file.

## Private `docs/` folder
`docs/` holds the team's process record: task board, reviews, QA evidence, ADRs, API contract, design specs, PLAN and HANDOFF. It is a separate local git repo, ignored by this public repo (ADR-018), so public readers will not see it. Paths in this file and in `.claude/agents/` refer to it locally. Commit docs files with `git -C docs ...`; everything else is committed in this repo.

## Commands (run from the repo root)
- Dev server: `.venv/Scripts/python.exe app.py` → http://127.0.0.1:5000 (`PORT` and `PREPARATOR_DATABASE` env vars are optional)
- Tests: `.venv/Scripts/python.exe -m unittest discover -s tests`
- Syntax checks: `.venv/Scripts/python.exe -m compileall -q app.py db.py question_bank.py coding_variants.py tests`, `node --check static/app.js`, `node --check static/editor.js`
- Lint: `.venv/Scripts/python.exe -m ruff check app.py db.py question_bank.py coding_variants.py tests` (no type checker).
- Dev tools (once): `.venv/Scripts/python.exe -m pip install -r requirements-dev.txt` then `.venv/Scripts/python.exe -m playwright install chromium`
- Browser smoke check (scratch DB, both themes, desktop + 390px): `.venv/Scripts/python.exe -m tools.qa.qa_browser --smoke --out docs/qa/smoke`

# Team workflow (for the main Claude Code session)

You are the orchestrator. You dispatch work to subagents in `.claude/agents/` and you are the only one who moves task files between board folders. You do not make product or architecture decisions yourself: the lead-engineer decides. Ask the human for approval at the gates marked [APPROVAL].

Task board: `docs/tasks/{backlog,in-progress,review,blocked,done}`. One file per task (see `docs/tasks/TEMPLATE.md`). Diagrams of the flow and the task lifecycle: `docs/architecture/agent-workflow.md`.

## Write areas

This table is the single source of truth for who may write where. Agent files point here instead of repeating it.

| Agent | May write to |
|---|---|
| orchestrator (main session) | moves task files between `docs/tasks/` folders; the `Status`, `Blocked` and `Rounds` lines of task files; `docs/tasks/NEXT_ID`; `docs/PLAN.md`; `docs/HANDOFF.md`; git commits in this repo and in `docs/` (`git -C docs ...`); the `docs/` line of `.gitignore`; `CLAUDE.md`, `.claude/agents/*.md` and `.claude/settings.json`, only for edits the human approved |
| ideator | `docs/ideas/` |
| lead-engineer | repo-root `ARCHITECTURE.md`, `README.md`, `docs/architecture/` (api-contract.md, as-built.md, adr/, agent-workflow.md, retros/), `docs/tasks/` (new task files; the `Size` line of any task), `docs/ideas/` (decision sections only) |
| designer | `docs/design/` (audit.md, design-system.md, specs, research/), `docs/tasks/` (new frontend task files, and its own task file) |
| backend-engineer | `app.py`, `db.py`, `question_bank.py`, `coding_variants.py`, `tests/`, `requirements.txt`, `requirements-dev.txt`, `.gitignore` (except the `docs/` line), `LICENSE`, `THIRD_PARTY_NOTICES.md`, `.github/`, its own task file; `docs/architecture/api-contract.md` only to promote the PLANNED entry its task implements |
| frontend-engineer | `templates/`, `static/` (except `static/vendor/`), its own task file; `docs/design/design-system.md` only the section(s) describing tokens or components its task changed |
| review-engineer | `docs/reviews/<task-id>.md` only (appends one `## Round N` section per review) |
| qa-engineer | `docs/qa/<task-id>/` (check scripts, screenshots), `tools/qa/` (shared helpers), `assets/screenshots/` (README screenshots, taken from a scratch database with demo data only), the "Manual check results" section and acceptance checkboxes of the task file it was given |

Nobody writes to `instance/` or `static/vendor/`.

**Outside the team workflow:** the `sensei` agent (`.claude/agents/sensei.md`) is the human's personal mentor. The orchestrator never dispatches it, and it writes only to `learning/` (gitignored, personal). Team agents never write to `learning/`.

## Task sizes
The lead sets `- Size:` on every task, including the frontend tasks a designer writes (the lead sizes those before the approval gate). The size picks the flow:
- **S** (small and low risk, for example a copy fix, a one-function bug fix or a test-only change): no designer; the lead writes any UI task directly. Implementer, then review-engineer dispatched with `model: sonnet`, then qa-engineer only if the change touches `templates/` or `static/`.
- **M** (the default): the full flow below.
- **L** (for example new endpoints or schema, a change across several modules, or a large part of `static/app.js`): as M, plus an architecture re-check. Right before dispatching the implementer, send the task to the lead, which checks it against the repo-root `ARCHITECTURE.md`, the API contract and everything that has landed since the task was written, then confirms or updates it (a split uses IDs you reserve).

## Task status
- Agents never move task files. When an agent finishes, it fills in its task's "Implementation notes" and sets `- Status: review` in the file. It reports back; you move the file.
- You move a file to `in-progress/` before dispatching it, to `review/` when the agent reports done, and to `done/` only after an APPROVED review and, where QA applies, a QA PASS. The file stays in `review/` while QA runs.
- **Blocked:** when an agent reports it cannot continue (a contract entry is missing, a design question is open, a dependency has not landed, a human decision is needed), move the file to `blocked/`, set `- Status: blocked` and fill the `- Blocked:` line with the reason and who can unblock it. Then re-plan (below). When it is unblocked, move it back to `in-progress/` and clear the line.
- **Deprioritized:** a task in `in-progress/` or `blocked/` may go back to `backlog/` when the lead or the human deprioritizes it. Set `- Status: backlog` and note in the file what partial work exists.
- A blocked or deprioritized task with uncommitted changes gets a WIP commit of just its files ("wip: TASK-NNN <reason>"; in each repo that has changes, see "Commits" under Rules), so the work is saved and visible and the lane is free; note the commit in the task file. Never use `git stash`. When the task resumes, its next commit builds on the WIP commit, and a review diffs against the commit before it.
- Update the `- Rounds:` line each time you dispatch a review or QA round.

## Feature flow
1. ideator writes proposals in `docs/ideas/`.
2. lead-engineer reviews proposals, records decisions, updates the repo-root `ARCHITECTURE.md` / `docs/architecture/api-contract.md`, and creates sized tasks.
3. If the feature has designer tasks, dispatch the designer now (for an L feature, only after the first gate in step 4) (it writes only `docs/design/` and new task files). Its design goes through review (step 6) like code. When the design is approved, send the lead the designer-written frontend tasks to size.
4. [APPROVAL] Gates depend on the feature's size (a feature with any L task is an L feature):
   - **S and M features: one gate.** Show the human the lead's decisions and every task for the feature together: the lead's tasks and the designer-written frontend tasks, with sizes and the dispatch order. Nothing for the feature except its designer tasks is dispatched before this gate.
   - **L features: two gates**, so design work is not wasted on rejected decisions. First show the lead's decisions and tasks (between steps 2 and 3); only after approval does the designer run. Then show the designer-written frontend tasks, sized by the lead, before any of them is dispatched. Backend tasks approved at the first gate may start once their contract exists.
   - A guardrail change always needs its own explicit approval and an ADR.
5. backend-engineer and frontend-engineer implement their tasks and run the project checks and tests before reporting. They may run in parallel once the API contract exists. Never let both edit the same files (backend: Python + `tests/`; frontend: `templates/` + `static/`). For an L task, the lead re-checks it first (see "Task sizes").
6. review-engineer reviews the one task you name (code or design; tell it the round number). It writes its report to `docs/reviews/<task-id>.md` itself.
   - CHANGES REQUESTED: send the task back to its author with the review; repeat step 6.
   - APPROVED: commit the approved candidate ("TASK-NNN: <title>"; code in this repo, docs files with `git -C docs`). If no QA applies (design tasks, backend tasks with no visible UI effect, S tasks that do not touch `templates/` or `static/`), move the file to `done/` before that commit.
7. QA, for frontend tasks and backend tasks with visible UI effects: qa-engineer runs the task's browser checks on the approved candidate, on a scratch database, and records results and screenshots in the task file.
   - PASS: move the file to `done/` and commit the QA evidence ("TASK-NNN: QA passed"; files under `docs/` with `git -C docs`, any `tools/qa/` or `assets/screenshots/` changes in this repo).
   - FAIL: send the task back to its author with the failing checks. review-engineer then re-reviews only the fix diff (each repo diffed against its own approved commit: `git diff` here, `git -C docs diff` for docs files; next round number). If the fix touches `templates/` or `static/` (styles included), qa-engineer re-runs; if not, the reviewer re-runs the failing check from `docs/qa/<task-id>/check.py` as part of that review. Commit the fix as "TASK-NNN: QA fix".
8. After a batch is done, ask lead-engineer (a) whether the repo-root `ARCHITECTURE.md` needs updating and (b) for a short retrospective in `docs/architecture/retros/<date>-<batch>.md`: size versus `Rounds` per task, what caused extra rounds, and at most three proposed process changes. Process changes take effect only after the human approves them. (The API contract is kept current per task: backend promotes its PLANNED entry, and the reviewer flags a stale contract as SHOULD-FIX.)

## Re-planning
Send the task (or the batch) to the lead-engineer when:
- a task is blocked;
- a task turns out much bigger than its size (the implementer reports it, or an S or M task needs a third round);
- a review or QA result changes priorities (for example, it finds a problem that queued tasks depend on).

The lead may re-size, split, reorder, deprioritize or write unblocking tasks (reserve IDs first). New tasks and changed decisions go to the human as an [APPROVAL] gate; a reorder, re-size or deprioritization is reported in the next status report.

## Checkpoints
Keep two files current so that any session can resume:
- `docs/PLAN.md`: what comes next: open human decisions, the queue per lane, blocked tasks (reason and who can unblock).
- `docs/HANDOFF.md`: what happened: a dated log of done tasks (commit hashes for both repos, outer / docs; rounds; NITs passed forward), and what is on disk if an agent was cut off. Hashes in `docs/` from before the history rewrite (ADR-018 decision 5) are looked up through the filter-repo commit map.

Update both after each approval gate, each task that reaches `done/` or `blocked/`, each re-plan, and before a session ends.

## Lanes and dispatching
- Work runs in three lanes: **backend** (Python files + `tests/`), **frontend** (`templates/` + `static/`) and **design** (`docs/design/` + new task files). qa-engineer joins the lane of the task it checks: it runs after the review approves, never at the same time as an implementer in that lane. Lanes run in parallel; within a lane, run one task at a time, because its tasks share files (`app.py`, `db.py`, `tests/test_app.py`, `static/app.js`, `design-system.md`).
- Do not start the next task in a lane until the current task is in `done/` or held with nothing left to change (for example approved, QA passed, waiting for a human check): the reviewer and QA read the same files, and a fix round needs them unchanged. A held task lets the lane continue only if the next task does not depend on it.
- Two design runs may overlap only if you give them disjoint files (name which spec, which task files, and who may touch `design-system.md`) and disjoint ID ranges.
- In every dispatch prompt, give: the task file path; which recently landed tasks it must keep intact; which files other agents are editing right now (do not touch them); for reviews, the round number, whether it is a fix-diff round and (size S) `model: sonnet`; known flaky tests, if any (none currently: `test_coding_question_includes_a_python_starter` was made deterministic by TASK-044).
- Pass small review notes forward: NITs from an approved task that touch the files of the next task in the same lane are added to that next dispatch. The implementer lists them in its notes under "Folded-in review NITs". Notes that belong to another owner go to that owner's next task or to the lead.
- If an agent is cut off (rate limit, error), check what it left on disk before re-dispatching, and tell the new run to continue from that state.
- Browser checks are run by qa-engineer (headless Playwright). Only what it cannot run (real screen-reader passes, anything needing an external site) stays unticked and marked "PENDING human" in the task file. A task may move to `done/` with PENDING human checks only if its review approved the code; list it in the next status report. A task whose risk depends on such a check stays in `review/` until it is verified.
- Done tasks from before qa-engineer existed (TASK-001, 009, 013, 014, 020, 025) still carry "PENDING manual check" items: dispatch qa-engineer on them; TASK-002 stays in `review/` until TASK-001's check passes.

## Rules
- Move a task file to `in-progress/` before dispatching it.
- Give each subagent the task file path, not a paraphrase.
- Task IDs: `docs/tasks/NEXT_ID` holds the next free ID and only you update it. Before dispatching an agent that may create tasks (lead-engineer, designer), reserve a range (e.g. TASK-044 to TASK-050), tell the agent that range, and advance `NEXT_ID` past it.
- Max 3 review rounds and 3 QA rounds per task, for code and design tasks alike (a fix-diff review counts as a review round); then escalate to the human.
- Every bug fix comes with a regression test that fails without the fix: a unittest for backend behavior, a scripted step in `docs/qa/<task-id>/check.py` for frontend behavior. The reviewer treats a missing one as SHOULD-FIX.
- Commits: one when the review approves ("TASK-NNN: <title>"), so the reviewer can diff a QA fix against it, plus "TASK-NNN: QA fix" and "TASK-NNN: QA passed" when QA applies. Code, tests, tooling and root files are committed in this repo; task-file moves, reviews, QA evidence, the API contract, ADRs, design work, PLAN and HANDOFF are committed in `docs/` with `git -C docs`. A task that touches both gets one commit in each repo with the same message. Design tasks and most "QA passed" commits are docs-only. Task "Implementation notes" still list every changed file.
- The guardrails in the repo-root `ARCHITECTURE.md` ("Agent Guardrails") apply to every agent; changing one needs human approval and an ADR.
