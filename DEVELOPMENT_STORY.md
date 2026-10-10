# How Preparator was built

I'm Nik. Preparator is a local app for practicing Python interview questions: one question at a time, a transparent keyword rubric, a weak-spots queue and progress kept in SQLite on my computer. I built it with a team of Claude Code agents. I designed the team, its workflow and its constraints, approved every guardrail change, decided at the approval gates and set the priorities. The agents implemented, reviewed and tested within those decisions. Dates and numbers come from the project's records.

## 1. Designing an AI engineering team

**Problem.** Preparator already worked as a small Flask and SQLite app with 20 tests. One AI session could change code, but couldn't keep architecture, design, implementation and review apart, or run work in parallel safely.

**What I designed.** Before building anything, I pressure-tested the architecture in conversations with Claude. Then I specified the roles (ideator, lead engineer, designer, frontend and backend engineers, reviewer) and the principles:

- **One writer for the task board.** Only the orchestrating main session moves tasks and commits.
- **Proposing is separate from deciding.** The ideator proposes, the lead evaluates and plans, and I approve at the gate.
- **File ownership.** Each agent owns its files, so backend and frontend can run in parallel.
- **Contract first.** Every endpoint goes into an API contract before either side starts.

**How AI fit in.** Each role is a Claude Code subagent with its own instructions, tools and model, and each runs in its own context.

**Result.** On 2026-10-03 the project went under git with the team in place. A baseline review of the code found 3 blockers and 11 should-fix issues. Two examples: Learn showed model answers before a question was answered, and cross-site requests could change saved data. For the Learn leak, I accepted the lead's recommendation to lock each answer until the first attempt.

## 2. Testing the system, not trusting it

**Problem.** A team defined in prose can contradict itself, and agents follow their instructions, not my intentions.

**What I designed.** I asked Claude to review the agent setup itself. It found:

- agent files that contradicted `CLAUDE.md` about who moves task files;
- a designer that could skip review;
- write areas that didn't match;
- no agent that could run the browser checks the process required;
- a reviewer that couldn't save its own reports.

I had it all fixed on 2026-10-03:

- one write-areas table as the single source of truth;
- deny rules in `.claude/settings.json` for the real database and the vendored editor bundle;
- one task per review, with the reviewer writing only its own report;
- the 3-round limit extended to design work;
- a gate for the frontend tasks the designer writes;
- a QA agent.

**Result.** Each rule lives in one place, and the rules that protect data are enforced by settings, not just instructions.

## 3. Closing the verification gap

**Problem.** The agents had no browser, so every UI task ended with "Pending manual check" for me. A security fix (JSON-only writes, a Host check) was written early but waited until someone confirmed in a browser that the buttons still worked.

**What I designed.** On 2026-10-03 I added a QA agent. It drives the real app in headless Chromium through Playwright, on a scratch database, in both themes, at desktop and phone width. I chose it over clicking through the checks myself so that they could run unattended.

**How AI fit in.** The QA agent writes a check script per task, records the results and saves screenshots. Real screen-reader passes stay with me.

**Result.** Its first run, on 2026-10-04, passed 52 of 52 checks and released the held fix.

## 4. Designing for failure

**Problem.** On 2026-10-04 a shutdown hit in the middle of a lead run and left part of its work uncommitted. On 2026-10-05 VS Code closed with two tasks in flight. I also worked in low and medium budget modes, so token limits could end a session at any point.

**What I designed.** Wrap-up, handoff and resume procedures, so a session can stop at any point without losing work:

- **Checkpoint files.** A plan (what comes next) and a handoff log (what happened), updated after every gate, finished or blocked task, and session end.
- **Checkpoint slices.** Sessions were planned as slices that each end on a committed checkpoint, so a session cut short stops at the last one reached.
- **Recovery notes.** These record what is on disk and what is missing, so the next agent continues instead of starting over.
- **WIP commits, never stash.** Unfinished work stays visible and diffable.

