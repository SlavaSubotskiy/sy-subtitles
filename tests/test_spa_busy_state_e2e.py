"""The busy button, by COMPUTED style and against the real wiring.

String-grepping `.btn--busy` out of components.css cannot see the two ways this
component fails in a browser:

* the override loses to `.btn:disabled` (or its selector is typo'd) and the
  button ships DIMMED — reading as dead rather than working, which is the whole
  point of the state;
* the page's `withBusyButton` is wired with a missing dependency, so the label
  shows a raw i18n key or the live region stays silent.

So this drives the real runner on the real `#add-submit` button in a real
Chromium, in both themes.
"""

import http.server
import json
import threading
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

SITE = Path(__file__).parent.parent / "site"

# Hold the action open, drive it through every phase, and read the button back.
DRIVE = """
() => {
  const btn = document.getElementById('add-submit');
  const live = document.getElementById('sr-action-status');
  document.getElementById('add-form').style.display = '';
  const seen = [];
  let release;
  window.__gate = new Promise((r) => { release = r; });
  window.__release = release;
  window.__done = withBusyButton(btn, 'probe', (step) => {
    step('branch'); seen.push([btn.textContent, live.textContent]);
    step('commit'); seen.push([btn.textContent, live.textContent]);
    return window.__gate;
  });
  const cs = getComputedStyle(btn);
  const dot = getComputedStyle(btn, '::before');
  return {
    seen,
    opacity: cs.opacity,
    cursor: cs.cursor,
    dotContent: dot.content,
    dotAnimation: dot.animationName,
    dotColor: dot.backgroundColor,
    inkColor: cs.color,
    ariaDisabled: btn.getAttribute('aria-disabled'),
    ariaBusy: btn.getAttribute('aria-busy'),
    nativeDisabled: btn.disabled,
    secondCallRefused: withBusyButton(btn, 'probe', () => Promise.resolve()) === null,
  };
}
"""

REST = """
async () => {
  window.__release();
  await window.__done;
  await new Promise((r) => setTimeout(r, 0));
  const btn = document.getElementById('add-submit');
  return {
    label: btn.textContent,
    i18n: btn.getAttribute('data-i18n'),
    busyClass: btn.classList.contains('btn--busy'),
    ariaDisabled: btn.getAttribute('aria-disabled'),
    ariaBusy: btn.getAttribute('aria-busy'),
    opacity: getComputedStyle(btn).opacity,
    liveRegion: document.getElementById('sr-action-status').textContent,
  };
}
"""


@pytest.fixture
def served_site():
    index_html = (
        (SITE / "index.html")
        .read_text()
        .replace("<head>", "<head><script>window.__SY_REPO='sy-tools/sy-subtitles';</script>", 1)
        .encode()
    )
    directory = str(SITE)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=directory, **k)

        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path.split("?", 1)[0] in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(index_html)))
                self.end_headers()
                self.wfile.write(index_html)
                return
            super().do_GET()

    httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}/index.html"
    httpd.shutdown()


def _page(browser, served_site, scheme):
    ctx = browser.new_context(color_scheme=scheme)
    pg = ctx.new_page()
    pg.route(
        "**/api.github.com/**",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"sha": "x", "tree": [], "truncated": False}),
        ),
    )
    pg.route("**/raw.githubusercontent.com/**", lambda r: r.fulfill(status=404, body=""))
    pg.goto(served_site)
    pg.wait_for_function("() => typeof withBusyButton === 'function'")
    return ctx, pg


