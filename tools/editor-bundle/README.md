# Editor bundle

`static/vendor/codemirror.js` is a prebuilt, minified ES module (CodeMirror 6, bundled with esbuild). It is vendored so the app needs no build step and works offline. This folder holds the recipe to rebuild it. It is dev-only and not needed to run Preparator.

## Rebuild

```powershell
cd tools/editor-bundle
npm install
npm run build
```

`npm run build` overwrites `static/vendor/codemirror.js`. `node_modules/` and `package-lock.json` here are git-ignored. After a rebuild, check the app's code editor in both themes (light and dark).

`entry.js` re-exports exactly what `static/editor.js` imports: `EditorView`, `keymap`, `basicSetup`, `python`, `EditorState`, `Compartment`, `Prec`, `indentWithTab`, `HighlightStyle`, `syntaxHighlighting`, `indentUnit`, `tags`.

## Provenance

The vendored bundle contains no version strings. The versions in `package.json` are the best reconstruction from the bundle's commit date (2026-10-03): the newest release of each package published before that date (`codemirror` is the 6.x line; the 5.x releases are a different editor). A rebuild with these versions is not byte-identical to the vendored file: it is 463,833 bytes against 463,394 (439 bytes larger), and it exports the same twelve names, though one minified export alias differs (`EditorView` is `A` in the rebuild and `P` in the vendored file). Treat the versions as an approximation, not a record.