**How AI fit in.** The orchestrating session keeps these files current, and re-dispatched agents continue from them.

**Result.** Both crashes were recovered from disk with no work redone.

## 5. Engineering for cost

**Problem.** Every task got the same treatment: every review ran on the large model, and QA ran before review, so a review finding could mean running QA again.

**What I designed.** From the start, Opus planned (the lead) and reviewed, and Sonnet executed (ideator, designer, engineers, QA). On 2026-10-05 I reworked the workflow:

- **Task sizes.** S, M or L. S tasks skip the designer and get a Sonnet review.
- **Two approval gates only for large features.** One gate before design, one after, so no design work is spent on decisions I might reject.
- **Review before QA.** QA runs on the committed, approved candidate, so a QA fix is re-reviewed as a small diff.

**How AI fit in.** The lead sized the 35 open tasks in one pass. Retrospectives after the two publishing batches compared each task's size with its rounds.

**Result.** In the last batch, all four small tasks stayed small. In the batch before it, both extra rounds came from scope that changed after a task was written, not from careless code. So I approved a rule: a scope change at a gate goes back to the lead before work starts.

## 6. Using my own product

**Problem.** Reviews check code against specs, not whether the product feels right.

**What I designed.** I used the app and turned what I found into requirements:

- **The search step.** Before every question, the original design opened a Google search in a new browser tab, and a guardrail protected that step. On 2026-10-04 I said I didn't want the app to send me to a browser. When I was asked what should replace the step, I chose to remove it. I approved the guardrail change and asked for the first question to appear after one button press.
- **The rubric.** On 2026-10-05 I answered the dictionary missing-key question myself. The rubric gave 3/10, marked two concepts "Not mentioned", and gave nothing for my valid try/except approach. I asked for graded concept states, highlighted matches, an "I covered this" self-assessment, accepted alternatives and a fixed rubric.

**How AI fit in.** The lead turned each request into decisions and tasks. For the rubric, it proposed half credit for related terms and a self-assessment that never changes the score, and I agreed.

**Result.** The search step is gone. My answer now scores 5/10. A check over 18,984 cases showed no old score changed, and a later task fixed 25 rubric rows that were likely too strict. The new feedback's frontend is still in the backlog.

## 7. Shipping safely

**Problem.** On 2026-10-10 I decided to publish Preparator on GitHub. The repository had my email in every commit and a large private process record.

**What I designed.** I started with a read-only privacy audit and a full backup. The audit found no secrets in the files or the 108-commit history; the only personal item was the email.

- **The split.** The code, `CLAUDE.md`, the agent definitions and a trimmed architecture document stay public. The process record (task board, reviews, decision records, plans) moved to its own private repository.
- **CI.** I added Windows next to Ubuntu.
- **Two overrides of the lead.** I had the editor bundle's build entry tracked under `tools/` instead of the README code block the lead suggested, and the screenshot demo data backdated over about three weeks (scratch database only) instead of showing one day.

I approved the history rewrite as the very last step.

**How AI fit in.** The agents did the split, CI, the comment cleanup and the README. Review caught a PowerShell CI step that would have hidden a failing command.

**Result.** On a fresh clone, the rewrite dropped the process folder and replaced the commit email with GitHub's noreply address, turning 125 commits into 64. The final tree was verified identical, with no personal email left and 147 tests passing. Then I pushed it.

## 8. What I learned

- **Structure beats instructions.** File ownership, one board writer and contracts written first did more for safe parallel work than any prompt wording.
- **Verify claims; don't trust reports.** One agent marked a half-done item "applied", and another wrote a comment about framework features the code doesn't use.
- **Most rework comes from moving scope.** Sending gate changes back to the planner is cheaper than catching them in review.
- **Plan for interruption from day one.** Checkpoints and WIP commits turned crashes and budget limits into pauses.
- **Using the product finds what reviews can't.** Both the rubric redesign and the removed search step came from my own use.
