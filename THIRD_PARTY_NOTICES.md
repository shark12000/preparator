# Third-party notices

Preparator itself is licensed under the MIT License (see `LICENSE`).

## Editor bundle: `static/vendor/codemirror.js`

`static/vendor/codemirror.js` is a minified esbuild bundle (rebuild recipe: `tools/editor-bundle/`). It has no license header, so the packages it is built from are listed here. All of them are MIT-licensed, copyright Marijn Haverbeke and others:

- `codemirror`
- `@codemirror/state`, `@codemirror/view`, `@codemirror/commands`, `@codemirror/language`, `@codemirror/autocomplete`, `@codemirror/search`, `@codemirror/lint`, `@codemirror/lang-python`
- `@lezer/common`, `@lezer/lr`, `@lezer/highlight`, `@lezer/python`
- `style-mod`, `w3c-keyname`, `crelt`, `@marijn/find-cluster-break` (small helper packages that the CodeMirror packages depend on)

The license of each package was checked against its entry in the npm registry (all report "MIT"); no package in the bundle uses a different license.

The Python dependencies installed from `requirements.txt` (Flask, Werkzeug, Jinja2, MarkupSafe, itsdangerous, click, blinker) are not redistributed in this repository; they are installed by `pip` under their own licenses.

## MIT License text (applies to each package above)

Copyright (C) the respective authors, Marijn Haverbeke <marijn@haverbeke.berlin> and others

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
