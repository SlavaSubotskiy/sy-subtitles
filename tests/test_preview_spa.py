"""E2E tests for the dynamic SPA preview (v2.html / index.html)."""

import contextlib
import http.server
import json
import re
import threading
from pathlib import Path
from urllib.parse import quote, unquote

import pytest
import yaml

from tools.vimeo_codec import decode_video_ref

pytestmark = pytest.mark.e2e

SAMPLE_META = """title: 'Test Talk: Subtitle Preview'
date: '2001-01-01'
location: Test Location
videos:
- slug: Test-Video
  title: Test Video
  video_ref: r1DBtMTl9VW1NC
- slug: Test-Video-2
  title: Test Video 2
  video_ref: r1CRxJTlpYUFZF
"""

# Hostile amruta_url values (the meta.yaml / scraping-bookmarklet attacker
# vector) that try to break out of the card's href="". Two distinct vectors,
# because esc() escapes < > independently of the quote fix:
#   - tag injection ("><img …>) — blocked by < > escaping + safeHref wiring
#   - attribute injection (" data-xss="…) — blocked only by the " -> &quot; fix
_XSS_AMRUTA_TAG = 'https://www.amruta.org/x"><img src=x onerror=window.__XSS_FIRED=true>'
_XSS_AMRUTA_ATTR = 'https://www.amruta.org/x" data-xss="pwned'
XSS_AMRUTA_TAG_META = SAMPLE_META + "amruta_url: '" + _XSS_AMRUTA_TAG + "'\n"
XSS_AMRUTA_ATTR_META = SAMPLE_META + "amruta_url: '" + _XSS_AMRUTA_ATTR + "'\n"

# Canonical pipeline shape (tools/srt_utils.py write_srt): a trailing blank line
# after EVERY block, so the file ends with "\n\n". Real repo files all end this
# way — the SPA rebuild must match byte-for-byte or reviewers see a spurious
# trailing-newline diff on every commit.
SAMPLE_SRT = """1
00:00:01,000 --> 00:00:05,000
Перший субтитр

2
00:00:06,000 --> 00:00:10,000
Другий субтитр

"""

SAMPLE_EN_SRT = """1
00:00:01,000 --> 00:00:04,000
First subtitle block

2
00:00:04,500 --> 00:00:08,000
Second subtitle block

3
00:00:08,500 --> 00:00:12,000
Third subtitle block
"""

SAMPLE_EN = "Talk Language: English\n\nFirst paragraph.\n\nSecond paragraph.\n"
SAMPLE_UK = "Мова промови: англійська\n\nПерший абзац.\n\nДругий абзац.\n"
SAMPLE_HI = "Talk Language: Hindi\n\nपहला पैराग्राफ।\n\nदूसरा पैराग्राफ।\n"

MOCK_REVIEW_STATUS = {
    "version": 1,
    "updated_at": "2026-04-01T00:00:00Z",
    "talks": {
        "2001-01-01_Test-Talk": {
            "status": "pending",
            "reviewer": None,
            "issue_number": 42,
            "updated_at": "2026-04-01T00:00:00Z",
        },
    },
}

# Simulated GitHub Trees API response — ALPHABETICAL ORDER like real API
# (final/uk.srt comes BEFORE meta.yaml — this is the order GitHub returns)
# Mock tree: Test-Talk is fully ready (both videos have uk.srt, transcript_uk exists, review_report exists)
# No-Uk is early stage (only meta.yaml + en transcript)
MOCK_TREE = {
    "sha": "test123",
    "tree": [
        {"path": "talks/2001-01-01_Test-Talk/Test-Video/final/uk.srt", "type": "blob"},
        {"path": "talks/2001-01-01_Test-Talk/Test-Video/source/en.srt", "type": "blob"},
        {"path": "talks/2001-01-01_Test-Talk/Test-Video/source/whisper.json", "type": "blob"},
        {"path": "talks/2001-01-01_Test-Talk/Test-Video-2/final/uk.srt", "type": "blob"},
        {"path": "talks/2001-01-01_Test-Talk/Test-Video-2/source/en.srt", "type": "blob"},
        {"path": "talks/2001-01-01_Test-Talk/Test-Video-2/source/whisper.json", "type": "blob"},
        {"path": "talks/2001-01-01_Test-Talk/meta.yaml", "type": "blob"},
        {"path": "talks/2001-01-01_Test-Talk/review_report.md", "type": "blob"},
        {"path": "talks/2001-01-01_Test-Talk/transcript_en.txt", "type": "blob"},
        {"path": "talks/2001-01-01_Test-Talk/transcript_hi.txt", "type": "blob"},
        {"path": "talks/2001-01-01_Test-Talk/transcript_uk.txt", "type": "blob"},
        {"path": "talks/2002-01-01_No-Uk/meta.yaml", "type": "blob"},
        {"path": "talks/2002-01-01_No-Uk/transcript_en.txt", "type": "blob"},
    ],
}


@pytest.fixture(scope="module")
def spa_path():
    return Path(__file__).parent.parent / "site" / "index.html"


@pytest.fixture(scope="module")
def server(spa_path):
    """Serve the SPA HTML.

    The SPA derives its owner/repo slug from the GitHub Pages host. The test
    server is 127.0.0.1, not <owner>.github.io, so it injects the
    window.__SY_REPO override the SPA falls back to off Pages — centralized
    here so every browser context and navigation gets it without per-test
    setup. Non-HTML requests fall through to the plain file handler."""
    directory = str(spa_path.parent)
    injected_index = (
        spa_path.read_text()
        .replace(
            "<head>",
            "<head><script>window.__SY_REPO = 'sy-tools/sy-subtitles';</script>",
            1,
        )
        .encode("utf-8")
    )

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)

        def do_GET(self):
            if self.path.split("?", 1)[0] in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(injected_index)))
                self.end_headers()
                self.wfile.write(injected_index)
                return
            super().do_GET()

    httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()


@pytest.fixture(scope="module")
def mock_player_js():
    return Path(__file__).parent.joinpath("fixtures", "mock_vimeo_player.js").read_text()


@pytest.fixture
def page(server, mock_player_js, browser):
    ctx = browser.new_context()
    pg = ctx.new_page()

    # Mock GitHub Trees API
    pg.route(
        "**/api.github.com/**",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            headers={"ETag": '"test-etag"'},
            body=json.dumps(MOCK_TREE),
        ),
    )

    # Mock meta.yaml fetches
    pg.route(
        "**/raw.githubusercontent.com/**/meta.yaml",
        lambda route: route.fulfill(
            status=200,
            content_type="text/plain",
            body=SAMPLE_META,
        ),
    )

    # Mock SRT (UK and EN)
    pg.route(
        "**/raw.githubusercontent.com/**/uk.srt",
        lambda route: route.fulfill(
            status=200,
            content_type="text/plain",
            body=SAMPLE_SRT,
        ),
    )
    pg.route(
        "**/raw.githubusercontent.com/**/en.srt",
        lambda route: route.fulfill(
            status=200,
            content_type="text/plain",
            body=SAMPLE_EN_SRT,
        ),
    )

    # Mock transcripts
    pg.route(
        "**/raw.githubusercontent.com/**/transcript_en.txt",
        lambda route: route.fulfill(
            status=200,
            content_type="text/plain",
            body=SAMPLE_EN,
        ),
    )
    pg.route(
        "**/raw.githubusercontent.com/**/transcript_uk.txt",
        lambda route: route.fulfill(
            status=200,
            content_type="text/plain",
            body=SAMPLE_UK,
        ),
    )
    pg.route(
        "**/raw.githubusercontent.com/**/transcript_hi.txt",
        lambda route: route.fulfill(
            status=200,
            content_type="text/plain",
            body=SAMPLE_HI,
        ),
    )

    # Mock Vimeo Player SDK
    pg.route(
        "**/player.vimeo.com/api/player.js",
        lambda route: route.fulfill(
            status=200,
            content_type="application/javascript",
            body=mock_player_js,
        ),
    )

    # Mock review-status.json
    pg.route(
        "**/raw.githubusercontent.com/**/review-status.json",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(MOCK_REVIEW_STATUS),
        ),
    )

    # Clear cache before each page load
    pg.add_init_script("localStorage.removeItem('sy_tree_cache__main');")
    # Auto-resolve SPA.confirm single-button info dialogs (e.g. the "copied
    # to clipboard — click Open GitHub" prompt after createIssue/openEditor).
    # Production keeps the blocking dialog; tests keep their direct
    # window.open / clipboard stub flow. Regression tests that need to
    # observe the dialog clear this flag before acting.
    pg.add_init_script("window.__spa_auto_info_confirm = true;")
    yield pg
    pg.close()
    ctx.close()


SPA_URL = "/index.html"


def goto_spa(page, server, hash=""):
    """Navigate to SPA."""
    page.goto(f"{server}{SPA_URL}{hash}")


def spa_confirm_accept(page, timeout=2000):
    """Accept the SPA custom confirm dialog (clicks primary/danger button).

    Returns the title+body text for assertions about what was shown.
    Replaces native confirm() handling via page.once("dialog", ...).
    """
    page.wait_for_selector(".sy-modal", timeout=timeout)
    title = page.locator(".sy-modal-title").text_content() or ""
    body_loc = page.locator(".sy-modal-body")
    body = body_loc.text_content() if body_loc.count() else ""
    page.locator(".sy-modal-btn.primary, .sy-modal-btn.danger").first.click()
    page.wait_for_selector(".sy-modal", state="detached", timeout=timeout)
    return f"{title}\n{body}".strip()


def spa_confirm_dismiss(page, timeout=2000):
    """Cancel the SPA custom confirm dialog (clicks the non-primary button)."""
    page.wait_for_selector(".sy-modal", timeout=timeout)
    page.locator(".sy-modal-btn:not(.primary):not(.danger)").first.click()
    page.wait_for_selector(".sy-modal", state="detached", timeout=timeout)


class TestIndexView:
    def test_loads_talks(self, server, page):
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        items = page.locator(".talk-item").count()
        assert items >= 1

    def test_shows_talk_title(self, server, page):
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        text = page.locator(".talk-item").first.text_content()
        assert "Test Talk" in text

    def test_shows_review_link(self, server, page):
        """Talk with both EN and UK transcripts should have review link."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        review_links = page.locator("a[href*='review']").count()
        assert review_links >= 1

    def test_shows_video_preview_link(self, server, page):
        """Video with uk.srt should have preview link."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        preview_links = page.locator("a[href*='preview']").count()
        assert preview_links >= 1

    def test_single_preview_link_for_multi_video(self, server, page):
        """Multi-video talks get a single consolidated preview link — users switch
        videos from within the preview page via the video selector."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        links = page.locator(".talk-item").first.locator("a.preview-link").count()
        assert links == 1

    def test_talk_without_uk_no_review(self, server, page):
        """Talk without UK transcript should NOT have review link."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        html = page.content()
        # 2002-01-01_No-Uk should not have review link
        assert "2002-01-01_No-Uk/review" not in html


