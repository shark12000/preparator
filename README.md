# Preparator

A local Python interview-practice app. Choose a topic, level, and question format; answer one prompt at a time; get a transparent concept-match score and theory review; then revisit missed or saved questions.

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000. Pick your filters and press **Start question** to get a question; there is no web search step. The app runs offline apart from the web fonts it loads from Google Fonts.

Progress is stored in `instance/preparator.sqlite3` on this computer. Remove that file to reset the local practice history.

The bank contains the original interview prompts plus 312 deterministic coding variants from 24 problem types (13 input examples per type). It stays balanced across Foundations, Intermediate, and Advanced, and the practice view shows the canonical prompt count. Topic breadth was informed by [DataCamp's Python interview guide](https://www.datacamp.com/blog/top-python-interview-questions-and-answers); prompts and explanations in this app are written for this project.

Coding questions open in a CodeMirror editor with Python highlighting, line numbers, and auto-indent (falling back to a plain text box if it cannot load). Submissions use the app's transparent keyword rubric and reveal the example solution after submission. Lines copied unchanged from the starter stub earn no rubric credit, and an untouched stub cannot be submitted. The app does not execute submitted code.

The Learn view reuses the theory prompts as short lessons, with expandable examples and personal notes. Save a lesson to keep it in the Saved filter. **Export for Sheets** downloads a CSV with the lesson, explanation, example, note, and saved date; import that file into Google Sheets. This avoids storing Google credentials in the app.

## Interface

- Light and dark themes (follows your system until you pick one in the sidebar).
- Keyboard shortcuts: `Ctrl+Enter` submit, `N` next question, `S` save for review, `1`–`4` switch views, `?` list shortcuts.
- Views are linkable: `/#practice`, `/#learn`, `/#weaknesses`, `/#progress`.
- Progress shows a daily trend, a topic × level grid, and your practice streak (days use this computer's time zone).

### Rebuilding the editor bundle

`static/vendor/codemirror.js` is a prebuilt ES module, so the app needs no build step. To update it:

```powershell
npm install codemirror @codemirror/lang-python esbuild
# entry.js re-exports: EditorView, basicSetup (codemirror); python; EditorState, Compartment, Prec;
# keymap; indentWithTab; HighlightStyle, syntaxHighlighting, indentUnit; tags (@lezer/highlight)
npx esbuild entry.js --bundle --format=esm --minify --outfile=static/vendor/codemirror.js
```

## Scoring note

Answer feedback uses a small, visible concept-keyword rubric. A concept counts as covered when its keywords (or an accepted alternative approach) appear, and as partly covered (half credit) when only related words appear. It is useful for deliberate practice, but it is not semantic grading and does not replace a human interviewer or a language model. Each prompt includes a theory explanation and an optional solution, revealed only after submission.

## Tests

```powershell
python -m unittest discover -s tests
```

## Next features to explore

- Difficulty progression that adapts to recent results.
- Spaced repetition with review dates and a daily queue.
- Direct Google Sheets sync using a user-owned Apps Script endpoint.
- Import/export of progress, and a configurable LLM grader for deeper feedback.