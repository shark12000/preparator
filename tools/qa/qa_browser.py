"""Headless browser helpers for the qa-engineer agent.

Starts Preparator on a scratch database and a free port, and opens pages in
headless Chromium with a forced theme and viewport width. Never touches
instance/preparator.sqlite3.

Usage from a QA script:

    from tools.qa.qa_browser import running_app, open_page

    with running_app() as base_url, sync_playwright() as pw:
        browser = pw.chromium.launch()
        page, errors = open_page(browser, base_url, theme="dark", width=390, path="/#learn")
        page.screenshot(path="docs/qa/TASK-NNN/learn-dark-390.png", full_page=True)

Smoke check (all four views, both themes, desktop and 390px):

    .venv/Scripts/python.exe -m tools.qa.qa_browser --smoke --out docs/qa/smoke
"""

from __future__ import annotations

import argparse
import contextlib
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VIEWS = ("practice", "learn", "weaknesses", "progress")
WIDTHS = {"desktop": 1280, "phone": 390}
THEMES = ("light", "dark")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextlib.contextmanager
def running_app(database: str | None = None):
    """Run app.py on a scratch SQLite file and a free port; yield the base URL."""
    # ignore_cleanup_errors: on Windows the just-terminated server can hold the log for a moment.
    with tempfile.TemporaryDirectory(prefix="preparator-qa-", ignore_cleanup_errors=True) as tmp:
        db_path = database or os.path.join(tmp, "qa.sqlite3")
        if "instance" in Path(db_path).resolve().parts:
            raise RuntimeError("QA must never use instance/; pass a scratch database path")
        port = _free_port()
        env = dict(os.environ, PORT=str(port), PREPARATOR_DATABASE=db_path, FLASK_DEBUG="0")
        # Server output goes to a file: an unread pipe fills up and blocks the server.
        log_path = os.path.join(tmp, "server.log")
        log = open(log_path, "w", encoding="utf-8")
        proc = subprocess.Popen(
            [sys.executable, "app.py"],
            cwd=REPO_ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        base_url = f"http://127.0.0.1:{port}"
        try:
            deadline = time.time() + 20
            while True:
                try:
                    with urllib.request.urlopen(base_url + "/", timeout=2) as response:
                        if response.status == 200:
                            break
                except (urllib.error.URLError, ConnectionError, TimeoutError):
                    pass
                if proc.poll() is not None or time.time() > deadline:
                    log.flush()
                    raise RuntimeError("app.py did not start: " + Path(log_path).read_text(errors="replace")[-2000:])
                time.sleep(0.2)
            yield base_url
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            log.close()


def open_page(browser, base_url: str, *, theme: str = "light", width: int = 1280, height: int = 900, path: str = "/"):
    """Open a page with a forced theme and width. Returns (page, console_errors)."""
    context = browser.new_context(viewport={"width": width, "height": height}, color_scheme=theme)
    # The app reads its theme from localStorage key "preparator-theme".
    context.add_init_script(f"try {{ localStorage.setItem('preparator-theme', '{theme}'); }} catch (e) {{}}")
    page = context.new_page()
    errors: list[str] = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    # Do not wait for the full "load" event: it also waits for Google Fonts,
    # which may be slow or blocked. Wait for the DOM, then briefly for idle.
    page.goto(base_url + path, wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    return page, errors


def smoke(out_dir: str) -> int:
    from playwright.sync_api import sync_playwright

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    failures = 0
    with running_app() as base_url, sync_playwright() as pw:
        browser = pw.chromium.launch()
        for theme in THEMES:
            for label, width in WIDTHS.items():
                for view in VIEWS:
                    page, errors = open_page(browser, base_url, theme=theme, width=width, path=f"/#{view}")
                    actual_theme = page.evaluate("document.documentElement.dataset.theme")
                    overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
                    shot = out / f"{view}-{theme}-{label}.png"
                    page.screenshot(path=str(shot), full_page=True)
                    status = "OK"
                    if errors or actual_theme != theme or overflow:
                        status = "FAIL"
                        failures += 1
                    print(f"{status} {view:<10} {theme:<5} {label:<7} theme={actual_theme} "
                          f"h-overflow={overflow} console-errors={len(errors)} -> {shot.as_posix()}")
                    for error in errors:
                        print(f"     console: {error}")
                    page.context.close()
        browser.close()
    return failures


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--smoke", action="store_true", help="screenshot all views in both themes at desktop and 390px")
    parser.add_argument("--out", default=os.path.join(tempfile.gettempdir(), "preparator-qa-smoke"))
    args = parser.parse_args()
    if not args.smoke:
        parser.print_help()
        sys.exit(0)
    sys.exit(1 if smoke(args.out) else 0)