class TestPreviewView:
    def _goto_preview(self, server, page):
        goto_spa(page, server, "#/preview/2001-01-01_Test-Talk/Test-Video")
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        page.wait_for_timeout(1000)  # Wait for SRT fetch

    def test_loads(self, server, page):
        self._goto_preview(server, page)
        assert "Preview" in page.title()

    def test_has_back_link(self, server, page):
        self._goto_preview(server, page)
        assert page.locator("a[href='#/']").count() >= 1

    def test_subtitle_sync(self, server, page):
        self._goto_preview(server, page)
        text = page.evaluate("""() => {
            window._vimeoPlayer._setTime(2);
            return new Promise(resolve => {
                setTimeout(() => resolve(document.getElementById('subtitle-overlay').textContent), 200);
            });
        }""")
        assert text == "Перший субтитр"

    def test_overlay_tracks_playhead_into_gap_without_timeupdate(self, server, page):
        # The deliberate gap between subtitles (here 5.0s..6.0s) must show as a
        # blank overlay. The overlay is driven by polling the player position
        # (getCurrentTime) every animation frame, NOT by the ~4x/sec timeupdate
        # event — so a playhead resting in the gap blanks the overlay even though
        # no timeupdate sample landed there. Moving _currentTime WITHOUT firing a
        # timeupdate reproduces exactly that case; the old event-driven overlay
        # would stay stuck on the previous subtitle.
        self._goto_preview(server, page)
        # Precondition: block 1 (1.0s..5.0s) is showing, so a later blank is a
        # real transition, not the empty overlay the page starts with.
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_function(
            "document.getElementById('subtitle-overlay').textContent === 'Перший субтитр'",
            timeout=2000,
        )
        # Move the playhead into the gap without emitting a timeupdate.
        page.evaluate("window._vimeoPlayer._currentTime = 5.5")
        page.wait_for_function(
            "document.getElementById('subtitle-overlay').textContent === ''",
            timeout=2000,
        )

    def test_overlay_height_held_through_gap(self, server, page):
        # During the brief 80ms gaps the overlay must not collapse its height —
        # a multi-line subtitle dropping to an empty (1-line) box and back is a
        # jarring vertical bounce. The overlay holds the prior subtitle's height
        # while blank, so the background stays put through the pause.
        self._goto_preview(server, page)
        # Force the (short) subtitle text to wrap to several lines so a collapse
        # to an empty 1-line box would be unmistakable.
        page.evaluate("document.getElementById('subtitle-overlay').style.maxWidth = '70px'")
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_function(
            "document.getElementById('subtitle-overlay').textContent === 'Перший субтитр'",
            timeout=2000,
        )
        page.wait_for_timeout(300)  # let the height settle
        h_text = page.evaluate("document.getElementById('subtitle-overlay').offsetHeight")
        # Into the gap (no timeupdate) — overlay blanks but must keep its height.
        page.evaluate("window._vimeoPlayer._currentTime = 5.5")
        page.wait_for_function(
            "document.getElementById('subtitle-overlay').textContent === ''",
            timeout=2000,
        )
        page.wait_for_timeout(300)  # past any height transition
        h_gap = page.evaluate("document.getElementById('subtitle-overlay').offsetHeight")
        assert h_text > 90, f"expected a multi-line subtitle, got {h_text}px"
        assert h_gap >= h_text - 5, f"overlay collapsed in gap: {h_text} -> {h_gap}"

    def test_overlay_fullscreen_pins_explicit_height(self, server, page):
        # Fullscreen eases size changes between subtitles, which needs an explicit
        # px height every frame (CSS cannot transition to/from `auto`). So in
        # fs-mode each subtitle pins a measured px height; embedded does not.
        self._goto_preview(server, page)
        page.evaluate("document.getElementById('view-preview').classList.add('fs-mode')")
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_function(
            "document.getElementById('subtitle-overlay').textContent === 'Перший субтитр'",
            timeout=2000,
        )
        h = page.evaluate("document.getElementById('subtitle-overlay').style.getPropertyValue('height')")
        assert h.endswith("px"), f"fullscreen should pin an explicit px height, got {h!r}"

    def test_overlay_embedded_does_not_pin_height(self, server, page):
        # Embedded keeps the default sizing (const + auto-expand, or the user's
        # resized height): no explicit height pinned for a shown subtitle.
        self._goto_preview(server, page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_function(
            "document.getElementById('subtitle-overlay').textContent === 'Перший субтитр'",
            timeout=2000,
        )
        h = page.evaluate("document.getElementById('subtitle-overlay').style.getPropertyValue('height')")
        assert h == "", f"embedded should not pin a height, got {h!r}"

    # NOTE: the fullscreen tests below simulate fs via the `.fs-mode` class —
    # they cover the CSS/JS behaviour, NOT the native requestFullscreen path.

    def test_overlay_height_held_through_gap_fullscreen(self, server, page):
        # The reported bug was the fullscreen gradient band collapsing on gaps.
        # The hold uses inline `height:!important` specifically because fs sets
        # `height: auto !important` and forces min-height to 0 — a "cleaner"
        # min-height refactor would pass the embedded hold test but silently
        # re-break fullscreen. This is the guard for that.
        self._goto_preview(server, page)
        page.evaluate("document.getElementById('view-preview').classList.add('fs-mode')")
        page.evaluate("document.getElementById('subtitle-overlay').style.maxWidth = '70px'")
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_function(
            "document.getElementById('subtitle-overlay').textContent === 'Перший субтитр'",
            timeout=2000,
        )
        page.wait_for_timeout(300)
        h_text = page.evaluate("document.getElementById('subtitle-overlay').offsetHeight")
        page.evaluate("window._vimeoPlayer._currentTime = 5.5")
        page.wait_for_function(
            "document.getElementById('subtitle-overlay').textContent === ''",
            timeout=2000,
        )
        page.wait_for_timeout(300)
        h_gap = page.evaluate("document.getElementById('subtitle-overlay').offsetHeight")
        assert h_text > 90, f"expected a multi-line subtitle, got {h_text}px"
        assert h_gap >= h_text - 5, f"fullscreen overlay collapsed in gap: {h_text} -> {h_gap}"

    def test_overlay_releases_pinned_height_on_exit_fullscreen(self, server, page):
        # Exiting fullscreen (even while paused) must release the pinned px height
        # so embedded returns to its default/auto sizing. The render loop's
        # mode-change branch is the only thing that does this; nothing else covers it.
        self._goto_preview(server, page)
        page.evaluate("document.getElementById('view-preview').classList.add('fs-mode')")
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_function(
            "document.getElementById('subtitle-overlay').style.getPropertyValue('height').endsWith('px')",
            timeout=2000,
        )
        page.evaluate("document.getElementById('view-preview').classList.remove('fs-mode')")
        page.wait_for_function(
            "document.getElementById('subtitle-overlay').style.getPropertyValue('height') === ''",
            timeout=2000,
        )

    def test_overlay_follows_scrub_while_paused(self, server, page):
        # Polling getCurrentTime each frame means a scrub updates the overlay with
        # no play/seeked event — a behaviour gained by dropping the event handlers.
        self._goto_preview(server, page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_function(
            "document.getElementById('subtitle-overlay').textContent === 'Перший субтитр'",
            timeout=2000,
        )
        # Scrub into block 2 (6..10s) by setting the raw field — no event fired.
        page.evaluate("window._vimeoPlayer._currentTime = 7")
        page.wait_for_function(
            "document.getElementById('subtitle-overlay').textContent !== 'Перший субтитр'"
            " && document.getElementById('subtitle-overlay').textContent !== ''",
            timeout=2000,
        )

    def test_marker_add(self, server, page):
        self._goto_preview(server, page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        count = page.locator("#marker-count").text_content()
        assert count == "1"

    def test_vimeo_embed_handles_missing_url(self, server, page):
        # showPreview calls vimeoEmbed(video.vimeo_url) for a link-less video
        # reached by deep link; a falsy URL must return '' rather than throwing
        # on undefined.match() and aborting the whole preview render.
        self._goto_preview(server, page)
        res = page.evaluate(
            "() => { try { return {ok: true, v: vimeoEmbed(undefined)}; }"
            " catch (e) { return {ok: false, err: String(e)}; } }"
        )
        assert res["ok"], f"vimeoEmbed threw on undefined: {res.get('err')}"
        assert res["v"] == ""
        assert page.evaluate("vimeoEmbed(null)") == ""
        assert page.evaluate("vimeoEmbed('not a url')") == ""


class TestReviewView:
    def _goto_review(self, server, page):
        goto_spa(page, server, "#/review/2001-01-01_Test-Talk")
        page.wait_for_function("document.querySelectorAll('.cell.en').length > 0", timeout=10000)

    def test_loads(self, server, page):
        self._goto_review(server, page)
        assert "Review" in page.title()

    def test_shows_paragraphs(self, server, page):
        self._goto_review(server, page)
        en = page.locator(".cell.en").count()
        uk = page.locator(".cell.uk").count()
        assert en == 2
        assert uk == 2

    def test_en_content(self, server, page):
        self._goto_review(server, page)
        text = page.locator(".cell.en").first.text_content()
        assert "First paragraph" in text

    def test_uk_editable(self, server, page):
        self._goto_review(server, page)
        attr = page.locator(".cell.uk .cell-text").first.get_attribute("contenteditable")
        assert attr == "true"

    def test_has_back_link(self, server, page):
        self._goto_review(server, page)
        assert page.locator("a[href='#/']").count() >= 1


class TestDirectNavigation:
    """Tests for navigating directly to preview/review URLs (without index first)."""

    def test_direct_preview_loads_manifest(self, server, page):
        """Navigating directly to preview URL should load manifest automatically."""
        goto_spa(page, server, "#/preview/2001-01-01_Test-Talk/Test-Video")
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        # Manifest should have been loaded
        cache = page.evaluate("localStorage.getItem('sy_tree_cache__main')")
        assert cache is not None

    def test_direct_preview_shows_title(self, server, page):
        """Direct preview navigation should show talk title from manifest."""
        goto_spa(page, server, "#/preview/2001-01-01_Test-Talk/Test-Video")
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        title = page.locator("#p-title").text_content()
        assert "Test Talk" in title

    def test_direct_preview_subtitle_sync(self, server, page):
        """Subtitles should work when navigating directly to preview URL."""
        goto_spa(page, server, "#/preview/2001-01-01_Test-Talk/Test-Video")
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        page.wait_for_timeout(1000)  # Wait for SRT fetch
        text = page.evaluate("""() => {
            window._vimeoPlayer._setTime(2);
            return new Promise(resolve => {
                setTimeout(() => resolve(document.getElementById('subtitle-overlay').textContent), 200);
            });
        }""")
        assert text == "Перший субтитр"

    def test_direct_review_loads_manifest(self, server, page):
        """Navigating directly to review URL should load manifest automatically."""
        goto_spa(page, server, "#/review/2001-01-01_Test-Talk")
        page.wait_for_function("document.querySelectorAll('.cell.en').length > 0", timeout=10000)
        cache = page.evaluate("localStorage.getItem('sy_tree_cache__main')")
        assert cache is not None

    def test_direct_review_shows_title(self, server, page):
        """Direct review navigation should show talk title."""
        goto_spa(page, server, "#/review/2001-01-01_Test-Talk")
        page.wait_for_function("document.querySelectorAll('.cell.en').length > 0", timeout=10000)
        title = page.locator("#r-title").text_content()
        assert "Test Talk" in title

    def test_direct_review_shows_content(self, server, page):
        """Direct review navigation should display transcript paragraphs."""
        goto_spa(page, server, "#/review/2001-01-01_Test-Talk")
        page.wait_for_function("document.querySelectorAll('.cell.en').length > 0", timeout=10000)
        en = page.locator(".cell.en").count()
        uk = page.locator(".cell.uk").count()
        assert en == 2
        assert uk == 2


class TestPreviewSubtitles:
    """Detailed subtitle behavior tests."""

    def _goto_preview(self, server, page):
        goto_spa(page, server, "#/preview/2001-01-01_Test-Talk/Test-Video")
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        page.wait_for_timeout(1000)

    def test_subtitle_appears_at_correct_time(self, server, page):
        """Subtitle should appear when time is within its range."""
        self._goto_preview(server, page)
        text = page.evaluate("""() => {
            window._vimeoPlayer._setTime(1.5);
            return new Promise(resolve => {
                setTimeout(() => resolve(document.getElementById('subtitle-overlay').textContent), 200);
            });
        }""")
        assert text == "Перший субтитр"

    def test_subtitle_disappears_between_blocks(self, server, page):
        """No subtitle when time is between blocks (5.0-6.0 gap)."""
        self._goto_preview(server, page)
        text = page.evaluate("""() => {
            window._vimeoPlayer._setTime(5.5);
            return new Promise(resolve => {
                setTimeout(() => resolve(document.getElementById('subtitle-overlay').textContent), 200);
            });
        }""")
        assert text == ""

    def test_second_subtitle_block(self, server, page):
        """Second subtitle block should display correctly."""
        self._goto_preview(server, page)
        text = page.evaluate("""() => {
            window._vimeoPlayer._setTime(7);
            return new Promise(resolve => {
                setTimeout(() => resolve(document.getElementById('subtitle-overlay').textContent), 200);
            });
        }""")
        assert text == "Другий субтитр"

    def test_no_subtitle_before_first_block(self, server, page):
        """No subtitle before the first block starts."""
        self._goto_preview(server, page)
        text = page.evaluate("""() => {
            window._vimeoPlayer._setTime(0.5);
            return new Promise(resolve => {
                setTimeout(() => resolve(document.getElementById('subtitle-overlay').textContent), 200);
            });
        }""")
        assert text == ""

    def test_no_subtitle_after_last_block(self, server, page):
        """No subtitle after all blocks end."""
        self._goto_preview(server, page)
        text = page.evaluate("""() => {
            window._vimeoPlayer._setTime(15);
            return new Promise(resolve => {
                setTimeout(() => resolve(document.getElementById('subtitle-overlay').textContent), 200);
            });
        }""")
        assert text == ""

    def test_time_display_updates(self, server, page):
        """Time display should update on timeupdate event."""
        self._goto_preview(server, page)
        text = page.evaluate("""() => {
            window._vimeoPlayer._setTime(65);
            return new Promise(resolve => {
                setTimeout(() => resolve(document.getElementById('time-display').textContent), 200);
            });
        }""")
        assert text == "00:01:05"


class TestMarkers:
    """Marker functionality tests."""

    def _goto_preview(self, server, page):
        goto_spa(page, server, "#/preview/2001-01-01_Test-Talk/Test-Video")
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        page.wait_for_timeout(1000)
        # Edit is the default mode now; these tests exercise markers, so opt in.
        page.click('.preview-mode-toggle [data-mode="marker"]')
        page.wait_for_timeout(100)

    def test_marker_persists_in_localStorage(self, server, page):
        """Markers should be saved to localStorage."""
        self._goto_preview(server, page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        markers = page.evaluate(
            "JSON.parse(localStorage.getItem('preview_2001-01-01_Test-Talk_Test-Video') || '{}').markers || null"
        )
        assert markers is not None
        assert len(markers) == 1
        assert markers[0]["text"] == "Перший субтитр"
        # Time comes from the polled position (previewState.currentTime), so it
        # must match where we set the player, not stay at 0.
        assert abs(markers[0]["time"] - 2) < 0.5, f"marker time off: {markers[0]['time']}"

    def test_marker_count_increments(self, server, page):
        """Adding multiple markers updates the count."""
        self._goto_preview(server, page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        page.click("#btn-mark")
        count = page.locator("#marker-count").text_content()
        assert count == "2"

    def test_marker_remove(self, server, page):
        """Removing a marker updates count and list."""
        self._goto_preview(server, page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        assert page.locator("#marker-count").text_content() == "1"
        page.click(".marker-item .del")
        assert page.locator("#marker-count").text_content() == "0"

    def test_clear_markers_with_confirm(self, server, page):
        """Clear all markers after confirmation."""
        self._goto_preview(server, page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        page.click("#btn-mark")
        assert page.locator("#marker-count").text_content() == "2"
        page.click("#btn-clear-all")
        spa_confirm_accept(page)
        assert page.locator("#marker-count").text_content() == "0"
        assert page.locator(".marker-item").count() == 0

    def test_clear_markers_cancel_keeps_markers(self, server, page):
        """Cancelling clear confirmation keeps markers."""
        self._goto_preview(server, page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        assert page.locator("#marker-count").text_content() == "1"
        page.click("#btn-clear-all")
        spa_confirm_dismiss(page)
        assert page.locator("#marker-count").text_content() == "1"
        assert page.locator(".marker-item").count() == 1

    def test_clear_markers_updates_localStorage(self, server, page):
        """Clear all removes markers from localStorage."""
        self._goto_preview(server, page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        data = page.evaluate(
            "JSON.parse(localStorage.getItem('preview_2001-01-01_Test-Talk_Test-Video') || '{}').markers || []"
        )
        assert len(data) == 1
        page.click("#btn-clear-all")
        spa_confirm_accept(page)
        data = page.evaluate(
            "JSON.parse(localStorage.getItem('preview_2001-01-01_Test-Talk_Test-Video') || '{}').markers || []"
        )
        assert len(data) == 0

    def test_marker_comment_input(self, server, page):
        """Marker should have a comment input field."""
        self._goto_preview(server, page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        inputs = page.locator(".marker-item .comment")
        assert inputs.count() == 1

    def test_marker_no_subtitle_text(self, server, page):
        """Marker added when no subtitle shows '(no subtitle)' text."""
        self._goto_preview(server, page)
        page.evaluate("window._vimeoPlayer._setTime(0.5)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        data = page.evaluate(
            "JSON.parse(localStorage.getItem('preview_2001-01-01_Test-Talk_Test-Video') || '{}').markers || []"
        )
        assert data[0]["text"] == "(no subtitle)"

    def test_comment_enter_blurs_input(self, server, page):
        """Pressing Enter in comment field should blur input so arrow keys work."""
        self._goto_preview(server, page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        comment_input = page.locator(".marker-item .comment").first
        comment_input.fill("test comment")
        comment_input.press("Enter")
        page.wait_for_timeout(200)
        focused_tag = page.evaluate("document.activeElement.tagName")
        assert focused_tag != "INPUT"

    def test_arrow_right_seeks_forward(self, server, page):
        """Right arrow key should seek video forward 5 seconds."""
        self._goto_preview(server, page)
        page.evaluate("window._vimeoPlayer._setTime(10)")
        page.wait_for_timeout(200)
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(200)
        time = page.evaluate("window._vimeoPlayer._currentTime")
        assert time == 15

    def test_arrow_left_seeks_backward(self, server, page):
        """Left arrow key should seek video backward 5 seconds."""
        self._goto_preview(server, page)
        page.evaluate("window._vimeoPlayer._setTime(10)")
        page.wait_for_timeout(200)
        page.keyboard.press("ArrowLeft")
        page.wait_for_timeout(200)
        time = page.evaluate("window._vimeoPlayer._currentTime")
        assert time == 5

    def test_arrow_left_clamps_to_zero(self, server, page):
        """Left arrow at start should not go below 0."""
        self._goto_preview(server, page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.keyboard.press("ArrowLeft")
        page.wait_for_timeout(200)
        time = page.evaluate("window._vimeoPlayer._currentTime")
        assert time == 0

    def test_space_toggles_play(self, server, page):
        """Space key should toggle play/pause."""
        self._goto_preview(server, page)
        page.wait_for_timeout(200)
        paused = page.evaluate("window._vimeoPlayer._paused")
        assert paused is not False
        page.keyboard.press("Space")
        page.wait_for_timeout(200)
        paused = page.evaluate("window._vimeoPlayer._paused")
        assert paused is False

    def test_subtitle_overlay_below_video(self, server, page):
        """Subtitle overlay should be a sibling of video-wrap (below video)."""
        self._goto_preview(server, page)
        parent_class = page.evaluate("""
            document.getElementById('subtitle-overlay').parentElement.className
        """)
        assert "player-container" in parent_class

    def test_subtitle_overlay_same_width_as_video(self, server, page):
        """Subtitle overlay width should match video container width."""
        self._goto_preview(server, page)
        widths = page.evaluate("""() => {
            var container = document.querySelector('.player-container');
            var overlay = document.getElementById('subtitle-overlay');
            return { container: container.offsetWidth, overlay: overlay.offsetWidth };
        }""")
        assert widths["overlay"] == widths["container"]

    def test_subtitle_overlay_always_visible(self, server, page):
        """Subtitle overlay should always be visible (even when empty)."""
        self._goto_preview(server, page)
        display = page.evaluate("""
            getComputedStyle(document.getElementById('subtitle-overlay')).display
        """)
        assert display != "none"


class TestFullscreenMode:
    """Fullscreen preview mode tests.

    Playwright headless doesn't support real Fullscreen API,
    so we test by toggling .fs-mode class directly and verifying
    CSS/DOM behavior, plus check that JS wiring exists.
    """

    def _goto_preview(self, server, page):
        goto_spa(page, server, "#/preview/2001-01-01_Test-Talk/Test-Video")
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        page.wait_for_timeout(1000)

    def _enter_fs(self, page):
        """Simulate entering fullscreen by adding .fs-mode class."""
        page.evaluate("document.getElementById('view-preview').classList.add('fs-mode')")
        page.wait_for_timeout(100)

    def _exit_fs(self, page):
        """Simulate exiting fullscreen by removing .fs-mode class."""
        page.evaluate("document.getElementById('view-preview').classList.remove('fs-mode')")
        page.wait_for_timeout(100)

    def test_fullscreen_button_exists(self, server, page):
        """Preview should have a fullscreen toggle button."""
        self._goto_preview(server, page)
        btn = page.locator("#btn-fullscreen")
        assert btn.count() == 1

    def test_toggle_fullscreen_function_exists(self, server, page):
        """SPA.toggleFullscreen should be a function."""
        self._goto_preview(server, page)
        is_fn = page.evaluate("typeof SPA.toggleFullscreen === 'function'")
        assert is_fn

    def test_fs_mode_hides_header(self, server, page):
        """In fullscreen, the preview header should be hidden."""
        self._goto_preview(server, page)
        self._enter_fs(page)
        display = page.evaluate("""
            getComputedStyle(document.querySelector('#view-preview .header')).display
        """)
        assert display == "none"

    def test_fs_mode_hides_markers(self, server, page):
        """In fullscreen, markers section should be hidden."""
        self._goto_preview(server, page)
        self._enter_fs(page)
        display = page.evaluate("""
            getComputedStyle(document.querySelector('#view-preview .preview-list')).display
        """)
        assert display == "none"

    def test_fs_mode_hides_mark_button(self, server, page):
        """In fullscreen, marker button should be hidden (not needed)."""
        self._goto_preview(server, page)
        self._enter_fs(page)
        display = page.evaluate("""
            getComputedStyle(document.getElementById('btn-mark')).display
        """)
        assert display == "none"

    def test_fs_mode_subtitle_overlay_fixed(self, server, page):
        """In fullscreen, subtitle overlay should be position:fixed."""
        self._goto_preview(server, page)
        self._enter_fs(page)
        position = page.evaluate("""
            getComputedStyle(document.getElementById('subtitle-overlay')).position
        """)
        assert position == "fixed"

    def test_fs_mode_subtitle_still_syncs(self, server, page):
        """Subtitles should still update in fullscreen mode."""
        self._goto_preview(server, page)
        self._enter_fs(page)
        text = page.evaluate("""() => {
            window._vimeoPlayer._setTime(2);
            return new Promise(resolve => {
                setTimeout(() => resolve(document.getElementById('subtitle-overlay').textContent), 200);
            });
        }""")
        assert text == "Перший субтитр"

    def test_fs_mode_exit_restores_header(self, server, page):
        """Exiting fullscreen should restore the header."""
        self._goto_preview(server, page)
        self._enter_fs(page)
        self._exit_fs(page)
        display = page.evaluate("""
            getComputedStyle(document.querySelector('#view-preview .header')).display
        """)
        assert display != "none"

    def test_fs_mode_exit_restores_subtitle_position(self, server, page):
        """Exiting fullscreen should restore subtitle overlay to normal position."""
        self._goto_preview(server, page)
        self._enter_fs(page)
        self._exit_fs(page)
        position = page.evaluate("""
            getComputedStyle(document.getElementById('subtitle-overlay')).position
        """)
        assert position != "fixed"

    def test_f_key_calls_toggle_fullscreen(self, server, page):
        """Pressing F should call SPA.toggleFullscreen."""
        self._goto_preview(server, page)
        # Track if toggleFullscreen was called
        page.evaluate("window._fsCalled = false; SPA.toggleFullscreen = function() { window._fsCalled = true; }")
        page.keyboard.press("f")
        page.wait_for_timeout(200)
        assert page.evaluate("window._fsCalled") is True

    def test_f_key_guarded_by_input_check(self, server, page):
        """Keyboard handler should check for INPUT/TEXTAREA before F key."""
        self._goto_preview(server, page)
        # Verify the keyboard handler has INPUT guard before F key handling
        # by inspecting the actual JS source order
        guard_ok = page.evaluate("""() => {
            var src = document.documentElement.outerHTML;
            var guardPos = src.indexOf("e.target.tagName === 'INPUT'");
            var fKeyPos = src.indexOf("'f' || e.key === 'F'");
            return guardPos > 0 && fKeyPos > 0 && guardPos < fKeyPos;
        }""")
        assert guard_ok, "INPUT guard must appear before F key handler"

    def test_fullscreen_button_has_title(self, server, page):
        """Fullscreen button should have a title/tooltip."""
        self._goto_preview(server, page)
        title = page.locator("#btn-fullscreen").get_attribute("title")
        assert title is not None and len(title) > 0

    def test_player_iframe_not_dark_color_scheme(self, server, page):
        """Regression: the Vimeo player iframe must not inherit color-scheme: dark.

        In dark theme the page sets `color-scheme: dark`, which a Vimeo
        <iframe> inherits. The Vimeo player reacts to a dark scheme by
        painting an opaque WHITE letterbox — so in fullscreen the surround
        turns white instead of black. The player iframe must override
        color-scheme so the player stays transparent and the letterbox shows
        the iframe's own (theme-coloured) background instead.
        """
        self._goto_preview(server, page)
        color_scheme = page.evaluate(
            """() => {
                document.documentElement.setAttribute('data-theme', 'dark');
                var wrap = document.querySelector('.video-wrap');
                var probe = document.createElement('iframe');
                wrap.appendChild(probe);
                var cs = getComputedStyle(probe)
                    .getPropertyValue('color-scheme').trim();
                probe.remove();
                return cs;
            }"""
        )
        assert color_scheme != "dark", (
            f"player iframe inherited color-scheme '{color_scheme}' — "
            "Vimeo paints a white letterbox in fullscreen when the scheme is dark"
        )

    def test_player_iframe_letterbox_tracks_theme(self, server, page):
        """The player iframe's letterbox follows the theme: black in dark,
        white in light. The Vimeo player is transparent, so the iframe's own
        background is what shows in the fullscreen letterbox.
        """
        self._goto_preview(server, page)
        colors = page.evaluate(
            """() => {
                var wrap = document.querySelector('.video-wrap');
                function bgFor(theme) {
                    document.documentElement.setAttribute('data-theme', theme);
                    var probe = document.createElement('iframe');
                    probe.src = 'x';  // non-empty: avoid the transparent override
                    wrap.appendChild(probe);
                    var bg = getComputedStyle(probe).backgroundColor;
                    probe.remove();
                    return bg;
                }
                return { dark: bgFor('dark'), light: bgFor('light') };
            }"""
        )
        assert colors["dark"] == "rgb(0, 0, 0)", f"dark-theme letterbox should be black, got {colors['dark']}"
        assert colors["light"] == "rgb(255, 255, 255)", f"light-theme letterbox should be white, got {colors['light']}"


class TestReviewModeToggle:
    """Tests for transcript/subtitle mode toggle in review page (expert mode)."""

    def _goto_review_expert(self, server, page):
        """Navigate to review page with expert mode enabled."""
        goto_spa(page, server)
        page.evaluate("localStorage.setItem('sy_expert_mode', '1'); expertMode = true; applyExpertMode();")
        page.evaluate("location.hash = '#/review/2001-01-01_Test-Talk'")
        page.wait_for_function("document.querySelectorAll('.cell').length > 0", timeout=10000)

    def test_switch_review_mode_function_exists(self, server, page):
        """SPA.switchReviewMode should be defined."""
        self._goto_review_expert(server, page)
        assert page.evaluate("typeof SPA.switchReviewMode === 'function'")

    def test_default_mode_is_transcript(self, server, page):
        """Review page should default to transcript mode."""
        self._goto_review_expert(server, page)
        mode = page.evaluate("reviewState.mode || 'transcript'")
        assert mode == "transcript"

    def test_mode_toggle_visible_in_expert(self, server, page):
        """Mode toggle should be visible and have SRT options in expert mode."""
        self._goto_review_expert(server, page)
        sel = page.locator("#review-mode-select")
        assert sel.count() == 1
        # Must be actually visible (display != none)
        display = page.evaluate("getComputedStyle(document.getElementById('review-mode-select')).display")
        assert display != "none", f"Mode selector should be visible, got display={display}"
        # Must have at least 2 options (transcript + at least one SRT video)
        opts = page.evaluate("document.getElementById('review-mode-select').options.length")
        assert opts >= 2, f"Expected at least 2 options (transcript + srt), got {opts}"

    def test_select_srt_option_switches_mode(self, server, page):
        """Selecting SRT option from dropdown should switch to SRT mode."""
        self._goto_review_expert(server, page)
        sel = page.locator("#review-mode-select")
        # Select the SRT option (second option)
        sel.select_option(index=1)
        page.wait_for_timeout(500)
        mode = page.evaluate("reviewState.mode")
        assert mode == "srt", f"Expected srt mode after select, got {mode}"

    def test_mode_toggle_visible_without_expert(self, server, page):
        """Mode toggle is available to all users (not expert-only). When a
        talk has at least one SRT-capable video, the selector must be
        visible in non-expert mode too."""
        goto_spa(page, server)
        page.evaluate("localStorage.removeItem('sy_expert_mode')")
        page.goto(f"{server}{SPA_URL}#/review/2001-01-01_Test-Talk")
        page.wait_for_function(
            "reviewState && reviewState.rightParas && reviewState.rightParas.length > 0",
            timeout=10000,
        )
        visible = page.evaluate("""() => {
            var el = document.querySelector('#review-mode-select');
            return el ? getComputedStyle(el).display !== 'none' : false;
        }""")
        assert visible is True
        # And it must have the SRT options populated
        opts = page.evaluate("document.getElementById('review-mode-select').options.length")
        assert opts >= 2

    def test_mode_toggle_hidden_when_no_srt_videos(self, server, page):
        """If the talk has no SRT-capable video, there's nothing to toggle
        to — the selector should stay hidden."""
        goto_spa(page, server)
        # Navigate to No-Uk which is early-stage (no uk.srt)
        page.goto(f"{server}{SPA_URL}#/review/2001-01-01_No-Uk")
        page.wait_for_timeout(500)
        visible = page.evaluate("""() => {
            var el = document.querySelector('#review-mode-select');
            if (!el) return false;
            return getComputedStyle(el).display !== 'none';
        }""")
        assert visible is False

    def test_switch_to_srt_mode_loads_subtitles(self, server, page):
        """Switching to SRT mode should load SRT files and show time-aligned grid."""
        self._goto_review_expert(server, page)
        page.evaluate("SPA.switchReviewMode('srt', 'Test-Video')")
        page.wait_for_timeout(500)
        mode = page.evaluate("reviewState.mode")
        assert mode == "srt"

    def test_srt_mode_shows_timecodes(self, server, page):
        """SRT mode should display timecodes in the grid cells."""
        self._goto_review_expert(server, page)
        page.evaluate("SPA.switchReviewMode('srt', 'Test-Video')")
        page.wait_for_timeout(500)
        # Grid should contain timecode text (HH:MM:SS format)
        html = page.locator("#review-grid").inner_html()
        assert "00:0" in html, "Grid should show timecodes in SRT mode"

    def test_srt_mode_persists_in_localstorage(self, server, page):
        """Selected review mode should persist per-talk in localStorage."""
        self._goto_review_expert(server, page)
        page.evaluate("SPA.switchReviewMode('srt', 'Test-Video')")
        page.wait_for_timeout(300)
        saved = page.evaluate("localStorage.getItem('sy_review_mode_2001-01-01_Test-Talk')")
        assert saved is not None
        assert "srt" in saved

    def test_switch_srt_lang_function_exists(self, server, page):
        """SPA.switchSrtLang should be defined."""
        self._goto_review_expert(server, page)
        assert page.evaluate("typeof SPA.switchSrtLang === 'function'")

    def test_switch_srt_lang_reloads_grid(self, server, page):
        """switchSrtLang should reload and re-render the SRT grid."""
        self._goto_review_expert(server, page)
        page.evaluate("SPA.switchReviewMode('srt', 'Test-Video')")
        page.wait_for_timeout(500)
        assert page.evaluate("reviewState.mode") == "srt"
        page.evaluate("SPA.switchSrtLang('right', 'uk')")
        page.wait_for_timeout(500)
        html = page.locator("#review-grid").inner_html()
        assert "00:0" in html, "Grid should still show timecodes after lang switch"

    def test_switch_srt_lang_updates_column_header(self, server, page):
        """switchSrtLang should update the column header text."""
        self._goto_review_expert(server, page)
        page.evaluate("SPA.switchReviewMode('srt', 'Test-Video')")
        page.wait_for_timeout(500)
        # Store srtLeftLang and srtRightLang in reviewState
        assert page.evaluate("reviewState.srtLeftLang") == "en"
        assert page.evaluate("reviewState.srtRightLang") == "uk"
        # Column header should reflect current SRT language
        right_text = page.locator("#col-header-right").text_content()
        assert "Ukrainian" in right_text

    def test_issue_body_links_to_srt_in_srt_mode(self, server, page):
        """Create Issue body should reference SRT file, not transcript, in SRT mode."""
        self._goto_review_expert(server, page)
        page.evaluate("SPA.switchReviewMode('srt', 'Test-Video')")
        page.wait_for_timeout(500)
        # Override window.open to capture URL
        page.evaluate("window._openedUrl = null; window.open = function(u) { window._openedUrl = u; }")
        page.evaluate("SPA.createReviewIssue()")
        page.wait_for_timeout(300)
        url = page.evaluate("window._openedUrl || ''")
        assert "uk.srt" in url, f"Issue URL should reference uk.srt in SRT mode, got: {url[:200]}"
        assert "Test-Video" in url, f"Issue URL should reference video slug, got: {url[:200]}"

    def test_editor_opens_srt_in_srt_mode(self, server, page):
        """Open Editor should link to SRT file in SRT mode."""
        self._goto_review_expert(server, page)
        page.evaluate("SPA.switchReviewMode('srt', 'Test-Video')")
        page.wait_for_timeout(500)
        page.evaluate("window._openedUrl = null; window.open = function(u) { window._openedUrl = u; }")
        page.evaluate("SPA.openEditor()")
        page.wait_for_timeout(300)
        url = page.evaluate("window._openedUrl || ''")
        assert "uk.srt" in url, f"Editor URL should open uk.srt in SRT mode, got: {url}"
        assert "Test-Video" in url, f"Editor URL should reference video slug, got: {url}"

    def test_issue_body_links_to_transcript_in_transcript_mode(self, server, page):
        """Create Issue body should reference transcript in transcript mode."""
        self._goto_review_expert(server, page)
        page.evaluate("window._openedUrl = null; window.open = function(u) { window._openedUrl = u; }")
        page.evaluate("SPA.createReviewIssue()")
        page.wait_for_timeout(300)
        url = page.evaluate("window._openedUrl || ''")
        assert "transcript_uk.txt" in url, f"Issue URL should reference transcript in transcript mode, got: {url[:200]}"

    def test_issue_body_uses_timecodes_in_srt_mode(self, server, page):
        """Issue body should use timecodes instead of P-numbers in SRT mode."""
        self._goto_review_expert(server, page)
        page.evaluate("SPA.switchReviewMode('srt', 'Test-Video')")
        page.wait_for_timeout(500)
        # Mark first block
        page.evaluate("reviewState.marks[0] = 'test'; saveReview()")
        page.evaluate("window._openedUrl = null; window.open = function(u) { window._openedUrl = u; }")
        page.evaluate("SPA.createReviewIssue()")
        page.wait_for_timeout(300)
        body = page.evaluate("decodeURIComponent(window._openedUrl || '')")
        assert "00:0" in body, f"Issue body should use timecodes in SRT mode, got: {body[:300]}"

    def test_srt_cell_shows_actual_block_timecode(self, server, page):
        """Each SRT cell must show its own block's timecode, not alignment slot boundaries.

        EN block 1: 00:00:01,000 --> 00:00:04,000
        UK block 1: 00:00:01,000 --> 00:00:05,000
        The UK cell's label must show 00:00:01 - 00:00:05 (the UK block's actual end),
        not 00:00:01 - 00:00:04 (slot boundary clipped by EN block 1 end).
        """
        self._goto_review_expert(server, page)
        page.evaluate("SPA.switchReviewMode('srt', 'Test-Video')")
        page.wait_for_timeout(500)
        # First UK cell should show the UK block's real timecode (00:01 - 00:05)
        first_uk_label = page.evaluate("document.querySelector('.cell.uk .cell-label').textContent")
        assert "00:01" in first_uk_label, f"Expected UK block start, got: {first_uk_label}"
        assert "00:05" in first_uk_label, f"Expected UK block real end (00:05), got: {first_uk_label}"
        # First EN cell should show EN block's real timecode (00:01 - 00:04)
        first_en_label = page.evaluate("document.querySelector('.cell.en .cell-label').textContent")
        assert "00:01" in first_en_label, f"Expected EN block start, got: {first_en_label}"
        assert "00:04" in first_en_label, f"Expected EN block real end (00:04), got: {first_en_label}"

    def test_transcript_clipboard_is_original_with_edits_applied(self, server, page):
        """Open Editor in transcript mode: clipboard contains the full original file
        with only the edits substituted in place."""
        self._goto_review_expert(server, page)
        page.evaluate("""
            window._clipText = '';
            navigator.clipboard.writeText = function(t) { window._clipText = t; return Promise.resolve(); };
            window.alert = function() {};
            window.open = function() {};
        """)
        # Edit only paragraph 0; leave paragraph 1 untouched
        page.evaluate("reviewState.edits[0] = 'ВІДРЕДАГОВАНИЙ ПЕРШИЙ'; saveReview()")
        page.evaluate("SPA.openEditor()")
        page.wait_for_timeout(300)
        clip = page.evaluate("window._clipText || ''")
        # The header from SAMPLE_UK
        assert "Мова промови: англійська" in clip, f"Clipboard missing original header: {clip[:400]}"
        # The edited paragraph
        assert "ВІДРЕДАГОВАНИЙ ПЕРШИЙ" in clip, f"Clipboard missing edited text: {clip[:400]}"
        # The unedited paragraph (preserved verbatim)
        assert "Другий абзац." in clip, f"Clipboard missing unedited paragraph: {clip[:400]}"
        # The original text of paragraph 0 must be gone (replaced)
        assert "Перший абзац." not in clip, f"Clipboard still contains pre-edit text: {clip[:400]}"

    def test_transcript_issue_body_shows_edits_and_links_full_file(self, server, page):
        """Create Issue in transcript mode: body links to transcript file and the
        Suggested edits section shows Before/After only for edited rows."""
        self._goto_review_expert(server, page)
        page.evaluate("reviewState.edits[0] = 'EDITED_TRANSCRIPT'; saveReview()")
        page.evaluate("window._openedUrl = null; window.open = function(u) { window._openedUrl = u; }")
        page.evaluate("SPA.createReviewIssue()")
        page.wait_for_timeout(300)
        body = page.evaluate("decodeURIComponent(window._openedUrl || '')")
        assert "transcript_uk.txt" in body, "Body must reference transcript file"
        assert "Suggested edits" in body, "Body must contain edits section"
        assert "EDITED_TRANSCRIPT" in body, "Body must contain edited text"
        # Original (Before) for the edited row should still be present
        assert "Перший абзац." in body, "Body must include the Before text for the edited row"
        # Unedited row should NOT appear in the Suggested edits section
        assert "Другий абзац" not in body, f"Unedited paragraph leaked into body: {body[:400]}"

    def test_srt_clipboard_is_original_with_edits_applied(self, server, page):
        """Open Editor in SRT mode: clipboard contains the full original SRT
        with only the edited block's text substituted."""
        self._goto_review_expert(server, page)
        page.evaluate("SPA.switchReviewMode('srt', 'Test-Video')")
        page.wait_for_timeout(500)
        page.evaluate("""
            window._clipText = '';
            navigator.clipboard.writeText = function(t) { window._clipText = t; return Promise.resolve(); };
            window.alert = function() {};
            window.open = function() {};
        """)
        # Edit the row whose UK text is "Перший субтитр"
        page.evaluate("""
            for (var i = 0; i < reviewState.rightParas.length; i++) {
              if (reviewState.rightParas[i] === 'Перший субтитр') {
                reviewState.edits[i] = 'ВІДРЕДАГОВАНИЙ СУБТИТР';
                break;
              }
            }
            saveReview();
        """)
        page.evaluate("SPA.openEditor()")
        page.wait_for_timeout(300)
        clip = page.evaluate("window._clipText || ''")
        # Original block numbering and timecodes preserved
        assert "00:00:01,000 --> 00:00:05,000" in clip, f"Clipboard missing block 1 timecode: {clip[:500]}"
        assert "00:00:06,000 --> 00:00:10,000" in clip, f"Clipboard missing block 2 timecode: {clip[:500]}"
        # Edited text appears
        assert "ВІДРЕДАГОВАНИЙ СУБТИТР" in clip, f"Clipboard missing edited text: {clip[:500]}"
        # Other (unedited) block text preserved verbatim
        assert "Другий субтитр" in clip, f"Clipboard missing unedited block: {clip[:500]}"
        # Original text of the edited block is replaced
        assert "Перший субтитр" not in clip, f"Clipboard still contains pre-edit text: {clip[:500]}"

    def test_srt_issue_body_shows_edits_and_links_srt_file(self, server, page):
        """Create Issue in SRT mode: body links to SRT file and Suggested edits
        section shows Before/After only for edited blocks."""
        self._goto_review_expert(server, page)
        page.evaluate("SPA.switchReviewMode('srt', 'Test-Video')")
        page.wait_for_timeout(500)
        page.evaluate("""
            for (var i = 0; i < reviewState.rightParas.length; i++) {
              if (reviewState.rightParas[i] === 'Перший субтитр') {
                reviewState.edits[i] = 'EDITED_SUBTITLE';
                break;
              }
            }
            saveReview();
        """)
        page.evaluate("window._openedUrl = null; window.open = function(u) { window._openedUrl = u; }")
        page.evaluate("SPA.createReviewIssue()")
        page.wait_for_timeout(300)
        body = page.evaluate("decodeURIComponent(window._openedUrl || '')")
        assert "uk.srt" in body, "Body must reference the SRT file"
        assert "Test-Video" in body, "Body must reference video slug"
        assert "Suggested edits" in body, "Body must contain edits section"
        assert "EDITED_SUBTITLE" in body, "Body must contain edited text"
        # Before text of the edited block
        assert "Перший субтитр" in body, "Body must include Before text for edited block"
        # Other (unedited) block must NOT leak into Suggested edits
        assert "Другий субтитр" not in body, f"Unedited block leaked into body: {body[:500]}"

    def test_switch_back_to_transcript(self, server, page):
        """Switching back to transcript mode should show paragraphs."""
        self._goto_review_expert(server, page)
        page.evaluate("SPA.switchReviewMode('srt', 'Test-Video')")
        page.wait_for_timeout(300)
        page.evaluate("SPA.switchReviewMode('transcript')")
        page.wait_for_timeout(500)
        mode = page.evaluate("reviewState.mode")
        assert mode == "transcript"
        # Should show paragraph content
        html = page.locator("#review-grid").inner_html()
        assert "P1" in html


class TestReviewCellStructure:
    """Review cell label/text separation — labels must not be editable."""

    def _goto_review(self, server, page):
        goto_spa(page, server, "#/review/2001-01-01_Test-Talk")
        page.wait_for_function("document.querySelectorAll('.cell.uk').length > 0", timeout=10000)

    def test_label_is_outside_editable_area(self, server, page):
        """Cell label (P1, timecode) should not be inside contentEditable element."""
        self._goto_review(server, page)
        # The contentEditable element should NOT contain the label
        has_label_inside = page.evaluate("""() => {
            var cell = document.querySelector('.cell.uk[contenteditable="true"], .cell.uk [contenteditable="true"]');
            if (!cell) return false;
            return /^P\\d/.test(cell.innerText);
        }""")
        assert has_label_inside is False, "Label P1 should not be inside contentEditable area"

    def test_label_is_not_contenteditable(self, server, page):
        """Cell label element must not be contentEditable."""
        self._goto_review(server, page)
        editable = page.evaluate("""() => {
            var label = document.querySelector('.cell.uk .cell-label');
            if (!label) return 'no .cell-label found';
            return label.isContentEditable;
        }""")
        assert editable is False

    def test_text_area_is_contenteditable(self, server, page):
        """Cell text area must be contentEditable."""
        self._goto_review(server, page)
        editable = page.evaluate("""() => {
            var text = document.querySelector('.cell.uk .cell-text');
            if (!text) return false;
            return text.isContentEditable;
        }""")
        assert editable is True

    def test_editing_text_does_not_affect_label(self, server, page):
        """Editing text should not change the label."""
        self._goto_review(server, page)
        # Get original label
        label_before = page.evaluate("""
            document.querySelector('.cell.uk .cell-label').textContent
        """)
        # Edit the text
        page.locator(".cell.uk .cell-text").first.click()
        page.keyboard.type(" test")
        page.wait_for_timeout(200)
        label_after = page.evaluate("""
            document.querySelector('.cell.uk .cell-label').textContent
        """)
        assert label_before == label_after


class TestReviewEditing:
    """Review page editing functionality tests."""

    def _goto_review(self, server, page):
        goto_spa(page, server, "#/review/2001-01-01_Test-Talk")
        page.wait_for_function("document.querySelectorAll('.cell.uk').length > 0", timeout=10000)

    def test_edit_marks_cell(self, server, page):
        """Editing a UK cell should add 'edited' class."""
        self._goto_review(server, page)
        cell = page.locator(".cell.uk").first
        cell.click()
        cell.press("End")
        cell.type(" edited")
        cell.press("Tab")
        page.wait_for_timeout(200)
        assert "edited" in (cell.get_attribute("class") or "")

    def test_edit_persists_to_localStorage(self, server, page):
        """Edits should be saved to localStorage."""
        self._goto_review(server, page)
        cell = page.locator(".cell.uk").first
        cell.click()
        cell.press("End")
        cell.type(" edited")
        cell.press("Tab")
        page.wait_for_timeout(200)
        data = page.evaluate("localStorage.getItem('review_2001-01-01_Test-Talk')")
        assert data is not None
        state = json.loads(data)
        assert "edits" in state

    def test_revert_btn_shows_count(self, server, page):
        """Revert-all button shows count suffix (N) after editing."""
        self._goto_review(server, page)
        cell = page.locator(".cell.uk").first
        cell.click()
        cell.press("End")
        cell.type(" edited")
        cell.press("Tab")
        page.wait_for_timeout(200)
        btn = page.locator("#btn-revert-all")
        assert btn.is_visible()
        assert "(1)" in (btn.text_content() or "")

    def test_uk_content(self, server, page):
        """UK cells should show translated content."""
        self._goto_review(server, page)
        text = page.locator(".cell.uk").first.text_content()
        assert "Перший абзац" in text

    def test_paragraph_numbers(self, server, page):
        """Cells should show paragraph numbers (P1, P2...)."""
        self._goto_review(server, page)
        text = page.locator(".cell.en").first.text_content()
        assert "P1" in text


class TestSearchFilter:
    """Tests for search, filter, and stats on index page."""

    def test_search_input_visible(self, server, page):
        """Search input should be visible after talks load."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        assert page.locator("#search-input").is_visible()

    def test_search_filters_talks(self, server, page):
        """Typing in search should filter visible talks."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        # Default filter: needs-review, Test-Talk visible
        before = page.locator(".talk-item").count()
        assert before >= 1
        # Search for something not matching
        page.fill("#search-input", "xyznonexistent")
        page.wait_for_timeout(300)
        assert page.locator(".talk-item").count() == 0
        # Search matching Test Talk
        page.fill("#search-input", "Test Talk")
        page.wait_for_timeout(300)
        assert page.locator(".talk-item").count() >= 1

    def test_normal_all_shows_reviewable_only(self, server, page):
        """Normal mode 'All' = needs-review + in-review (not pending/approved)."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        # Click "All" stat card
        page.locator(".stat-card", has_text="All").click()
        page.wait_for_timeout(300)
        all_count = page.locator(".talk-item").count()
        # Test-Talk is ready-for-review → visible; No-Uk is in-progress → hidden
        assert all_count == 1, f"Normal 'All' should show 1 reviewable talk, got {all_count}"

    def test_stat_cards_exist(self, server, page):
        """Normal mode shows 3 filter cards: All, Needs review, In review."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        assert page.locator(".stat-card").count() == 3

    def test_stat_card_shows_all_count(self, server, page):
        """'All' stat card shows reviewable count (needs-review + in-review)."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        card = page.locator(".stat-card[data-filter='all']")
        # Test-Talk = ready-for-review (1), No-Uk = in-progress (0)
        assert "1" in card.text_content()

    def test_stat_card_click_filters(self, server, page):
        """Clicking needs-review filter shows only ready-for-review talks."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        page.click(".stat-card[data-filter='needs-review']")
        page.wait_for_timeout(200)
        badges = page.locator(".review-badge").all()
        for badge in badges:
            assert "ready-for-review" in (badge.get_attribute("class") or "")

    def test_stat_card_toggle_off(self, server, page):
        """Clicking same stat card again should reset to 'all'."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        all_count = page.locator(".talk-item").count()
        page.click(".stat-card[data-filter='needs-review']")
        page.wait_for_timeout(200)
        page.click(".stat-card[data-filter='needs-review']")
        page.wait_for_timeout(200)
        assert page.locator(".talk-item").count() == all_count

    def test_stat_card_active_class(self, server, page):
        """Clicked stat card should get 'active' class."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        # Default is 'needs-review'; click 'in-review' (different card) to test active toggling
        page.click(".stat-card[data-filter='in-review']")
        page.wait_for_timeout(200)
        cls = page.locator(".stat-card[data-filter='in-review']").get_attribute("class")
        assert "active" in cls

    def test_search_updates_stat_counts(self, server, page):
        """Searching should update stat card numbers (filtered/total)."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        page.fill("#search-input", "Test")
        page.wait_for_timeout(300)
        # All card shows filtered/total with slash when search is active
        all_card = page.locator(".stat-card[data-filter='all']")
        text = all_card.text_content()
        assert "/" in text  # search mode shows "filtered/total"


class TestHashNavigation:
    """Tests for SPA hash-based routing."""

    def test_index_default(self, server, page):
        """Empty hash should show index view."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        assert page.locator("#view-index").get_attribute("class") == "view active"

    def test_navigate_index_to_preview(self, server, page):
        """Clicking preview link should navigate to preview view."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        page.click("a[href*='preview']")
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        assert "active" in (page.locator("#view-preview").get_attribute("class") or "")

    def test_back_link_from_preview(self, server, page):
        """Back link from preview should return to index."""
        goto_spa(page, server, "#/preview/2001-01-01_Test-Talk/Test-Video")
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        page.click("#view-preview a[href='#/']")
        page.wait_for_selector(".talk-item", timeout=10000)
        assert "active" in (page.locator("#view-index").get_attribute("class") or "")

    def test_navigate_index_to_review(self, server, page):
        """Clicking review link should navigate to review view."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        page.click("a.review-link")
        page.wait_for_function("document.querySelectorAll('.cell.en').length > 0", timeout=10000)
        assert "active" in (page.locator("#view-review").get_attribute("class") or "")

    def test_back_link_from_review(self, server, page):
        """Back link from review should return to index."""
        goto_spa(page, server, "#/review/2001-01-01_Test-Talk")
        page.wait_for_function("document.querySelectorAll('.cell.en').length > 0", timeout=10000)
        page.click("#view-review a[href='#/']")
        page.wait_for_selector(".talk-item", timeout=10000)
        assert "active" in (page.locator("#view-index").get_attribute("class") or "")

    def test_page_title_updates_preview(self, server, page):
        """Page title should update for preview view."""
        goto_spa(page, server, "#/preview/2001-01-01_Test-Talk/Test-Video")
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        assert "Preview" in page.title()

    def test_page_title_updates_review(self, server, page):
        """Page title should update for review view."""
        goto_spa(page, server, "#/review/2001-01-01_Test-Talk")
        page.wait_for_function("document.querySelectorAll('.cell.en').length > 0", timeout=10000)
        assert "Review" in page.title()

    def test_page_title_index(self, server, page):
        """Index page should have base title."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        assert page.title() == "SY Subtitles — Index"


class TestReviewStatus:
    """Tests for review status badges on the index page."""

    def test_status_badge_shown(self, server, page):
        """Talks should show status badges based on pipeline state."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        badges = page.locator(".review-badge")
        assert badges.count() >= 1

    def test_badge_links_to_issue(self, server, page):
        """Badge should link to the GitHub issue."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        badge = page.locator(".review-badge")
        href = badge.first.get_attribute("href")
        assert "/issues/42" in href

    def test_in_progress_badge(self, server, page, browser):
        """Talk with in-progress status should show reviewer name."""
        ctx = browser.new_context()
        pg = ctx.new_page()
        # Mock with in-progress status
        in_progress_status = {
            "version": 1,
            "updated_at": "2026-04-01T00:00:00Z",
            "talks": {
                "2001-01-01_Test-Talk": {
                    "status": "in-progress",
                    "reviewer": "YogiReviewer",
                    "issue_number": 42,
                    "updated_at": "2026-04-01T00:00:00Z",
                },
            },
        }
        pg.route(
            "**/api.github.com/**",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                headers={"ETag": '"test-etag"'},
                body=json.dumps(MOCK_TREE),
            ),
        )
        pg.route(
            "**/raw.githubusercontent.com/**/meta.yaml",
            lambda route: route.fulfill(status=200, content_type="text/plain", body=SAMPLE_META),
        )
        pg.route(
            "**/raw.githubusercontent.com/**/review-status.json",
            lambda route: route.fulfill(
                status=200, content_type="application/json", body=json.dumps(in_progress_status)
            ),
        )
        pg.route(
            "**/player.vimeo.com/api/player.js",
            lambda route: route.fulfill(status=200, content_type="application/javascript", body=""),
        )
        pg.add_init_script("localStorage.removeItem('sy_tree_cache__main');")
        pg.goto(f"{server}/index.html")
        # 'in-progress' review status maps to 'in-review' overall status,
        # visible under the 'in-review' filter (not the default 'needs-review')
        pg.wait_for_selector(".stat-card[data-filter='in-review']", timeout=10000)
        pg.click(".stat-card[data-filter='in-review']")
        pg.wait_for_selector(".talk-item", timeout=10000)
        badge = pg.locator(".review-badge.in-review")
        assert badge.count() >= 1
        assert "YogiReviewer" in badge.first.text_content()
        pg.close()
        ctx.close()

    def test_approved_badge(self, server, page, browser):
        """Talk with approved status should show green badge (visible in expert mode)."""
        ctx = browser.new_context()
        pg = ctx.new_page()
        approved_status = {
            "version": 1,
            "updated_at": "2026-04-01T00:00:00Z",
            "talks": {
                "2001-01-01_Test-Talk": {
                    "status": "approved",
                    "reviewer": "YogiReviewer",
                    "issue_number": 42,
                    "updated_at": "2026-04-01T00:00:00Z",
                },
            },
        }
        pg.route(
            "**/api.github.com/**",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                headers={"ETag": '"test-etag"'},
                body=json.dumps(MOCK_TREE),
            ),
        )
        pg.route(
            "**/raw.githubusercontent.com/**/meta.yaml",
            lambda route: route.fulfill(status=200, content_type="text/plain", body=SAMPLE_META),
        )
        pg.route(
            "**/raw.githubusercontent.com/**/review-status.json",
            lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(approved_status)),
        )
        pg.route(
            "**/player.vimeo.com/api/player.js",
            lambda route: route.fulfill(status=200, content_type="application/javascript", body=""),
        )
        # Approved talks only show in expert mode (not in normal mode filters)
        pg.add_init_script(
            "localStorage.removeItem('sy_tree_cache__main'); localStorage.setItem('sy_expert_mode', '1');"
        )
        pg.goto(f"{server}/index.html")
        # Expert mode default filter is 'pending'; switch to 'approved' to see approved talks
        pg.wait_for_selector(".stat-card[data-filter='approved']", timeout=10000)
        pg.click(".stat-card[data-filter='approved']")
        pg.wait_for_selector(".talk-item", timeout=10000)
        badge = pg.locator(".review-badge.approved")
        assert badge.count() >= 1
        assert "approved" in badge.first.text_content()
        pg.close()
        ctx.close()

    def test_no_status_file_graceful(self, server, page, browser):
        """Missing review-status.json should not break the page."""
        ctx = browser.new_context()
        pg = ctx.new_page()
        pg.route(
            "**/api.github.com/**",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                headers={"ETag": '"test-etag"'},
                body=json.dumps(MOCK_TREE),
            ),
        )
        pg.route(
            "**/raw.githubusercontent.com/**/meta.yaml",
            lambda route: route.fulfill(status=200, content_type="text/plain", body=SAMPLE_META),
        )
        pg.route(
            "**/raw.githubusercontent.com/**/review-status.json",
            lambda route: route.fulfill(status=404, body="Not found"),
        )
        pg.route(
            "**/player.vimeo.com/api/player.js",
            lambda route: route.fulfill(status=200, content_type="application/javascript", body=""),
        )
        # In expert mode (pending filter default) in-progress talks are visible
        pg.add_init_script(
            "localStorage.removeItem('sy_tree_cache__main'); localStorage.setItem('sy_expert_mode', '1');"
        )
        pg.goto(f"{server}/index.html")
        # Without review status, talks are in-progress → visible in expert mode pending filter
        pg.wait_for_selector(".talk-item", timeout=10000)
        # Page loads fine; badges present even without review status (in-progress badge shown)
        assert pg.locator(".talk-item").count() >= 1
        assert pg.locator(".review-badge").count() >= 1
        pg.close()
        ctx.close()

    def test_default_filter_shows_only_ready(self, server, page):
        """Default filter (needs-review) shows only ready-for-review talks."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        items = page.locator(".talk-item").all()
        # Test-Talk is ready-for-review (srt+uk+issue), should be visible
        texts = [item.text_content() for item in items]
        assert any("Test Talk" in t for t in texts), f"Test Talk should be visible: {texts}"
        # No-Uk is in-progress, should NOT be visible in needs-review filter
        assert not any("No-Uk" in t or "2002" in t for t in texts), f"No-Uk should be hidden: {texts}"

    def test_ready_for_review_requires_only_srt_and_issue(self, server, page):
        """Per relaxed criteria: a talk with SRT + GitHub issue is
        ready-for-review even without transcript_uk.txt or review_report.md.
        Transcript and proofreading are optional quality-of-life artefacts,
        not gating requirements."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        # Call getOverallStatus directly with constructed stage flags.
        status = page.evaluate("""() => getOverallStatus(
            { srt: true, translated: false, reviewed: false, hasIssue: true },
            null
        )""")
        assert status == "ready-for-review"

    def test_srt_only_without_issue_still_in_progress(self, server, page):
        """SRT alone is not enough — without a review issue the talk stays
        in-progress. The issue is what tells reviewers where to report."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        status = page.evaluate("""() => getOverallStatus(
            { srt: true, translated: true, reviewed: true, hasIssue: false },
            null
        )""")
        assert status == "in-progress"

    def test_transcript_without_srt_stays_in_progress(self, server, page):
        """SRTs are required: transcript alone (with issue) is not enough."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        status = page.evaluate("""() => getOverallStatus(
            { srt: false, translated: true, reviewed: true, hasIssue: true },
            null
        )""")
        assert status == "in-progress"


class TestCaching:
    def test_cache_written_to_localStorage(self, server, page):
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        cache = page.evaluate("localStorage.getItem('sy_tree_cache__main')")
        assert cache is not None
        data = json.loads(cache)
        assert "talks" in data

    def test_cache_schema_stored(self, server, page):
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        cache = page.evaluate("localStorage.getItem('sy_tree_cache__main')")
        assert cache is not None
        import json

        data = json.loads(cache)
        assert "_schema" in data

    def test_cached_manifest_has_hasSrt(self, server, page):
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        cache = json.loads(page.evaluate("localStorage.getItem('sy_tree_cache__main')"))
        talk = next(t for t in cache["talks"] if t["id"] == "2001-01-01_Test-Talk")
        video = next(v for v in talk["videos"] if v["slug"] == "Test-Video")
        assert video["hasSrt"] is True
        video2 = next(v for v in talk["videos"] if v["slug"] == "Test-Video-2")
        assert video2["hasSrt"] is True

    def test_cached_manifest_has_pipeline_fields(self, server, page):
        """Manifest should track whisper and review_report for pipeline."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        cache = json.loads(page.evaluate("localStorage.getItem('sy_tree_cache__main')"))
        talk = next(t for t in cache["talks"] if t["id"] == "2001-01-01_Test-Talk")
        assert talk["hasReviewReport"] is True
        assert "Test-Video" in talk["_whisperSlugs"]
        assert "Test-Video-2" in talk["_whisperSlugs"]
        # No-Uk talk has no pipeline data
        no_uk = next(t for t in cache["talks"] if t["id"] == "2002-01-01_No-Uk")
        assert no_uk["hasReviewReport"] is False
        assert no_uk["_whisperSlugs"] == []


MOCK_BRANCHES = [
    {"name": "main", "commit": {"sha": "abc123"}},
    {"name": "fix/review-edits", "commit": {"sha": "def456"}},
    {"name": "feature/new-talk", "commit": {"sha": "ghi789"}},
]


class TestBranchSelector:
    def test_default_branch_is_main(self, server, page):
        """Without ?branch= param, BRANCH should be 'main'."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        branch = page.evaluate("BRANCH")
        assert branch == "main"

    def test_branch_label_shows_current(self, server, page):
        """Branch button displays current branch name."""
        goto_spa(page, server)
        page.wait_for_selector("#branch-btn", timeout=10000)
        text = page.locator("#branch-btn").text_content()
        assert "main" in text

    def test_no_branches_api_call_on_load(self, server, page):
        """No /branches API call should be made on initial page load."""
        api_calls = []
        page.on("request", lambda req: api_calls.append(req.url) if "/branches" in req.url else None)
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        assert not any("/branches" in url for url in api_calls)

    def test_click_fetches_branches(self, server, page):
        """Clicking branch button fetches branches from API."""
        page.route(
            "**/api.github.com/repos/**/branches*",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(MOCK_BRANCHES),
            ),
        )
        goto_spa(page, server)
        page.wait_for_selector("#branch-btn", timeout=10000)
        page.locator("#branch-btn").click()
        page.wait_for_selector("#branch-dropdown.open div.active", timeout=5000)
        items = page.locator("#branch-dropdown div").count()
        assert items == 3

    def test_dropdown_shows_branch_names(self, server, page):
        """Dropdown lists all branch names from API response."""
        page.route(
            "**/api.github.com/repos/**/branches*",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(MOCK_BRANCHES),
            ),
        )
        goto_spa(page, server)
        page.wait_for_selector("#branch-btn", timeout=10000)
        page.locator("#branch-btn").click()
        page.wait_for_selector("#branch-dropdown.open div.active", timeout=5000)
        texts = [el.text_content() for el in page.locator("#branch-dropdown div").all()]
        assert "main" in texts
        assert "fix/review-edits" in texts
        assert "feature/new-talk" in texts

    def test_current_branch_marked_active(self, server, page):
        """Current branch has .active class in dropdown."""
        page.route(
            "**/api.github.com/repos/**/branches*",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(MOCK_BRANCHES),
            ),
        )
        goto_spa(page, server)
        page.wait_for_selector("#branch-btn", timeout=10000)
        page.locator("#branch-btn").click()
        page.wait_for_selector("#branch-dropdown.open div.active", timeout=5000)
        active = page.locator("#branch-dropdown div.active")
        assert active.count() == 1
        assert active.text_content() == "main"

    def test_select_branch_changes_url(self, server, page):
        """Selecting a branch navigates to URL with ?branch= param."""
        page.route(
            "**/api.github.com/repos/**/branches*",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(MOCK_BRANCHES),
            ),
        )
        goto_spa(page, server)
        page.wait_for_selector("#branch-btn", timeout=10000)
        page.locator("#branch-btn").click()
        page.wait_for_selector("#branch-dropdown.open div.active", timeout=5000)
        # Click the second branch
        page.locator(".branch-dropdown div", has_text="fix/review-edits").click()
        page.wait_for_load_state("load")
        assert "branch=fix%2Freview-edits" in page.url or "branch=fix/review-edits" in page.url

    def test_branch_from_url_param(self, server, page):
        """?branch=dev sets BRANCH variable to 'dev'."""
        goto_spa(page, server, hash="")
        # Navigate with branch param
        page.goto(f"{server}{SPA_URL}?branch=dev")
        page.wait_for_selector("#branch-btn", timeout=10000)
        branch = page.evaluate("BRANCH")
        assert branch == "dev"

    def test_branch_param_used_in_api_calls(self, server, page):
        """API calls use the branch from URL param."""
        tree_urls = []
        page.route(
            "**/api.github.com/**",
            lambda route: (
                tree_urls.append(route.request.url),
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    headers={"ETag": '"test-etag-dev"'},
                    body=json.dumps(MOCK_TREE),
                ),
            )[-1],
        )
        page.route(
            "**/raw.githubusercontent.com/**/meta.yaml",
            lambda route: route.fulfill(status=200, content_type="text/plain", body=SAMPLE_META),
        )
        page.route(
            "**/raw.githubusercontent.com/**/review-status.json",
            lambda route: route.fulfill(
                status=200, content_type="application/json", body=json.dumps(MOCK_REVIEW_STATUS)
            ),
        )
        page.route(
            "**/player.vimeo.com/api/player.js",
            lambda route: route.fulfill(status=200, content_type="application/javascript", body=""),
        )
        page.add_init_script("localStorage.removeItem('sy_tree_cache__dev');")
        page.goto(f"{server}{SPA_URL}?branch=dev")
        page.wait_for_selector(".talk-item", timeout=10000)
        assert any("trees/dev" in url for url in tree_urls)

    def test_cache_key_includes_branch(self, server, page):
        """Cache uses branch-specific localStorage key."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        cache = page.evaluate("localStorage.getItem('sy_tree_cache__main')")
        assert cache is not None
        # Other branch key should be null
        other = page.evaluate("localStorage.getItem('sy_tree_cache__dev')")
        assert other is None

    def test_non_main_visual_indicator(self, server, page):
        """Branch button has .non-main class when not on main."""
        page.goto(f"{server}{SPA_URL}?branch=dev")
        page.wait_for_selector("#branch-btn", timeout=10000)
        cls = page.locator("#branch-btn").get_attribute("class")
        assert "non-main" in cls

    def test_main_no_non_main_class(self, server, page):
        """Branch button does NOT have .non-main on main."""
        goto_spa(page, server)
        page.wait_for_selector("#branch-btn", timeout=10000)
        cls = page.locator("#branch-btn").get_attribute("class")
        assert "non-main" not in cls

    def test_close_dropdown_on_outside_click(self, server, page):
        """Clicking outside the dropdown closes it."""
        page.route(
            "**/api.github.com/repos/**/branches*",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(MOCK_BRANCHES),
            ),
        )
        goto_spa(page, server)
        page.wait_for_selector("#branch-btn", timeout=10000)
        page.locator("#branch-btn").click()
        page.wait_for_selector("#branch-dropdown.open div.active", timeout=5000)
        # Click on the body
        page.locator("body").click(position={"x": 10, "y": 10})
        page.wait_for_timeout(300)
        assert not page.locator("#branch-dropdown.open").is_visible()

    def test_deep_link_with_branch(self, server, page):
        """Direct URL with ?branch= and hash route works."""
        page.route(
            "**/raw.githubusercontent.com/**/uk.srt",
            lambda route: route.fulfill(status=200, content_type="text/plain", body=SAMPLE_SRT),
        )
        page.route(
            "**/player.vimeo.com/api/player.js",
            lambda route: route.fulfill(status=200, content_type="application/javascript", body=""),
        )
        page.goto(f"{server}{SPA_URL}?branch=dev#/preview/2001-01-01_Test-Talk/Test-Video")
        page.wait_for_selector("#branch-btn", timeout=10000)
        assert page.evaluate("BRANCH") == "dev"
        # Preview view should be active
        assert page.locator("#view-preview.active").count() == 1

    def test_branch_preserved_in_preview_back_link(self, server, page):
        """Back link from preview preserves ?branch= param."""
        page.goto(f"{server}{SPA_URL}?branch=dev#/preview/2001-01-01_Test-Talk/Test-Video")
        page.wait_for_selector("#branch-btn", timeout=10000)
        btn_text = page.locator("#branch-btn").text_content()
        assert "dev" in btn_text

    def test_branch_cache_isolated_between_branches(self, server, page, browser):
        """Different branches write to separate cache keys."""

        def make_page(ctx):
            pg = ctx.new_page()
            pg.route(
                "**/api.github.com/**",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    headers={"ETag": '"etag-test"'},
                    body=json.dumps(MOCK_TREE),
                ),
            )
            pg.route(
                "**/raw.githubusercontent.com/**/meta.yaml",
                lambda route: route.fulfill(status=200, content_type="text/plain", body=SAMPLE_META),
            )
            pg.route(
                "**/raw.githubusercontent.com/**/review-status.json",
                lambda route: route.fulfill(
                    status=200, content_type="application/json", body=json.dumps(MOCK_REVIEW_STATUS)
                ),
            )
            pg.route(
                "**/player.vimeo.com/api/player.js",
                lambda route: route.fulfill(status=200, content_type="application/javascript", body=""),
            )
            return pg

        ctx = browser.new_context()
        # Clear all caches
        pg = make_page(ctx)
        pg.add_init_script(
            "localStorage.removeItem('sy_tree_cache__main'); localStorage.removeItem('sy_tree_cache__dev');"
        )
        pg.goto(f"{server}{SPA_URL}")
        pg.wait_for_selector(".talk-item", timeout=10000)
        assert pg.evaluate("localStorage.getItem('sy_tree_cache__main')") is not None
        assert pg.evaluate("localStorage.getItem('sy_tree_cache__dev')") is None
        pg.close()

        # Load dev branch in a fresh page (no init_script clearing main cache)
        pg2 = make_page(ctx)
        pg2.goto(f"{server}{SPA_URL}?branch=dev")
        pg2.wait_for_selector(".talk-item", timeout=10000)
        assert pg2.evaluate("localStorage.getItem('sy_tree_cache__dev')") is not None
        assert pg2.evaluate("localStorage.getItem('sy_tree_cache__main')") is not None
        pg2.close()
        ctx.close()

    def test_raw_urls_use_branch(self, server, page):
        """Fetch calls for SRT/transcripts use the correct branch in URL."""
        raw_urls = []
        # Register catch-all first; specific routes registered last take priority (LIFO)
        page.route(
            "**/raw.githubusercontent.com/**",
            lambda route: (
                raw_urls.append(route.request.url),
                route.fulfill(status=200, content_type="text/plain", body=SAMPLE_EN),
            )[-1],
        )
        page.route(
            "**/raw.githubusercontent.com/**/meta.yaml",
            lambda route: (
                raw_urls.append(route.request.url),
                route.fulfill(status=200, content_type="text/plain", body=SAMPLE_META),
            )[-1],
        )
        page.route(
            "**/raw.githubusercontent.com/**/review-status.json",
            lambda route: (
                raw_urls.append(route.request.url),
                route.fulfill(status=200, content_type="application/json", body=json.dumps(MOCK_REVIEW_STATUS)),
            )[-1],
        )
        page.route(
            "**/api.github.com/**",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                headers={"ETag": '"etag-feat"'},
                body=json.dumps(MOCK_TREE),
            ),
        )
        page.route(
            "**/player.vimeo.com/api/player.js",
            lambda route: route.fulfill(status=200, content_type="application/javascript", body=""),
        )
        page.add_init_script("localStorage.removeItem('sy_tree_cache__feature/test');")
        page.goto(f"{server}{SPA_URL}?branch=feature/test")
        page.wait_for_selector(".talk-item", timeout=10000)
        assert any("feature/test" in url for url in raw_urls)

    def test_markers_persist_across_branch_switch(self, server, page, browser):
        """Preview markers survive branch switch (localStorage key is branch-independent)."""

        def make_page(ctx):
            pg = ctx.new_page()
            pg.route(
                "**/api.github.com/**",
                lambda route: route.fulfill(
                    status=200, content_type="application/json", headers={"ETag": '"etag"'}, body=json.dumps(MOCK_TREE)
                ),
            )
            pg.route(
                "**/raw.githubusercontent.com/**/meta.yaml",
                lambda route: route.fulfill(status=200, content_type="text/plain", body=SAMPLE_META),
            )
            pg.route(
                "**/raw.githubusercontent.com/**/uk.srt",
                lambda route: route.fulfill(status=200, content_type="text/plain", body=SAMPLE_SRT),
            )
            pg.route(
                "**/raw.githubusercontent.com/**/review-status.json",
                lambda route: route.fulfill(
                    status=200, content_type="application/json", body=json.dumps(MOCK_REVIEW_STATUS)
                ),
            )
            pg.route(
                "**/player.vimeo.com/api/player.js",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/javascript",
                    body=(Path(__file__).parent / "fixtures" / "mock_vimeo_player.js").read_text(),
                ),
            )
            return pg

        ctx = browser.new_context()

        # Add a marker on main
        pg = make_page(ctx)
        pg.add_init_script("localStorage.clear();")
        pg.goto(f"{server}{SPA_URL}#/preview/2001-01-01_Test-Talk/Test-Video")
        pg.wait_for_selector("#subtitle-overlay", timeout=10000)
        pg.click('.preview-mode-toggle [data-mode="marker"]')
        pg.click("#btn-mark")
        pg.wait_for_selector(".marker-item", timeout=5000)
        assert pg.locator(".marker-item").count() == 1
        pg.close()

        # Switch to dev branch — marker should still be there
        pg2 = make_page(ctx)
        pg2.goto(f"{server}{SPA_URL}?branch=dev#/preview/2001-01-01_Test-Talk/Test-Video")
        pg2.wait_for_selector("#subtitle-overlay", timeout=10000)
        pg2.wait_for_timeout(500)
        assert pg2.locator(".marker-item").count() == 1
        pg2.close()
        ctx.close()

    def test_review_edits_persist_across_branch_switch(self, server, page, browser):
        """Review edits survive branch switch (localStorage key is branch-independent)."""

        def make_page(ctx):
            pg = ctx.new_page()
            pg.route(
                "**/api.github.com/**",
                lambda route: route.fulfill(
                    status=200, content_type="application/json", headers={"ETag": '"etag"'}, body=json.dumps(MOCK_TREE)
                ),
            )
            pg.route(
                "**/raw.githubusercontent.com/**/meta.yaml",
                lambda route: route.fulfill(status=200, content_type="text/plain", body=SAMPLE_META),
            )
            pg.route(
                "**/raw.githubusercontent.com/**/transcript_en.txt",
                lambda route: route.fulfill(status=200, content_type="text/plain", body=SAMPLE_EN),
            )
            pg.route(
                "**/raw.githubusercontent.com/**/transcript_uk.txt",
                lambda route: route.fulfill(status=200, content_type="text/plain", body=SAMPLE_UK),
            )
            pg.route(
                "**/raw.githubusercontent.com/**/review-status.json",
                lambda route: route.fulfill(
                    status=200, content_type="application/json", body=json.dumps(MOCK_REVIEW_STATUS)
                ),
            )
            pg.route(
                "**/player.vimeo.com/api/player.js",
                lambda route: route.fulfill(status=200, content_type="application/javascript", body=""),
            )
            return pg

        ctx = browser.new_context()

        # Make an edit on main
        pg = make_page(ctx)
        pg.add_init_script("localStorage.clear();")
        pg.goto(f"{server}{SPA_URL}#/review/2001-01-01_Test-Talk")
        pg.wait_for_selector(".cell.uk", timeout=10000)
        cell = pg.locator(".cell.uk").first
        cell.click()
        cell.press_sequentially(" edited", delay=20)
        cell.press("Tab")
        pg.wait_for_timeout(300)
        assert "(1)" in (pg.locator("#btn-revert-all").text_content() or "")
        pg.close()

        # Switch to dev — edit should persist
        pg2 = make_page(ctx)
        pg2.goto(f"{server}{SPA_URL}?branch=dev#/review/2001-01-01_Test-Talk")
        pg2.wait_for_selector(".cell.uk", timeout=10000)
        pg2.wait_for_timeout(500)
        assert "(1)" in (pg2.locator("#btn-revert-all").text_content() or "")
        pg2.close()
        ctx.close()


class TestTranscriptSelector:
    def _goto_review(self, server, page):
        goto_spa(page, server, hash="#/review/2001-01-01_Test-Talk")
        page.wait_for_selector(".cell.uk", timeout=10000)

    def test_default_languages_en_uk(self, server, page):
        """Default review uses en (left) and uk (right)."""
        self._goto_review(server, page)
        left = page.evaluate("reviewState.leftLang")
        right = page.evaluate("reviewState.rightLang")
        assert left == "en"
        assert right == "uk"

    def test_column_headers_clickable(self, server, page):
        """Column headers have click targets."""
        self._goto_review(server, page)
        assert page.locator("#col-header-left").count() == 1
        assert page.locator("#col-header-right").count() == 1

    def test_left_header_shows_language_name(self, server, page):
        """Left header displays language name."""
        self._goto_review(server, page)
        text = page.locator("#col-header-left").text_content()
        assert "English" in text

    def test_right_header_shows_language_name(self, server, page):
        """Right header displays language name."""
        self._goto_review(server, page)
        text = page.locator("#col-header-right").text_content()
        assert "Ukrainian" in text

    def test_click_header_shows_dropdown(self, server, page):
        """Clicking column header shows transcript dropdown."""
        self._goto_review(server, page)
        page.locator("#col-header-left").click()
        page.wait_for_selector("#transcript-dropdown-left.open", timeout=5000)
        assert page.locator("#transcript-dropdown-left.open").is_visible()

    def test_dropdown_lists_available_transcripts(self, server, page):
        """Dropdown lists all transcripts from manifest (en, hi, uk)."""
        self._goto_review(server, page)
        page.locator("#col-header-left").click()
        page.wait_for_selector("#transcript-dropdown-left.open", timeout=5000)
        texts = [el.text_content() for el in page.locator("#transcript-dropdown-left div").all()]
        assert any("English" in t for t in texts), f"Expected English in {texts}"
        assert any("Hindi" in t for t in texts), f"Expected Hindi in {texts}"
        assert any("Ukrainian" in t for t in texts), f"Expected Ukrainian in {texts}"

    def test_current_language_marked_active(self, server, page):
        """Current language has .active class in dropdown."""
        self._goto_review(server, page)
        page.locator("#col-header-left").click()
        page.wait_for_selector("#transcript-dropdown-left.open", timeout=5000)
        active = page.locator("#transcript-dropdown-left div.active")
        assert active.count() == 1
        assert "English" in active.text_content()

    def test_select_language_changes_column(self, server, page):
        """Selecting a language reloads the transcript in that column."""
        self._goto_review(server, page)
        page.locator("#col-header-left").click()
        page.wait_for_selector("#transcript-dropdown-left.open", timeout=5000)
        page.locator("#transcript-dropdown-left div", has_text="Hindi").click()
        page.wait_for_function(
            "document.querySelector('.cell.en') && document.querySelector('.cell.en').textContent.indexOf('पहला') !== -1",
            timeout=10000,
        )
        left_text = page.locator(".cell.en").first.text_content()
        assert "पहला" in left_text

    def test_language_from_url_params(self, server, page):
        """?left=hi&right=uk in hash sets correct languages."""
        goto_spa(page, server, hash="#/review/2001-01-01_Test-Talk?left=hi&right=uk")
        page.wait_for_function(
            "document.querySelector('.cell.en') && document.querySelector('.cell.en').textContent.indexOf('पहला') !== -1",
            timeout=10000,
        )
        assert page.evaluate("reviewState.leftLang") == "hi"
        assert page.evaluate("reviewState.rightLang") == "uk"

    def test_language_in_url_after_switch(self, server, page):
        """After switching language, URL hash contains language params."""
        self._goto_review(server, page)
        page.locator("#col-header-left").click()
        page.wait_for_selector("#transcript-dropdown-left.open", timeout=5000)
        page.locator("#transcript-dropdown-left div", has_text="Hindi").click()
        page.wait_for_function(
            "document.querySelector('.cell.en') && document.querySelector('.cell.en').textContent.indexOf('पहला') !== -1",
            timeout=10000,
        )
        assert "left=hi" in page.url

    def test_edit_warning_on_language_switch(self, server, page):
        """Confirm dialog shown when switching language with unsaved edits."""
        self._goto_review(server, page)
        cell = page.locator(".cell.uk").first
        cell.click()
        cell.press_sequentially(" test", delay=20)
        cell.press("Tab")
        page.wait_for_timeout(300)
        assert "(1)" in (page.locator("#btn-revert-all").text_content() or "")
        page.locator("#col-header-left").click()
        page.wait_for_selector("#transcript-dropdown-left.open", timeout=5000)
        page.locator("#transcript-dropdown-left div", has_text="Hindi").click()
        spa_confirm_accept(page)
        page.wait_for_function(
            "document.querySelector('.cell.en') && document.querySelector('.cell.en').textContent.indexOf('पहला') !== -1",
            timeout=10000,
        )

    def test_edit_warning_cancel_keeps_language(self, server, page):
        """Cancelling confirm keeps current language."""
        self._goto_review(server, page)
        cell = page.locator(".cell.uk").first
        cell.click()
        cell.press_sequentially(" test", delay=20)
        cell.press("Tab")
        page.wait_for_timeout(300)
        page.locator("#col-header-left").click()
        page.wait_for_selector("#transcript-dropdown-left.open", timeout=5000)
        page.locator("#transcript-dropdown-left div", has_text="Hindi").click()
        spa_confirm_dismiss(page)
        page.wait_for_timeout(200)
        assert page.evaluate("reviewState.leftLang") == "en"

    def test_no_warning_without_edits(self, server, page):
        """No confirm dialog when switching language without edits."""
        self._goto_review(server, page)
        page.locator("#col-header-left").click()
        page.wait_for_selector("#transcript-dropdown-left.open", timeout=5000)
        page.locator("#transcript-dropdown-left div", has_text="Hindi").click()
        page.wait_for_function(
            "document.querySelector('.cell.en') && document.querySelector('.cell.en').textContent.indexOf('पहला') !== -1",
            timeout=10000,
        )
        # No SPA modal should have appeared during the switch.
        assert page.locator(".sy-modal").count() == 0

    def test_edits_cleared_after_switch(self, server, page):
        """Edits are cleared after confirmed language switch."""
        self._goto_review(server, page)
        cell = page.locator(".cell.uk").first
        cell.click()
        cell.press_sequentially(" test", delay=20)
        cell.press("Tab")
        page.wait_for_timeout(300)
        assert "(1)" in (page.locator("#btn-revert-all").text_content() or "")
        page.locator("#col-header-left").click()
        page.wait_for_selector("#transcript-dropdown-left.open", timeout=5000)
        page.locator("#transcript-dropdown-left div", has_text="Hindi").click()
        spa_confirm_accept(page)
        page.wait_for_function(
            "document.querySelector('.cell.en') && document.querySelector('.cell.en').textContent.indexOf('पहला') !== -1",
            timeout=10000,
        )
        assert not page.locator("#btn-revert-all").is_visible()

    def test_close_dropdown_on_outside_click(self, server, page):
        """Clicking outside closes dropdown."""
        self._goto_review(server, page)
        page.locator("#col-header-left").click()
        page.wait_for_selector("#transcript-dropdown-left.open", timeout=5000)
        page.locator(".cell.en").first.click()
        page.wait_for_timeout(300)
        assert not page.locator("#transcript-dropdown-left.open").is_visible()

    def test_deep_link_with_languages(self, server, page):
        """Direct URL with language params works."""
        goto_spa(page, server, hash="#/review/2001-01-01_Test-Talk?left=hi&right=en")
        page.wait_for_selector(".cell.uk", timeout=10000)
        assert page.evaluate("reviewState.leftLang") == "hi"
        assert page.evaluate("reviewState.rightLang") == "en"
        right_text = page.locator(".cell.uk").first.text_content()
        assert "First paragraph" in right_text

    def test_fallback_language_name(self, server, page):
        """Unknown language code displays capitalized code."""
        self._goto_review(server, page)
        result = page.evaluate("langName('xyz')")
        assert result == "Xyz"

    def test_mobile_viewport_shows_both_en_and_uk(self, server, page):
        """On a narrow viewport the review page must still show EN cells —
        a translation review tool without the source text is broken. Before
        this fix .cell.en had display:none under the 768px breakpoint."""
        page.set_viewport_size({"width": 375, "height": 800})
        goto_spa(page, server)
        page.evaluate("location.hash = '#/review/2001-01-01_Test-Talk'")
        page.wait_for_function("document.querySelectorAll('.cell').length > 0", timeout=10000)
        # Both .cell.en and .cell.uk should be visible (non-zero box)
        en_visible = page.evaluate("""() => {
            var el = document.querySelector('.cell.en');
            if (!el) return false;
            var r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0 && getComputedStyle(el).display !== 'none';
        }""")
        uk_visible = page.evaluate("""() => {
            var el = document.querySelector('.cell.uk');
            if (!el) return false;
            var r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0 && getComputedStyle(el).display !== 'none';
        }""")
        assert en_visible, "EN cell should be visible on mobile"
        assert uk_visible, "UK cell should be visible on mobile"
        # In 1-column layout EN should visually precede its UK partner
        relative = page.evaluate("""() => {
            var en = document.querySelector('.cell.en');
            var uk = document.querySelector('.cell.uk');
            if (!en || !uk) return 'missing';
            var enR = en.getBoundingClientRect();
            var ukR = uk.getBoundingClientRect();
            return enR.bottom <= ukR.top ? 'en-above-uk' : 'side-by-side';
        }""")
        assert relative == "en-above-uk", f"Expected EN above UK, got: {relative}"

    def test_per_cell_revert_button(self, server, page):
        """Edited cells expose a visible revert button wired to SPA.revertEdit.
        Clicking it should drop the edit and restore the original text."""
        goto_spa(page, server)
        page.evaluate("location.hash = '#/review/2001-01-01_Test-Talk'")
        # Wait for real transcripts (not skeleton cells).
        page.wait_for_function(
            "reviewState && reviewState.rightParas && reviewState.rightParas.length > 0",
            timeout=10000,
        )
        orig = page.evaluate("reviewState.rightParas[0]")
        page.evaluate("reviewState.edits[0] = 'EDITED'; saveReview(); renderReview();")
        page.wait_for_timeout(100)
        btn_exists = page.evaluate("!!document.querySelector('.cell.uk.edited .cell-revert[data-idx=\"0\"]')")
        assert btn_exists, "revert button should exist on edited cell"
        page.click(".cell.uk.edited .cell-revert[data-idx='0']")
        page.wait_for_timeout(200)
        has_edit = page.evaluate("reviewState.edits[0] !== undefined")
        assert not has_edit, "edit should be cleared after revert click"
        text_after = page.evaluate("document.querySelector('.cell-text[data-idx=\"0\"]').textContent")
        assert text_after == orig

    def test_editable_cells_have_aria_label(self, server, page):
        """Contenteditable cells must have role=textbox and aria-labelledby
        pointing to the sibling .cell-label so screen readers announce
        P1/P2/timecode + 'editable' together."""
        goto_spa(page, server)
        page.evaluate("location.hash = '#/review/2001-01-01_Test-Talk'")
        page.wait_for_function("document.querySelectorAll('.cell.uk').length > 0", timeout=10000)
        info = page.evaluate("""() => {
            var text = document.querySelector('.cell-text');
            if (!text) return null;
            var labelId = text.getAttribute('aria-labelledby');
            var label = labelId && document.getElementById(labelId);
            return {
                role: text.getAttribute('role'),
                labelId: labelId,
                labelText: label && label.textContent,
            };
        }""")
        assert info is not None
        assert info["role"] == "textbox"
        assert info["labelId"] and info["labelId"].startswith("cell-label-")
        assert info["labelText"] and info["labelText"].startswith("P")

    def test_col_header_keyboard_accessible(self, server, page):
        """Column header dropdowns must be reachable and activatable via
        keyboard: tabindex=0, role=button, and Enter/Space should toggle."""
        goto_spa(page, server)
        page.evaluate("location.hash = '#/review/2001-01-01_Test-Talk'")
        page.wait_for_function("document.querySelectorAll('.cell').length > 0", timeout=10000)
        # Both headers should have role=button and tabindex=0
        attrs = page.evaluate("""() => {
            var lh = document.getElementById('col-header-left');
            var rh = document.getElementById('col-header-right');
            return {
                lhRole: lh && lh.getAttribute('role'),
                lhTabindex: lh && lh.getAttribute('tabindex'),
                rhRole: rh && rh.getAttribute('role'),
                rhTabindex: rh && rh.getAttribute('tabindex'),
            };
        }""")
        assert attrs["lhRole"] == "button"
        assert attrs["lhTabindex"] == "0"
        assert attrs["rhRole"] == "button"
        assert attrs["rhTabindex"] == "0"
        # Focus and press Enter on the right header — dropdown should open
        page.evaluate("document.getElementById('col-header-right').focus()")
        page.keyboard.press("Enter")
        page.wait_for_timeout(200)
        is_open = page.evaluate("document.getElementById('transcript-dropdown-right').classList.contains('open')")
        assert is_open, "dropdown should open on Enter"
        # Press Space to close
        page.evaluate("document.getElementById('col-header-right').focus()")
        page.keyboard.press(" ")
        page.wait_for_timeout(200)
        is_open_after = page.evaluate("document.getElementById('transcript-dropdown-right').classList.contains('open')")
        assert not is_open_after, "dropdown should close on Space"

    def test_manifest_has_transcripts_array(self, server, page):
        """Manifest talks contain transcripts array with all languages."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        transcripts = page.evaluate(
            "manifest.talks.find(function(t) { return t.id === '2001-01-01_Test-Talk'; }).transcripts"
        )
        assert "en" in transcripts
        assert "hi" in transcripts
        assert "uk" in transcripts


REAL_TRANSCRIPT_FIXTURES = [
    "single_sep.txt",
    "single_sep_v2.txt",
    "double_sep.txt",
    "hindi_header.txt",
]


class TestRealTranscriptRoundTrip:
    """Round-trip real-world transcript files through the SPA review page.

    Loads each fixture as transcript_uk.txt, navigates to review (transcript
    mode), edits one paragraph programmatically, calls Open Editor, and
    asserts that the clipboard content equals the original file with only
    the targeted edit applied. Catches paragraph-split / separator /
    whitespace regressions in parseTranscript and openEditor reconstruction.
    """

    @staticmethod
    def _load_fixture(name: str) -> str:
        return Path(__file__).parent.joinpath("fixtures", "transcripts", name).read_text(encoding="utf-8")

    def _goto_review_with(self, server, page, transcript_text: str):
        """Override the transcript_uk.txt route to serve the given content,
        then navigate to the review page in transcript mode."""
        # Specific routes registered later take priority over the default
        # SAMPLE_UK route already registered by the page fixture.
        page.route(
            "**/raw.githubusercontent.com/**/transcript_uk.txt",
            lambda route: route.fulfill(status=200, content_type="text/plain", body=transcript_text),
        )
        goto_spa(page, server)
        page.evaluate("localStorage.setItem('sy_expert_mode', '1'); expertMode = true; applyExpertMode();")
        page.evaluate("location.hash = '#/review/2001-01-01_Test-Talk'")
        page.wait_for_function("document.querySelectorAll('.cell.uk').length > 0", timeout=10000)

    @pytest.mark.parametrize("fixture", REAL_TRANSCRIPT_FIXTURES)
    def test_no_edits_clipboard_byte_identical(self, server, page, fixture):
        """With zero edits, Open Editor's clipboard content must equal the
        original file byte-for-byte. Any difference means parseTranscript or
        the reconstruction in openEditor is silently mutating the file."""
        original = self._load_fixture(fixture)
        self._goto_review_with(server, page, original)
        page.evaluate(
            """
            window._clipText = '';
            navigator.clipboard.writeText = function(t) { window._clipText = t; return Promise.resolve(); };
            window.alert = function() {};
            window.open = function() {};
            // Force at least one edit so openEditor takes the clipboard branch.
            // Then immediately revert it so the diff is empty.
            var firstIdx = 0;
            reviewState.edits[firstIdx] = reviewState.rightParas[firstIdx];
            saveReview();
            """
        )
        page.evaluate("SPA.openEditor()")
        page.wait_for_timeout(300)
        clip = page.evaluate("window._clipText || ''")
        assert clip == original, (
            f"[{fixture}] clipboard content drifted from original\n"
            f"orig len: {len(original)}, clip len: {len(clip)}\n"
            f"first diff at: {next((i for i in range(min(len(original), len(clip))) if original[i] != clip[i]), 'tail')}\n"
            f"orig head: {original[:200]!r}\n"
            f"clip head: {clip[:200]!r}\n"
        )

    @pytest.mark.parametrize("fixture", REAL_TRANSCRIPT_FIXTURES)
    def test_single_edit_only_target_paragraph_changes(self, server, page, fixture):
        """A single paragraph edit must produce a clipboard that differs from
        the original ONLY in the edited paragraph. Header, separators, and all
        other paragraphs are byte-identical."""
        original = self._load_fixture(fixture)
        self._goto_review_with(server, page, original)

        # Pick a middle paragraph to edit (avoid first/last to also catch
        # boundary issues).
        para_count = page.evaluate("reviewState.rightParas.length")
        assert para_count >= 3, f"[{fixture}] need at least 3 paragraphs, got {para_count}"
        target_idx = para_count // 2
        original_para = page.evaluate(f"reviewState.rightParas[{target_idx}]")
        edited_para = original_para + " [TEST_EDIT]"

        page.evaluate(
            """
            window._clipText = '';
            navigator.clipboard.writeText = function(t) { window._clipText = t; return Promise.resolve(); };
            window.alert = function() {};
            window.open = function() {};
            """
        )
        page.evaluate(f"reviewState.edits[{target_idx}] = {json.dumps(edited_para)}; saveReview()")
        page.evaluate("SPA.openEditor()")
        page.wait_for_timeout(300)
        clip = page.evaluate("window._clipText || ''")

        # The edit must be present
        assert "[TEST_EDIT]" in clip, f"[{fixture}] edit marker not found in clipboard"

        # Replace the edit back to the original — the result must equal the
        # original file byte-for-byte. This proves the only diff is our edit.
        clip_reverted = clip.replace(" [TEST_EDIT]", "", 1)
        assert clip_reverted == original, (
            f"[{fixture}] clipboard differs from original beyond the edit\n"
            f"orig len: {len(original)}, reverted len: {len(clip_reverted)}\n"
            f"first diff: {next((i for i in range(min(len(original), len(clip_reverted))) if original[i] != clip_reverted[i]), 'tail')}\n"
        )

    @pytest.mark.parametrize("fixture", REAL_TRANSCRIPT_FIXTURES)
    def test_paragraph_count_preserved(self, server, page, fixture):
        """parseTranscript must split the body into the same number of
        paragraphs the file actually has, regardless of separator style."""
        original = self._load_fixture(fixture)
        self._goto_review_with(server, page, original)
        para_count = page.evaluate("reviewState.rightParas.length")

        # Count paragraphs by parsing the body the same way the SPA should:
        # everything after the language line, split by either \n\n+ or single \n.
        lines = original.split("\n")
        body_start = 0
        for i, line in enumerate(lines[:10]):
            if line.strip().startswith(("Talk Language:", "Language:", "Мова промови:", "Мова:", "भाषण भाषा:")):
                body_start = i + 1
                break
        body = "\n".join(lines[body_start:]).strip()
        import re as _re

        if _re.search(r"\n\s*\n", body):
            expected = len([p for p in _re.split(r"\n\s*\n", body) if p.strip()])
        else:
            expected = len([p for p in body.split("\n") if p.strip()])

        assert para_count == expected, (
            f"[{fixture}] paragraph count mismatch: SPA reports {para_count}, expected {expected}"
        )


# ============================================================
# Preview: marker ↔ edit mode toggle
# ============================================================

PREVIEW_KEY = "preview_2001-01-01_Test-Talk_Test-Video"
LEGACY_KEY = "markers_preview_2001-01-01_Test-Talk_Test-Video"
# Subtitle text edits now live in the canonical per-block store (js/edit_store.js),
# shared by the preview and review-SRT views; the preview key keeps only
# mode + markers. See the edit-store consolidation.
CANON_UK_KEY = "srt_edits_2001-01-01_Test-Talk_Test-Video_uk"


def _goto_preview_video(page, server, video_slug="Test-Video"):
    # Always do a full navigation so route() runs against a clean previewState.
    # page.goto with only a hash change would not reload when already on the
    # same path in Playwright, and hashchange alone can race with manifest load.
    page.goto(f"{server}{SPA_URL}?_r={video_slug}#/preview/2001-01-01_Test-Talk/{video_slug}")
    page.wait_for_selector("#mock-player", state="visible", timeout=10000)
    page.wait_for_function(
        f"window.previewState && window.previewState.videoSlug === {video_slug!r}",
        timeout=10000,
    )
    page.wait_for_timeout(300)


class TestPreviewModeDefaults:
    def test_default_mode_is_edit(self, server, page):
        _goto_preview_video(page, server)
        mode = page.evaluate(
            "document.querySelector('.preview-mode-toggle [data-mode=\"edit\"]').classList.contains('active')"
        )
        assert mode is True

    def test_marker_new_key_shape_on_first_mutation(self, server, page):
        # Marker mode is now opt-in (edit is the default); switch to it, then
        # the first mark writes the well-formed new-key shape.
        _goto_preview_video(page, server)
        page.click('.preview-mode-toggle [data-mode="marker"]')
        page.wait_for_timeout(100)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        stored = page.evaluate(f"JSON.parse(localStorage.getItem('{PREVIEW_KEY}') || 'null')")
        assert stored is not None
        assert stored["mode"] == "marker"
        assert isinstance(stored["markers"], list)
        assert isinstance(stored["edits"], dict)
        assert len(stored["markers"]) == 1

    def test_mode_persisted_across_reload(self, server, page):
        _goto_preview_video(page, server)
        # Switch away from the edit default so the reload actually proves the
        # choice was persisted (re-selecting the default would save nothing).
        page.click('.preview-mode-toggle [data-mode="marker"]')
        page.wait_for_timeout(100)
        _goto_preview_video(page, server)
        mode = page.evaluate(
            "document.querySelector('.preview-mode-toggle [data-mode=\"marker\"]').classList.contains('active')"
        )
        assert mode is True

    def test_mode_independent_per_video(self, server, page):
        _goto_preview_video(page, server, "Test-Video")
        # v1 → marker (non-default); v2 must still open on the edit default.
        page.click('.preview-mode-toggle [data-mode="marker"]')
        page.wait_for_timeout(100)
        _goto_preview_video(page, server, "Test-Video-2")
        debug = page.evaluate("""
          ({
            state_mode: (window.previewState || {}).mode,
            btn_marker_classes: document.querySelector('.preview-mode-toggle [data-mode=\"marker\"]').className,
            btn_edit_classes: document.querySelector('.preview-mode-toggle [data-mode=\"edit\"]').className,
            v2_key: localStorage.getItem('preview_2001-01-01_Test-Talk_Test-Video-2'),
            v1_key: localStorage.getItem('preview_2001-01-01_Test-Talk_Test-Video'),
          })
        """)
        mode2 = page.evaluate(
            "document.querySelector('.preview-mode-toggle [data-mode=\"edit\"]').classList.contains('active')"
        )
        assert mode2 is True, f"debug: {debug}"
        _goto_preview_video(page, server, "Test-Video")
        mode1 = page.evaluate(
            "document.querySelector('.preview-mode-toggle [data-mode=\"marker\"]').classList.contains('active')"
        )
        assert mode1 is True


class TestPreviewLegacyMigration:
    def test_legacy_markers_migrated_to_new_key(self, server, page):
        # Seed legacy key before navigation — use init script so it runs
        # before any SPA code sees localStorage.
        legacy = json.dumps([{"time": 2.0, "tc": "00:00:02", "text": "legacy one", "comment": ""}])
        page.add_init_script(f"localStorage.setItem({LEGACY_KEY!r}, {legacy!r});")
        _goto_preview_video(page, server)
        new = page.evaluate(f"JSON.parse(localStorage.getItem('{PREVIEW_KEY}') || 'null')")
        assert new is not None
        assert new["mode"] == "marker"
        assert len(new["markers"]) == 1
        assert new["markers"][0]["text"] == "legacy one"
        legacy_after = page.evaluate(f"localStorage.getItem('{LEGACY_KEY}')")
        assert legacy_after is None

    def test_legacy_ignored_when_new_key_exists(self, server, page):
        new_payload = json.dumps({"mode": "edit", "markers": [], "edits": {"uk": {"0": "нове"}}})
        legacy_payload = json.dumps([{"time": 1, "tc": "00:00:01", "text": "stale", "comment": ""}])
        page.add_init_script(
            f"localStorage.setItem({PREVIEW_KEY!r}, {new_payload!r});"
            f"localStorage.setItem({LEGACY_KEY!r}, {legacy_payload!r});"
        )
        _goto_preview_video(page, server)
        stored = page.evaluate(f"JSON.parse(localStorage.getItem('{PREVIEW_KEY}') || 'null')")
        assert stored["mode"] == "edit"
        legacy_after = page.evaluate(f"localStorage.getItem('{LEGACY_KEY}')")
        assert legacy_after is None

    def test_corrupt_legacy_json_falls_back_to_default(self, server, page):
        page.add_init_script(f"localStorage.setItem({LEGACY_KEY!r}, '{{not-json');")
        _goto_preview_video(page, server)
        stored = page.evaluate(f"JSON.parse(localStorage.getItem('{PREVIEW_KEY}') || 'null')")
        assert stored is not None
        assert stored["mode"] == "marker"
        assert stored["markers"] == []
        assert stored["edits"] == {}
        # Legacy key is wiped regardless of parse outcome.
        assert page.evaluate(f"localStorage.getItem({LEGACY_KEY!r})") is None


class TestPreviewLayoutButtons:
    def test_action_buttons_live_in_header(self, server, page):
        _goto_preview_video(page, server)
        # Buttons that should be in the preview header.
        for sel in ["#btn-preview-issue", "#btn-clear-all"]:
            count = page.locator(f"#view-preview .header .header-actions {sel}").count()
            assert count == 1, f"{sel} not found in preview header-actions"

    def test_mark_button_stays_in_player_controls(self, server, page):
        _goto_preview_video(page, server)
        count = page.locator("#view-preview .player-container .controls #btn-mark").count()
        assert count == 1

    def test_segmented_control_in_header(self, server, page):
        _goto_preview_video(page, server)
        count = page.locator("#view-preview .header .preview-mode-toggle").count()
        assert count == 1
        btns = page.locator(".preview-mode-toggle button").count()
        assert btns == 2

    def test_edit_chip_comes_first(self, server, page):
        """Edit is the default mode, so its chip is the leftmost in the toggle."""
        _goto_preview_video(page, server)
        modes = page.evaluate(
            "Array.from(document.querySelectorAll('.preview-mode-toggle button'))"
            ".map(function(b){ return b.getAttribute('data-mode'); })"
        )
        assert modes == ["edit", "marker"]

    def test_clear_btn_hidden_when_empty(self, server, page):
        _goto_preview_video(page, server)
        visible = page.locator("#btn-clear-all").is_visible()
        assert visible is False

    def test_clear_btn_shown_after_adding_marker(self, server, page):
        _goto_preview_video(page, server)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        visible = page.locator("#btn-clear-all").is_visible()
        assert visible is True

    def test_copy_btn_only_visible_in_marker_mode(self, server, page):
        _goto_preview_video(page, server)
        page.click('.preview-mode-toggle [data-mode="marker"]')
        assert page.locator("#btn-copy-all").is_visible() is True
        page.click('.preview-mode-toggle [data-mode="edit"]')
        assert page.locator("#btn-copy-all").is_visible() is False

    def test_open_editor_btn_only_visible_in_edit_mode(self, server, page):
        _goto_preview_video(page, server)
        page.click('.preview-mode-toggle [data-mode="marker"]')
        assert page.locator("#btn-preview-editor").is_visible() is False
        page.click('.preview-mode-toggle [data-mode="edit"]')
        assert page.locator("#btn-preview-editor").is_visible() is True


class TestPreviewEditMode:
    def _switch_to_edit(self, page):
        page.click('.preview-mode-toggle [data-mode="edit"]')
        page.wait_for_timeout(50)

    def test_add_edit_creates_item_and_pauses(self, server, page):
        _goto_preview_video(page, server)
        self._switch_to_edit(page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")  # same button, label now "Edit"
        count = page.locator(".edit-item").count()
        assert count == 1
        paused = page.evaluate("window._vimeoPlayer._paused")
        assert paused is True

    def test_add_edit_initial_text_equals_original(self, server, page):
        _goto_preview_video(page, server)
        self._switch_to_edit(page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        text = page.locator(".edit-item .edited").first.inner_text().strip()
        assert text == "Перший субтитр"

    def test_add_edit_focuses_contenteditable(self, server, page):
        _goto_preview_video(page, server)
        self._switch_to_edit(page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        page.wait_for_timeout(100)
        focused = page.evaluate("document.activeElement.classList.contains('edited')")
        assert focused is True

    def test_add_edit_existing_block_does_not_duplicate(self, server, page):
        _goto_preview_video(page, server)
        self._switch_to_edit(page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        page.keyboard.press("Escape")  # blur
        page.evaluate("window._vimeoPlayer._setTime(3)")  # still inside block 0 (1000-5000)
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        count = page.locator(".edit-item").count()
        assert count == 1

    def test_add_edit_no_active_subtitle_does_nothing(self, server, page):
        _goto_preview_video(page, server)
        self._switch_to_edit(page)
        page.evaluate("window._vimeoPlayer._setTime(5.5)")  # gap between blocks
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        count = page.locator(".edit-item").count()
        assert count == 0

    def test_edit_text_persists_to_storage(self, server, page):
        _goto_preview_video(page, server)
        self._switch_to_edit(page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        page.wait_for_timeout(100)
        # Type new text into focused contenteditable.
        page.evaluate("""
          var el = document.activeElement;
          el.innerText = 'Змінений текст';
          el.dispatchEvent(new Event('input', { bubbles: true }));
        """)
        page.wait_for_timeout(50)
        canon = page.evaluate(f"JSON.parse(localStorage.getItem('{CANON_UK_KEY}') || 'null')")
        assert canon and canon["0"] == "Змінений текст"

    def test_edit_equal_to_original_removes_entry(self, server, page):
        _goto_preview_video(page, server)
        self._switch_to_edit(page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        page.evaluate("""
          var el = document.activeElement;
          el.innerText = 'Інакший';
          el.dispatchEvent(new Event('input', { bubbles: true }));
        """)
        page.wait_for_timeout(50)
        page.evaluate("""
          var el = document.activeElement;
          el.innerText = 'Перший субтитр';
          el.dispatchEvent(new Event('input', { bubbles: true }));
        """)
        page.wait_for_timeout(50)
        canon = page.evaluate(f"JSON.parse(localStorage.getItem('{CANON_UK_KEY}') || 'null') || {{}}")
        assert "0" not in canon and 0 not in canon

    def test_edit_enter_resumes_video(self, server, page):
        _goto_preview_video(page, server)
        self._switch_to_edit(page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        page.wait_for_timeout(100)
        assert page.evaluate("window._vimeoPlayer._paused") is True
        # Send Enter to the focused contenteditable.
        page.keyboard.press("Enter")
        page.wait_for_timeout(100)
        assert page.evaluate("window._vimeoPlayer._paused") is False

    def test_delete_edit_row_removes_from_storage(self, server, page):
        _goto_preview_video(page, server)
        self._switch_to_edit(page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        page.evaluate("""
          var el = document.activeElement;
          el.innerText = 'Змінений';
          el.dispatchEvent(new Event('input', { bubbles: true }));
        """)
        page.wait_for_timeout(50)
        page.click(".edit-item .del")
        canon = page.evaluate(f"JSON.parse(localStorage.getItem('{CANON_UK_KEY}') || 'null') || {{}}")
        assert canon == {}

    def test_edit_list_rows_visible_when_navigating_from_index(self, server, page):
        # Seed an edit for block 0 in uk, then navigate to the preview from
        # scratch. The edit list must render a row once the SRT is fetched.
        page.add_init_script(
            "localStorage.setItem('preview_2001-01-01_Test-Talk_Test-Video',"
            " JSON.stringify({mode:'edit', markers:[], edits:{uk:{'0':'Мій правлений блок'}}}))"
        )
        _goto_preview_video(page, server)
        # Wait until the SRT-dependent re-render finishes.
        page.wait_for_function(
            "document.querySelectorAll('.edit-item').length > 0",
            timeout=5000,
        )
        rows = page.locator(".edit-item").count()
        assert rows == 1
        text = page.locator(".edit-item .edited").first.inner_text().strip()
        assert text == "Мій правлений блок"

    def test_create_issue_edit_mode_body_has_before_after(self, server, page):
        _goto_preview_video(page, server)
        self._switch_to_edit(page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        page.wait_for_timeout(100)
        page.evaluate("""
          var el = document.activeElement;
          el.innerText = 'НОВА ВЕРСІЯ';
          el.dispatchEvent(new Event('input', { bubbles: true }));
        """)
        page.wait_for_timeout(50)
        page.evaluate(
            "window._openedUrl = null;"
            " window.open = function(u) { window._openedUrl = u; };"
            " navigator.clipboard.writeText = function() { return Promise.resolve(); };"
            " window.alert = function() {};"
        )
        page.evaluate("SPA.createPreviewIssue()")
        page.wait_for_timeout(200)
        body = page.evaluate("decodeURIComponent(window._openedUrl || '')")
        assert "Suggested edits" in body, body[:400]
        assert "НОВА ВЕРСІЯ" in body, body[:400]
        assert "Перший субтитр" in body, body[:400]

    def test_open_preview_editor_clipboards_rebuilt_srt(self, server, page):
        _goto_preview_video(page, server)
        self._switch_to_edit(page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        page.wait_for_timeout(100)
        page.evaluate("""
          var el = document.activeElement;
          el.innerText = 'ЗМІНА';
          el.dispatchEvent(new Event('input', { bubbles: true }));
        """)
        page.wait_for_timeout(50)
        page.evaluate(
            "window._clipText = '';"
            " navigator.clipboard.writeText = function(t) {"
            "   window._clipText = t; return Promise.resolve();"
            " };"
            " window.alert = function() {};"
            " window._openedUrl = null;"
            " window.open = function(u) { window._openedUrl = u; };"
        )
        page.evaluate("SPA.openPreviewEditor()")
        page.wait_for_timeout(200)
        clip = page.evaluate("window._clipText || ''")
        opened = page.evaluate("window._openedUrl || ''")
        assert "ЗМІНА" in clip, clip[:400]
        assert "00:00:01,000 --> 00:00:05,000" in clip, clip[:400]
        assert "Другий субтитр" in clip, clip[:400]
        assert opened.startswith("https://github.com/") and "final/uk.srt" in opened

    def test_open_preview_editor_url_points_to_full_final_uk_path(self, server, page):
        """PR target must be the exact canonical path and branch, not just a suffix match.
        A bug that swapped the repo, branch, or directory would currently slip through
        the 'final/uk.srt in opened' substring check."""
        _goto_preview_video(page, server)
        self._switch_to_edit(page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        page.evaluate("""
          var el = document.activeElement;
          el.innerText = 'НОВА';
          el.dispatchEvent(new Event('input', { bubbles: true }));
        """)
        page.wait_for_timeout(50)
        page.evaluate(
            "window._openedUrl = null;"
            " window.open = function(u) { window._openedUrl = u; };"
            " navigator.clipboard.writeText = function() { return Promise.resolve(); };"
            " window.alert = function() {};"
        )
        page.evaluate("SPA.openPreviewEditor()")
        page.wait_for_timeout(200)
        opened = page.evaluate("window._openedUrl || ''")
        expected = (
            "https://github.com/sy-tools/sy-subtitles/edit/main/talks/2001-01-01_Test-Talk/Test-Video/final/uk.srt"
        )
        assert opened == expected, f"expected exact editor URL, got: {opened}"

    def test_open_preview_editor_no_edits_opens_url_without_clipboard(self, server, page):
        """Zero-edit path: must open the editor URL directly and NOT touch the clipboard.
        A bug that always rebuilt/clipboarded would overwrite the user's buffer on a
        plain 'go edit this file' click."""
        _goto_preview_video(page, server)
        self._switch_to_edit(page)
        page.evaluate(
            "window._openedUrl = null;"
            " window._clipText = null;"
            " window.open = function(u) { window._openedUrl = u; };"
            " navigator.clipboard.writeText = function(t) {"
            "   window._clipText = t; return Promise.resolve();"
            " };"
            " window.alert = function() {};"
        )
        page.evaluate("SPA.openPreviewEditor()")
        page.wait_for_timeout(150)
        opened = page.evaluate("window._openedUrl || ''")
        clip_written = page.evaluate("window._clipText")
        assert "final/uk.srt" in opened, opened[:300]
        assert clip_written is None, f"clipboard should not be touched, got: {clip_written!r}"

    def test_open_preview_editor_clipboard_byte_exact_with_edits_applied(self, server, page):
        """The clipboard must equal the SOURCE SRT byte-for-byte, with ONLY the edited
        blocks substituted. Any stray whitespace, reordering, or drift in timecodes/
        block numbers counts as a regression — reviewers would then see spurious diffs
        in their PR and lose trust in the tool."""
        _goto_preview_video(page, server)
        self._switch_to_edit(page)
        # Edit block 0 ("Перший субтитр") via UI, block 1 ("Другий субтитр") via state.
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        page.wait_for_timeout(100)
        page.evaluate("""
          var el = document.activeElement;
          el.innerText = 'ПЕРШИЙ_НОВ';
          el.dispatchEvent(new Event('input', { bubbles: true }));
        """)
        page.wait_for_timeout(50)
        page.evaluate("previewState.edits.uk[1] = 'ДРУГИЙ_НОВ'; savePreviewState();")
        page.evaluate(
            "window._clipText = '';"
            " navigator.clipboard.writeText = function(t) {"
            "   window._clipText = t; return Promise.resolve();"
            " };"
            " window.alert = function() {};"
            " window.open = function() {};"
        )
        page.evaluate("SPA.openPreviewEditor()")
        page.wait_for_timeout(200)
        clip = page.evaluate("window._clipText || ''")
        expected = SAMPLE_SRT.replace("Перший субтитр", "ПЕРШИЙ_НОВ").replace("Другий субтитр", "ДРУГИЙ_НОВ")
        assert clip == expected, (
            "Clipboard does not match source with edits applied.\n"
            f"--- expected ({len(expected)} bytes) ---\n{expected!r}\n"
            f"--- got ({len(clip)} bytes) ---\n{clip!r}"
        )

    def test_open_preview_editor_clipboard_unedited_blocks_are_byte_identical(self, server, page):
        """When only ONE block is edited, every OTHER byte in the clipboard must be
        byte-identical to the source (block numbers, timecodes, untouched text,
        separator blank lines, trailing newline). This guards against the rebuilder
        subtly normalizing the source file."""
        _goto_preview_video(page, server)
        self._switch_to_edit(page)
        page.evaluate("window._vimeoPlayer._setTime(7)")  # inside block 2 (6–10s)
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        page.wait_for_timeout(100)
        page.evaluate("""
          var el = document.activeElement;
          el.innerText = 'ТІЛЬКИ_ДРУГИЙ';
          el.dispatchEvent(new Event('input', { bubbles: true }));
        """)
        page.wait_for_timeout(50)
        page.evaluate(
            "window._clipText = '';"
            " navigator.clipboard.writeText = function(t) {"
            "   window._clipText = t; return Promise.resolve();"
            " };"
            " window.alert = function() {};"
            " window.open = function() {};"
        )
        page.evaluate("SPA.openPreviewEditor()")
        page.wait_for_timeout(200)
        clip = page.evaluate("window._clipText || ''")
        expected = SAMPLE_SRT.replace("Другий субтитр", "ТІЛЬКИ_ДРУГИЙ")
        assert clip == expected, (
            f"Unedited block drifted from source.\n--- expected ---\n{expected!r}\n--- got ---\n{clip!r}"
        )

    # ------------------------------------------------------------------
    # Canonicalization coverage for the preview PR button.
    #
    # Our pipeline produces SRTs in ONE canonical form (tools/srt_utils.py
    # write_srt): UTF-8 without BOM, LF line endings, blocks numbered from 1,
    # a single blank line between blocks, and a trailing blank line after the
    # last block too (the file ends with "\n\n"). If a human manually commits
    # an SRT in a different shape, `openPreviewEditor` MUST rewrite it back to
    # canonical form rather than faithfully preserve the source bytes — reviewers
    # should never see arbitrary formatting drift in their PRs.
    #
    # These tests codify that contract, so an accidental "preserve source"
    # refactor of parseSRT / applyEditsToSrt would fail loudly.
    # ------------------------------------------------------------------
    CANONICAL_SRT = (
        "1\n00:00:01,000 --> 00:00:05,000\nПЕРШИЙ_НОВ\n\n2\n00:00:06,000 --> 00:00:10,000\nДругий субтитр\n\n"
    )

    def _override_uk_srt(self, page, body):
        """Replace the UK SRT mock with `body`. MUST be called before navigation."""
        page.unroute("**/raw.githubusercontent.com/**/uk.srt")
        page.route(
            "**/raw.githubusercontent.com/**/uk.srt",
            lambda route: route.fulfill(status=200, content_type="text/plain", body=body),
        )

    def _edit_block0_and_grab_clip(self, page):
        """Edit block 0 to 'ПЕРШИЙ_НОВ' via the UI, trigger openPreviewEditor,
        return the captured clipboard text."""
        self._switch_to_edit(page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        page.wait_for_timeout(100)
        page.evaluate("""
          var el = document.activeElement;
          el.innerText = 'ПЕРШИЙ_НОВ';
          el.dispatchEvent(new Event('input', { bubbles: true }));
        """)
        page.wait_for_timeout(50)
        page.evaluate(
            "window._clipText = '';"
            " navigator.clipboard.writeText = function(t) {"
            "   window._clipText = t; return Promise.resolve();"
            " };"
            " window.alert = function() {};"
            " window.open = function() {};"
        )
        page.evaluate("SPA.openPreviewEditor()")
        page.wait_for_timeout(200)
        return page.evaluate("window._clipText || ''")

    def test_canonicalize_strips_utf8_bom(self, server, page):
        """Source with a leading BOM → clipboard must NOT carry the BOM."""
        source = "\ufeff" + (
            "1\n00:00:01,000 --> 00:00:05,000\nПерший субтитр\n\n2\n00:00:06,000 --> 00:00:10,000\nДругий субтитр\n"
        )
        self._override_uk_srt(page, source)
        _goto_preview_video(page, server)
        clip = self._edit_block0_and_grab_clip(page)
        assert not clip.startswith("\ufeff"), f"BOM leaked into clipboard: {clip[:10]!r}"
        assert clip == self.CANONICAL_SRT, (
            f"BOM source not canonicalized.\n--- expected ---\n{self.CANONICAL_SRT!r}\n--- got ---\n{clip!r}"
        )

    def test_canonicalize_renumbers_block_indices(self, server, page):
        """Source with non-sequential block numbers (5, 10) → clipboard renumbers from 1."""
        source = (
            "5\n00:00:01,000 --> 00:00:05,000\nПерший субтитр\n\n10\n00:00:06,000 --> 00:00:10,000\nДругий субтитр\n"
        )
        self._override_uk_srt(page, source)
        _goto_preview_video(page, server)
        clip = self._edit_block0_and_grab_clip(page)
        assert clip == self.CANONICAL_SRT, (
            f"Block numbers not renumbered.\n--- expected ---\n{self.CANONICAL_SRT!r}\n--- got ---\n{clip!r}"
        )

    def test_canonicalize_collapses_extra_blank_lines(self, server, page):
        """Source with triple blank lines between blocks → clipboard has a single blank line."""
        source = (
            "1\n00:00:01,000 --> 00:00:05,000\nПерший субтитр\n\n\n\n2\n00:00:06,000 --> 00:00:10,000\nДругий субтитр\n"
        )
        self._override_uk_srt(page, source)
        _goto_preview_video(page, server)
        clip = self._edit_block0_and_grab_clip(page)
        assert clip == self.CANONICAL_SRT, (
            f"Extra blank lines not collapsed.\n--- expected ---\n{self.CANONICAL_SRT!r}\n--- got ---\n{clip!r}"
        )

    def test_canonicalize_adds_trailing_newline_when_missing(self, server, page):
        """Source without a trailing newline → clipboard is canonicalized to the
        write_srt shape, ending with a trailing blank line (`\\n\\n`)."""
        source = "1\n00:00:01,000 --> 00:00:05,000\nПерший субтитр\n\n2\n00:00:06,000 --> 00:00:10,000\nДругий субтитр"
        assert not source.endswith("\n")
        self._override_uk_srt(page, source)
        _goto_preview_video(page, server)
        clip = self._edit_block0_and_grab_clip(page)
        assert clip.endswith("\n\n"), f"canonical form must end with a trailing blank line: {clip[-20:]!r}"
        assert not clip.endswith("\n\n\n"), f"no doubled trailing blank line: {clip[-20:]!r}"
        assert clip == self.CANONICAL_SRT, (
            f"Trailing newline not canonicalized.\n--- expected ---\n{self.CANONICAL_SRT!r}\n--- got ---\n{clip!r}"
        )

    def test_canonicalize_converts_crlf_to_lf(self, server, page):
        """Source with CRLF line endings → clipboard has pure LF."""
        source = (
            "1\r\n00:00:01,000 --> 00:00:05,000\r\nПерший субтитр\r\n\r\n"
            "2\r\n00:00:06,000 --> 00:00:10,000\r\nДругий субтитр\r\n"
        )
        self._override_uk_srt(page, source)
        _goto_preview_video(page, server)
        clip = self._edit_block0_and_grab_clip(page)
        assert "\r" not in clip, f"CR leaked into clipboard: {clip!r}"
        assert clip == self.CANONICAL_SRT, (
            f"CRLF source not canonicalized.\n--- expected ---\n{self.CANONICAL_SRT!r}\n--- got ---\n{clip!r}"
        )

    # ------------------------------------------------------------------
    # Multi-language coverage for the preview PR button.
    #
    # Preview supports switching `previewState.srtLang` between whatever
    # languages are present under `final/` for a video. The PR target
    # path, the clipboard body, and the byte-for-byte canonicalization
    # contract must all track the current language — NOT hardcode `uk`.
    #
    # We also verify that `previewState.edits` is scoped per-language:
    # an edit made while viewing UK must not leak into the EN clipboard.
    # ------------------------------------------------------------------
    MULTI_LANG_TREE = {
        "sha": "test-multi-lang",
        "tree": [
            {"path": "talks/2001-01-01_Test-Talk/Test-Video/final/uk.srt", "type": "blob"},
            {"path": "talks/2001-01-01_Test-Talk/Test-Video/final/en.srt", "type": "blob"},
            {"path": "talks/2001-01-01_Test-Talk/Test-Video/source/en.srt", "type": "blob"},
            {"path": "talks/2001-01-01_Test-Talk/Test-Video/source/whisper.json", "type": "blob"},
            {"path": "talks/2001-01-01_Test-Talk/Test-Video-2/final/uk.srt", "type": "blob"},
            {"path": "talks/2001-01-01_Test-Talk/meta.yaml", "type": "blob"},
            {"path": "talks/2001-01-01_Test-Talk/review_report.md", "type": "blob"},
            {"path": "talks/2001-01-01_Test-Talk/transcript_en.txt", "type": "blob"},
            {"path": "talks/2001-01-01_Test-Talk/transcript_uk.txt", "type": "blob"},
        ],
    }

    EN_SRT_TIGHT = (
        "1\n00:00:01,000 --> 00:00:05,000\nFirst EN block\n\n2\n00:00:06,000 --> 00:00:10,000\nSecond EN block\n\n"
    )

    def _install_multi_lang_tree(self, page, en_body=None):
        """Replace the Trees API mock with one that exposes both uk.srt and
        en.srt under final/, and narrow the en.srt content mock. MUST be
        called before navigation."""
        page.unroute("**/api.github.com/**")
        page.route(
            "**/api.github.com/**",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                headers={"ETag": '"test-etag-multi"'},
                body=json.dumps(self.MULTI_LANG_TREE),
            ),
        )
        page.unroute("**/raw.githubusercontent.com/**/en.srt")
        body = en_body if en_body is not None else self.EN_SRT_TIGHT
        page.route(
            "**/raw.githubusercontent.com/**/en.srt",
            lambda route: route.fulfill(status=200, content_type="text/plain", body=body),
        )

    def test_en_language_selector_becomes_visible(self, server, page):
        """Sanity check: with two languages in the tree, the #srt-lang-select
        chip is shown. Without this, the following tests could pass trivially
        against a SPA that silently ignored our tree override."""
        self._install_multi_lang_tree(page)
        _goto_preview_video(page, server)
        assert page.locator("#srt-lang-select").is_visible() is True
        options = page.evaluate("Array.from(document.querySelectorAll('#srt-lang-select option')).map(o => o.value)")
        assert set(options) == {"uk", "en"}, options

    def test_open_preview_editor_en_url_and_clipboard_byte_exact(self, server, page):
        """After SPA.switchSubLang('en'):
        * openPreviewEditor must open `.../final/en.srt` (NOT uk.srt);
        * the clipboard must be the EN source with the EN edit applied,
          byte-for-byte — proving canonicalization is language-agnostic
          and that no 'uk' value is hardcoded in the PR pipeline."""
        self._install_multi_lang_tree(page)
        _goto_preview_video(page, server)
        page.evaluate("SPA.switchSubLang('en')")
        page.wait_for_function("previewState.srtLang === 'en'", timeout=5000)

        self._switch_to_edit(page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        page.wait_for_timeout(100)
        page.evaluate("""
          var el = document.activeElement;
          el.innerText = 'EN_EDIT';
          el.dispatchEvent(new Event('input', { bubbles: true }));
        """)
        page.wait_for_timeout(50)
        page.evaluate(
            "window._clipText = '';"
            " window._openedUrl = null;"
            " navigator.clipboard.writeText = function(t) {"
            "   window._clipText = t; return Promise.resolve();"
            " };"
            " window.open = function(u) { window._openedUrl = u; };"
            " window.alert = function() {};"
        )
        page.evaluate("SPA.openPreviewEditor()")
        page.wait_for_timeout(200)
        opened = page.evaluate("window._openedUrl || ''")
        clip = page.evaluate("window._clipText || ''")

        expected_url = (
            "https://github.com/sy-tools/sy-subtitles/edit/main/talks/2001-01-01_Test-Talk/Test-Video/final/en.srt"
        )
        assert opened == expected_url, f"wrong PR target for EN: {opened}"
        expected_clip = self.EN_SRT_TIGHT.replace("First EN block", "EN_EDIT")
        assert clip == expected_clip, (
            f"EN clipboard mismatch.\n--- expected ---\n{expected_clip!r}\n--- got ---\n{clip!r}"
        )

    def test_canonicalize_en_srt_strips_bom(self, server, page):
        """Canonicalization must apply to any language — verify BOM is stripped
        from an EN source too. This catches a hypothetical regression where
        canonicalization was only wired up for the UK code path."""
        en_with_bom = "\ufeff" + self.EN_SRT_TIGHT
        self._install_multi_lang_tree(page, en_body=en_with_bom)
        _goto_preview_video(page, server)
        page.evaluate("SPA.switchSubLang('en')")
        page.wait_for_function("previewState.srtLang === 'en'", timeout=5000)

        self._switch_to_edit(page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        page.wait_for_timeout(100)
        page.evaluate("""
          var el = document.activeElement;
          el.innerText = 'EN_EDIT';
          el.dispatchEvent(new Event('input', { bubbles: true }));
        """)
        page.wait_for_timeout(50)
        page.evaluate(
            "window._clipText = '';"
            " navigator.clipboard.writeText = function(t) {"
            "   window._clipText = t; return Promise.resolve();"
            " };"
            " window.open = function() {};"
            " window.alert = function() {};"
        )
        page.evaluate("SPA.openPreviewEditor()")
        page.wait_for_timeout(200)
        clip = page.evaluate("window._clipText || ''")
        assert not clip.startswith("\ufeff"), f"BOM leaked into EN clipboard: {clip[:10]!r}"
        expected = self.EN_SRT_TIGHT.replace("First EN block", "EN_EDIT")
        assert clip == expected, (
            f"EN BOM source not canonicalized.\n--- expected ---\n{expected!r}\n--- got ---\n{clip!r}"
        )

    def test_edits_are_scoped_by_language(self, server, page):
        """An edit made while viewing UK must NOT leak into the EN clipboard.
        After switching to EN with no EN edits, openPreviewEditor must take
        the no-clipboard branch (open URL only) — even though previewState.edits
        still holds UK edits. A regression that checked `Object.keys(edits).length`
        instead of `edits[lang]` would fail this test."""
        self._install_multi_lang_tree(page)
        _goto_preview_video(page, server)

        # Plant a UK edit through the real UI flow.
        self._switch_to_edit(page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        page.wait_for_timeout(100)
        page.evaluate("""
          var el = document.activeElement;
          el.innerText = 'UK_ONLY_EDIT';
          el.dispatchEvent(new Event('input', { bubbles: true }));
        """)
        page.wait_for_timeout(50)
        assert page.evaluate("previewState.edits.uk && previewState.edits.uk[0]") == "UK_ONLY_EDIT"

        # Switch to EN — edits for EN should be empty.
        page.evaluate("SPA.switchSubLang('en')")
        page.wait_for_function("previewState.srtLang === 'en'", timeout=5000)

        page.evaluate(
            "window._clipText = null;"
            " window._openedUrl = null;"
            " navigator.clipboard.writeText = function(t) {"
            "   window._clipText = t; return Promise.resolve();"
            " };"
            " window.open = function(u) { window._openedUrl = u; };"
            " window.alert = function() {};"
        )
        page.evaluate("SPA.openPreviewEditor()")
        page.wait_for_timeout(200)
        opened = page.evaluate("window._openedUrl || ''")
        clip_written = page.evaluate("window._clipText")

        assert "final/en.srt" in opened, f"EN target expected: {opened}"
        assert "final/uk.srt" not in opened, f"UK leaked into EN URL: {opened}"
        assert clip_written is None, f"Clipboard must NOT be touched for EN (no EN edits), got: {clip_written!r}"
        # UK edit must survive the language switch untouched.
        assert page.evaluate("previewState.edits.uk[0]") == "UK_ONLY_EDIT"

    def test_overlay_reflects_edited_text_during_playback(self, server, page):
        _goto_preview_video(page, server)
        self._switch_to_edit(page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        page.wait_for_timeout(100)
        # Overwrite the edit text.
        page.evaluate("""
          var el = document.activeElement;
          el.innerText = 'Відредагований субтитр';
          el.dispatchEvent(new Event('input', { bubbles: true }));
        """)
        page.wait_for_timeout(50)
        # Drive the player timeupdate to re-render overlay.
        page.evaluate("window._vimeoPlayer._setTime(3)")
        page.wait_for_timeout(200)
        overlay = page.evaluate("document.getElementById('subtitle-overlay').textContent")
        assert overlay == "Відредагований субтитр"

    def test_overlay_falls_back_to_original_when_edit_reverted(self, server, page):
        _goto_preview_video(page, server)
        self._switch_to_edit(page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        page.evaluate("""
          var el = document.activeElement;
          el.innerText = 'Перший субтитр';
          el.dispatchEvent(new Event('input', { bubbles: true }));
        """)
        page.wait_for_timeout(50)
        page.evaluate("window._vimeoPlayer._setTime(3)")
        page.wait_for_timeout(200)
        overlay = page.evaluate("document.getElementById('subtitle-overlay').textContent")
        assert overlay == "Перший субтитр"

    def test_clear_all_edit_mode(self, server, page):
        _goto_preview_video(page, server)
        self._switch_to_edit(page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        page.evaluate("""
          var el = document.activeElement;
          el.innerText = 'X';
          el.dispatchEvent(new Event('input', { bubbles: true }));
        """)
        page.wait_for_timeout(50)
        page.click("#btn-clear-all")
        spa_confirm_accept(page)
        count = page.locator(".edit-item").count()
        assert count == 0
        canon = page.evaluate(f"JSON.parse(localStorage.getItem('{CANON_UK_KEY}') || 'null') || {{}}")
        assert canon == {}


class TestIndexSingleLink:
    def test_single_preview_link_per_talk(self, server, page):
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        # Test-Talk has 2 videos but we want a single preview entry.
        links = page.locator(".talk-item").first.locator(".preview-link").count()
        assert links == 1, f"expected 1 preview link, got {links}"

    def test_preview_link_points_to_first_video(self, server, page):
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        href = page.locator(".talk-item").first.locator(".preview-link").get_attribute("href")
        assert href == "#/preview/2001-01-01_Test-Talk/Test-Video"


class TestSubtitleLangPerTalk:
    """Subtitle language choice is persisted per-talk, not per-video."""

    def test_lang_choice_saved_per_talk(self, server, page):
        # Seed availability of both uk and en for Test-Talk via manifest — the
        # default Test-Video only advertises uk in the fixture, so we flip via
        # the setter directly and then assert the new per-talk key.
        page.goto(f"{server}/index.html?_=1#/preview/2001-01-01_Test-Talk/Test-Video")
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        page.wait_for_function(
            "window.previewState && window.previewState.videoSlug === 'Test-Video'",
            timeout=10000,
        )
        page.evaluate("localStorage.setItem('sy_srt_lang_2001-01-01_Test-Talk', 'uk')")
        # Navigate to second video of the same talk — it should pick up the
        # per-talk saved lang without needing a video-specific entry.
        page.goto(f"{server}/index.html?_=2#/preview/2001-01-01_Test-Talk/Test-Video-2")
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        page.wait_for_function(
            "window.previewState && window.previewState.videoSlug === 'Test-Video-2'",
            timeout=10000,
        )
        lang = page.evaluate("window.previewState && window.previewState.srtLang")
        assert lang == "uk"

    def test_legacy_per_video_key_ignored(self, server, page):
        # Legacy per-video keys from before the per-talk change should not
        # leak into the new per-talk default behavior. We seed a legacy key
        # and expect it to be ignored (no crash, no false positive).
        page.add_init_script("localStorage.setItem('sy_srt_lang_2001-01-01_Test-Talk_Test-Video', 'xx')")
        page.goto(f"{server}/index.html?_=3#/preview/2001-01-01_Test-Talk/Test-Video")
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        page.wait_for_function(
            "window.previewState && window.previewState.videoSlug === 'Test-Video'",
            timeout=10000,
        )
        lang = page.evaluate("window.previewState && window.previewState.srtLang")
        # Only uk is available in the fixture — defaults to uk, legacy ignored.
        assert lang == "uk"


class TestReviewSrtLangDropdowns:
    """Review SRT mode: left dropdown shows source/ languages,
    right dropdown shows final/ languages, choices are persisted."""

    MULTI_SRC_TREE = {
        "sha": "test-multi-src",
        "tree": [
            {"path": "talks/2001-01-01_Test-Talk/Test-Video/final/uk.srt", "type": "blob"},
            {"path": "talks/2001-01-01_Test-Talk/Test-Video/final/en.srt", "type": "blob"},
            {"path": "talks/2001-01-01_Test-Talk/Test-Video/source/en.srt", "type": "blob"},
            {"path": "talks/2001-01-01_Test-Talk/Test-Video/source/hi.srt", "type": "blob"},
            {"path": "talks/2001-01-01_Test-Talk/Test-Video/source/whisper.json", "type": "blob"},
            {"path": "talks/2001-01-01_Test-Talk/Test-Video-2/final/uk.srt", "type": "blob"},
            {"path": "talks/2001-01-01_Test-Talk/Test-Video-2/source/en.srt", "type": "blob"},
            {"path": "talks/2001-01-01_Test-Talk/Test-Video-2/source/whisper.json", "type": "blob"},
            {"path": "talks/2001-01-01_Test-Talk/meta.yaml", "type": "blob"},
            {"path": "talks/2001-01-01_Test-Talk/review_report.md", "type": "blob"},
            {"path": "talks/2001-01-01_Test-Talk/transcript_en.txt", "type": "blob"},
            {"path": "talks/2001-01-01_Test-Talk/transcript_uk.txt", "type": "blob"},
        ],
    }

    def _install_tree(self, page):
        page.unroute("**/api.github.com/**")
        page.route(
            "**/api.github.com/**",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                headers={"ETag": '"test-etag-multi-src"'},
                body=json.dumps(self.MULTI_SRC_TREE),
            ),
        )

    def _goto_review_srt(self, server, page):
        self._install_tree(page)
        goto_spa(page, server)
        page.evaluate("localStorage.setItem('sy_expert_mode', '1'); expertMode = true; applyExpertMode();")
        page.evaluate("location.hash = '#/review/2001-01-01_Test-Talk'")
        page.wait_for_function("document.querySelectorAll('.cell').length > 0", timeout=10000)
        page.evaluate("SPA.switchReviewMode('srt', 'Test-Video')")
        page.wait_for_timeout(500)

    def test_manifest_has_src_srt_langs(self, server, page):
        """buildManifest should populate _srcSrtLangs from source/*.srt."""
        self._install_tree(page)
        goto_spa(page, server)
        page.evaluate("location.hash = '#/review/2001-01-01_Test-Talk'")
        page.wait_for_function("document.querySelectorAll('.cell').length > 0", timeout=10000)
        src_langs = page.evaluate(
            "manifest.talks.find(t => t.id === '2001-01-01_Test-Talk')._srcSrtLangs['Test-Video']"
        )
        assert sorted(src_langs) == ["en", "hi"]

    def test_manifest_has_final_srt_langs(self, server, page):
        """buildManifest should populate _srtLangs from final/*.srt."""
        self._install_tree(page)
        goto_spa(page, server)
        page.evaluate("location.hash = '#/review/2001-01-01_Test-Talk'")
        page.wait_for_function("document.querySelectorAll('.cell').length > 0", timeout=10000)
        final_langs = page.evaluate("manifest.talks.find(t => t.id === '2001-01-01_Test-Talk')._srtLangs['Test-Video']")
        assert sorted(final_langs) == ["en", "uk"]

    def test_left_dropdown_shows_source_langs(self, server, page):
        """Left column dropdown should list source/ languages."""
        self._goto_review_srt(server, page)
        page.evaluate("SPA.toggleTranscriptDropdown('left')")
        page.wait_for_selector("#transcript-dropdown-left.open", timeout=5000)
        texts = [el.text_content() for el in page.locator("#transcript-dropdown-left div").all()]
        assert len(texts) == 2
        assert "English" in texts
        assert "Hindi" in texts

    def test_right_dropdown_shows_final_langs(self, server, page):
        """Right column dropdown should list final/ languages."""
        self._goto_review_srt(server, page)
        page.evaluate("SPA.toggleTranscriptDropdown('right')")
        page.wait_for_selector("#transcript-dropdown-right.open", timeout=5000)
        texts = [el.text_content() for el in page.locator("#transcript-dropdown-right div").all()]
        assert len(texts) == 2
        assert "English" in texts
        assert "Ukrainian" in texts

    def test_srt_lang_choice_persisted(self, server, page):
        """switchSrtLang should save choice to localStorage."""
        self._goto_review_srt(server, page)
        page.evaluate("SPA.switchSrtLang('right', 'en')")
        page.wait_for_timeout(500)
        saved = page.evaluate("localStorage.getItem('sy_review_srt_right_2001-01-01_Test-Talk')")
        assert saved == "en"

    def test_srt_lang_choice_restored(self, server, page):
        """Saved SRT lang should be restored on re-entering SRT mode."""
        self._goto_review_srt(server, page)
        page.evaluate("localStorage.setItem('sy_review_srt_right_2001-01-01_Test-Talk', 'en')")
        # Re-enter SRT mode
        page.evaluate("SPA.switchReviewMode('srt', 'Test-Video')")
        page.wait_for_timeout(500)
        lang = page.evaluate("reviewState.srtRightLang")
        assert lang == "en"

    def test_default_langs_without_saved(self, server, page):
        """Without saved choice, left defaults to en, right to uk."""
        self._goto_review_srt(server, page)
        assert page.evaluate("reviewState.srtLeftLang") == "en"
        assert page.evaluate("reviewState.srtRightLang") == "uk"


class TestIndexFilterPersistence:
    """Active filter on the index is persisted separately for normal and
    expert mode so each mode recalls its own last choice."""

    def test_normal_mode_filter_persisted(self, server, page):
        page.add_init_script("localStorage.setItem('sy_expert_mode', '0');")
        goto_spa(page, server)
        page.wait_for_selector(".stat-card", timeout=10000)
        # Click the "in-review" stat card to change the filter (valid in normal mode).
        page.click('.stat-card[data-filter="in-review"]')
        page.wait_for_timeout(50)
        saved = page.evaluate("localStorage.getItem('sy_filter_normal')")
        assert saved == "in-review"
        # Reload and verify — the active stat card should match on rehydration.
        goto_spa(page, server)
        page.wait_for_selector(".stat-card.active", timeout=10000)
        active = page.evaluate(
            "document.querySelector('.stat-card.active') && document.querySelector('.stat-card.active').dataset.filter"
        )
        assert active == "in-review"

    def test_expert_mode_filter_persisted_separately(self, server, page):
        page.add_init_script("localStorage.setItem('sy_expert_mode', '1');")
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        page.click('.stat-card[data-filter="in-review"]')
        page.wait_for_timeout(50)
        assert page.evaluate("localStorage.getItem('sy_filter_expert')") == "in-review"
        # Normal-mode filter key must be untouched by expert-mode clicks.
        assert page.evaluate("localStorage.getItem('sy_filter_normal')") in (None, "needs-review")

    def test_toggle_expert_switches_filter_to_saved(self, server, page):
        page.add_init_script(
            "localStorage.setItem('sy_expert_mode', '0');"
            "localStorage.setItem('sy_filter_normal', 'in-review');"
            "localStorage.setItem('sy_filter_expert', 'approved');"
        )
        goto_spa(page, server)
        page.wait_for_selector(".stat-card.active", timeout=10000)
        active = page.evaluate("document.querySelector('.stat-card.active').dataset.filter")
        assert active == "in-review"
        # Toggle to expert mode — filter should switch to the expert saved value.
        page.evaluate("SPA.toggleExpert()")
        page.wait_for_timeout(50)
        active = page.evaluate("document.querySelector('.stat-card.active').dataset.filter")
        assert active == "approved"


class TestIndexRemembersLastVideo:
    def test_last_viewed_video_saved_on_preview(self, server, page):
        _goto_preview_video(page, server, "Test-Video-2")
        saved = page.evaluate("localStorage.getItem('sy_last_video_2001-01-01_Test-Talk')")
        assert saved == "Test-Video-2"

    def test_index_link_targets_last_viewed_video(self, server, page):
        page.add_init_script("localStorage.setItem('sy_last_video_2001-01-01_Test-Talk', 'Test-Video-2')")
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        href = page.locator(".talk-item").first.locator(".preview-link").get_attribute("href")
        assert href == "#/preview/2001-01-01_Test-Talk/Test-Video-2"

    def test_index_link_falls_back_to_first_video_when_last_invalid(self, server, page):
        page.add_init_script("localStorage.setItem('sy_last_video_2001-01-01_Test-Talk', 'Nope-Does-Not-Exist')")
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        href = page.locator(".talk-item").first.locator(".preview-link").get_attribute("href")
        assert href == "#/preview/2001-01-01_Test-Talk/Test-Video"


class TestPreviewVideoSwitcher:
    def test_switcher_visible_for_multi_video(self, server, page):
        _goto_preview_video(page, server)
        visible = page.locator("#preview-video-select").is_visible()
        assert visible is True

    def test_switcher_changes_route(self, server, page):
        _goto_preview_video(page, server)
        page.select_option("#preview-video-select", "Test-Video-2")
        page.wait_for_timeout(500)
        assert "Test-Video-2" in page.url


class TestPreviewMarkerIssueAndCopy:
    """Coverage for the 'Copy all' and marker-mode 'Create issue' buttons.

    These verify that the *content* handed to clipboard/window.open is correct,
    not just that the buttons render. Gaps in this area previously let broken
    markdown tables or wrong file paths slip through silently."""

    def _seed_markers(self, page):
        # Markers live in marker mode; edit is the default now, so switch first.
        page.click('.preview-mode-toggle [data-mode="marker"]')
        page.wait_for_timeout(50)
        page.evaluate(
            """
            previewState.markers = [
              { time: 2, tc: '00:00:02', text: 'Перший субтитр', comment: 'timing off' },
              { time: 7, tc: '00:00:07', text: 'Другий субтитр', comment: '' }
            ];
            savePreviewState();
            renderMarkers();
            updateClearBtn();
            """
        )

    def test_copy_all_puts_markdown_markers_on_clipboard(self, server, page):
        """#btn-copy-all must copy a markdown bullet list: `- **{tc}** {text} — _{comment}_`.
        Empty comments must NOT produce a trailing em-dash."""
        _goto_preview_video(page, server)
        self._seed_markers(page)
        page.evaluate(
            """
            window._clipText = '';
            navigator.clipboard.writeText = function(t) {
              window._clipText = t; return Promise.resolve();
            };
            """
        )
        page.click("#btn-copy-all")
        page.wait_for_timeout(150)
        clip = page.evaluate("window._clipText || ''")
        assert clip.startswith("# "), f"expected title header, got: {clip[:200]}"
        # Both marker timestamps and texts present.
        assert "**00:00:02**" in clip and "Перший субтитр" in clip, clip[:500]
        assert "**00:00:07**" in clip and "Другий субтитр" in clip, clip[:500]
        # Commented marker → em-dash italic suffix.
        assert "— _timing off_" in clip, clip[:500]
        # Empty-comment marker must NOT carry an em-dash / italic block.
        second = next(line for line in clip.splitlines() if "Другий субтитр" in line)
        assert "—" not in second and "_" not in second, f"stray comment suffix: {second!r}"

    def test_create_issue_marker_mode_body_contains_markers_table(self, server, page):
        """SPA.createPreviewIssue() in marker mode must build a GitHub issues/new URL
        whose body has the SRT path, a `### Markers` table with `| Time | Subtitle | Comment |`
        header, and a row per marker — including an empty comment cell. It must NOT
        leak the edit-mode `Suggested edits` section."""
        _goto_preview_video(page, server)
        self._seed_markers(page)
        page.evaluate(
            "window._openedUrl = null;"
            " window.open = function(u) { window._openedUrl = u; };"
            " navigator.clipboard.writeText = function() { return Promise.resolve(); };"
            " window.alert = function() {};"
        )
        page.evaluate("SPA.createPreviewIssue()")
        page.wait_for_timeout(200)
        url = page.evaluate("window._openedUrl || ''")
        body = unquote(url)
        assert "/issues/new" in url, url[:300]
        assert "labels=review:pending" in url, url[:300]
        assert "Test-Video/final/uk.srt" in body, body[:500]
        assert "### Markers" in body, body[:600]
        assert "| Time | Subtitle | Comment |" in body, body[:600]
        assert "| 00:00:02 | Перший субтитр | timing off |" in body, body[:600]
        assert "| 00:00:07 | Другий субтитр |  |" in body, body[:600]
        assert "Suggested edits" not in body, f"marker body leaked edits section: {body[:500]}"


class TestAddTalkForm:
    """E2E coverage for the 'Create PR' (Add Talk) button.

    `SPA.submitAddTalk()` builds a GitHub 'new file' URL from DOM inputs. Until
    now only the yaml builder was unit-tested in isolation — nothing verified
    that the button produces the right filename/message/encoded yaml at runtime,
    so a broken form→URL wiring would ship silently."""

    ADD_DATA = {
        "t": "My Test Talk",
        "d": "2020-05-05",
        "u": "https://www.amruta.org/2020/05/05/my-test-talk/",
        "loc": "Test City",
        "v": [{"id": "1234", "h": "abcd"}],
        "tx": "Intro line. Second line of transcript body.",
    }

    def _open_add_form(self, page, server, transcript=None):
        data = dict(self.ADD_DATA)
        if transcript is not None:
            data["tx"] = transcript
        encoded = quote(json.dumps(data), safe="")
        page.goto(f"{server}{SPA_URL}#/add?data={encoded}")
        page.wait_for_selector("#add-form", state="visible", timeout=5000)
        page.wait_for_timeout(200)  # let updateAddPreview run

    def test_form_prefilled_from_bookmarklet_data(self, server, page):
        self._open_add_form(page, server)
        assert page.input_value("#add-title") == "My Test Talk"
        assert page.input_value("#add-date") == "2020-05-05"
        assert "amruta.org" in page.input_value("#add-url")
        assert page.input_value("#add-location") == "Test City"

    def test_preview_yaml_contains_expected_fields(self, server, page):
        self._open_add_form(page, server)
        yaml_text = page.locator("#add-preview").text_content()
        assert "title: 'My Test Talk'" in yaml_text
        assert "date: '2020-05-05'" in yaml_text
        # Free-text scalars are single-quoted so a colon can't corrupt the YAML.
        assert "location: 'Test City'" in yaml_text
        assert "amruta_url: https://www.amruta.org/" in yaml_text
        assert "language: en" in yaml_text
        assert "videos:" in yaml_text
        # Link stored obfuscated as video_ref — no plaintext vimeo in the preview.
        assert "vimeo_url" not in yaml_text
        ref = re.search(r"video_ref: (r1\S+)", yaml_text).group(1)
        assert decode_video_ref(ref) == "https://vimeo.com/1234/abcd"
        assert "transcript_en_base64: |" in yaml_text
        # The preview must be valid YAML — this is the exact path the pipeline's
        # yaml.safe_load takes; substring checks alone would miss a quoting bug.
        parsed = yaml.safe_load(yaml_text)
        assert parsed["location"] == "Test City"

    def test_preview_yaml_valid_when_fields_contain_colons(self, server, page):
        """Regression (sy-tools/sy-subtitles#293): a colon in a video title —
        e.g. "Guru Puja Talk: Gurus Who Belong To The Collective" — was emitted
        unquoted and produced YAML that failed yaml.safe_load ("mapping values
        are not allowed here"), breaking the new-talk `detect` job. Drive the
        real form with colons in the talk title, location, and a video title,
        then assert the preview parses and every value round-trips intact."""
        data = {
            "t": "Guru Puja: Gurus who belong to the collective",
            "d": "1993-07-04",
            "u": "https://www.amruta.org/1993/07/04/guru-puja-1993/",
            "loc": "Public Program: Cabella Ligure",
            "v": [
                {"id": "666666666", "h": "ffffffffff", "l": "Guru Puja"},
                {
                    "id": "555555555",
                    "h": "eeeeeeeeee",
                    "l": "Guru Puja Talk: Gurus Who Belong To The Collective",
                },
            ],
            "tx": "He said 100% & it's done.",
        }
        encoded = quote(json.dumps(data), safe="")
        page.goto(f"{server}{SPA_URL}#/add?data={encoded}")
        page.wait_for_selector("#add-form", state="visible", timeout=5000)
        page.wait_for_timeout(200)  # let updateAddPreview run

        yaml_text = page.locator("#add-preview").text_content()
        # The colon-bearing video title must be quoted in the rendered preview.
        assert "title: 'Guru Puja Talk: Gurus Who Belong To The Collective'" in yaml_text, yaml_text

        # Parsing is the real contract — this is what the pipeline runs.
        parsed = yaml.safe_load(yaml_text)
        assert parsed["title"] == "Guru Puja: Gurus who belong to the collective"
        assert parsed["location"] == "Public Program: Cabella Ligure"
        assert [v["title"] for v in parsed["videos"]] == [
            "Guru Puja",
            "Guru Puja Talk: Gurus Who Belong To The Collective",
        ]

    def test_create_pr_button_generates_github_new_file_url(self, server, page):
        self._open_add_form(page, server)
        page.evaluate(
            "window._openedUrl = null;"
            " window.open = function(u) { window._openedUrl = u; };"
            " window.alert = function() {};"
        )
        page.evaluate("SPA.submitAddTalk()")
        page.wait_for_timeout(200)
        url = page.evaluate("window._openedUrl || ''")
        assert url.startswith("https://github.com/"), url[:300]
        assert "/new/main" in url, url[:300]
        # Filename from slugify("My Test Talk") → "My-Test-Talk".
        assert "filename=talks%2F2020-05-05_My-Test-Talk%2Fmeta.yaml" in url, url[:500]
        assert "message=Add%20My%20Test%20Talk" in url, url[:500]
        m = re.search(r"[?&]value=([^&]+)", url)
        assert m, f"no value= in URL: {url[:300]}"
        yaml_decoded = unquote(m.group(1))
        assert "title: 'My Test Talk'" in yaml_decoded, yaml_decoded[:400]
        assert "date: '2020-05-05'" in yaml_decoded, yaml_decoded[:400]
        assert "vimeo_url" not in yaml_decoded, yaml_decoded[:400]
        ref = re.search(r"video_ref: (r1\S+)", yaml_decoded).group(1)
        assert decode_video_ref(ref) == "https://vimeo.com/1234/abcd", yaml_decoded[:400]
        assert "transcript_en_base64: |" in yaml_decoded, yaml_decoded[:400]
        assert "language: en" in yaml_decoded, yaml_decoded[:400]
        # Description carries the source amruta URL.
        d = re.search(r"[?&]description=([^&]+)", url)
        assert d is not None, url[:400]
        assert "amruta.org" in unquote(d.group(1))

    def test_create_pr_submit_via_real_form_submit(self, server, page):
        """Clicking the actual <button type="submit">Create PR</button> must
        trigger the same URL (not just calling SPA.submitAddTalk() manually)."""
        self._open_add_form(page, server)
        page.evaluate(
            "window._openedUrl = null;"
            " window.open = function(u) { window._openedUrl = u; };"
            " window.alert = function() {};"
        )
        page.click('#add-form button[type="submit"]')
        page.wait_for_timeout(200)
        url = page.evaluate("window._openedUrl || ''")
        assert "/new/main" in url, url[:400]
        assert "filename=talks%2F2020-05-05_My-Test-Talk%2Fmeta.yaml" in url, url[:400]

    def test_create_pr_with_long_yaml_copies_to_clipboard(self, server, page):
        """When the full URL would exceed 8000 chars the yaml is copied to the
        clipboard and a short URL (without `value=`) is opened instead."""
        self._open_add_form(page, server, transcript="a" * 12000)
        page.evaluate("updateAddPreview()")
        page.evaluate(
            "window._openedUrl = null;"
            " window._clipText = '';"
            " window.open = function(u) { window._openedUrl = u; };"
            " navigator.clipboard.writeText = function(t) {"
            "   window._clipText = t; return Promise.resolve();"
            " };"
            " window.alert = function() {};"
        )
        page.evaluate("SPA.submitAddTalk()")
        page.wait_for_timeout(300)
        url = page.evaluate("window._openedUrl || ''")
        clip = page.evaluate("window._clipText || ''")
        assert "/new/main" in url, url[:400]
        assert "value=" not in url, f"long URL should be shortened: {url[:400]}"
        assert "filename=talks%2F2020-05-05_My-Test-Talk%2Fmeta.yaml" in url, url[:400]
        assert "message=Add%20My%20Test%20Talk" in url, url[:400]
        assert "title: 'My Test Talk'" in clip, clip[:400]
        assert "transcript_en_base64" in clip, clip[:400]


class TestBookmarkletExtraction:
    """E2E for the add-talk bookmarklet's page scraping.

    The scraping logic lives in site/js/bookmarklet.js. The saved bookmark is a
    thin loader that injects that file from the deployed site; on an amruta.org
    talk page it reads the DOM and opens the SPA with the extracted payload.
    The extraction had no test before (the 'real amruta parsing' suite asserts
    pre-parsed JSON, not the live code), so a selector that silently stopped
    matching a page shape would ship unnoticed — exactly what surfaced on the
    Christmas Puja 1998 talk (empty location / video titles / transcript).

    These tests load the exact shipped bookmarklet.js and run its
    extractAmrutaTalk against a saved fixture, locking in the DOM structures
    its selectors depend on."""

    FIXTURE = Path(__file__).parent / "fixtures" / "amruta_christmas_puja_1998.html"
    BOOKMARKLET_JS = Path(__file__).parent.parent / "site" / "js" / "bookmarklet.js"

    def _run_bookmarklet(self, page):
        """Load the shipped scraper (site/js/bookmarklet.js) into the page and
        return extractAmrutaTalk(document) — the exact payload the loader
        bookmarklet would hand to the SPA.

        eval() is intentional: it loads our own shipped source into a throwaway
        test page (no untrusted input). The file's auto-open branch is inert
        here — document.currentScript is null under eval — so we call
        extractAmrutaTalk directly and assert its payload."""
        js = self.BOOKMARKLET_JS.read_text()
        return page.evaluate(
            "(src) => { eval(src); return window.extractAmrutaTalk(document); }",
            js,
        )

    def test_fixture_exists(self):
        assert self.FIXTURE.exists(), f"missing fixture: {self.FIXTURE}"
        assert self.BOOKMARKLET_JS.exists(), f"missing scraper: {self.BOOKMARKLET_JS}"

    def test_loader_path_injects_scraper_and_opens_spa(self, browser, server):
        """Full production path: inject bookmarklet.js as a real <script> (as
        the loader bookmarklet does) and confirm it scrapes the page and opens
        the SPA add view. Exercises the auto-open branch + SPA-base derivation
        from document.currentScript.src — which the direct extractAmrutaTalk
        call cannot cover."""
        ctx = browser.new_context()
        try:
            pg = ctx.new_page()
            pg.goto(f"{server}/index.html")  # same-origin host for the injected <script>
            pg.set_content(
                '<div class="entry-content"><p>A paragraph with plenty of words so it is kept by the scraper.</p></div>'
            )
            pg.evaluate("() => { window.__opened = null; window.open = (u) => { window.__opened = u; }; }")
            pg.add_script_tag(url=f"{server}/js/bookmarklet.js")
            opened = pg.evaluate("() => window.__opened")
        finally:
            ctx.close()

        assert opened, "bookmarklet.js did not call window.open when injected"
        assert "/index.html#/add?data=" in opened, opened
        data = json.loads(unquote(opened.split("#/add?data=", 1)[1]))
        assert data["tx"] == "A paragraph with plenty of words so it is kept by the scraper."

    def test_extracts_nonempty_fields_from_real_page(self, browser):
        ctx = browser.new_context()
        try:
            pg = ctx.new_page()
            pg.goto(self.FIXTURE.as_uri())
            data = self._run_bookmarklet(pg)
        finally:
            ctx.close()

        # Talk title (h1.entry-title).
        assert data["t"] == "Christmas Puja: Become Thoughtlessly Aware", data["t"]
        # Location — the line before "Talk Language:" in the .entry-content h4.
        # This was reported empty; guard it explicitly.
        assert data["loc"] == "Ganapatipule (India)", repr(data["loc"])
        # Both video titles (from .video-meta-info), each with a vimeo id+hash.
        assert [v["l"] for v in data["v"]] == [
            "Christmas Puja",
            "Christmas Puja Talk",
        ], data["v"]
        assert all(v["id"] and v["h"] for v in data["v"]), data["v"]
        # Transcript (.entry-content paragraphs) — non-empty and real content.
        assert len(data["tx"]) > 1000, len(data["tx"])
        assert "Christ was born" in data["tx"], data["tx"][:200]

    def test_transcript_collapses_hardwrapped_paragraphs_and_nbsp(self, browser):
        """Older amruta posts hard-wrap paragraph text with literal newlines,
        and stray non-breaking spaces sneak in. The bookmarklet must normalize
        each paragraph to a single line (so the transcript is one line per
        paragraph, joined by \\n) with no U+00A0.

        Regression: the 1983 Shri Saraswati Puja transcript came through
        bookmarklet→PR with every paragraph split across ~75-char lines and a
        non-breaking space mid-text."""
        ctx = browser.new_context()
        try:
            pg = ctx.new_page()
            pg.set_content(
                '<div class="entry-content">'
                "<p>This is the first paragraph that the source HTML\n"
                "hard-wrapped across several\nlines for readability.</p>"
                "<p>Second paragraph with a non-breaking\u00a0space sitting inside it.</p>"
                "</div>"
            )
            data = self._run_bookmarklet(pg)
        finally:
            ctx.close()

        assert data["tx"] == (
            "This is the first paragraph that the source HTML hard-wrapped "
            "across several lines for readability.\n"
            "Second paragraph with a non-breaking space sitting inside it."
        ), repr(data["tx"])
        assert "\u00a0" not in data["tx"]
        # Exactly two lines — one per <p>, no mid-paragraph breaks.
        assert len(data["tx"].split("\n")) == 2, data["tx"]

    def test_skips_header_p_and_spaces_br_separated_sentences(self, browser):
        """Some pages (e.g. 1997 Sahasrara Puja) separate sentences inside a
        paragraph with <br>, and duplicate the date/title/location/language
        header into a <p>. textContent drops <br> (merging "end.Start") and
        the header <p> would leak into the transcript body. The bookmarklet
        must turn <br> into a space and skip a header-like <p> so new-talk.yml
        synthesizes the clean header instead.

        Regression: 1997 Sahasrara Puja came through with a crushed run-on
        header line and merged sentences."""
        ctx = browser.new_context()
        try:
            pg = ctx.new_page()
            pg.set_content(
                '<div class="entry-content">'
                "<p>4 May 1997<br>Sahasrara Puja<br>Cabella (Italy)<br>"
                "Talk Language: English | Transcript (English)</p>"
                "<p>First sentence here.<br>Second sentence here.<br>Third sentence here.</p>"
                "<p>Another paragraph with a single sentence in it here.</p>"
                "</div>"
            )
            data = self._run_bookmarklet(pg)
        finally:
            ctx.close()

        # Header <p> (has "Talk Language:") is skipped — not in the transcript.
        assert "Talk Language:" not in data["tx"], data["tx"]
        # <br> between sentences becomes a space (not a merge, not a line break);
        # each <p> is one line.
        assert data["tx"] == (
            "First sentence here. Second sentence here. Third sentence here.\n"
            "Another paragraph with a single sentence in it here."
        ), repr(data["tx"])


class TestTranscriptVideoSync:
    """Review-page transcript mode: Show Video button, video picker,
    paragraph ↔ SRT-block wiring."""

    TALK_ID = "2001-01-01_Test-Talk"
    UK_TRANSCRIPT = "Мова промови: англійська\n\nПерший субтитр\n\nДругий субтитр\n"
    UK_SRT = "1\n00:00:01,000 --> 00:00:05,000\nПерший субтитр\n\n2\n00:00:06,000 --> 00:00:10,000\nДругий субтитр\n"

    def _patch_matching_fixtures(self, page):
        """Override UK transcript + UK SRT so paragraph text maps cleanly
        to SRT block times. Must be called BEFORE navigating."""
        page.route(
            "**/raw.githubusercontent.com/**/transcript_uk.txt",
            lambda route: route.fulfill(status=200, content_type="text/plain", body=self.UK_TRANSCRIPT),
        )
        page.route(
            "**/raw.githubusercontent.com/**/final/uk.srt",
            lambda route: route.fulfill(status=200, content_type="text/plain", body=self.UK_SRT),
        )

    def _goto_review(self, server, page):
        self._patch_matching_fixtures(page)
        goto_spa(page, server, f"#/review/{self.TALK_ID}")
        page.wait_for_function("document.querySelectorAll('.cell.uk').length > 0", timeout=10000)

    def test_show_video_btn_visible_in_transcript_mode(self, server, page):
        self._goto_review(server, page)
        assert page.locator("#btn-sync-player").is_visible()

    def test_multi_video_click_opens_picker(self, server, page):
        self._goto_review(server, page)
        page.click("#btn-sync-player")
        page.wait_for_timeout(100)
        dd = page.locator("#video-picker-dropdown")
        assert dd.evaluate("el => el.classList.contains('open')")
        options = dd.locator("div[role='option']")
        assert options.count() == 2  # two videos in the fixture

    def test_picker_lists_video_titles(self, server, page):
        self._goto_review(server, page)
        page.click("#btn-sync-player")
        page.wait_for_timeout(100)
        texts = page.locator("#video-picker-dropdown div[role='option']").all_text_contents()
        assert "Test Video" in texts
        assert "Test Video 2" in texts

    def test_picking_video_annotates_cells_with_ms(self, server, page):
        self._goto_review(server, page)
        page.click("#btn-sync-player")
        page.wait_for_timeout(100)
        page.click('#video-picker-dropdown div[data-slug="Test-Video"]')
        page.wait_for_function("document.querySelector('.cell.uk[data-ms-start]') !== null", timeout=5000)
        # First paragraph maps to SRT block 1 → 1000ms start.
        first_uk_ms = page.locator(".cell.uk[data-ms-start]").first.get_attribute("data-ms-start")
        assert first_uk_ms == "1000"

    def test_picking_video_persists_selection(self, server, page):
        self._goto_review(server, page)
        page.click("#btn-sync-player")
        page.wait_for_timeout(100)
        page.click('#video-picker-dropdown div[data-slug="Test-Video-2"]')
        page.wait_for_function("document.querySelector('.cell.uk[data-ms-start]') !== null", timeout=5000)
        stored = page.evaluate(f"localStorage.getItem('sy_review_transcript_video_{self.TALK_ID}')")
        assert stored == "Test-Video-2"

    def test_dropdown_closes_on_outside_click(self, server, page):
        self._goto_review(server, page)
        page.click("#btn-sync-player")
        page.wait_for_timeout(50)
        assert page.evaluate("document.getElementById('video-picker-dropdown').classList.contains('open')")
        page.click("#review-grid", position={"x": 10, "y": 10})
        page.wait_for_timeout(50)
        assert not page.evaluate("document.getElementById('video-picker-dropdown').classList.contains('open')")

    def test_click_on_paragraph_seeks_player(self, server, page):
        self._goto_review(server, page)
        page.click("#btn-sync-player")
        page.wait_for_timeout(100)
        page.click('#video-picker-dropdown div[data-slug="Test-Video"]')
        # Wait for SyncPlayer + mock-player to be wired up.
        page.wait_for_selector("#mock-player", state="visible", timeout=5000)
        # Reset any auto-set time, then click the SECOND EN paragraph
        # which should seek to 6000ms (block 2 start).
        page.evaluate("window._vimeoPlayer._setTime(0)")
        en_cells = page.locator("#view-review .cell.en[data-ms-start]")
        # Grab the second paragraph (index 1) so we seek past 0.
        en_cells.nth(1).click()
        page.wait_for_timeout(200)
        t = page.evaluate("window._vimeoPlayer._currentTime")
        assert t == pytest.approx(6.0, abs=0.05)

    def test_paragraph_label_includes_timecode_after_pick(self, server, page):
        self._goto_review(server, page)
        page.click("#btn-sync-player")
        page.wait_for_timeout(100)
        page.click('#video-picker-dropdown div[data-slug="Test-Video"]')
        page.wait_for_function("document.querySelector('.cell.uk[data-ms-start]') !== null", timeout=5000)
        first_label = page.locator(".cell.uk .cell-label").first.text_content()
        # Label should include the paragraph id AND a timecode derived from SRT.
        assert "P1" in first_label
        assert "00:01" in first_label  # 00:00:01 → compact msToTC formats as 00:01

    def test_reclick_show_btn_reopens_picker_when_hidden(self, server, page):
        """After picking a video and hiding the player, clicking Show again
        must reopen the picker so the user can switch videos."""
        self._goto_review(server, page)
        page.click("#btn-sync-player")
        page.wait_for_timeout(100)
        page.click('#video-picker-dropdown div[data-slug="Test-Video"]')
        page.wait_for_selector("#mock-player", state="visible", timeout=5000)
        # Hide the player via the toggle (button now says "Hide video").
        page.click("#btn-sync-player")
        page.wait_for_timeout(100)
        assert page.evaluate("!SyncPlayer.isOpen()")
        # Click again → dropdown should reopen.
        page.click("#btn-sync-player")
        page.wait_for_timeout(100)
        assert page.evaluate("document.getElementById('video-picker-dropdown').classList.contains('open')")

    def test_revisit_autoloads_saved_video(self, server, page):
        """Leaving and returning to the transcript review should auto-open
        the player for the last-chosen video — it's "remembered state"."""
        self._patch_matching_fixtures(page)
        page.add_init_script(f"localStorage.setItem('sy_review_transcript_video_{self.TALK_ID}', 'Test-Video');")
        goto_spa(page, server, f"#/review/{self.TALK_ID}")
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        # And paragraph cells carry data-ms-start → mapping actually ran.
        page.wait_for_function("document.querySelector('.cell.uk[data-ms-start]') !== null", timeout=5000)

    def test_label_resets_to_plain_after_render_without_video(self, server, page):
        """Before any video is picked, labels stay plain P1/P2/... (no times)."""
        self._goto_review(server, page)
        labels = page.locator(".cell.uk .cell-label").all_text_contents()
        for text in labels:
            assert "00:" not in text


class TestMatchParagraphsToSrt:
    """Pure-function tests for SPA._matchParagraphsToSrt — the paragraph →
    SRT-block mapping that powers the transcript-mode sync player."""

    SRT = (
        "1\n00:00:01,000 --> 00:00:05,000\nThis is the first block.\n\n"
        "2\n00:00:05,500 --> 00:00:09,000\nSecond block continues here.\n\n"
        "3\n00:00:09,500 --> 00:00:13,000\nThird block, final line.\n\n"
        "4\n00:00:14,000 --> 00:00:18,000\nFourth block says something new.\n\n"
        "5\n00:00:18,500 --> 00:00:22,000\nFifth block wraps the talk.\n"
    )

    def _open_spa(self, server, page):
        goto_spa(page, server, "")
        page.wait_for_function(
            "typeof SPA !== 'undefined' && !!SPA._matchParagraphsToSrt",
            timeout=5000,
        )

    def _match(self, page, paragraphs, srt=None):
        return page.evaluate(
            "([paras, srt]) => SPA._matchParagraphsToSrt(paras, SPA._parseSRT(srt))",
            [paragraphs, srt if srt is not None else self.SRT],
        )

    def test_identical_paragraphs_mapped_to_block_spans(self, server, page):
        self._open_spa(server, page)
        out = self._match(
            page,
            [
                "This is the first block.",
                "Second block continues here. Third block, final line.",
                "Fourth block says something new. Fifth block wraps the talk.",
            ],
        )
        assert out[0] == {"startMs": 1000, "endMs": 5000}
        assert out[1] == {"startMs": 5500, "endMs": 13000}
        assert out[2] == {"startMs": 14000, "endMs": 22000}

    def test_paragraph_with_punctuation_differences_still_matches(self, server, page):
        self._open_spa(server, page)
        out = self._match(page, ["THIS is; the, FIRST block!"])
        assert out[0] == {"startMs": 1000, "endMs": 5000}

    def test_empty_paragraph_returns_null(self, server, page):
        self._open_spa(server, page)
        out = self._match(page, ["", "   ", "This is the first block."])
        assert out[0] is None
        assert out[1] is None
        assert out[2] == {"startMs": 1000, "endMs": 5000}

    def test_unmatched_paragraph_returns_null_and_does_not_block_next(self, server, page):
        self._open_spa(server, page)
        out = self._match(
            page,
            [
                "This paragraph has nothing in common with the subtitles at all.",
                "Second block continues here.",
            ],
        )
        assert out[0] is None
        assert out[1] == {"startMs": 5500, "endMs": 9000}

    def test_matching_is_monotonic(self, server, page):
        """A phrase that appears twice should map to its Nth occurrence for
        the Nth paragraph, not collapse to the first."""
        self._open_spa(server, page)
        srt = (
            "1\n00:00:01,000 --> 00:00:05,000\nShared phrase here.\n\n"
            "2\n00:00:06,000 --> 00:00:10,000\nDifferent content.\n\n"
            "3\n00:00:11,000 --> 00:00:15,000\nShared phrase here.\n"
        )
        out = self._match(page, ["Shared phrase here.", "Shared phrase here."], srt)
        assert out[0]["startMs"] == 1000
        assert out[1]["startMs"] == 11000  # second occurrence, not first

    def test_probe_fallback_handles_small_edits(self, server, page):
        """A paragraph whose tail diverged from SRT (an edit) should still
        resolve its start via the first-60-chars probe."""
        self._open_spa(server, page)
        out = self._match(page, ["This is the first block but with an extra tail added locally."])
        assert out[0] is not None
        assert out[0]["startMs"] == 1000


class TestStickyHeaders:
    """Headers must remain visible while scrolling so action buttons are
    always reachable."""

    def _goto_review(self, server, page):
        goto_spa(page, server, "#/review/2001-01-01_Test-Talk")
        page.wait_for_function("document.querySelectorAll('.cell.uk').length > 0", timeout=10000)

    def _goto_preview(self, server, page):
        goto_spa(page, server, "#/preview/2001-01-01_Test-Talk/Test-Video")
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        page.wait_for_timeout(500)

    def test_freshness_bar_is_sticky(self, server, page):
        self._goto_review(server, page)
        pos = page.evaluate("getComputedStyle(document.getElementById('freshness-bar')).position")
        assert pos == "sticky"

    def test_review_header_is_sticky(self, server, page):
        self._goto_review(server, page)
        pos = page.evaluate("getComputedStyle(document.querySelector('#view-review > .header')).position")
        assert pos == "sticky"

    def test_preview_header_is_sticky(self, server, page):
        self._goto_preview(server, page)
        pos = page.evaluate("getComputedStyle(document.querySelector('#view-preview > .header')).position")
        assert pos == "sticky"

    def test_review_header_visible_after_scroll(self, server, page):
        self._goto_review(server, page)
        # Inject enough cells to make the page actually scroll past the header,
        # otherwise sticky has no work to do and the test would falsely pass.
        page.evaluate("""
          const grid = document.getElementById('review-grid');
          for (let i = 0; i < 100; i++) {
            const en = document.createElement('div'); en.className = 'cell en'; en.textContent = 'EN ' + i;
            const uk = document.createElement('div'); uk.className = 'cell uk'; uk.textContent = 'UK ' + i;
            grid.appendChild(en); grid.appendChild(uk);
          }
        """)
        page.evaluate("window.scrollTo(0, 2000)")
        page.wait_for_timeout(100)
        sy = page.evaluate("window.scrollY")
        assert sy > 1500, f"page failed to scroll (scrollY={sy})"
        rect = page.evaluate(
            "(() => { const r = document.querySelector('#view-review > .header').getBoundingClientRect(); return {top: r.top, bottom: r.bottom}; })()"
        )
        # Header bottom edge should still be inside the viewport (sticky pinned).
        assert rect["bottom"] > 0
        assert rect["top"] < 100  # near the top of viewport

    def test_freshness_bar_above_view_header(self, server, page):
        """When both are pinned, freshness-bar must sit above the view header."""
        self._goto_review(server, page)
        page.evaluate("window.scrollTo(0, 1500)")
        page.wait_for_timeout(100)
        fb_bottom = page.evaluate("document.getElementById('freshness-bar').getBoundingClientRect().bottom")
        hdr_top = page.evaluate("document.querySelector('#view-review > .header').getBoundingClientRect().top")
        # Header should sit at or below the freshness-bar bottom (no overlap).
        assert hdr_top >= fb_bottom - 1


class TestStickyHeaderWithSyncPlayer:
    """Regression: when the SyncPlayer is open on the review page, the
    player bar must not overlap the view header."""

    def _goto_review(self, server, page):
        goto_spa(page, server, "#/review/2001-01-01_Test-Talk")
        page.wait_for_function("document.querySelectorAll('.cell.uk').length > 0", timeout=10000)

    def test_view_header_visible_when_sync_player_open(self, server, page):
        self._goto_review(server, page)
        # Add scrollable content so sticky pinning kicks in.
        page.evaluate("""
          const grid = document.getElementById('review-grid');
          for (let i = 0; i < 100; i++) {
            const en = document.createElement('div'); en.className = 'cell en'; en.textContent = 'EN ' + i;
            const uk = document.createElement('div'); uk.className = 'cell uk'; uk.textContent = 'UK ' + i;
            grid.appendChild(en); grid.appendChild(uk);
          }
        """)
        # Force-show the sync player bar (avoids touching Vimeo player init).
        page.evaluate("document.getElementById('sync-player-bar').hidden = false;")
        page.evaluate("window.scrollTo(0, 2000)")
        page.wait_for_timeout(150)
        info = page.evaluate("""(() => {
          const h = document.querySelector('#view-review > .header').getBoundingClientRect();
          const p = document.getElementById('sync-player-bar').getBoundingClientRect();
          return {header_top: h.top, header_bottom: h.bottom, player_top: p.top};
        })()""")
        # View header must remain inside the viewport, and the player bar must
        # sit BELOW the header (no overlap).
        assert info["header_bottom"] > 0, f"header off-screen: {info}"
        assert info["header_top"] < 100, f"header not pinned: {info}"
        assert info["player_top"] >= info["header_bottom"] - 1, f"player overlaps header: {info}"


class TestUkrainianPlurals:
    """Clear/revert confirm dialogs must agree grammatically in Ukrainian:
    1 редагування, 2–4 редагування, 5+ редагувань; 1 маркер, 2–4 маркери,
    5+ маркерів."""

    def _goto_preview(self, server, page):
        goto_spa(page, server, "#/preview/2001-01-01_Test-Talk/Test-Video")
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        page.wait_for_timeout(500)

    def _force_lang(self, page, lang):
        page.evaluate(f"currentLang = '{lang}'")

    def test_uk_plural_edits_shape(self, server, page):
        self._goto_preview(server, page)
        self._force_lang(page, "uk")
        # Spot-check the boundary cases defined by Ukrainian plural rules.
        cases = {
            1: "редагування",  # n%10==1 && n%100!=11 → one
            2: "редагування",  # few — same form for this neuter -ння word
            4: "редагування",
            5: "редагувань",  # many
            11: "редагувань",  # 11 is special (many, not one)
            21: "редагування",  # 21 back to one
            22: "редагування",
            25: "редагувань",
        }
        for n, expected in cases.items():
            actual = page.evaluate(f"pluralFor({n}, 'edits')")
            assert actual == expected, f"n={n}: expected {expected!r}, got {actual!r}"

    def test_uk_plural_markers_shape(self, server, page):
        self._goto_preview(server, page)
        self._force_lang(page, "uk")
        cases = {
            1: "маркер",
            2: "маркери",
            4: "маркери",
            5: "маркерів",
            11: "маркерів",
            21: "маркер",
        }
        for n, expected in cases.items():
            actual = page.evaluate(f"pluralFor({n}, 'markers')")
            assert actual == expected, f"n={n}: expected {expected!r}, got {actual!r}"

    def test_en_plural_default(self, server, page):
        self._goto_preview(server, page)
        self._force_lang(page, "en")
        assert page.evaluate("pluralFor(1, 'edits')") == "edit"
        assert page.evaluate("pluralFor(2, 'edits')") == "edits"
        assert page.evaluate("pluralFor(1, 'markers')") == "marker"
        assert page.evaluate("pluralFor(5, 'markers')") == "markers"

    def test_confirm_revert_all_uses_correct_form(self, server, page):
        """Single edit → confirm mentions 'редагування' (not 'редагувань')."""
        goto_spa(page, server, "#/review/2001-01-01_Test-Talk")
        page.wait_for_function("document.querySelectorAll('.cell.uk').length > 0", timeout=10000)
        self._force_lang(page, "uk")
        cell = page.locator(".cell.uk .cell-text").first
        cell.click()
        cell.press("End")
        cell.type(" edited")
        cell.press("Tab")
        page.wait_for_timeout(200)
        page.click("#btn-revert-all")
        message = spa_confirm_accept(page)
        assert "редагування" in message
        assert "редагувань" not in message
        # The plural quantifier "всі" never agrees with a singular noun —
        # make sure we don't print "Скасувати всі 1 редагування?" again.
        assert "всі 1" not in message
        assert "всі" not in message


class TestEndFreeze:
    """Fullscreen end-freeze: the player pauses just before the video ends so
    the Vimeo 'more from this user' end screen never fires (js/end_freeze.js).
    The mock player reports a 3600s duration; 3599.8 is inside the 0.3s
    epsilon window before the end."""

    END_SEC = 3599.8

    def _goto_preview(self, server, page):
        goto_spa(page, server, "#/preview/2001-01-01_Test-Talk/Test-Video")
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        page.wait_for_timeout(1000)

    def _enter_fs(self, page):
        page.evaluate("document.getElementById('view-preview').classList.add('fs-mode')")
        page.wait_for_timeout(100)

    def test_freezes_on_last_frame_in_fullscreen(self, server, page):
        self._goto_preview(server, page)
        self._enter_fs(page)
        page.evaluate("window._vimeoPlayer.play()")
        page.evaluate(f"window._vimeoPlayer._setTime({self.END_SEC})")
        page.wait_for_timeout(300)
        assert page.evaluate("window._vimeoPlayer._paused") is True

    def test_no_freeze_outside_fullscreen(self, server, page):
        self._goto_preview(server, page)
        page.evaluate("window._vimeoPlayer.play()")
        page.evaluate(f"window._vimeoPlayer._setTime({self.END_SEC})")
        page.wait_for_timeout(300)
        assert page.evaluate("window._vimeoPlayer._paused") is False

    def test_frozen_latch_lets_viewer_play_the_tail(self, server, page):
        self._goto_preview(server, page)
        self._enter_fs(page)
        page.evaluate("window._vimeoPlayer.play()")
        page.evaluate(f"window._vimeoPlayer._setTime({self.END_SEC})")
        page.wait_for_timeout(300)
        assert page.evaluate("window._vimeoPlayer._paused") is True
        # A viewer who presses play at the freeze point must be able to watch
        # the tail — the frozen latch must not re-pause.
        page.evaluate("window._vimeoPlayer.play()")
        page.wait_for_timeout(300)
        assert page.evaluate("window._vimeoPlayer._paused") is False

    def test_freeze_clears_saved_resume_position(self, server, page):
        self._goto_preview(server, page)
        self._enter_fs(page)
        page.evaluate("window._vimeoPlayer.play()")
        page.evaluate(f"window._vimeoPlayer._setTime({self.END_SEC})")
        page.wait_for_timeout(300)
        pos = page.evaluate("localStorage.getItem('sy.preview_pos.2001-01-01_Test-Talk.Test-Video')")
        assert pos in (None, "0"), f"freeze must not persist the end position, got {pos}"


class TestClearAllCount:
    """Preview's Clear-all button must show (N) suffix, matching Revert-all."""

    def _goto_preview(self, server, page):
        goto_spa(page, server, "#/preview/2001-01-01_Test-Talk/Test-Video")
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        page.wait_for_timeout(500)

    def test_clear_all_btn_shows_count(self, server, page):
        self._goto_preview(server, page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        btn = page.locator("#btn-clear-all")
        assert btn.is_visible()
        assert "(1)" in (btn.text_content() or "")
        page.evaluate("window._vimeoPlayer._setTime(7)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        assert "(2)" in (btn.text_content() or "")


class TestEditItemLayout:
    """The × delete button on the preview edit list must be the last column
    (to the right of the edit field), not between tc and orig."""

    def _open_edit_mode(self, server, page):
        goto_spa(page, server, "#/preview/2001-01-01_Test-Talk/Test-Video")
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        page.click('.preview-mode-toggle [data-mode="edit"]')
        page.wait_for_timeout(50)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        page.wait_for_selector(".edit-item", timeout=3000)

    def test_delete_button_is_rightmost(self, server, page):
        self._open_edit_mode(server, page)
        rects = page.evaluate(
            "(() => { const it = document.querySelector('.edit-item'); "
            "const q = s => it.querySelector(s).getBoundingClientRect(); "
            "return {tc: q('.tc'), orig: q('.orig'), edited: q('.edited'), del: q('.del')}; })()"
        )
        # × must sit to the right of the edit field (grid col 3, after col 2).
        assert rects["del"]["left"] >= rects["edited"]["right"] - 1, rects
        # × must not sit between tc and orig (the old broken layout).
        assert rects["del"]["left"] > rects["orig"]["left"], rects

    def test_delete_still_removes(self, server, page):
        self._open_edit_mode(server, page)
        assert page.locator(".edit-item").count() == 1
        page.locator(".edit-item .del").click()
        page.wait_for_timeout(100)
        assert page.locator(".edit-item").count() == 0


class TestDestructiveButtonsInSync:
    """Clear-all (preview) and Revert-all (review) are the same kind of
    'blow away my local changes' button; make sure they stay aligned in
    layout, color, and visibility so the UI reads consistently."""

    def _goto_preview(self, server, page):
        goto_spa(page, server, "#/preview/2001-01-01_Test-Talk/Test-Video")
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        page.wait_for_timeout(500)

    def _goto_review_with_edit(self, server, page):
        goto_spa(page, server, "#/review/2001-01-01_Test-Talk")
        page.wait_for_function("document.querySelectorAll('.cell.uk').length > 0", timeout=10000)
        cell = page.locator(".cell.uk .cell-text").first
        cell.click()
        cell.press("End")
        cell.type(" edited")
        cell.press("Tab")
        page.wait_for_timeout(200)

    def test_both_buttons_have_danger_class(self, server, page):
        self._goto_preview(server, page)
        assert "danger" in (page.locator("#btn-clear-all").get_attribute("class") or "")
        self._goto_review_with_edit(server, page)
        assert "danger" in (page.locator("#btn-revert-all").get_attribute("class") or "")

    def test_both_buttons_use_danger_background(self, server, page):
        """Clear-all and Revert-all must share the same red danger-bg so
        the UI communicates 'destructive action' consistently."""
        self._goto_preview(server, page)
        # Make clear-all visible by adding a marker.
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        clear_bg = page.evaluate("getComputedStyle(document.getElementById('btn-clear-all')).backgroundColor")
        self._goto_review_with_edit(server, page)
        revert_bg = page.evaluate("getComputedStyle(document.getElementById('btn-revert-all')).backgroundColor")
        assert clear_bg == revert_bg

    def test_both_buttons_sit_last_in_header_actions(self, server, page):
        """Destructive action should be the rightmost button in both
        headers, so destructive and primary are never adjacent by accident."""
        self._goto_preview(server, page)
        last_preview = page.evaluate("document.querySelector('#view-preview .header-actions').lastElementChild.id")
        assert last_preview == "btn-clear-all"
        self._goto_review_with_edit(server, page)
        last_review = page.evaluate("document.querySelector('#view-review .header-actions').lastElementChild.id")
        assert last_review == "btn-revert-all"


class TestRevertAllConfirmation:
    """Revert all on the review page must ask for confirmation, mirroring
    the preview's Clear all button."""

    def _goto_review_with_edit(self, server, page):
        goto_spa(page, server, "#/review/2001-01-01_Test-Talk")
        page.wait_for_function("document.querySelectorAll('.cell.uk').length > 0", timeout=10000)
        cell = page.locator(".cell.uk .cell-text").first
        cell.click()
        cell.press("End")
        cell.type(" edited")
        cell.press("Tab")
        page.wait_for_timeout(200)
        return cell

    def test_revert_all_button_visible_after_edit(self, server, page):
        self._goto_review_with_edit(server, page)
        assert page.locator("#btn-revert-all").is_visible()

    def test_revert_all_prompts_confirmation(self, server, page):
        self._goto_review_with_edit(server, page)
        page.click("#btn-revert-all")
        # If the dialog never opens, the helper raises — fail with a clear
        # assertion message instead of a timeout.
        assert page.wait_for_selector(".sy-modal", timeout=2000) is not None, (
            "Expected a confirm dialog before reverting"
        )
        spa_confirm_accept(page)

    def test_revert_all_cancel_keeps_edits(self, server, page):
        self._goto_review_with_edit(server, page)
        page.click("#btn-revert-all")
        spa_confirm_dismiss(page)
        edits = page.evaluate("JSON.parse(localStorage.getItem('review_2001-01-01_Test-Talk') || '{}').edits || {}")
        assert len(edits) == 1, "Cancelling confirm must keep edits intact"
        assert page.locator("#btn-revert-all").is_visible()

    def test_revert_all_confirm_clears_edits(self, server, page):
        self._goto_review_with_edit(server, page)
        page.click("#btn-revert-all")
        spa_confirm_accept(page)
        edits = page.evaluate("JSON.parse(localStorage.getItem('review_2001-01-01_Test-Talk') || '{}').edits || {}")
        assert edits == {}
        assert page.locator("#btn-revert-all").is_visible() is False


class TestClipboardCopyDialog:
    """Regression: the clipboard-copy branch of createIssue / openEditor /
    createPreviewIssue / openPreviewEditor / addTalk MUST block on a confirm
    dialog before calling window.open — otherwise the new tab steals focus
    and the user never sees the "paste Ctrl+V" instruction. A prior PR
    downgraded these five alert() calls to showToast(), silently dropping
    the notification. These tests fail the moment window.open fires before
    the user clicks through the dialog.
    """

    # Stubs mirror the ones used throughout this module: capture the URL
    # window.open was called with, and pretend the clipboard write
    # succeeded. `__spa_auto_info_confirm = false` turns OFF the fixture's
    # fast-path so the real DOM dialog renders and the test can assert on
    # it.
    _STUBS = (
        "window.__spa_auto_info_confirm = false;"
        " window._openedUrl = null;"
        " window._openCount = 0;"
        " window.open = function(u) { window._openCount++; window._openedUrl = u; };"
        " window._clipText = '';"
        " navigator.clipboard.writeText = function(t) {"
        "   window._clipText = t; return Promise.resolve();"
        " };"
    )

    def _expect_dialog_then_opens(self, page, expected_url_substr):
        """Assert: (1) dialog appears, (2) window.open has NOT been called,
        (3) clicking the primary button fires window.open with the expected
        URL. Guarantees the dialog actually blocks the tab-open."""
        page.wait_for_selector(".sy-modal", timeout=2000)
        assert page.evaluate("window._openCount") == 0, "window.open must NOT be called until the dialog is accepted"
        body = page.locator(".sy-modal-body").text_content() or ""
        # Dialog body must tell user what to do next (paste / select-all).
        assert ("Ctrl+V" in body) or ("paste" in body.lower()), (
            f"Dialog body must contain next-step instructions, got: {body!r}"
        )
        page.locator(".sy-modal-btn.primary").first.click()
        page.wait_for_selector(".sy-modal", state="detached", timeout=2000)
        url = page.evaluate("window._openedUrl || ''")
        assert expected_url_substr in url, (
            f"window.open not called with expected URL after dialog accept.\n"
            f"expected substr: {expected_url_substr!r}\ngot: {url!r}"
        )

    def test_open_preview_editor_blocks_on_dialog_before_open(self, server, page):
        """openPreviewEditor with edits → clipboard copy → dialog → open."""
        _goto_preview_video(page, server)
        page.click('.preview-mode-toggle [data-mode="edit"]')
        page.wait_for_timeout(50)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        page.evaluate("""
          var el = document.activeElement;
          el.innerText = 'DIALOG_REGRESSION_EDIT';
          el.dispatchEvent(new Event('input', { bubbles: true }));
        """)
        page.wait_for_timeout(50)
        page.evaluate(self._STUBS)
        page.evaluate("SPA.openPreviewEditor()")
        self._expect_dialog_then_opens(page, "final/uk.srt")

    def test_open_preview_editor_no_edits_skips_dialog(self, server, page):
        """Zero-edit path must NOT show the dialog — it opens GitHub directly."""
        _goto_preview_video(page, server)
        page.click('.preview-mode-toggle [data-mode="edit"]')
        page.wait_for_timeout(50)
        page.evaluate(self._STUBS)
        page.evaluate("SPA.openPreviewEditor()")
        page.wait_for_timeout(200)
        assert page.locator(".sy-modal").count() == 0, "No dialog should appear when there are no edits"
        assert page.evaluate("window._openCount") == 1
        assert "final/uk.srt" in page.evaluate("window._openedUrl || ''")

    def test_open_editor_transcript_mode_blocks_on_dialog_before_open(self, server, page):
        """Review-page openEditor (transcript mode) with edits → dialog before open."""
        goto_spa(page, server, "#/review/2001-01-01_Test-Talk")
        page.wait_for_function("document.querySelectorAll('.cell.uk').length > 0", timeout=10000)
        page.evaluate("reviewState.edits[0] = 'REGRESSION_DIALOG'; saveReview()")
        page.evaluate(self._STUBS)
        page.evaluate("SPA.openEditor()")
        self._expect_dialog_then_opens(page, "transcript_uk.txt")

    def test_create_review_issue_long_body_blocks_on_dialog_before_open(self, server, page):
        """createReviewIssue with an oversize body must copy to clipboard
        AND show the dialog before opening GitHub (URL > 8000 chars)."""
        goto_spa(page, server, "#/review/2001-01-01_Test-Talk")
        page.wait_for_function("document.querySelectorAll('.cell.uk').length > 0", timeout=10000)
        # Inflate the body over the 8000-char threshold: one big edit is
        # enough since edits are URL-encoded into the body.
        page.evaluate("reviewState.edits[0] = 'X'.repeat(9000); saveReview();")
        page.evaluate(self._STUBS)
        page.evaluate("SPA.createReviewIssue()")
        self._expect_dialog_then_opens(page, "/issues/new")
        # And the clipboard got the body (not the URL) so the user can paste.
        clip = page.evaluate("window._clipText || ''")
        assert "XXXXX" in clip, "Clipboard should hold the issue body text"

    def test_create_preview_issue_long_body_blocks_on_dialog_before_open(self, server, page):
        """createPreviewIssue in edit mode with an oversize body must show
        the dialog before opening GitHub."""
        _goto_preview_video(page, server)
        page.click('.preview-mode-toggle [data-mode="edit"]')
        page.wait_for_timeout(50)
        # Inflate a single edit so the URL crosses 8000 chars.
        page.evaluate(
            "previewState.edits = previewState.edits || {};"
            " previewState.edits.uk = previewState.edits.uk || {};"
            " previewState.edits.uk[0] = 'X'.repeat(9000);"
        )
        page.evaluate(self._STUBS)
        page.evaluate("SPA.createPreviewIssue()")
        self._expect_dialog_then_opens(page, "/issues/new")
        clip = page.evaluate("window._clipText || ''")
        assert "XXXXX" in clip, "Clipboard should hold the issue body text"

    def test_fixture_auto_confirm_flag_is_default(self, server, page):
        """Sanity check: by default the fixture's fast-path flag is ON, so
        tests that don't care about the dialog don't see it. If this test
        fails, the fast-path stopped working and every other test in this
        module will silently leak modals into page teardown."""
        _goto_preview_video(page, server)
        val = page.evaluate("window.__spa_auto_info_confirm")
        assert val is True, (
            "Fixture must set window.__spa_auto_info_confirm = true so tests that "
            "don't explicitly clear it get the direct window.open path."
        )

    # --- Dismiss affordance: a corner close (X) + Escape/backdrop must NOT
    # open a GitHub tab. The primary "Open GitHub" button is the ONLY path
    # that opens. Regression for: Escape (and a missing cancel button) still
    # firing window.open because the .then() callback ignored the resolved
    # value.
    def _open_preview_editor_dialog(self, page, server):
        """Drive openPreviewEditor with one edit so the clipboard-copy
        confirm dialog renders, and wait for it."""
        _goto_preview_video(page, server)
        page.click('.preview-mode-toggle [data-mode="edit"]')
        page.wait_for_timeout(50)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        page.evaluate("""
          var el = document.activeElement;
          el.innerText = 'DIALOG_DISMISS_EDIT';
          el.dispatchEvent(new Event('input', { bubbles: true }));
        """)
        page.wait_for_timeout(50)
        page.evaluate(self._STUBS)
        page.evaluate("SPA.openPreviewEditor()")
        page.wait_for_selector(".sy-modal", timeout=2000)

    def test_info_dialog_has_corner_close_button(self, server, page):
        """The info dialog must offer a corner close (X) so the user can
        dismiss it without triggering the primary Open-GitHub action."""
        self._open_preview_editor_dialog(page, server)
        assert page.locator(".sy-modal-close").count() == 1, "Info dialog must render a corner close (X) button."

    def test_escape_dismisses_without_opening_tab(self, server, page):
        """Escape closes the dialog and must NOT open a GitHub tab."""
        self._open_preview_editor_dialog(page, server)
        page.keyboard.press("Escape")
        page.wait_for_selector(".sy-modal", state="detached", timeout=2000)
        assert page.evaluate("window._openCount") == 0, "Escape must dismiss the dialog WITHOUT opening a GitHub tab."

    def test_corner_close_dismisses_without_opening_tab(self, server, page):
        """Clicking the corner close (X) closes the dialog and must NOT open
        a GitHub tab."""
        self._open_preview_editor_dialog(page, server)
        page.locator(".sy-modal-close").click()
        page.wait_for_selector(".sy-modal", state="detached", timeout=2000)
        assert page.evaluate("window._openCount") == 0, (
            "Clicking the corner close (X) must dismiss the dialog WITHOUT opening a GitHub tab."
        )


class TestPreviewResizeHandleI18n:
    """The preview resize handles are built imperatively (makeDragHandle), so
    their title/aria-label must carry data-i18n* keys — otherwise a UI language
    toggle leaves the tooltip stuck in the previous language."""

    def test_resize_handle_tooltip_refreshes_on_language_toggle(self, server, page):
        page.add_init_script("localStorage.setItem('sy_lang', 'en');")
        page.set_viewport_size({"width": 1600, "height": 900})
        goto_spa(page, server, "#/preview/2001-01-01_Test-Talk/Test-Video")
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        page.wait_for_selector("#preview-player-resize", timeout=10000)
        before = page.evaluate("document.getElementById('preview-player-resize').title")
        assert before == "Drag to resize the player"
        page.click("#prefs-btn")
        page.click("#prefs-lang button[aria-pressed='false']")
        handle = "document.getElementById('preview-player-resize')"
        after_title = page.evaluate(f"{handle}.title")
        after_aria = page.evaluate(f"{handle}.getAttribute('aria-label')")
        assert after_title != before, "resize-handle tooltip must refresh on language toggle"
        expected = page.evaluate("t('preview.resize_player')")
        assert after_title == expected
        assert after_aria == expected


class TestSubtitleOverlaySize:
    """Subtitle overlay font sizing: width-bound formula, fs-mode baseline,
    and the bidirectional handle→fs-mode mirror."""

    def _goto_preview(self, server, page):
        page.set_viewport_size({"width": 1600, "height": 900})
        goto_spa(page, server, "#/preview/2001-01-01_Test-Talk/Test-Video")
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        # ensurePreviewResizers fires from a 400ms setTimeout AND from
        # hashchange/resize listeners. Until it has run the no-saved-subs
        # branch will wipe data-subs-tuned and the scale var, racing with
        # anything the test sets. Wait for the handle to appear — that's
        # the deterministic signal that ensurePreviewResizers finished.
        page.wait_for_selector("#preview-subs-resize", timeout=10000)

    def test_width_bound_uses_15_3_divisor(self, server, page):
        """The width-bound font is `(cqw - 48px) / 15.3`. On a wide enough
        container the realized font must hit that bound (within rounding)."""
        self._goto_preview(server, page)
        result = page.evaluate(
            """() => {
              const overlay = document.getElementById('subtitle-overlay');
              overlay.textContent = 'Перший субтитр';
              document.documentElement.style.setProperty('--preview-subs-h', '720px');
              const vp = document.getElementById('view-preview');
              vp.setAttribute('data-subs-tuned', '1');
              const cqw = overlay.parentElement.clientWidth;
              return {
                font: parseFloat(getComputedStyle(overlay).fontSize),
                cqw,
              };
            }"""
        )
        width_bound = (result["cqw"] - 48) / 15.3
        assert result["font"] >= width_bound - 1, (
            f"Font {result['font']}px should reach the /15.3 width-bound ≈{width_bound:.1f}px (cqw={result['cqw']}px)"
        )

    def test_min_handle_height_keeps_floor(self, server, page):
        """Floor should still be the 24px lower bound from the clamp."""
        self._goto_preview(server, page)
        font_px = page.evaluate(
            """() => {
              const overlay = document.getElementById('subtitle-overlay');
              document.documentElement.style.setProperty('--preview-subs-h', '60px');
              const vp = document.getElementById('view-preview');
              vp.setAttribute('data-subs-tuned', '1');
              return parseFloat(getComputedStyle(overlay).fontSize);
            }"""
        )
        assert font_px >= 24, f"Subtitle font fell below 24px floor: {font_px}px"

    def test_fs_mode_font_follows_subs_handle(self, server, page):
        """Fullscreen overlay must scale with the embedded resize handle:
        dragging the subs taller in preview should also enlarge fullscreen
        subtitles. The scale is set by JS (applySubsPx), not derived from
        --preview-subs-h via CSS calc — so the test must set both vars."""
        self._goto_preview(server, page)
        result = page.evaluate(
            """() => {
              const overlay = document.getElementById('subtitle-overlay');
              const vp = document.getElementById('view-preview');
              vp.classList.add('fs-mode');
              vp.setAttribute('data-subs-tuned', '1');
              const setHandle = (h) => {
                const scale = Math.max(0.5, Math.min(4, h / 120));
                document.documentElement.style.setProperty('--preview-subs-h', h + 'px');
                document.documentElement.style.setProperty('--preview-subs-scale', String(scale));
              };
              setHandle(120);
              const small = parseFloat(getComputedStyle(overlay).fontSize);
              setHandle(720);
              const big = parseFloat(getComputedStyle(overlay).fontSize);
              vp.classList.remove('fs-mode');
              return { small, big };
            }"""
        )
        assert result["big"] > result["small"], (
            f"Fullscreen font should grow with subs handle, got small={result['small']}px big={result['big']}px"
        )

    # fs-mode no-drag baseline = clamp(28px, 4vw, 80px). On a 1600px
    # viewport that's min(80, 64) = 64px; FLOOR_PX leaves ~12% rounding
    # slack. TINY_PX catches regressions to the embedded base 32px font.
    FS_MODE_BASELINE_PX = 64
    FS_MODE_BASELINE_FLOOR_PX = 56
    FS_MODE_TINY_PX = 30
    FS_MODE_FLOOR_PX = 20  # CSS hard floor: drag-down must stay readable.

    # Single source of truth for the test-side mirror of applySubsPx — used
    # by every "set the handle to h, read the resulting font" probe so a
    # constant change in the production formula doesn't silently leave the
    # tests asserting against stale numbers.
    #
    # It must also PERSIST the height (localStorage keySubs), exactly as a real
    # drag's onCommit does. Without that, the tuned state is unsaved: the resize
    # that fires when this probe toggles native fullscreen re-runs
    # ensurePreviewResizers, which — seeing no saved subs — wipes data-subs-tuned
    # and --preview-subs-scale, dropping the fs-mode font back to the un-tuned
    # baseline. That race is the long-standing `big == baseline` flake. Saving
    # makes ensurePreviewResizers RE-APPLY the height (the real-usage path) so the
    # scale survives the toggle deterministically. Key mirrors production:
    # 'sy.preview_subs_h.' + previewTalkKey() where previewTalkKey = talk '.' video
    # parsed from the #/preview/<talk>/<video> hash.
    _SET_HANDLE_JS = """
      (h) => {
        const scale = Math.max(0.5, Math.min(4, h / 120));
        document.documentElement.style.setProperty('--preview-subs-h', h + 'px');
        document.documentElement.style.setProperty('--preview-subs-scale', String(scale));
        document.getElementById('view-preview').setAttribute('data-subs-tuned', '1');
        const m = (location.hash || '').match(/^#\\/preview\\/([^/]+)\\/([^/?#]+)/);
        if (m) localStorage.setItem('sy.preview_subs_h.' + m[1] + '.' + m[2], String(h));
      }
    """

    def _wait_for_handle(self, page):
        """The resize handle is installed asynchronously via a setTimeout
        chain after hashchange — a fixed sleep is unreliable across machines."""
        page.wait_for_selector("#preview-subs-resize", timeout=10000)

    def _wait_fs_engaged(self, page):
        """Wait until requestFullscreen has actually engaged. Best-effort:
        some headless environments never grant native fullscreen, in which
        case there is no pending request to race and the synchronous .fs-mode
        class (added by toggleFullscreen itself) is already in effect, so a
        timeout here is benign."""
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        with contextlib.suppress(PlaywrightTimeoutError):
            page.wait_for_function(
                "document.fullscreenElement === document.getElementById('view-preview')",
                timeout=2000,
            )

    def _enter_fs(self, page):
        """Enter REAL native fullscreen and wait until requestFullscreen has
        actually engaged. requestFullscreen is async: without this wait a
        following exit toggle can fire while the request is still pending,
        leaving document.fullscreenElement set after .fs-mode is removed — the
        next enter is then misread as an exit and the font is measured in the
        embedded (non-fs) state. Waiting for the native state to settle keeps
        the enter/exit probe sequence deterministic while still exercising the
        real Fullscreen API."""
        page.evaluate("SPA.toggleFullscreen()")
        self._wait_fs_engaged(page)

    def _exit_fs(self, page):
        """Exit native fullscreen and wait until it has fully released, so the
        next _enter_fs starts from a clean state. Best-effort like _enter_fs:
        if native FS never engaged there is nothing to release."""
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        page.evaluate("SPA.toggleFullscreen()")
        with contextlib.suppress(PlaywrightTimeoutError):
            page.wait_for_function("document.fullscreenElement === null", timeout=2000)

    def _read_fs_font_px_via_toggle(self, page, drag_to_h=None):
        """Enter real fullscreen (optionally after dragging the embedded handle,
        which sets --preview-subs-scale via JS) and read the resulting subtitle
        overlay font size.

        The tune and the fullscreen toggle run in ONE evaluate. Two separate
        evaluates leave an event-loop gap between them, and the preview boot's
        pending `setTimeout(maybeInstallResize, 50)` chain could fire in that
        gap — still in EMBEDDED mode — re-applying the just-persisted height
        through computeSubsMaxPx's narrow embedded clamp (~115px on this
        layout), silently shrinking the scale the probe just set; entering
        fullscreen then locked the shrunken value in (maybeInstallResize is
        gated on `!fs-mode`), the long-standing `big=59.6 < baseline=64`
        flake. With no gap the stray timer can only fire after .fs-mode is on,
        where it is gated out."""
        if drag_to_h is not None:
            page.evaluate(
                f"(h) => {{ const setHandle = {self._SET_HANDLE_JS}; setHandle(h); SPA.toggleFullscreen(); }}",
                drag_to_h,
            )
            self._wait_fs_engaged(page)
        else:
            self._enter_fs(page)
        return page.evaluate("parseFloat(getComputedStyle(document.getElementById('subtitle-overlay')).fontSize)")

    def test_fs_mode_default_matches_baseline(self, server, page):
        """Entering fullscreen WITHOUT having dragged must give the
        un-tuned baseline `clamp(28px, 4vw, 80px)` — not tiny
        (cascade-fallback bug) and not oversize."""
        self._goto_preview(server, page)
        font_px = self._read_fs_font_px_via_toggle(page, drag_to_h=None)
        assert font_px >= self.FS_MODE_BASELINE_FLOOR_PX, (
            f"fs-mode default font shrank to {font_px}px — expected ≈ "
            f"{self.FS_MODE_BASELINE_PX}px (4vw on 1600 viewport)"
        )
        # Ceiling for the baseline rule clamp(28, 4vw, 80) on a 1600px
        # viewport is 80px; allow 10px slack for rounding/scrollbars.
        assert font_px <= 90, f"fs-mode default {font_px}px exceeds the 80px ceiling of clamp(28, 4vw, 80)"

    def test_fs_mode_smaller_block_shrinks_proportionally(self, server, page):
        """A smaller embedded subtitle block (handle dragged UP — the handle
        sits below the overlay, so handle-up = block shrinks) must mirror
        into a smaller fullscreen font. This is the new bidirectional
        behavior."""
        self._goto_preview(server, page)
        baseline = self._read_fs_font_px_via_toggle(page, drag_to_h=None)
        self._exit_fs(page)
        small = self._read_fs_font_px_via_toggle(page, drag_to_h=60)
        assert small < baseline, f"Smaller block did NOT shrink fs-mode font: baseline={baseline}px, small={small}px"
        assert small >= self.FS_MODE_FLOOR_PX, (
            f"fs-mode shrank past the readable floor: {small}px < {self.FS_MODE_FLOOR_PX}px"
        )

    def test_fs_mode_taller_block_enlarges_proportionally(self, server, page):
        """A taller embedded subtitle block (handle dragged DOWN — handle
        sits below the overlay, dy>0 grows the block) must mirror into a
        bigger fullscreen font."""
        self._goto_preview(server, page)
        baseline = self._read_fs_font_px_via_toggle(page, drag_to_h=None)
        self._exit_fs(page)
        big = self._read_fs_font_px_via_toggle(page, drag_to_h=600)
        assert big > baseline, f"Taller block did NOT enlarge fs-mode font: baseline={baseline}px, big={big}px"

    def test_fs_mode_drag_to_default_keeps_baseline(self, server, page):
        """Setting handle exactly at the embedded default (120px → scale 1)
        must give exactly the un-tuned baseline."""
        self._goto_preview(server, page)
        font_px = self._read_fs_font_px_via_toggle(page, drag_to_h=120)
        assert font_px >= self.FS_MODE_BASELINE_FLOOR_PX, (
            f"fs-mode at scale 1.0 disagreed with baseline: {font_px}px < {self.FS_MODE_BASELINE_FLOOR_PX}px"
        )

    def test_toggleFullscreen_applies_class_synchronously(self, server, page):
        """The bug: when toggleFullscreen relied on the fullscreenchange
        event to add the .fs-mode class, browsers that delay or never fire
        the event (Safari → webkitfullscreenchange; headless chromium can
        skip it) showed the embedded base 32px font instead of fs-mode.
        Reading getComputedStyle synchronously, before any RAF, must already
        see the fs-mode font."""
        self._goto_preview(server, page)
        result = page.evaluate(
            """() => {
              const overlay = document.getElementById('subtitle-overlay');
              const vp = document.getElementById('view-preview');
              SPA.toggleFullscreen();
              // No await, no rAF: we MUST already be in fs-mode now.
              return {
                hasFsClass: vp.classList.contains('fs-mode'),
                font: parseFloat(getComputedStyle(overlay).fontSize),
              };
            }"""
        )
        assert result["hasFsClass"], "SPA.toggleFullscreen() did not add .fs-mode synchronously"
        assert result["font"] > self.FS_MODE_TINY_PX, (
            f"Synchronous fs-mode font is {result['font']}px — falling back "
            f"to the embedded base 32px means .fs-mode CSS isn't applying yet"
        )

    def test_toggleFullscreen_survives_missing_fullscreenchange(self, server, page):
        """Simulate a browser that dispatches no fullscreenchange event
        (Safari without the webkit listener wired, sandboxed iframe, etc).
        The class must still come from toggleFullscreen itself."""
        self._goto_preview(server, page)
        font = page.evaluate(
            """() => {
              const overlay = document.getElementById('subtitle-overlay');
              const vp = document.getElementById('view-preview');
              // Block the standard event from firing — a stand-in for
              // browsers that only emit a vendor-prefixed variant.
              document.addEventListener('fullscreenchange',
                e => e.stopImmediatePropagation(), true);
              SPA.toggleFullscreen();
              return parseFloat(getComputedStyle(overlay).fontSize);
            }"""
        )
        assert font > self.FS_MODE_TINY_PX, (
            f"Without a fullscreenchange event, fs-mode font fell back to "
            f"{font}px — toggleFullscreen must add the class itself"
        )

    def test_drag_handle_mirrors_into_fs_mode(self, server, page):
        """Once in fs-mode, the embedded resize state must mirror
        bidirectionally — taller block → bigger fs font; shorter block →
        smaller fs font (down to the readable floor)."""
        self._goto_preview(server, page)
        result = page.evaluate(
            f"""() => {{
              const overlay = document.getElementById('subtitle-overlay');
              SPA.toggleFullscreen();
              const setHandle = {self._SET_HANDLE_JS};
              const fontAt = (h) => {{
                setHandle(h);
                return parseFloat(getComputedStyle(overlay).fontSize);
              }};
              return {{
                baseline: fontAt(120),
                enlarged: fontAt(600),
                shrunk:   fontAt(60),
              }};
            }}"""
        )
        assert result["enlarged"] > result["baseline"], (
            f"Taller block did not grow fs-mode font: baseline={result['baseline']}px enlarged={result['enlarged']}px"
        )
        assert result["shrunk"] < result["baseline"], (
            f"Shorter block did not shrink fs-mode font: baseline={result['baseline']}px shrunk={result['shrunk']}px"
        )

    # === Tests that exercise the actual JS code path (applySubsPx, reset,
    # persistence, hard caps) so a refactor of those code paths can't slip
    # past with a green suite. ===

    def test_handle_arrow_keys_set_scale_var_via_real_apply(self, server, page):
        """ArrowDown on the focused resize handle calls onMove.apply, which
        IS the production applySubsPx. This exercises the real JS path
        instead of the test re-implementing the formula."""
        self._goto_preview(server, page)
        self._wait_for_handle(page)
        page.locator("#preview-subs-resize").focus()
        for _ in range(5):
            page.keyboard.press("ArrowDown")
        result = page.evaluate(
            """() => ({
              scale: getComputedStyle(document.documentElement)
                .getPropertyValue('--preview-subs-scale').trim(),
              tuned: document.getElementById('view-preview')
                .getAttribute('data-subs-tuned'),
            })"""
        )
        assert result["tuned"] == "1", "applySubsPx didn't set data-subs-tuned"
        assert result["scale"] != "", "applySubsPx didn't set --preview-subs-scale"
        # Must be a valid finite number string, never 'NaN'.
        scale_val = float(result["scale"])
        assert 0.5 <= scale_val <= 4, f"scale {scale_val} outside [0.5, 4] clamp"

    def test_handle_double_click_resets_scale_and_tuned(self, server, page):
        """Double-clicking the handle triggers onReset, which must wipe
        --preview-subs-scale and data-subs-tuned. A future refactor that
        forgets one of those would silently leave fs scaled after reset."""
        self._goto_preview(server, page)
        self._wait_for_handle(page)
        handle = page.locator("#preview-subs-resize")
        handle.focus()
        for _ in range(5):
            page.keyboard.press("ArrowDown")
        before = page.evaluate(
            """() => ({
              tuned: document.getElementById('view-preview').getAttribute('data-subs-tuned'),
              scale: getComputedStyle(document.documentElement)
                .getPropertyValue('--preview-subs-scale').trim(),
            })"""
        )
        assert before["tuned"] == "1" and before["scale"] != "", (
            f"Test setup failed — drag didn't tune the overlay: {before}"
        )
        handle.dblclick()
        # --preview-subs-h falls back to its :root default (120px) after
        # removeProperty, that's by design — only data-subs-tuned and the
        # scale var are user-set state we need to wipe.
        after = page.evaluate(
            """() => ({
              tuned: document.getElementById('view-preview').getAttribute('data-subs-tuned'),
              scale: getComputedStyle(document.documentElement)
                .getPropertyValue('--preview-subs-scale').trim(),
              hInline: document.documentElement.style.getPropertyValue('--preview-subs-h'),
            })"""
        )
        assert after["tuned"] is None, f"Reset didn't clear data-subs-tuned (got {after['tuned']!r})"
        assert after["scale"] == "", f"Reset didn't clear --preview-subs-scale (got {after['scale']!r})"
        assert after["hInline"] == "", f"Reset didn't clear inline --preview-subs-h (got {after['hInline']!r})"

    def test_localstorage_subs_height_round_trips_on_load(self, server, page):
        """A persisted subs-h value must be re-applied on the next page
        load by applySubsPx (which sets the scale var). Persistence
        silently breaking is the most common subtle bug for handle features."""
        self._goto_preview(server, page)
        self._wait_for_handle(page)
        page.locator("#preview-subs-resize").focus()
        for _ in range(8):
            page.keyboard.press("ArrowDown")
        # Reload the same talk and check persistence ran applySubsPx.
        self._goto_preview(server, page)
        self._wait_for_handle(page)
        result = page.evaluate(
            """() => ({
              tuned: document.getElementById('view-preview').getAttribute('data-subs-tuned'),
              scale: getComputedStyle(document.documentElement)
                .getPropertyValue('--preview-subs-scale').trim(),
              h: getComputedStyle(document.documentElement)
                .getPropertyValue('--preview-subs-h').trim(),
            })"""
        )
        assert result["tuned"] == "1", f"Reload didn't re-tune the overlay from localStorage: {result}"
        assert result["h"] != "", f"Reload didn't re-apply --preview-subs-h: {result}"
        assert result["scale"] != "", f"Reload didn't re-apply --preview-subs-scale via applySubsPx: {result}"
        scale_val = float(result["scale"])
        assert 0.5 <= scale_val <= 4, f"scale {scale_val} outside [0.5, 4]"

    def test_fs_mode_22vh_cap_holds_on_short_viewport(self, server, page):
        """The 22vh hard cap must pin the fs-mode font on a short viewport
        even with the handle dragged to its largest position. Without the
        cap, two-line subtitles get pushed off-screen."""
        # Use a deliberately short viewport so 22vh < 4vw * scale_max.
        page.set_viewport_size({"width": 1600, "height": 400})
        goto_spa(page, server, "#/preview/2001-01-01_Test-Talk/Test-Video")
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        page.wait_for_selector("#preview-subs-resize", timeout=10000)
        font_px = self._read_fs_font_px_via_toggle(page, drag_to_h=720)
        # 22vh on 400px viewport = 88px. Allow 1px rounding slack.
        assert font_px <= 89, f"22vh cap not enforced: font {font_px}px > 88px on a 400px viewport"


class TestRepoAutoDetect:
    """deriveRepo() makes the SPA org-agnostic: the repo owner/name comes from
    the GitHub Pages host in production, with explicit overrides (?repo= /
    window.__SY_REPO) off Pages and a loud error when unresolvable.
    """

    def test_derive_repo_from_github_pages_host(self, server, page):
        goto_spa(page, server)
        result = page.evaluate(
            """() => ({
                project: deriveRepo('sy-tools.github.io', '/sy-subtitles/', ''),
                nested: deriveRepo('sy-tools.github.io', '/sy-subtitles/index.html', ''),
                old_owner: deriveRepo('slavasubotskiy.github.io', '/sy-subtitles/', ''),
                user_page: deriveRepo('acme.github.io', '/', ''),
            })"""
        )
        assert result["project"] == "sy-tools/sy-subtitles"
        assert result["nested"] == "sy-tools/sy-subtitles"
        assert result["old_owner"] == "slavasubotskiy/sy-subtitles"
        # User/org root page (no path segment): repo is <owner>.github.io.
        assert result["user_page"] == "acme/acme.github.io"

    def test_derive_repo_explicit_overrides_off_pages(self, server, page):
        goto_spa(page, server)
        result = page.evaluate(
            """() => ({
                query: deriveRepo('localhost', '/', '?repo=acme/widgets'),
                injected: deriveRepo('localhost', '/', ''),
            })"""
        )
        # ?repo= wins; otherwise fall back to the test-injected window.__SY_REPO.
        assert result["query"] == "acme/widgets"
        assert result["injected"] == "sy-tools/sy-subtitles"

    def test_derive_repo_throws_when_unresolvable(self, server, page):
        goto_spa(page, server)
        threw = page.evaluate(
            """() => {
                var saved = window.__SY_REPO;
                try { delete window.__SY_REPO; } catch (e) { window.__SY_REPO = undefined; }
                var threw = false;
                try { deriveRepo('example.com', '/', ''); }
                catch (e) { threw = true; }
                window.__SY_REPO = saved;
                return threw;
            }"""
        )
        assert threw, "deriveRepo must throw (loud error) when the repo cannot be resolved"


class TestLocalEditsSurviveReload:
    """Regression: local review/preview edits must persist across a tab reload
    (close-reopen). localStorage is per-origin and the SPA keys edits by talk;
    a reload must restore them.
    """

    def test_review_edits_survive_reload(self, server, page):
        goto_spa(page, server)
        page.evaluate("localStorage.setItem('sy_expert_mode','1'); expertMode=true; applyExpertMode();")
        page.evaluate("location.hash = '#/review/2001-01-01_Test-Talk'")
        page.wait_for_function("document.querySelectorAll('.cell.uk').length > 0", timeout=10000)
        page.evaluate("reviewState.edits[0] = 'PERSIST_ME'; reviewState.marks[1] = 'note'; saveReview()")
        raw = page.evaluate("localStorage.getItem('review_2001-01-01_Test-Talk')")
        assert raw and "PERSIST_ME" in raw, f"edit not written to localStorage: {raw!r}"
        page.reload()
        page.wait_for_function("document.querySelectorAll('.cell.uk').length > 0", timeout=10000)
        state = page.evaluate("({edits: reviewState.edits, marks: reviewState.marks})")
        assert state["edits"].get("0") == "PERSIST_ME", f"review edit lost after reload: {state}"
        assert state["marks"].get("1") == "note", f"review mark lost after reload: {state}"

    def test_preview_edits_markers_and_mode_survive_reload(self, server, page):
        """All preview-view local changes survive a reload: text edits, markers
        (with their comment), and the marker/edit mode."""
        goto_spa(page, server, "#/preview/2001-01-01_Test-Talk/Test-Video")
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        page.evaluate(
            "previewState.mode = 'edit';"
            "previewState.edits.uk = {0: 'PREVIEW_EDIT'};"
            "previewState.markers.push({time: 12, tc: '00:00:12', text: 'blk', comment: 'note'});"
            "savePreviewState()"
        )
        # Text edits go to the canonical per-block store; the preview key keeps
        # only mode + markers.
        canon = page.evaluate(f"localStorage.getItem('{CANON_UK_KEY}')")
        assert canon and "PREVIEW_EDIT" in canon, f"preview edit not written to canonical store: {canon!r}"
        raw = page.evaluate("localStorage.getItem('preview_2001-01-01_Test-Talk_Test-Video')")
        assert raw and "00:00:12" in raw and '"edit"' in raw, f"preview markers/mode not written: {raw!r}"
        page.reload()
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        state = page.evaluate(
            "({edits: (previewState.edits && previewState.edits.uk) || {},"
            " markers: previewState.markers, mode: previewState.mode})"
        )
        assert state["edits"].get("0") == "PREVIEW_EDIT", f"preview edit lost after reload: {state}"
        assert len(state["markers"]) == 1 and state["markers"][0]["comment"] == "note", (
            f"preview marker lost after reload: {state}"
        )
        assert state["mode"] == "edit", f"preview mode lost after reload: {state}"


class TestSrtReviewEditsPersist:
    """Regression: edits made in SRT (subtitles) review mode must persist
    across a reload AND across switching between transcript and SRT modes.

    Transcript-mode edits already persisted; SRT-mode edits were wiped because
    switchReviewMode / switchSrtLang reset reviewState.edits to {} after load,
    and SRT shared the transcript storage key.
    """

    def _goto_review(self, server, page):
        goto_spa(page, server)
        page.evaluate("localStorage.setItem('sy_expert_mode','1'); expertMode=true; applyExpertMode();")
        page.evaluate("location.hash = '#/review/2001-01-01_Test-Talk'")
        page.wait_for_function("document.querySelectorAll('.cell.uk').length > 0", timeout=10000)

    def _enter_srt(self, page):
        page.evaluate("SPA.switchReviewMode('srt', 'Test-Video')")
        page.wait_for_function(
            "typeof reviewState !== 'undefined' && reviewState.mode === 'srt'"
            " && document.querySelectorAll('.cell.uk').length > 0",
            timeout=10000,
        )

    def test_srt_edits_survive_reload(self, server, page):
        self._goto_review(server, page)
        self._enter_srt(page)
        page.evaluate("reviewState.edits[0] = 'SRT_PERSIST'; reviewState.marks[1] = 'm'; saveReview()")
        page.reload()
        page.wait_for_function(
            "typeof reviewState !== 'undefined' && reviewState.mode === 'srt'"
            " && document.querySelectorAll('.cell.uk').length > 0",
            timeout=10000,
        )
        state = page.evaluate("({edits: reviewState.edits, marks: reviewState.marks})")
        assert state["edits"].get("0") == "SRT_PERSIST", f"SRT edit lost after reload: {state}"
        assert state["marks"].get("1") == "m", f"SRT mark lost after reload: {state}"

    def test_srt_edits_and_marks_survive_mode_switch(self, server, page):
        """A full transcript→SRT→transcript→SRT round-trip keeps each mode's
        own edits AND marks intact."""
        self._goto_review(server, page)
        page.evaluate("reviewState.edits[0] = 'TRANSCRIPT_EDIT'; reviewState.marks[2] = 'T_MARK'; saveReview()")
        self._enter_srt(page)
        page.evaluate("reviewState.edits[0] = 'SRT_EDIT'; reviewState.marks[1] = 'SRT_MARK'; saveReview()")
        # SRT → transcript: transcript edits/marks must come back
        page.evaluate("SPA.switchReviewMode('transcript')")
        page.wait_for_function(
            "reviewState.mode === 'transcript' && document.querySelectorAll('.cell.uk').length > 0",
            timeout=10000,
        )
        tr = page.evaluate("({edits: reviewState.edits, marks: reviewState.marks})")
        assert tr["edits"].get("0") == "TRANSCRIPT_EDIT", f"transcript edit lost on switch: {tr}"
        assert tr["marks"].get("2") == "T_MARK", f"transcript mark lost on switch: {tr}"
        # transcript → SRT: SRT edits/marks must come back
        self._enter_srt(page)
        sr = page.evaluate("({edits: reviewState.edits, marks: reviewState.marks})")
        assert sr["edits"].get("0") == "SRT_EDIT", f"SRT edit lost after round-trip: {sr}"
        assert sr["marks"].get("1") == "SRT_MARK", f"SRT mark lost after round-trip: {sr}"

    def test_srt_edits_stored_under_separate_video_lang_key(self, server, page):
        """SRT edits live under their own canonical video+language block store
        (srt_edits_<talk>_<video>_<lang>), not the transcript key — which is
        what keeps them isolated across language switches and shared with the
        preview view of the same video+lang."""
        self._goto_review(server, page)
        page.evaluate("reviewState.edits[0] = 'TRANSCRIPT_EDIT'; saveReview()")
        self._enter_srt(page)
        page.evaluate("reviewState.edits[0] = 'SRT_EDIT'; saveReview()")
        keys = page.evaluate(
            """() => {
                var transcript = localStorage.getItem('review_2001-01-01_Test-Talk') || '';
                var srtKey = Object.keys(localStorage).find(
                    k => k.indexOf('srt_edits_2001-01-01_Test-Talk_Test-Video') === 0);
                return { transcript, srtKey, srtVal: srtKey ? localStorage.getItem(srtKey) : null };
            }"""
        )
        assert "TRANSCRIPT_EDIT" in keys["transcript"], f"transcript key missing its edit: {keys}"
        assert "SRT_EDIT" not in keys["transcript"], f"SRT edit leaked into transcript key: {keys}"
        assert keys["srtKey"] and "SRT_EDIT" in (keys["srtVal"] or ""), (
            f"SRT edit not stored under the canonical video+lang block key: {keys}"
        )

    def test_transcript_and_srt_edits_are_independent(self, server, page):
        self._goto_review(server, page)
        page.evaluate("reviewState.edits[0] = 'TRANSCRIPT_EDIT'; saveReview()")
        self._enter_srt(page)
        page.evaluate("reviewState.edits[0] = 'SRT_EDIT'; saveReview()")
        page.evaluate("SPA.switchReviewMode('transcript')")
        page.wait_for_function(
            "reviewState.mode === 'transcript' && document.querySelectorAll('.cell.uk').length > 0",
            timeout=10000,
        )
        assert page.evaluate("reviewState.edits['0']") == "TRANSCRIPT_EDIT", "transcript edit clobbered by SRT edit"


class TestExpertPipelineButton:
    """The expert-mode pipeline button copies the talk id to the clipboard.

    The copy was reworked from an inline onclick that concatenated the raw
    talk id into an HTML attribute (an XSS sink — CodeQL js/xss #18) to a
    dataset-free addEventListener that reads the id from the render closure.
    This guards that the copy behaviour survived the rework.
    """

    def test_expert_button_copies_talk_id(self, server, page):
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        page.evaluate(
            "window._clipText = '';"
            "navigator.clipboard.writeText = function(t){ window._clipText = t; return Promise.resolve(); };"
        )
        page.evaluate("localStorage.setItem('sy_expert_mode','1'); expertMode=true; applyExpertMode();")
        # Drop the href so the anchor's default new-tab navigation doesn't open
        # a popup during the test; the copy listener fires regardless.
        page.evaluate("document.querySelector('.talk-item .expert-btn').removeAttribute('href')")
        page.click(".talk-item .expert-btn")
        clip = page.evaluate("window._clipText || ''")
        assert clip == "2001-01-01_Test-Talk", f"expert button copied wrong id: {clip!r}"

    def test_talk_id_never_appears_inside_an_inline_onclick(self, server, page):
        """Defense-in-depth: no rendered card carries an inline onclick at all,
        so a talk id (a directory name a malicious PR could craft with quotes)
        can never break out of an attribute into script."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        page.evaluate("localStorage.setItem('sy_expert_mode','1'); expertMode=true; applyExpertMode();")
        onclick_count = page.evaluate("document.querySelectorAll('.talk-item [onclick]').length")
        assert onclick_count == 0, f"a card still uses an inline onclick handler: {onclick_count}"


class TestIndexCardXssDefenses:
    """A hostile amruta_url from meta.yaml (the PR / scraping-bookmarklet vector)
    must not break out of the card's href="". esc()/safeHref() are the only
    defense — there is no CSP — so this renders a card from a real breakout
    payload and asserts the DOM stays clean. Complements the source-regex guards
    in test_spa_xss.js with a behavioural, refactor-resilient check."""

    def test_hostile_amruta_url_cannot_inject_a_tag(self, server, page):
        # Override the default meta.yaml mock with a tag-injection payload.
        page.route(
            "**/raw.githubusercontent.com/**/meta.yaml",
            lambda route: route.fulfill(status=200, content_type="text/plain", body=XSS_AMRUTA_TAG_META),
        )
        page.add_init_script("window.__XSS_FIRED = false;")
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        page.wait_for_timeout(200)
        assert page.evaluate("window.__XSS_FIRED === true") is False, (
            "amruta_url payload broke out of href= and fired onerror"
        )
        assert page.evaluate("document.querySelectorAll('.talk-item img').length") == 0, (
            "an <img> element was injected from the amruta_url payload"
        )

    def test_hostile_amruta_url_cannot_inject_an_attribute(self, server, page):
        # Quote-only breakout: " data-xss="pwned attempts to add a NEW attribute
        # to the anchor. Only the esc() " -> &quot; fix blocks this (< > escaping
        # does not), so this is the test with teeth for the attribute-sanitization
        # alerts (#11-#17).
        page.route(
            "**/raw.githubusercontent.com/**/meta.yaml",
            lambda route: route.fulfill(status=200, content_type="text/plain", body=XSS_AMRUTA_ATTR_META),
        )
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        injected = page.evaluate("document.querySelectorAll('.talk-item [data-xss]').length")
        assert injected == 0, "amruta_url broke out of href= and injected a data-xss attribute"

    def test_javascript_scheme_amruta_url_is_dropped(self, server, page):
        js_meta = SAMPLE_META + "amruta_url: 'javascript:window.__XSS_FIRED=true'\n"
        page.route(
            "**/raw.githubusercontent.com/**/meta.yaml",
            lambda route: route.fulfill(status=200, content_type="text/plain", body=js_meta),
        )
        page.add_init_script("window.__XSS_FIRED = false;")
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        bad = page.evaluate(
            "Array.from(document.querySelectorAll('.talk-item a')).filter("
            "a => (a.getAttribute('href') || '').toLowerCase().startsWith('javascript:')).length"
        )
        assert bad == 0, "a javascript: amruta_url survived into an anchor href"


GATE_TEST_PHRASE = "test-passphrase"
GATE_TEST_HASH = "289fa9ee16cb75d517736c68cd7d9a646fde31efead2e17b59c3219bd1548f5f"


def _enable_gate(pg):
    """Inject the expected hash so the gate is active (set BEFORE goto)."""
    pg.add_init_script(f"window.__SY_GATE_HASH = '{GATE_TEST_HASH}';")


class TestPassphraseGate:
    def test_clicking_preview_link_prompts_on_index(self, server, page):
        _enable_gate(page)
        goto_spa(page, server)
        page.wait_for_selector("a.preview-link", timeout=10000)
        page.click("a.preview-link")
        page.wait_for_selector("#sy-gate-input", timeout=2000)
        # Still on the index; preview NOT rendered.
        assert "active" in page.locator("#view-index").get_attribute("class")
        assert "active" not in page.locator("#view-preview").get_attribute("class")

    def test_wrong_passphrase_shows_error_no_nav(self, server, page):
        _enable_gate(page)
        goto_spa(page, server)
        page.wait_for_selector("a.preview-link", timeout=10000)
        page.click("a.preview-link")
        page.fill("#sy-gate-input", "wrong-phrase")
        page.click(".sy-modal-btn.primary")
        page.wait_for_selector(".sy-modal-error", state="visible", timeout=2000)
        assert "active" not in page.locator("#view-preview").get_attribute("class")
        assert page.locator("#sy-gate-input").count() == 1  # modal still open

    def test_correct_passphrase_navigates_to_preview(self, server, page):
        _enable_gate(page)
        goto_spa(page, server)
        page.wait_for_selector("a.preview-link", timeout=10000)
        page.click("a.preview-link")
        page.fill("#sy-gate-input", GATE_TEST_PHRASE)
        page.press("#sy-gate-input", "Enter")
        # 6000ms: PBKDF2(200k) verify + preview render can be slow on CI.
        page.wait_for_selector("#view-preview.active", timeout=6000)
        # close() removes the backdrop on a 120ms animation timer; wait it out
        # before asserting (same pattern as test_cancel_stays_on_index).
        page.wait_for_selector(".sy-modal", state="detached", timeout=2000)
        assert page.locator(".sy-modal").count() == 0

    def test_cancel_stays_on_index(self, server, page):
        _enable_gate(page)
        goto_spa(page, server)
        page.wait_for_selector("a.preview-link", timeout=10000)
        page.click("a.preview-link")
        page.wait_for_selector("#sy-gate-input", timeout=2000)
        page.click(".sy-modal-btn:not(.primary)")
        page.wait_for_selector(".sy-modal", state="detached", timeout=2000)
        assert "active" in page.locator("#view-index").get_attribute("class")

    def test_deep_link_to_review_while_locked_redirects_and_prompts(self, server, page):
        _enable_gate(page)
        goto_spa(page, server, "#/review/2001-01-01_Test-Talk")
        page.wait_for_selector("#sy-gate-input", timeout=4000)
        # Redirected to the index; review NOT rendered.
        assert "active" in page.locator("#view-index").get_attribute("class")
        assert "active" not in page.locator("#view-review").get_attribute("class")
        # Correct phrase -> proceeds to the originally-requested review.
        page.fill("#sy-gate-input", GATE_TEST_PHRASE)
        page.press("#sy-gate-input", "Enter")
        page.wait_for_selector("#view-review.active", timeout=6000)

    def test_already_unlocked_browser_skips_prompt(self, server, page):
        _enable_gate(page)
        page.add_init_script(f"localStorage.setItem('sy_gate', '{GATE_TEST_HASH}');")
        goto_spa(page, server, "#/preview/2001-01-01_Test-Talk/Test-Video")
        page.wait_for_selector("#view-preview.active", timeout=6000)
        assert page.locator("#sy-gate-input").count() == 0

    def test_gate_disabled_opens_without_prompt(self, server, page):
        # No _enable_gate(): APP_GATE_HASH is empty -> fail-open.
        goto_spa(page, server, "#/preview/2001-01-01_Test-Talk/Test-Video")
        page.wait_for_selector("#view-preview.active", timeout=6000)
        assert page.locator("#sy-gate-input").count() == 0

    def test_gate_modal_buttons_do_not_overlap_input(self, server, page):
        _enable_gate(page)
        goto_spa(page, server)
        page.wait_for_selector("a.preview-link", timeout=10000)
        page.click("a.preview-link")
        page.wait_for_selector("#sy-gate-input", timeout=2000)
        inp = page.locator("#sy-gate-input").bounding_box()
        okb = page.locator(".sy-modal-btn.primary").bounding_box()
        # The buttons must sit clearly BELOW the input — a flush/zero gap renders
        # as the buttons crowding (and visually overlapping) the field.
        gap = okb["y"] - (inp["y"] + inp["height"])
        assert gap >= 10, f"buttons crowd the input: gap={gap:.1f}px (want >= 10)"

    def test_gate_password_reveal_toggle(self, server, page):
        _enable_gate(page)
        goto_spa(page, server)
        page.wait_for_selector("a.preview-link", timeout=10000)
        page.click("a.preview-link")
        page.wait_for_selector("#sy-gate-input", timeout=2000)
        inp = page.locator("#sy-gate-input")
        page.fill("#sy-gate-input", "secret123")
        assert inp.get_attribute("type") == "password"  # masked by default
        # The reveal toggle sits inside the field, on the right.
        reveal = page.locator(".sy-gate-reveal")
        rb = reveal.bounding_box()
        ib = inp.bounding_box()
        assert rb["x"] > ib["x"] + ib["width"] / 2  # right half of the field
        # An <svg> icon (not an emoji glyph), and a state that flips on click.
        assert reveal.locator("svg").count() == 1
        assert reveal.get_attribute("aria-pressed") == "false"
        reveal.click()
        assert inp.get_attribute("type") == "text"  # revealed
        assert inp.input_value() == "secret123"  # value preserved
        assert reveal.get_attribute("aria-pressed") == "true"  # state visibly flips
        reveal.click()
        assert inp.get_attribute("type") == "password"  # masked again
        assert reveal.get_attribute("aria-pressed") == "false"


class TestEditFieldHygiene:
    """The document-level edit-field guards (site/index.html): language
    routing, paste interception, Enter commit, focusout reconciliation.

    The review grid's editable column is NOT always Ukrainian -- it follows
    ?right=<lang> and falls back to the first available final SRT language --
    so typography must follow the column, not a hardcoded 'uk'."""

    REVIEW_UK = "#/review/2001-01-01_Test-Talk"
    REVIEW_EN = "#/review/2001-01-01_Test-Talk?left=uk&right=en"

    def _goto_review(self, page, server, hash):
        goto_spa(page, server, hash)
        page.wait_for_selector(".cell.uk .cell-text", timeout=10000)

    def _focus_empty_cell(self, page):
        """Focus the first editable cell with an empty value and the caret in
        it. Not Control+A: on macOS that is 'move to line start', so the typed
        text would be prepended to the existing content instead of replacing it.
        """
        page.evaluate(
            """() => {
              var el = document.querySelector('.cell.uk .cell-text');
              el.focus();
              el.textContent = '';
              var r = document.createRange();
              r.selectNodeContents(el);
              r.collapse(true);
              var s = window.getSelection();
              s.removeAllRanges();
              s.addRange(r);
            }"""
        )

    def _first_cell_edit(self, page, text):
        page.evaluate(
            """(text) => {
              var el = document.querySelector('.cell.uk .cell-text');
              el.focus();
              el.innerText = text;
              el.dispatchEvent(new Event('input', { bubbles: true }));
            }""",
            text,
        )
        page.wait_for_timeout(100)

    def test_english_column_keeps_english_typography(self, server, page):
        """Ukrainian quotes/dashes must NOT be forced onto an English column;
        edit_sync would commit the corrupted English upstream."""
        self._goto_review(page, server, self.REVIEW_EN)
        self._first_cell_edit(page, 'He said "Yes" \u2014 really')
        stored = page.evaluate("reviewState.edits[0]")
        assert '"Yes"' in stored, f"straight quotes were rewritten: {stored!r}"
        assert "\u2014" in stored, f"the em dash was rewritten: {stored!r}"

    def test_ukrainian_column_still_gets_typography(self, server, page):
        self._goto_review(page, server, self.REVIEW_UK)
        self._first_cell_edit(page, 'Він сказав "так"')
        stored = page.evaluate("reviewState.edits[0]")
        assert stored.endswith("«так»"), f"UK typography not applied: {stored!r}"

    def test_paste_keeps_whitespace_but_gets_field_wide_typography(self, server, page):
        """The paste handler itself only cleans invisibles and flattens breaks
        -- no trim, because a leading space may be intended, and no quote
        resolution, because a fragment has no caret context. Typography then
        arrives from the live pass on the input event the insert fires, which
        sees the WHOLE field and therefore resolves quotes correctly."""
        self._goto_review(page, server, self.REVIEW_UK)
        # Paste AFTER existing text: pasting a leading space into an EMPTY
        # contenteditable makes the browser itself render it as &nbsp; (the
        # very injection this PR fights), and the store trims a leading space
        # anyway. Mid-text is where the fragment's leading space is real.
        page.evaluate(
            """() => {
              var el = document.querySelector('.cell.uk .cell-text');
              el.innerText = 'слово';
              el.focus();
              var r = document.createRange();
              r.selectNodeContents(el);
              r.collapse(false);
              var s = window.getSelection();
              s.removeAllRanges();
              s.addRange(r);
              var dt = new DataTransfer();
              dt.setData('text/plain', ' "х"\\u00a0і\\nдалі');
              el.dispatchEvent(new ClipboardEvent('paste',
                { clipboardData: dt, bubbles: true, cancelable: true }));
            }"""
        )
        page.wait_for_timeout(100)
        cell = page.evaluate("document.querySelector('.cell.uk .cell-text').innerText")
        assert "слово «х» і далі" in cell, f"fragment was trimmed or mis-resolved: {cell!r}"
        assert "\n" not in cell and "\u00a0" not in cell, f"breaks/NBSP survived paste: {cell!r}"
        stored = page.evaluate("reviewState.edits[0]")
        assert "«х»" in stored, f"store missed the input-event sanitize: {stored!r}"

    def test_enter_commits_without_a_line_break(self, server, page):
        self._goto_review(page, server, self.REVIEW_UK)
        page.evaluate("document.querySelector('.cell.uk .cell-text').focus()")
        page.keyboard.type("абв")
        page.keyboard.press("Enter")
        page.wait_for_timeout(100)
        focused = page.evaluate("document.activeElement.classList.contains('cell-text')")
        assert focused is False, "Enter did not commit (blur) the cell"
        cell = page.evaluate("document.querySelector('.cell.uk .cell-text').innerText")
        assert "\n" not in cell, f"Enter inserted a line break: {cell!r}"

    def test_focusout_reconciles_the_visible_text(self, server, page):
        self._goto_review(page, server, self.REVIEW_UK)
        self._first_cell_edit(page, 'слово "х"')
        page.evaluate("document.querySelector('.cell.uk .cell-text').blur()")
        page.wait_for_timeout(100)
        cell = page.evaluate("document.querySelector('.cell.uk .cell-text').innerText")
        assert "«х»" in cell, f"focusout did not reconcile the display: {cell!r}"

    def test_quote_converts_while_typing(self, server, page):
        """The conversion must happen under the caret, not at blur: waiting
        until focus leaves reads as the field ignoring you."""
        self._goto_review(page, server, self.REVIEW_UK)
        self._focus_empty_cell(page)
        page.keyboard.type('Він сказав "так')
        page.wait_for_timeout(100)
        cell = page.evaluate("document.querySelector('.cell.uk .cell-text').textContent")
        assert cell == "Він сказав «так", f"live typography did not run: {cell!r}"
        focused = page.evaluate("document.activeElement.classList.contains('cell-text')")
        assert focused is True, "the field lost focus, so this proved nothing"

    def test_typing_continues_after_a_live_conversion(self, server, page):
        """If the caret jumped on conversion, the tail would land in the wrong
        place and the text would come out scrambled."""
        self._goto_review(page, server, self.REVIEW_UK)
        self._focus_empty_cell(page)
        page.keyboard.type('Він сказав "так" — і пішов')
        page.wait_for_timeout(100)
        cell = page.evaluate("document.querySelector('.cell.uk .cell-text').textContent")
        assert cell == "Він сказав «так» – і пішов", f"caret drifted: {cell!r}"

    def test_word_hyphen_survives_typing(self, server, page):
        """`будь-` must not become an en dash between keystrokes: mid-typing
        the end of the text is only where the caret happens to be."""
        self._goto_review(page, server, self.REVIEW_UK)
        self._focus_empty_cell(page)
        page.keyboard.type("будь-хто")
        page.wait_for_timeout(100)
        cell = page.evaluate("document.querySelector('.cell.uk .cell-text').textContent")
        assert cell == "будь-хто", f"a word hyphen was eaten mid-typing: {cell!r}"

    def test_quote_after_a_typed_space_opens(self, server, page):
        """contenteditable turns the typed space into NBSP; the quote rule must
        read through it or the quote resolves as closing."""
        self._goto_review(page, server, self.REVIEW_UK)
        self._focus_empty_cell(page)
        page.keyboard.type('слово "')
        page.wait_for_timeout(100)
        cell = page.evaluate("document.querySelector('.cell.uk .cell-text').textContent")
        assert cell.endswith("«"), f"quote after a typed space closed instead of opening: {cell!r}"

    def test_english_column_is_not_converted_while_typing(self, server, page):
        self._goto_review(page, server, self.REVIEW_EN)
        self._focus_empty_cell(page)
        page.keyboard.type('He said "yes"')
        page.wait_for_timeout(100)
        cell = page.evaluate("document.querySelector('.cell.uk .cell-text').textContent")
        assert cell == 'He said "yes"', f"English text was converted live: {cell!r}"

    def test_undo_survives_a_live_conversion(self, server, page):
        """The replacement goes through execCommand precisely so the browser's
        undo stack stays intact; a textContent rewrite would flatten it."""
        self._goto_review(page, server, self.REVIEW_UK)
        self._focus_empty_cell(page)
        page.keyboard.type('слово "х')
        page.wait_for_timeout(100)
        before = page.evaluate("document.querySelector('.cell.uk .cell-text').textContent")
        assert "«х" in before, before
        page.evaluate("document.execCommand('undo')")
        page.wait_for_timeout(100)
        after = page.evaluate("document.querySelector('.cell.uk .cell-text').textContent")
        assert after != before, "undo did nothing -- the undo stack was reset by the live rewrite"

    def test_preview_shift_enter_also_commits(self, server, page):
        """The old preview handler let Shift+Enter insert a line break into a
        single-line subtitle cue; now every Enter commits."""
        _goto_preview_video(page, server)
        page.click('.preview-mode-toggle [data-mode="edit"]')
        page.wait_for_timeout(50)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        page.wait_for_timeout(100)
        page.keyboard.type("Перший рядок")
        page.keyboard.press("Shift+Enter")
        page.wait_for_timeout(100)
        cell = page.evaluate("document.querySelector('.edited').innerText")
        assert "\n" not in cell, f"Shift+Enter inserted a break: {cell!r}"
        focused = page.evaluate("document.activeElement.classList.contains('edited')")
        assert focused is False, "Shift+Enter did not commit (blur) the cue"


class TestPreferencesMenu:
    """The gear menu is the only way into language, theme and expert mode.

    These preferences follow the user across every view, so their controls live
    in one panel rather than as separate header buttons — and each one has to
    keep driving the same stored value the rest of the app reads.
    """

    def test_menu_is_closed_until_the_gear_is_clicked(self, server, page):
        goto_spa(page, server)
        assert page.locator("#prefs-menu").is_visible() is False
        page.click("#prefs-btn")
        assert page.locator("#prefs-menu").is_visible() is True

    def test_escape_closes_the_menu_and_returns_focus_to_the_gear(self, server, page):
        goto_spa(page, server)
        page.click("#prefs-btn")
        page.keyboard.press("Escape")
        assert page.locator("#prefs-menu").is_visible() is False
        # Focus must come back, or a keyboard user is dropped at the top of the
        # document with no idea where the menu went.
        assert page.evaluate("document.activeElement.id") == "prefs-btn"

    def test_clicking_outside_closes_the_menu(self, server, page):
        goto_spa(page, server)
        page.click("#prefs-btn")
        page.click("h1")
        assert page.locator("#prefs-menu").is_visible() is False

    def test_choosing_a_theme_applies_and_stores_it(self, server, page):
        goto_spa(page, server)
        page.click("#prefs-btn")
        page.click("#prefs-theme button:has-text('Dark')")
        assert page.evaluate("document.documentElement.getAttribute('data-theme')") == "dark"
        assert page.evaluate("localStorage.getItem('sy_theme')") == "dark"

    def test_auto_clears_the_theme_so_the_os_decides_again(self, server, page):
        """'auto' is the ABSENCE of a choice: leaving the key set would pin the
        page to whatever theme was current when the user picked auto."""
        goto_spa(page, server)
        page.click("#prefs-btn")
        page.click("#prefs-theme button:has-text('Dark')")
        page.click("#prefs-theme button:has-text('Auto')")
        assert page.evaluate("document.documentElement.getAttribute('data-theme')") is None
        assert page.evaluate("localStorage.getItem('sy_theme')") is None

    def test_the_chosen_theme_is_marked_pressed(self, server, page):
        goto_spa(page, server)
        page.click("#prefs-btn")
        page.click("#prefs-theme button:has-text('Light')")
        pressed = page.evaluate(
            "Array.from(document.querySelectorAll('#prefs-theme button'))"
            ".filter(b => b.getAttribute('aria-pressed') === 'true').map(b => b.textContent)"
        )
        assert pressed == ["Light"]

    def test_switching_language_translates_the_page(self, server, page):
        page.add_init_script("localStorage.setItem('sy_lang', 'en');")
        goto_spa(page, server)
        page.click("#prefs-btn")
        page.click("#prefs-lang button:has-text('UK')")
        assert page.evaluate("localStorage.getItem('sy_lang')") == "uk"
        assert page.evaluate("document.documentElement.lang") == "uk"

    def test_the_menu_relabels_itself_on_a_language_switch(self, server, page):
        """The rows are composed text, not data-i18n elements, so translatePage()
        cannot reach them — they stick in the old language unless redrawn."""
        page.add_init_script("localStorage.setItem('sy_lang', 'en');")
        goto_spa(page, server)
        page.click("#prefs-btn")
        assert "Theme" in page.locator("#prefs-menu").inner_text()
        page.click("#prefs-lang button:has-text('UK')")
        assert "Авто" in page.locator("#prefs-theme").inner_text()

    def test_expert_switch_reflects_the_stored_value_on_load(self, server, page):
        page.add_init_script("localStorage.setItem('sy_expert_mode', '1');")
        goto_spa(page, server)
        page.click("#prefs-btn")
        assert page.locator("#prefs-expert").is_checked() is True

    def test_expert_switch_reads_a_stored_zero_as_off(self, server, page):
        """Expert mode shipped as `=== '1'`, so users who turned it off carry a
        literal "0" — treating that as truthy would switch it on for them."""
        page.add_init_script("localStorage.setItem('sy_expert_mode', '0');")
        goto_spa(page, server)
        page.click("#prefs-btn")
        assert page.locator("#prefs-expert").is_checked() is False

    def test_toggling_the_expert_switch_stores_and_applies_it(self, server, page):
        goto_spa(page, server)
        page.click("#prefs-btn")
        page.click("#prefs-expert")
        assert page.evaluate("localStorage.getItem('sy_expert_mode')") == "1"
        assert page.evaluate("expertMode") is True

    def test_the_gear_is_reachable_from_the_keyboard(self, server, page):
        goto_spa(page, server)
        page.evaluate("document.getElementById('prefs-btn').focus()")
        page.keyboard.press("Enter")
        assert page.locator("#prefs-menu").is_visible() is True

    def test_the_menu_stays_open_while_choosing(self, server, page):
        """Regression: the rows used to be rebuilt on every change, which
        detached the clicked button before the event reached the document —
        the outside-click handler then saw no .prefs ancestor and closed the
        menu on every single choice."""
        goto_spa(page, server)
        page.click("#prefs-btn")
        page.click("#prefs-theme button:has-text('Dark')")
        assert page.locator("#prefs-menu").is_visible() is True

    def test_the_menu_is_not_dressed_by_whatever_it_sits_in(self, server, page):
        """The gear lives inside #freshness-bar, which is monospaced with wide
        letter-spacing for dates and branch names. A settings panel full of
        sentence labels must not inherit that — the component sets its own type,
        which is also what makes the styleguide's rendering honest."""
        goto_spa(page, server)
        page.click("#prefs-btn")
        font = page.evaluate("getComputedStyle(document.querySelector('.prefs-row__label')).fontFamily")
        assert "mono" not in font.lower(), f"menu inherited the freshness bar's mono type: {font!r}"
        spacing = page.evaluate("getComputedStyle(document.querySelector('.prefs-row__label')).letterSpacing")
        assert spacing == "normal", f"menu inherited tracking meant for codes: {spacing!r}"

    def test_space_chooses_an_option_instead_of_playing_the_video(self, server, page):
        """In the preview view a bare Space toggles playback. The menu's options
        are buttons, which the shortcut handler did not exempt — so Space on
        "Dark" preventDefault()ed the button's own click and played the video
        instead. The menu is the only way to these settings, so a keyboard user
        had no way in at all."""
        _goto_preview_video(page, server)
        page.click("#prefs-btn")
        page.focus("#prefs-theme button:has-text('Dark')")
        page.keyboard.press(" ")
        assert page.evaluate("localStorage.getItem('sy_theme')") == "dark"

    def test_expert_mode_says_so_next_to_the_gear(self, server, page):
        """Expert mode changes what the index shows — extra badges, pipeline
        links. Left unsaid, someone who switched it on last session has no cue
        why their screen looks different, and the gear looks identical either
        way."""
        page.add_init_script("localStorage.setItem('sy_expert_mode', '1');")
        page.add_init_script("localStorage.setItem('sy_lang', 'uk');")
        goto_spa(page, server)
        flag = page.locator("#expert-flag")
        assert flag.is_visible() is True
        assert flag.inner_text().strip() == "Експертний режим"

    def test_nothing_is_said_when_expert_mode_is_off(self, server, page):
        goto_spa(page, server)
        assert page.locator("#expert-flag").is_visible() is False

    def test_the_flag_appears_the_moment_the_switch_is_thrown(self, server, page):
        goto_spa(page, server)
        page.click("#prefs-btn")
        page.click("#prefs-expert")
        assert page.locator("#expert-flag").is_visible() is True
        page.click("#prefs-expert")
        assert page.locator("#expert-flag").is_visible() is False

    def test_the_flag_follows_a_language_switch(self, server, page):
        """Asserting the English text alone proved nothing: "Expert mode" is the
        static fallback in the markup, so that assertion held even with the
        data-i18n attribute deleted and translatePage() never reaching the flag.
        Watching it cross from one language to the other is what needs the
        translation to actually run."""
        page.add_init_script("localStorage.setItem('sy_expert_mode', '1');")
        page.add_init_script("localStorage.setItem('sy_lang', 'uk');")
        goto_spa(page, server)
        flag = page.locator("#expert-flag")
        assert flag.inner_text().strip() == "Експертний режим"
        page.click("#prefs-btn")
        page.click("#prefs-lang button:has-text('EN')")
        assert flag.inner_text().strip() == "Expert mode"

    def test_the_switch_and_the_flag_never_contradict_each_other(self, server, page):
        """Two painters, one state: the flag was painted from the `expertMode`
        variable while the menu painted the switch from storage, and nothing
        reconciled them. A change made in another tab left one saying on and the
        other off, in the same panel, at the same moment."""
        page.add_init_script("localStorage.setItem('sy_expert_mode', '1');")
        goto_spa(page, server)
        # Another tab turns expert off. This tab is told nothing.
        page.evaluate("localStorage.removeItem('sy_expert_mode')")
        page.click("#prefs-btn")
        checked = page.evaluate("document.getElementById('prefs-expert').checked")
        flagged = page.locator("#expert-flag").is_visible()
        assert checked == flagged, f"switch says {checked}, flag says {flagged}"

    def test_the_switch_does_what_it_shows(self, server, page):
        """Whatever it is showing, throwing it must move expert mode to the other
        state. Painted from storage but toggled through a stale variable, an
        unchecked box turned expert OFF — the opposite of what checking it
        promises — and then snapped straight back to unchecked."""
        page.add_init_script("localStorage.setItem('sy_expert_mode', '1');")
        goto_spa(page, server)
        page.evaluate("localStorage.removeItem('sy_expert_mode')")
        page.click("#prefs-btn")
        was_checked = page.evaluate("document.getElementById('prefs-expert').checked")
        page.click("#prefs-expert")
        now_on = page.evaluate("localStorage.getItem('sy_expert_mode') === '1'")
        assert now_on is not was_checked, "the switch moved expert mode the way it was already set"

    def test_the_flag_is_not_dressed_by_whatever_it_sits_in(self, server, page):
        """The same trap the menu itself fell into: the flag sits in
        #freshness-bar, which sets the mono family and the tracking meant for
        codes and dates. The styleguide renders the component outside that bar,
        so left inheriting, the catalog and the app disagree about what
        .expert-flag looks like."""
        page.add_init_script("localStorage.setItem('sy_expert_mode', '1');")
        goto_spa(page, server)
        font = page.evaluate("getComputedStyle(document.getElementById('expert-flag')).fontFamily")
        assert "mono" not in font.lower(), f"flag inherited the freshness bar's mono type: {font!r}"
        spacing = page.evaluate("getComputedStyle(document.getElementById('expert-flag')).letterSpacing")
        assert spacing == "normal", f"flag inherited tracking meant for codes: {spacing!r}"

    def test_escape_elsewhere_does_not_yank_focus_to_the_gear(self, server, page):
        """The menu closes on an outside click but not on focus leaving it, so it
        can still be open while the user works elsewhere. Escape then belongs to
        whatever they are doing — leaving fullscreen, cancelling a dialog — and
        must not drag the caret across the page to the gear."""
        goto_spa(page, server)
        page.click("#prefs-btn")
        outside = page.evaluate(
            """() => {
                const el = document.querySelector('a[href]');
                if (!el) return null;
                if (!el.id) el.id = 'zz-outside-link';
                el.focus();
                return document.activeElement.id;
            }"""
        )
        assert outside, "no focusable element outside the menu to test with"
        page.keyboard.press("Escape")
        assert page.evaluate("document.activeElement.id") == outside

    def test_the_flag_sits_before_the_gear(self, server, page):
        page.add_init_script("localStorage.setItem('sy_expert_mode', '1');")
        goto_spa(page, server)
        order = page.evaluate(
            "document.getElementById('expert-flag').compareDocumentPosition(document.getElementById('prefs-btn'))"
        )
        # Node.DOCUMENT_POSITION_FOLLOWING — the gear comes after the flag.
        assert order & 4, "the flag must read as a label for the control it sits beside"


@pytest.mark.e2e
class TestTypoHints:
    """Words neither a Ukrainian dictionary nor this project's own vocabulary
    knows get a wavy underline while the translator types.

    The dictionary is served in miniature here: the real one is 9 MB and costs
    seconds to parse, and none of that is what these tests are about. The rest
    of the chain is real — the worker, the module inside it, the message round
    trip and the painting.
    """

    REVIEW_UK = "#/review/2001-01-01_Test-Talk"

    # The "dictionary" spells the words a test types deliberately, plus the
    # fixture's own paragraphs — the hints judge every visible cell, so leaving
    # those unknown would bury each assertion under the rest of the grid.
    # `ґрантхі` is in no Ukrainian dictionary and comes from the project's list.
    AFF = "SET UTF-8\n"
    DIC = "6\nваші\nслабшають\nперший\nдругий\nабзац\nмова\n"
    OWN_WORDS = "ґрантхі\n"

    def _serve_small_dictionary(self, page):
        page.route("**/dict/uk_UA.aff", lambda r: r.fulfill(status=200, content_type="text/plain", body=self.AFF))
        page.route("**/dict/uk_UA.dic", lambda r: r.fulfill(status=200, content_type="text/plain", body=self.DIC))
        page.route(
            "**/dict/words_uk.txt",
            lambda r: r.fulfill(status=200, content_type="text/plain", body=self.OWN_WORDS),
        )

    def _open_editor_with_hints_on(self, page, server, lang=None):
        self._serve_small_dictionary(page)
        page.add_init_script("localStorage.setItem('sy_typo_hints', '1');")
        if lang:
            page.add_init_script(f"localStorage.setItem('sy_lang', '{lang}');")
        goto_spa(page, server, self.REVIEW_UK)
        page.wait_for_selector(".cell.uk .cell-text", timeout=10000)

    def _hover_the_mixed_word(self, page):
        """Put the pointer in the middle of whatever sy-typo-script covers."""
        box = page.evaluate(
            """() => {
              const marks = CSS.highlights.get('sy-typo-script');
              if (!marks) return null;
              const r = [...marks][0].getBoundingClientRect();
              return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
            }"""
        )
        assert box, "nothing is marked as mixed-script"
        page.mouse.move(box["x"], box["y"])

    def _type_into_first_cell(self, page, text, wait_for_paint=True):
        """Replace the first cell's text and wait for the hints to catch up.

        The wait belongs here, with the edit that causes the repaint, and not in
        whatever reads the result afterwards. A scan is debounced, so an instant
        after the edit `typoSeq` has not moved yet — anything comparing it with
        `typoPaintedSeq` is answered by the paint that came BEFORE the edit and
        reads the screen as it was. Assertions about what is painted survive
        that; assertions that nothing is painted do not.

        `wait_for_paint=False` is for the one case where no paint is coming
        because the preference is off and nothing is scanning.
        """
        before = page.evaluate("() => typoPaintedSeq")
        page.evaluate(
            """(text) => {
              var el = document.querySelector('.cell.uk .cell-text');
              el.focus();
              el.innerText = text;
              el.dispatchEvent(new Event('input', { bubbles: true }));
            }""",
            text,
        )
        if wait_for_paint:
            self._wait_for_repaint(page, before)

    def _wait_for_repaint(self, page, before):
        """Wait for a paint LATER than `before` (from `_paint_count`).

        Later, not merely current: `typoPaintedSeq == typoSeq` is already true
        while a debounced scan is still pending, so on its own it is satisfied
        by the paint that preceded whatever the test just did.
        """
        page.wait_for_function(
            "(before) => typoPaintedSeq > before && typoPaintedSeq === typoSeq",
            arg=before,
            timeout=15000,
        )

    def _paint_count(self, page):
        return page.evaluate("() => typoPaintedSeq")

    def _painted_words(self, page):
        """What the highlight registry covers. A read, nothing more — whatever
        caused the paint is what waited for it."""
        return page.evaluate("() => [...CSS.highlights.get('sy-typo')].map(r => r.toString())")

    def test_underlines_a_word_no_source_knows(self, server, page):
        self._open_editor_with_hints_on(page, server)
        self._type_into_first_cell(page, "ваші відрації слабшають")

        assert self._painted_words(page) == ["відрації"]

    def test_leaves_the_project_vocabulary_alone(self, server, page):
        """`ґрантхі` is in no Ukrainian dictionary — the project's own wordlist
        is the whole reason the hints are usable on this material."""
        self._open_editor_with_hints_on(page, server)
        self._type_into_first_cell(page, "ваші ґрантхі слабшають")

        assert self._painted_words(page) == []

    def test_paints_without_touching_the_text(self, server, page):
        """The whole point of the Highlight API: the cell the edit store reads
        must be byte-identical to what the user typed, with no wrapper element
        inserted around the underlined word."""
        self._open_editor_with_hints_on(page, server)
        self._type_into_first_cell(page, "ваші відрації слабшають")

        assert page.evaluate("document.querySelector('.cell.uk .cell-text').innerText") == "ваші відрації слабшають"
        assert page.evaluate("document.querySelectorAll('.cell.uk .cell-text *').length") == 0

    def test_keeps_the_caret_where_the_user_left_it(self, server, page):
        """A repaint must not move the caret: this runs on every keystroke, and
        a caret that jumps makes the editor unusable."""
        self._open_editor_with_hints_on(page, server)
        self._type_into_first_cell(page, "ваші відрації слабшають")
        page.evaluate(
            """() => {
              var el = document.querySelector('.cell.uk .cell-text');
              var r = document.createRange();
              r.setStart(el.firstChild, 7);
              r.collapse(true);
              var s = getSelection(); s.removeAllRanges(); s.addRange(r);
            }"""
        )
        before = page.evaluate("getSelection().getRangeAt(0).startOffset")
        page.evaluate("scheduleTypoScan()")
        page.wait_for_timeout(600)

        assert page.evaluate("getSelection().getRangeAt(0).startOffset") == before

    def test_the_hints_go_when_the_preference_does(self, server, page):
        self._open_editor_with_hints_on(page, server)
        self._type_into_first_cell(page, "ваші відрації слабшають")
        assert self._painted_words(page) == ["відрації"]

        page.evaluate("SPA.toggleTypoHints()")

        assert page.evaluate("CSS.highlights.has('sy-typo')") is False
        assert page.evaluate("localStorage.getItem('sy_typo_hints')") is None

    def test_nothing_is_painted_until_the_preference_is_on(self, server, page):
        self._serve_small_dictionary(page)
        goto_spa(page, server, self.REVIEW_UK)
        page.wait_for_selector(".cell.uk .cell-text", timeout=10000)
        self._type_into_first_cell(page, "ваші відрації слабшають", wait_for_paint=False)
        page.wait_for_timeout(600)

        assert page.evaluate("CSS.highlights.has('sy-typo')") is False

    def test_a_mixed_script_word_is_marked_apart_from_an_unknown_one(self, server, page):
        """The two hints mean different things. An unknown word is a suggestion
        to look again; a word carrying a Latin letter is a defect the checker is
        certain of and can explain. Painted alike, the certain one reads as
        another guess."""
        self._open_editor_with_hints_on(page, server)
        self._type_into_first_cell(page, "ваші відрації Mати слабшають")

        marks = page.evaluate(
            """() => ({
              unknown: [...(CSS.highlights.get('sy-typo') || [])].map(r => r.toString()),
              script: [...(CSS.highlights.get('sy-typo-script') || [])].map(r => r.toString()),
            })"""
        )

        assert marks["unknown"] == ["відрації"]
        assert marks["script"] == ["Mати"]

    def test_the_offending_letter_itself_is_marked(self, server, page):
        """Naming the letter in words cannot work here: «T» and «Т» are the same
        shape, so a tip reading "Latin «T» where «Т» belongs" shows the reader
        two glyphs they cannot tell apart. The mark has to be ON the letter, in
        the word, where the eye can go straight to it."""
        self._open_editor_with_hints_on(page, server)
        self._type_into_first_cell(page, "ваші Toм слабшають")

        letters = page.evaluate("() => [...(CSS.highlights.get('sy-typo-letter') || [])].map(r => r.toString())")

        assert letters == ["T", "o"], "the Latin letters of `Toм` are not marked"

    def test_a_word_the_checker_merely_does_not_know_has_no_letter_marked(self, server, page):
        """There is no offending letter to point at — the checker knows only
        that neither source has the word."""
        self._open_editor_with_hints_on(page, server)
        self._type_into_first_cell(page, "ваші відрації слабшають")

        letters = page.evaluate("() => [...(CSS.highlights.get('sy-typo-letter') || [])].map(r => r.toString())")

        assert letters == []

    def test_hovering_a_mixed_script_word_names_the_letter(self, server, page):
        """The whole difficulty of this typo is that there is nothing to see: the
        word reads as correct. An underline alone sends the writer to stare at
        it; the hint has to say which letter, and what belonged there."""
        self._open_editor_with_hints_on(page, server, lang="uk")
        self._type_into_first_cell(page, "ваші Mати слабшають")

        self._hover_the_mixed_word(page)

        tip = page.locator("#typo-tip")
        tip.wait_for(state="visible", timeout=5000)
        assert tip.inner_text().strip() == "Різні розкладки в одному слові: латинська «M» замість «М»"

    def test_the_tip_goes_when_the_pointer_leaves(self, server, page):
        self._open_editor_with_hints_on(page, server, lang="uk")
        self._type_into_first_cell(page, "ваші Mати слабшають")
        self._hover_the_mixed_word(page)
        page.locator("#typo-tip").wait_for(state="visible", timeout=5000)

        page.mouse.move(2, 2)

        assert page.locator("#typo-tip").is_visible() is False

    def test_the_tip_goes_when_the_last_flagged_word_is_fixed(self, server, page):
        """Fixing the word the tip is about, with the pointer still on it.

        The hands are on the keyboard, so no mousemove follows the keystroke —
        and once the last flag is gone there is no mark left for a later
        mousemove to land on either. The tip has to be settled by the repaint,
        or it outlives the mistake it describes and cannot be dismissed at all.
        """
        self._open_editor_with_hints_on(page, server, lang="uk")
        self._type_into_first_cell(page, "ваші Mати слабшають")
        self._hover_the_mixed_word(page)
        page.locator("#typo-tip").wait_for(state="visible", timeout=5000)

        self._type_into_first_cell(page, "ваші слабшають")

        assert page.locator("#typo-tip").is_visible() is False

    def test_the_tip_goes_when_its_word_is_fixed_and_others_remain(self, server, page):
        """The same keystroke, with another mixed word still on screen.

        Marks remain, so nothing stops a mousemove here — but the pointer does
        not move, and the Range the tip was placed from is replaced by the
        repaint. Left alone, the tip keeps describing a letter that is no longer
        under it.
        """
        self._open_editor_with_hints_on(page, server, lang="uk")
        self._type_into_first_cell(page, "ваші Mати Toм")
        self._hover_the_mixed_word(page)
        page.locator("#typo-tip").wait_for(state="visible", timeout=5000)

        self._type_into_first_cell(page, "ваші слабшають Toм")

        assert page.locator("#typo-tip").is_visible() is False

    def test_the_tip_stays_when_a_different_word_is_fixed(self, server, page):
        """The pointer rests on `Mати` while the OTHER mixed word is corrected.

        The repaint replaces every Range, including the one the tip was placed
        from — so it has to be re-placed, not blanked. Hiding on every repaint
        would satisfy the tests about a tip going away and quietly take the tip
        away from a mistake that is still there, still under the pointer.
        """
        self._open_editor_with_hints_on(page, server, lang="uk")
        self._type_into_first_cell(page, "ваші Mати Toм")
        self._hover_the_mixed_word(page)
        page.locator("#typo-tip").wait_for(state="visible", timeout=5000)

        self._type_into_first_cell(page, "ваші Mати слабшають")

        tip = page.locator("#typo-tip")
        assert tip.is_visible() is True, "the tip was blanked while its word was still under the pointer"
        assert "«M»" in tip.inner_text()

    def test_the_tip_redescribes_the_letter_now_under_the_pointer(self, server, page):
        """Same spot, different mistake: `Mати` becomes `Tати` without the
        pointer moving. A tip that only survives is not enough — it has to be
        about the word that is there now."""
        self._open_editor_with_hints_on(page, server, lang="uk")
        self._type_into_first_cell(page, "ваші Mати слабшають")
        self._hover_the_mixed_word(page)
        page.locator("#typo-tip").wait_for(state="visible", timeout=5000)
        assert "«M»" in page.locator("#typo-tip").inner_text()

        self._type_into_first_cell(page, "ваші Tати слабшають")

        tip = page.locator("#typo-tip")
        assert tip.is_visible() is True
        assert "«T»" in tip.inner_text(), tip.inner_text()

    def test_the_tip_goes_when_the_preference_does(self, server, page):
        """Switching the hints off with a tip open. The underlines go by
        themselves — the tip is a separate element and needs saying."""
        self._open_editor_with_hints_on(page, server, lang="uk")
        self._type_into_first_cell(page, "ваші Mати слабшають")
        self._hover_the_mixed_word(page)
        page.locator("#typo-tip").wait_for(state="visible", timeout=5000)

        page.evaluate("() => SPA.toggleTypoHints()")

        assert page.locator("#typo-tip").is_visible() is False

    def test_the_tip_goes_when_the_pointer_leaves_the_window(self, server, page):
        """Leaving the window fires mouseout, never mousemove.

        Nothing else reports it, so a tip left standing here has no event coming
        that could take it down — and the pointer it was placed from is no
        longer anywhere on the page.
        """
        self._open_editor_with_hints_on(page, server, lang="uk")
        self._type_into_first_cell(page, "ваші Mати слабшають")
        self._hover_the_mixed_word(page)
        page.locator("#typo-tip").wait_for(state="visible", timeout=5000)

        # relatedTarget null is how the browser says "gone from the window".
        page.evaluate(
            """() => document.querySelector('.cell.uk .cell-text').dispatchEvent(
                 new MouseEvent('mouseout', { bubbles: true, relatedTarget: null })
               )"""
        )

        assert page.locator("#typo-tip").is_visible() is False

    def test_a_pointer_crossing_the_page_never_touches_the_tip(self, server, page):
        """The guards are the cheap path, and cheap has to mean untouched.

        Writing `hidden = true` onto an already-hidden element is an attribute
        write like any other: the browser recalculates style for it. On a
        mousemove — which fires for every pixel across the whole page, whether
        or not anything is marked — that is a cost paid for nothing.
        """
        self._open_editor_with_hints_on(page, server, lang="uk")
        self._type_into_first_cell(page, "ваші Mати слабшають")

        writes = page.evaluate(
            """() => {
              const tip = document.getElementById('typo-tip');
              let n = 0;
              const obs = new MutationObserver(records => { n += records.length; });
              obs.observe(tip, { attributes: true });
              const outside = document.body;
              for (let i = 0; i < 50; i++) {
                outside.dispatchEvent(new MouseEvent('mousemove', {
                  bubbles: true, clientX: 10 + i, clientY: 10,
                }));
              }
              return new Promise(done => setTimeout(() => {
                obs.disconnect();
                done(n);
              }, 50));
            }"""
        )

        assert writes == 0, f"{writes} attribute writes onto a tip that was already hidden"

    def test_the_tip_goes_when_the_cells_it_pointed_into_are_gone(self, server, page):
        """A talk loading replaces the grid with a skeleton: no cells to judge.

        The scan gives up on an empty screen, which is right — but giving up
        left the marks and the tip describing text that is no longer there.
        """
        self._open_editor_with_hints_on(page, server, lang="uk")
        self._type_into_first_cell(page, "ваші Mати слабшають")
        self._hover_the_mixed_word(page)
        page.locator("#typo-tip").wait_for(state="visible", timeout=5000)

        page.evaluate("() => document.getElementById('review-grid').replaceChildren()")

        page.wait_for_function("() => !CSS.highlights.has('sy-typo')", timeout=5000)
        assert page.locator("#typo-tip").is_visible() is False

    def test_the_tip_survives_the_text_being_wrapped(self, server, page):
        """Cmd+B is not blocked, and it leaves the cell's text inside a <b>.

        The pointer is then over that wrapper rather than over the cell itself,
        and a hint that asks only what the event's target is loses the word for
        good — the underline stays, and no tip ever explains it again.
        """
        self._open_editor_with_hints_on(page, server, lang="uk")
        self._type_into_first_cell(page, "ваші Mати слабшають")

        painted = self._paint_count(page)
        page.evaluate(
            """() => {
              const el = document.querySelector('.cell.uk .cell-text');
              const b = document.createElement('b');
              b.textContent = el.textContent;
              el.replaceChildren(b);
            }"""
        )
        self._wait_for_repaint(page, painted)
        self._hover_the_mixed_word(page)

        tip = page.locator("#typo-tip")
        tip.wait_for(state="visible", timeout=5000)
        assert "«M»" in tip.inner_text()

    def test_the_tip_goes_when_the_view_does(self, server, page):
        """Leaving the review for the index hides the grid without emptying it.

        Nothing mutates, so no scan runs and every mark stays valid — while the
        cells they describe are off screen and the tip floats over the index.
        """
        self._open_editor_with_hints_on(page, server, lang="uk")
        self._type_into_first_cell(page, "ваші Mати слабшають")
        self._hover_the_mixed_word(page)
        page.locator("#typo-tip").wait_for(state="visible", timeout=5000)

        page.evaluate("() => { location.hash = '#/'; }")

        page.locator("#typo-tip").wait_for(state="hidden", timeout=5000)

    def test_an_unknown_word_gets_no_tip_because_there_is_nothing_to_say(self, server, page):
        """`відрації` is flagged because neither source has it — which is all the
        checker knows. A tip there could only repeat the underline."""
        self._open_editor_with_hints_on(page, server, lang="uk")
        self._type_into_first_cell(page, "ваші відрації слабшають")

        box = page.evaluate(
            """() => {
              const r = [...CSS.highlights.get('sy-typo')][0].getBoundingClientRect();
              return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
            }"""
        )
        page.mouse.move(box["x"], box["y"])
        page.wait_for_timeout(300)

        assert page.locator("#typo-tip").is_visible() is False

    def test_the_tip_speaks_the_chosen_language(self, server, page):
        self._open_editor_with_hints_on(page, server, lang="en")
        self._type_into_first_cell(page, "ваші Mати слабшають")

        self._hover_the_mixed_word(page)

        tip = page.locator("#typo-tip")
        tip.wait_for(state="visible", timeout=5000)
        assert tip.inner_text().strip() == "Two keyboard layouts in one word: Latin «M» where «М» belongs"

    def test_refuses_a_reply_measured_before_the_last_keystroke(self, server, page):
        """`seq` advances when a request is SENT, so an edit made between the
        send and the reply left the two counters equal and the stale offsets
        were painted onto the new text — underlining the wrong letters until the
        next scan landed. Offsets only describe the string they were measured
        on, so that string is what has to still be on screen."""
        self._open_editor_with_hints_on(page, server)
        self._type_into_first_cell(page, "ваші відрації слабшають")
        assert self._painted_words(page) == ["відрації"]

        # The user types on, then the reply for the previous text arrives. Read
        # back in the same evaluate, before the rescan this edit schedules.
        # Offsets 5-13 covered `відрації` in the old text; in the new one they
        # cover `ваші від`.
        result = page.evaluate(
            """() => {
              const el = document.querySelector('.cell.uk .cell-text');
              const before = typoPaintedSeq;
              el.innerText = 'ЗЗЗЗ ваші відрації слабшають';
              typoWorker.onmessage({ data: { seq: typoSeq, spans: [[{ start: 5, end: 13 }]] } });
              return {
                seq_before: before,
                seq_after: typoPaintedSeq,
                painted: [...CSS.highlights.get('sy-typo')].map(r => r.toString()),
              };
            }"""
        )

        # Replacing the text detaches the ranges already painted, so what
        # survives reads as empty. What must never appear is the slice those
        # stale offsets describe in the NEW text.
        assert "ваші від" not in result["painted"], f"stale offsets landed on the new text: {result}"

    def test_a_dictionary_that_never_loads_turns_the_switch_back_off(self, server, page):
        """The worker stops when the dictionary cannot be fetched, but the
        preference and the switch went on saying the feature was running. That
        is the same lie in the other direction: the user's next click reads as
        "turn it off", so there is no way to retry."""
        self._serve_small_dictionary(page)
        page.route("**/dict/uk_UA.dic", lambda r: r.fulfill(status=404, body=""))
        page.add_init_script("localStorage.setItem('sy_typo_hints', '1');")
        goto_spa(page, server, self.REVIEW_UK)
        page.wait_for_selector(".cell.uk .cell-text", timeout=10000)
        page.wait_for_function("() => typoWorker === null", timeout=15000)

        assert page.evaluate("localStorage.getItem('sy_typo_hints')") is None
        page.click("#prefs-btn")
        assert page.evaluate("document.getElementById('prefs-typo').checked") is False
