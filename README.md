# Preparator

[![CI](https://github.com/shark12000/preparator/actions/workflows/ci.yml/badge.svg)](https://github.com/shark12000/preparator/actions/workflows/ci.yml)

Preparator is a local web app for practicing Python interview questions. It is for developers preparing for Python interviews who want to answer one question at a time, get transparent feedback, and come back to what they missed. It runs on your own computer, with no account, and keeps your progress in a local SQLite file.

<table>
  <tr>
    <td valign="top"><img src="assets/screenshots/practice-coding-light.png" alt="Practice view, light theme: a coding question with a Python answer in the code editor" width="100%"></td>
    <td valign="top"><img src="assets/screenshots/feedback-dark.png" alt="Feedback after submitting a coding answer, dark theme: rubric score, concepts marked Covered or Not mentioned, the explanation, and your code next to the model solution" width="100%"></td>
  </tr>
  <tr>
    <td valign="top"><img src="assets/screenshots/learn-light.png" alt="Learn view, light theme: a theory lesson with a personal note" width="100%"></td>
    <td valign="top"><img src="assets/screenshots/progress-dark.png" alt="Progress view, dark theme: totals, average match by day, topic by level grid, recent attempts" width="100%"></td>
  </tr>
</table>
<p align="center"><img src="assets/screenshots/practice-mobile-light.png" alt="Practice view on a 390px-wide phone screen, light theme" width="260"></p>

*Screenshots show demo data from a scratch database, not real practice history.*

## Features

- **Practice**: pick a topic, level and format (Theory or Coding), then answer one question at a time. The bank has the hand-written prompts plus 312 generated coding variants from 24 problem types, balanced across Foundations, Intermediate and Advanced.
- **Code editor**: coding questions open in a CodeMirror editor with Python highlighting, line numbers and auto-indent, and fall back to a plain text box if it cannot load. Submitted code is stored as text and never executed.
- **Transparent feedback**: a visible keyword rubric scores the answer out of 10 and lists each concept as "Covered" or "Not mentioned" (related terms earn half credit in the score), then shows the explanation and the model answer. Lines copied unchanged from the starter stub earn no credit. The rubric is a heuristic, not semantic or AI grading.
- **Weak spots**: missed questions, and any you save for review, go into a queue you can practice again.
- **Learn**: theory questions double as short lessons with personal notes. A lesson's explanation and example are sent to the browser only after you have answered that question once in Practice. **Export CSV** downloads your saved lessons and notes for import into Google Sheets (formula-like cells are neutralized), so the app never needs Google credentials.
- **Progress**: totals, a daily trend, a topic-by-level grid and your practice streak (days use your computer's time zone).
- **Interface**: light and dark themes, a phone layout, linkable views (`/#practice`, `/#learn`, `/#weaknesses`, `/#progress`) and keyboard shortcuts (`Ctrl+Enter` submit, `N` next, `S` save for review, `1`-`4` switch views, `?` list shortcuts).

**Privacy**: everything stays on your computer. The server listens on 127.0.0.1 only and makes no outbound calls; the page loads its web fonts from Google Fonts, and nothing else leaves the machine. Progress lives in `instance/preparator.sqlite3`; delete that file to reset.

## Tech stack

- Python 3.14, Flask 3, SQLite through the standard-library `sqlite3` module
- Vanilla JavaScript ES modules, plain CSS with design tokens, a vendored CodeMirror 6 bundle (no build step)
- `unittest`, ruff, and GitHub Actions CI on Linux and Windows; Playwright for headless browser checks during development

## Setup

You need Python 3.14 (and Node.js only if you want to run the JavaScript syntax checks).

Windows (PowerShell):

```powershell
git clone <repo-url> preparator; cd preparator
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

Linux and macOS:

```bash
git clone <repo-url> preparator && cd preparator
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

Then open http://127.0.0.1:5000 and press **Start question**.

Optional environment variables: `PORT` (listen port, default 5000), `PREPARATOR_DATABASE` (path of the SQLite file), and `FLASK_DEBUG=1` (reloader and debugger; never use it when anyone else can reach the port).

## Tests and lint

`requirements-dev.txt` adds ruff and Playwright to the runtime pins. Point `PREPARATOR_DATABASE` at a scratch file so nothing touches your real progress.

Windows (PowerShell):

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:PREPARATOR_DATABASE = "$PWD\scratch.sqlite3"
.venv\Scripts\python.exe -m unittest discover -s tests
.venv\Scripts\python.exe -m ruff check app.py db.py question_bank.py coding_variants.py tests
.venv\Scripts\python.exe -m compileall -q app.py db.py question_bank.py coding_variants.py tests
node --check static/app.js; node --check static/editor.js
```

Linux and macOS:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
export PREPARATOR_DATABASE="$PWD/scratch.sqlite3"
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m ruff check app.py db.py question_bank.py coding_variants.py tests
.venv/bin/python -m compileall -q app.py db.py question_bank.py coding_variants.py tests
node --check static/app.js && node --check static/editor.js
```

CI runs the same checks on every push and pull request.

## Project structure

```
app.py                  Flask app: localhost guard, JSON API, rubric scoring, question selection
db.py                   SQLite connection, versioned migrations, seeding from the question bank
question_bank.py        hand-written questions, rubrics, explanations and solutions
coding_variants.py      312 generated coding prompts from 24 problem types
templates/index.html    the single-page shell
static/                 app.js (views, routing, API calls), editor.js, style.css, vendor/codemirror.js
tests/                  unittest suites, each test on its own temporary database
tools/qa/               headless-browser check helpers (Playwright)
tools/editor-bundle/    recipe for rebuilding static/vendor/codemirror.js
assets/screenshots/     the images in this README
ARCHITECTURE.md         design rules, boundaries and guardrails
DEVELOPMENT_STORY.md    how I designed and ran the agent team, and what I learned
CLAUDE.md, .claude/     the AI agent team setup (see below)
```

The CodeMirror bundle is prebuilt so the app needs no build step; see `tools/editor-bundle/README.md` to rebuild it.

## Architecture

One Flask process on 127.0.0.1 serves a single HTML page and a small JSON API; the browser switches views and calls that API; SQLite stores all progress. Question content lives in Python files and is copied into the database on start. `ARCHITECTURE.md` has the full rules.

```mermaid
flowchart LR
    subgraph browser["Browser"]
        ui["index.html, app.js, editor.js"]
        ls[("localStorage: theme, filters")]
    end
    subgraph server["Flask app on 127.0.0.1"]
        api["app.py: localhost guard, JSON API, rubric scoring"]
        dbmod["db.py: connection, migrations, seeding"]
        bank["question_bank.py, coding_variants.py"]
    end
    sqlite[("SQLite file")]
    ui -->|"fetch JSON"| api
    ui --- ls
    api --> dbmod
    bank -->|"seed on start"| dbmod
    dbmod --> sqlite
```

## Built with a multi-agent AI team

Preparator was built by a team of Claude Code agents. Their instructions are in `CLAUDE.md` and `.claude/agents/`, and every agent may write only to its own files. The team's working record (task board, reviews, QA evidence, decision records) is kept in a private repository and is not part of this one.

The dated story of the build is in [DEVELOPMENT_STORY.md](DEVELOPMENT_STORY.md). It covers how I designed the team, audited it, closed its verification gap with a QA agent, made it survive crashes and token limits, cut its cost, and shipped it safely.

```mermaid
flowchart TD
    human(["Human"]) -->|"request"| orch["Orchestrator: board, dispatch, commits"]
    orch --> idea["Ideator: proposals"]
    idea --> lead["Lead engineer: decisions, API contract, sized tasks"]
    lead --> gate{"Human approval gate"}
    gate -->|"UI work, size M or L"| design["Designer: spec and frontend tasks"]
    gate -->|"size S, or no UI work"| impl["Backend or frontend engineer"]
    design --> impl
    impl --> review["Review engineer"]
    review -->|"changes requested"| impl
    review -->|"approved, no UI change"| done["Done: commit"]
    review -->|"approved, UI change"| qa["QA engineer: headless browser checks"]
    qa -->|"fail"| impl
    qa -->|"pass"| done
```

Task sizes: S skips the designer and is reviewed with the same checklist on a smaller model; L adds a lead re-check against the architecture before implementation.

- **Orchestrator** (the main session): task board, dispatching, commits.
- **Ideator**: feature proposals.
- **Lead engineer**: architecture, decision records, API contract, sized tasks.
- **Designer**: UI specs and the frontend tasks for them.
- **Backend / frontend engineers**: Python and tests / templates, JavaScript and CSS.
- **Review engineer**: reviews every task, code or design.
- **QA engineer**: headless-browser checks on a scratch database, both themes, desktop and phone.

Lessons learned:

- Giving each agent its own files made parallel work safe: backend and frontend ran side by side once the API contract was written.
- Reviewing before QA, and running QA on the committed candidate, kept fix rounds small and diffable.
- Most extra rounds came from scope that changed after a task was written, so a scope change now goes back to the lead before work starts.
- Agents sometimes report more than they did (a half-done item marked "applied", a comment claiming something the code does not do); reviewers who check claims against the diff are essential.
- Some steps stay with the human on purpose: guardrail changes, permission edits (applied by hand) and real screen-reader checks.

**My role.** I designed the agent team and its workflow, made the product and architecture decisions at the approval gates, and directed the work. The lead engineer agent proposed options and I decided; the agents wrote the code, tests, design specs and reviews within those decisions.

Some of what that meant in practice:

- **Testing the setup, not trusting it.** A review of the agent setup found agent files that contradicted `CLAUDE.md`, and no agent able to run the browser checks the process required. I had both fixed: one write-areas table as the single source of truth, deny rules in `.claude/settings.json`, and a QA agent running headless Playwright.
- **Designing for failure and cost.** Checkpoint files, WIP commits and a recovery procedure let a session stop at any point without losing work. Task sizes and model routing (Opus to plan and review, Sonnet to execute) keep small changes cheap.
- **Using my own product.** My own answer scored 3/10 even though it used try/except, a valid approach, so I asked for graded rubric feedback. I had the web-search step before each question removed and approved the guardrail change.

The full story, with the trade-offs, is in [DEVELOPMENT_STORY.md](DEVELOPMENT_STORY.md).

## AI engineering concepts applied

The app itself uses no AI model. Its scoring is a transparent keyword rubric. AI was used only to build it:

- **Multi-agent orchestration:** the main session dispatches seven specialist subagents and is the only one that moves tasks and commits.
- **Human-in-the-loop gates:** I approve decisions and tasks before work starts, and every guardrail change needs my explicit approval.
- **Evaluator-optimizer loop:** a separate review agent sends each task back to its author until it approves, for at most 3 rounds before the task comes to me.
- **Model routing:** Opus for the lead and the reviewer, Sonnet for the other agents and for reviews of small tasks.
- **Least-privilege tool access:** per-agent `tools:` lists, a write-areas table, and `.claude/settings.json` deny rules for the real database and the vendored bundle.
- **Shared file-based state and checkpoints:** agents coordinate through a task board, an API contract and plan and handoff files, so a crashed session resumes from disk.
- **Contract-first development:** each endpoint goes into the API contract before work starts, so backend and frontend build in parallel.
- **Prompt and context engineering:** each subagent runs in its own context, with a role definition in `.claude/agents/` and a dispatch that names the task file and the files it must not touch.
- **Agentic web research:** the designer's specs rest on web research notes that cite their sources (for example WCAG guidance).

## License

MIT, see `LICENSE`. The bundled CodeMirror and Lezer packages are MIT-licensed as well; see `THIRD_PARTY_NOTICES.md`.

Topic breadth was informed by [DataCamp's Python interview guide](https://www.datacamp.com/blog/top-python-interview-questions-and-answers); the prompts and explanations in this app were written for this project.