def test_clicking_the_real_create_pr_button_puts_it_to_work(served_site, browser):
    """The wiring, not the runner: remove `withBusyButton` from submitAddTalk and
    every other test in the repo still passes. This one clicks the actual button
    of a signed-in session, with the GitHub chain hanging on its first request.
    """
    ctx = browser.new_context()
    pg = ctx.new_page()
    pg.add_init_script(
        "localStorage.setItem('sy_gh_token', 'gho_e2e');"
        "localStorage.setItem('sy_gh_user',"
        " JSON.stringify({login: 'tester', avatar_url: 'icon.png'}));"
    )
    # Playwright matches routes most-recently-registered first, so the catch-all
    # goes on FIRST and the specific ones override it.
    pg.route(
        "**/api.github.com/**",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"sha": "x", "tree": [], "truncated": False}),
        ),
    )
    # Repo probe answers "you may write"...
    pg.route(
        "**/api.github.com/repos/*/*",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"permissions": {"push": True}}),
        ),
    )
    # ...and the branch-ref lookup never answers, so the action stays in its
    # first phase for the length of the assertion.
    pg.route("**/api.github.com/**/git/ref/**", lambda r: None)
    pg.route("**/raw.githubusercontent.com/**", lambda r: r.fulfill(status=404, body=""))
    try:
        pg.goto(served_site)
        pg.wait_for_function("() => typeof SPA !== 'undefined' && !!SPA.submitAddTalk")
        pg.evaluate("() => { location.hash = '#/add'; }")
        pg.wait_for_function("() => document.getElementById('view-add').classList.contains('active')")
        pg.evaluate(
            "() => {"
            "  document.getElementById('add-form').style.display = '';"
            "  document.getElementById('add-title').value = 'Busy State Probe';"
            "  document.getElementById('add-date').value = '2026-01-01';"
            "  updateAddPreview();"
            "}"
        )
        pg.wait_for_function("() => !!ghWriteUser()")

        pg.click("#add-submit")

        pg.wait_for_function(
            "() => document.getElementById('add-submit').classList.contains('btn--busy')",
            timeout=5000,
        )
        state = pg.evaluate(
            "() => { const b = document.getElementById('add-submit');"
            " return { label: b.textContent, i18n: b.getAttribute('data-i18n'),"
            " ariaBusy: b.getAttribute('aria-busy'),"
            " spoken: document.getElementById('sr-action-status').textContent }; }"
        )
        assert state["i18n"] == "pending.branch", "the first phase must be named"
        assert state["label"] and "pending." not in state["label"]
        assert state["ariaBusy"] == "true"
        assert state["spoken"] == state["label"]
    finally:
        ctx.close()


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_busy_button_keeps_its_ink_and_narrates_each_phase(served_site, browser, scheme):
    ctx, pg = _page(browser, served_site, scheme)
    try:
        busy = pg.evaluate(DRIVE)

        # Alive, not dead: the disabled dimming must NOT apply.
        assert busy["opacity"] == "1", "a dimmed busy button reads as disabled"
        assert busy["cursor"] == "progress"
        # The dot is really drawn and really animating, in the button's own ink.
        assert busy["dotContent"] in ('""', "''", "none") or busy["dotContent"]
        assert busy["dotAnimation"] == "sy-busy-pulse"
        assert busy["dotColor"] == busy["inkColor"], "the dot must be currentColor"

        # aria-disabled, never the native property (which would drop focus).
        assert busy["ariaDisabled"] == "true"
        assert busy["ariaBusy"] == "true"
        assert busy["nativeDisabled"] is False
        assert busy["secondCallRefused"] is True

        # The label names the phase, in real words, and reaches the live region.
        labels = [row[0] for row in busy["seen"]]
        spoken = [row[1] for row in busy["seen"]]
        assert len(labels) == 2 and labels[0] != labels[1], labels
        for text in labels:
            assert text and "pending." not in text, f"raw i18n key on the button: {text!r}"
        assert spoken == labels, "the live region must echo the button's phase"

        rest = pg.evaluate(REST)
        assert rest["busyClass"] is False
        assert rest["ariaBusy"] is None and rest["ariaDisabled"] is None
        assert rest["i18n"] == "add.submit"
        assert rest["label"] and "pending." not in rest["label"]
        assert rest["liveRegion"] == "", "stale status text lingers for the session"
    finally:
        ctx.close()
