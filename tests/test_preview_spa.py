"""E2E tests for the dynamic SPA preview (v2.html / index.html)."""

import functools
import http.server
import json
import re
import threading
from pathlib import Path
from urllib.parse import quote, unquote

import pytest

SAMPLE_META = """title: 'Test Talk: Subtitle Preview'
date: '2001-01-01'
location: Test Location
videos:
- slug: Test-Video
  title: Test Video
  vimeo_url: https://vimeo.com/12345/abc
- slug: Test-Video-2
  title: Test Video 2
  vimeo_url: https://vimeo.com/67890/def
"""

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
    """Serve the SPA HTML."""
    directory = str(spa_path.parent)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
    httpd = http.server.HTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()


@pytest.fixture(scope="module")
def mock_player_js():
    return Path(__file__).parent.joinpath("fixtures", "mock_vimeo_player.js").read_text()


@pytest.fixture(scope="module")
def browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright not installed")
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


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

    def test_marker_add(self, server, page):
        self._goto_preview(server, page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        count = page.locator("#marker-count").text_content()
        assert count == "1"


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
        page.click("button.danger")
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
        page.click("button.danger")
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
        page.click("button.danger")
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
    def test_default_mode_is_marker(self, server, page):
        _goto_preview_video(page, server)
        mode = page.evaluate(
            "document.querySelector('.preview-mode-toggle [data-mode=\"marker\"]').classList.contains('active')"
        )
        assert mode is True

    def test_default_new_key_shape_on_first_mutation(self, server, page):
        _goto_preview_video(page, server)
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
        page.click('.preview-mode-toggle [data-mode="edit"]')
        page.wait_for_timeout(100)
        _goto_preview_video(page, server)
        mode = page.evaluate(
            "document.querySelector('.preview-mode-toggle [data-mode=\"edit\"]').classList.contains('active')"
        )
        assert mode is True

    def test_mode_independent_per_video(self, server, page):
        _goto_preview_video(page, server, "Test-Video")
        page.click('.preview-mode-toggle [data-mode="edit"]')
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
            "document.querySelector('.preview-mode-toggle [data-mode=\"marker\"]').classList.contains('active')"
        )
        assert mode2 is True, f"debug: {debug}"
        _goto_preview_video(page, server, "Test-Video")
        mode1 = page.evaluate(
            "document.querySelector('.preview-mode-toggle [data-mode=\"edit\"]').classList.contains('active')"
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
        assert page.locator("#btn-copy-all").is_visible() is True
        page.click('.preview-mode-toggle [data-mode="edit"]')
        assert page.locator("#btn-copy-all").is_visible() is False

    def test_open_editor_btn_only_visible_in_edit_mode(self, server, page):
        _goto_preview_video(page, server)
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
        stored = page.evaluate(f"JSON.parse(localStorage.getItem('{PREVIEW_KEY}') || 'null')")
        assert stored["edits"]["uk"]["0"] == "Змінений текст"

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
        stored = page.evaluate(f"JSON.parse(localStorage.getItem('{PREVIEW_KEY}') || 'null')")
        uk_edits = stored["edits"].get("uk", {})
        assert "0" not in uk_edits and 0 not in uk_edits

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
        stored = page.evaluate(f"JSON.parse(localStorage.getItem('{PREVIEW_KEY}') || 'null')")
        assert stored["edits"].get("uk", {}) == {}

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
            "https://github.com/SlavaSubotskiy/sy-subtitles/edit/main/"
            "talks/2001-01-01_Test-Talk/Test-Video/final/uk.srt"
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
    # Our pipeline produces SRTs in ONE canonical form: UTF-8 without BOM,
    # LF line endings, blocks numbered from 1, a single blank line between
    # blocks, and exactly one trailing newline. If a human manually commits
    # an SRT in a different shape, `openPreviewEditor` MUST rewrite it back
    # to canonical form rather than faithfully preserve the source bytes —
    # reviewers should never see arbitrary formatting drift in their PRs.
    #
    # These tests codify that contract, so an accidental "preserve source"
    # refactor of parseSRT / applyEditsToSrt would fail loudly.
    # ------------------------------------------------------------------
    CANONICAL_SRT = "1\n00:00:01,000 --> 00:00:05,000\nПЕРШИЙ_НОВ\n\n2\n00:00:06,000 --> 00:00:10,000\nДругий субтитр\n"

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
        """Source without a trailing newline → clipboard ends with exactly one `\\n`."""
        source = "1\n00:00:01,000 --> 00:00:05,000\nПерший субтитр\n\n2\n00:00:06,000 --> 00:00:10,000\nДругий субтитр"
        assert not source.endswith("\n")
        self._override_uk_srt(page, source)
        _goto_preview_video(page, server)
        clip = self._edit_block0_and_grab_clip(page)
        assert clip.endswith("\n"), f"missing trailing newline: {clip[-20:]!r}"
        assert not clip.endswith("\n\n"), f"extra trailing newline: {clip[-20:]!r}"
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
        "1\n00:00:01,000 --> 00:00:05,000\nFirst EN block\n\n2\n00:00:06,000 --> 00:00:10,000\nSecond EN block\n"
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
            "https://github.com/SlavaSubotskiy/sy-subtitles/edit/main/"
            "talks/2001-01-01_Test-Talk/Test-Video/final/en.srt"
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
        stored = page.evaluate(f"JSON.parse(localStorage.getItem('{PREVIEW_KEY}') || 'null')")
        assert stored["edits"].get("uk", {}) == {}


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
        assert "location: Test City" in yaml_text
        assert "amruta_url: https://www.amruta.org/" in yaml_text
        assert "language: en" in yaml_text
        assert "videos:" in yaml_text
        assert "vimeo_url: https://vimeo.com/1234/abcd" in yaml_text
        assert "transcript_en_base64: |" in yaml_text

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
        assert "vimeo_url: https://vimeo.com/1234/abcd" in yaml_decoded, yaml_decoded[:400]
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


class TestSubtitleOverlaySize:
    """Subtitle overlay resize ceiling — guards the +50% bump from drifting back."""

    def _goto_preview(self, server, page):
        page.set_viewport_size({"width": 1600, "height": 900})
        goto_spa(page, server, "#/preview/2001-01-01_Test-Talk/Test-Video")
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        page.wait_for_timeout(500)

    def test_width_term_widened_by_50pct(self, server, page):
        """The +50% bump widens the char-width divisor (23 → 15.3). On a
        wide enough container the width-bound font should be ~1.5× what the
        old formula would have produced for the same container."""
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
        old_width_bound = (result["cqw"] - 48) / 23
        new_width_bound = (result["cqw"] - 48) / 15.3
        assert result["font"] > old_width_bound + 5, (
            f"Font {result['font']}px should beat the old /23 width-bound "
            f"≈{old_width_bound:.1f}px (cqw={result['cqw']}px)"
        )
        assert result["font"] >= new_width_bound - 1, (
            f"Font {result['font']}px should reach the new /15.3 width-bound ≈{new_width_bound:.1f}px"
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

    # The fs-mode no-drag baseline is clamp(28px, 4vw, 80px) — the original
    # rule the user wants restored. On a 1600px viewport that's min(80, 64)
    # = 64px. Use 56px (~12% safety margin) for stable baseline asserts and
    # 30px as a "definitely tiny" floor for regression checks.
    FS_MODE_BASELINE_PX = 64
    FS_MODE_BASELINE_FLOOR_PX = 56
    FS_MODE_TINY_PX = 30
    FS_MODE_FLOOR_PX = 20  # Hard floor in CSS so even drag-down stays readable.

    def _wait_for_handle(self, page):
        """The resize handle is installed asynchronously via a setTimeout
        chain after hashchange — a fixed sleep is unreliable across machines."""
        page.wait_for_selector("#preview-subs-resize", timeout=10000)

    def _read_fs_font_px_via_toggle(self, page, drag_to_h=None):
        """Use SPA.toggleFullscreen — exercises the real user flow including
        the synchronous .fs-mode class addition. Optionally drag the embedded
        handle (which sets --preview-subs-scale via JS, mirroring fs-mode)."""
        return page.evaluate(
            """(opts) => {
              const overlay = document.getElementById('subtitle-overlay');
              const vp = document.getElementById('view-preview');
              if (opts.h !== null) {
                // Mirror what applySubsPx does so we exercise the same JS path.
                document.documentElement.style.setProperty('--preview-subs-h', opts.h + 'px');
                const scale = Math.max(0.5, Math.min(4, opts.h / 120));
                document.documentElement.style.setProperty('--preview-subs-scale', String(scale));
                vp.setAttribute('data-subs-tuned', '1');
              }
              SPA.toggleFullscreen();
              return parseFloat(getComputedStyle(overlay).fontSize);
            }""",
            {"h": drag_to_h},
        )

    def test_fs_mode_default_matches_original_size(self, server, page):
        """Entering fullscreen WITHOUT having dragged must give the original
        clamp(28px, 4vw, 80px) — neither huge (post-bump regression) nor
        tiny (cascade-fallback bug)."""
        self._goto_preview(server, page)
        font_px = self._read_fs_font_px_via_toggle(page, drag_to_h=None)
        assert font_px >= self.FS_MODE_BASELINE_FLOOR_PX, (
            f"fs-mode default font shrank to {font_px}px — expected ≈ "
            f"{self.FS_MODE_BASELINE_PX}px (4vw on 1600 viewport)"
        )
        # Sanity ceiling: should NOT be the old "huge" 6vw bump on this size.
        assert font_px <= 90, (
            f"fs-mode default {font_px}px is too big — should be the original "
            f"clamp(28, 4vw, 80) ≈ 64px on 1600vw, not the bumped 6vw size"
        )

    def test_fs_mode_smaller_block_shrinks_proportionally(self, server, page):
        """A smaller embedded subtitle block (handle dragged UP — the handle
        sits below the overlay, so handle-up = block shrinks) must mirror
        into a smaller fullscreen font. This is the new bidirectional
        behavior."""
        self._goto_preview(server, page)
        baseline = self._read_fs_font_px_via_toggle(page, drag_to_h=None)
        page.evaluate("SPA.toggleFullscreen()")  # exit
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
        page.evaluate("SPA.toggleFullscreen()")
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
            """() => {
              const overlay = document.getElementById('subtitle-overlay');
              const vp = document.getElementById('view-preview');
              SPA.toggleFullscreen();
              const setHandle = (h) => {
                const scale = Math.max(0.5, Math.min(4, h / 120));
                document.documentElement.style.setProperty('--preview-subs-h', h + 'px');
                document.documentElement.style.setProperty('--preview-subs-scale', String(scale));
                vp.setAttribute('data-subs-tuned', '1');
              };
              setHandle(120);
              const baseline = parseFloat(getComputedStyle(overlay).fontSize);
              setHandle(600);
              const enlarged = parseFloat(getComputedStyle(overlay).fontSize);
              setHandle(60);
              const shrunk = parseFloat(getComputedStyle(overlay).fontSize);
              return { baseline, enlarged, shrunk };
            }"""
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
        result = page.evaluate(
            """() => {
              const handle = document.getElementById('preview-subs-resize');
              if (!handle) return { error: 'handle missing' };
              handle.focus();
              const before = getComputedStyle(document.documentElement)
                .getPropertyValue('--preview-subs-scale');
              // Arrow keys nudge the handle and route through onMove.apply
              // (= applySubsPx) — the same path as a real drag/keyboard nudge.
              for (let i = 0; i < 5; i++) {
                handle.dispatchEvent(new KeyboardEvent('keydown',
                  { key: 'ArrowDown', bubbles: true }));
              }
              return {
                scale: getComputedStyle(document.documentElement)
                  .getPropertyValue('--preview-subs-scale').trim(),
                tuned: document.getElementById('view-preview')
                  .getAttribute('data-subs-tuned'),
                before: before.trim(),
              };
            }"""
        )
        assert result.get("error") is None, result
        assert result["before"] == "", f"--preview-subs-scale should be unset before any drag, got {result['before']!r}"
        assert result["tuned"] == "1", "applySubsPx didn't set data-subs-tuned"
        assert result["scale"] != "", "applySubsPx didn't set --preview-subs-scale"
        # Scale must be a valid finite number string, never 'NaN'.
        scale_val = float(result["scale"])
        assert 0.5 <= scale_val <= 4, f"scale {scale_val} outside [0.5, 4] clamp"

    def test_handle_double_click_resets_scale_and_tuned(self, server, page):
        """Double-clicking the handle triggers onReset, which must wipe
        --preview-subs-scale and data-subs-tuned. A future refactor that
        forgets one of those would silently leave fs scaled after reset."""
        self._goto_preview(server, page)
        self._wait_for_handle(page)
        result = page.evaluate(
            """() => {
              const handle = document.getElementById('preview-subs-resize');
              if (!handle) return { error: 'handle missing' };
              handle.focus();
              for (let i = 0; i < 5; i++) {
                handle.dispatchEvent(new KeyboardEvent('keydown',
                  { key: 'ArrowDown', bubbles: true }));
              }
              const tunedBefore = document.getElementById('view-preview')
                .getAttribute('data-subs-tuned');
              const scaleBefore = getComputedStyle(document.documentElement)
                .getPropertyValue('--preview-subs-scale').trim();
              // dblclick → onReset
              handle.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
              return {
                tunedBefore, scaleBefore,
                tunedAfter: document.getElementById('view-preview')
                  .getAttribute('data-subs-tuned'),
                scaleAfter: getComputedStyle(document.documentElement)
                  .getPropertyValue('--preview-subs-scale').trim(),
                hAfter: getComputedStyle(document.documentElement)
                  .getPropertyValue('--preview-subs-h').trim(),
              };
            }"""
        )
        assert result.get("error") is None, result
        assert result["tunedBefore"] == "1" and result["scaleBefore"] != "", (
            "Test setup failed — drag didn't put us in tuned state"
        )
        assert result["tunedAfter"] is None, f"Reset didn't clear data-subs-tuned (got {result['tunedAfter']!r})"
        assert result["scaleAfter"] == "", f"Reset didn't clear --preview-subs-scale (got {result['scaleAfter']!r})"

    def test_localstorage_subs_height_round_trips_on_load(self, server, page):
        """A persisted subs-h value must be re-applied on the next page
        load by applySubsPx (which sets the scale var). Persistence
        silently breaking is the most common subtle bug for handle features."""
        # First navigation: drag the handle to seed localStorage.
        self._goto_preview(server, page)
        self._wait_for_handle(page)
        page.evaluate(
            """() => {
              const handle = document.getElementById('preview-subs-resize');
              handle.focus();
              for (let i = 0; i < 8; i++) {
                handle.dispatchEvent(new KeyboardEvent('keydown',
                  { key: 'ArrowDown', bubbles: true }));
              }
            }"""
        )
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
        assert result["scale"] != "", f"Reload didn't re-apply --preview-subs-scale via applySubsPx: {result}"
        scale_val = float(result["scale"])
        assert 0.5 <= scale_val <= 4, f"scale {scale_val} outside [0.5, 4]"

    def test_fs_mode_22vh_cap_holds_on_short_viewport(self, server, page):
        """The 22vh hard cap must pin the fs-mode font on a short viewport
        even with the handle dragged to its largest position. Without the
        cap, two-line subtitles get pushed off-screen."""
        # Use a deliberately short viewport so 22vh < 6vw * scale.
        page.set_viewport_size({"width": 1600, "height": 400})
        goto_spa(page, server, "#/preview/2001-01-01_Test-Talk/Test-Video")
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        page.wait_for_timeout(400)
        font_px = self._read_fs_font_px_via_toggle(page, drag_to_h=720)
        # 22vh on 400px viewport = 88px. Allow 1px rounding slack.
        assert font_px <= 89, f"22vh cap not enforced: font {font_px}px > 88px on a 400px viewport"
