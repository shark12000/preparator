// CodeMirror 6 wrapper. The bundle in vendor/ is built once from tools/editor-bundle/ so the
// app needs no build step and works offline.
import {
  EditorView, basicSetup, python, keymap, indentWithTab, indentUnit, Prec,
  HighlightStyle, syntaxHighlighting, tags,
} from "./vendor/codemirror.js";

// Colors come from CSS variables so the editor follows the light/dark theme.
const highlight = HighlightStyle.define([
  { tag: [tags.keyword, tags.controlKeyword, tags.definitionKeyword, tags.operatorKeyword], color: "var(--syn-keyword)", fontWeight: "500" },
  { tag: [tags.string, tags.special(tags.string)], color: "var(--syn-string)" },
  { tag: [tags.number, tags.bool, tags.null], color: "var(--syn-number)" },
  { tag: [tags.comment, tags.lineComment], color: "var(--syn-comment)", fontStyle: "italic" },
  { tag: [tags.function(tags.variableName), tags.function(tags.definition(tags.variableName))], color: "var(--syn-function)" },
  { tag: [tags.className, tags.definition(tags.className), tags.typeName], color: "var(--syn-type)" },
  { tag: [tags.self, tags.special(tags.variableName)], color: "var(--syn-keyword)" },
]);

export function createCodeEditor(parent, { doc = "", onSubmit, onChange } = {}) {
  const view = new EditorView({
    parent,
    doc,
    extensions: [
      basicSetup,
      python(),
      indentUnit.of("    "),
      syntaxHighlighting(highlight),
      // Highest precedence: basicSetup binds Mod-Enter to "insert blank line".
      Prec.highest(keymap.of([{ key: "Mod-Enter", run: () => { onSubmit?.(); return true; } }])),
      keymap.of([indentWithTab]),
      EditorView.updateListener.of((update) => { if (update.docChanged) onChange?.(); }),
      EditorView.contentAttributes.of({ "aria-label": "Python code editor" }),
    ],
  });
  return {
    getValue: () => view.state.doc.toString(),
    setValue: (text) => view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: text } }),
    focus: () => view.focus(),
  };
}
