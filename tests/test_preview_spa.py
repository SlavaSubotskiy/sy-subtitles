"""E2E tests for the dynamic SPA preview (v2.html / index.html)."""

import functools
import http.server
import json
import threading
from pathlib import Path

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
    yield pg
    pg.close()
    ctx.close()


SPA_URL = "/index.html"


def goto_spa(page, server, hash=""):
    """Navigate to SPA."""
    page.goto(f"{server}{SPA_URL}{hash}")


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

    def test_both_videos_have_preview(self, server, page):
        """Both videos have uk.srt — both should have preview links."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        links = page.locator("a[href*='preview']").all()
        link_texts = [el.text_content().strip() for el in links]
        assert any("Test Video" in t for t in link_texts), f"'Test Video' not found in {link_texts}"
        assert any("Test Video 2" in t for t in link_texts), f"'Test Video 2' not found in {link_texts}"

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
        attr = page.locator(".cell.uk").first.get_attribute("contenteditable")
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
        data = page.evaluate("localStorage.getItem('markers_preview_2001-01-01_Test-Talk_Test-Video')")
        assert data is not None
        markers = json.loads(data)
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
        page.once("dialog", lambda dialog: dialog.accept())
        page.click("button.danger")
        assert page.locator("#marker-count").text_content() == "0"
        assert page.locator(".marker-item").count() == 0

    def test_clear_markers_cancel_keeps_markers(self, server, page):
        """Cancelling clear confirmation keeps markers."""
        self._goto_preview(server, page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        assert page.locator("#marker-count").text_content() == "1"
        page.once("dialog", lambda dialog: dialog.dismiss())
        page.click("button.danger")
        assert page.locator("#marker-count").text_content() == "1"
        assert page.locator(".marker-item").count() == 1

    def test_clear_markers_updates_localStorage(self, server, page):
        """Clear all removes markers from localStorage."""
        self._goto_preview(server, page)
        page.evaluate("window._vimeoPlayer._setTime(2)")
        page.wait_for_timeout(200)
        page.click("#btn-mark")
        data = json.loads(page.evaluate("localStorage.getItem('markers_preview_2001-01-01_Test-Talk_Test-Video')"))
        assert len(data) == 1
        page.once("dialog", lambda dialog: dialog.accept())
        page.click("button.danger")
        data = json.loads(page.evaluate("localStorage.getItem('markers_preview_2001-01-01_Test-Talk_Test-Video')"))
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
        data = json.loads(page.evaluate("localStorage.getItem('markers_preview_2001-01-01_Test-Talk_Test-Video')"))
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
            getComputedStyle(document.querySelector('#view-preview .markers')).display
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
        page.evaluate("localStorage.setItem('sy_expert_mode', '1')")
        page.goto(f"{server}{SPA_URL}#/review/2001-01-01_Test-Talk")
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
        """Mode toggle should be visible in expert mode."""
        self._goto_review_expert(server, page)
        # The title area should have a mode selector or dropdown
        selector = page.locator("#review-mode-select, .review-mode-toggle")
        assert selector.count() >= 1

    def test_mode_toggle_hidden_without_expert(self, server, page):
        """Mode toggle should be hidden in normal mode."""
        goto_spa(page, server)
        page.evaluate("localStorage.removeItem('sy_expert_mode')")
        page.goto(f"{server}{SPA_URL}#/review/2001-01-01_Test-Talk")
        page.wait_for_function("document.querySelectorAll('.cell').length > 0", timeout=10000)
        # Mode selector should be hidden
        visible = page.evaluate("""() => {
            var el = document.querySelector('#review-mode-select, .review-mode-toggle');
            return el ? getComputedStyle(el).display !== 'none' : false;
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

    def test_edit_counter_shows(self, server, page):
        """Edit counter should appear after editing."""
        self._goto_review(server, page)
        cell = page.locator(".cell.uk").first
        cell.click()
        cell.press("End")
        cell.type(" edited")
        cell.press("Tab")
        page.wait_for_timeout(200)
        counter = page.locator("#review-counter")
        assert counter.is_visible()

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
        edit_count = pg.locator("#edit-count").text_content()
        assert edit_count == "1"
        pg.close()

        # Switch to dev — edit should persist
        pg2 = make_page(ctx)
        pg2.goto(f"{server}{SPA_URL}?branch=dev#/review/2001-01-01_Test-Talk")
        pg2.wait_for_selector(".cell.uk", timeout=10000)
        pg2.wait_for_timeout(500)
        edit_count = pg2.locator("#edit-count").text_content()
        assert edit_count == "1"
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
        assert "English" in texts
        assert "Hindi" in texts
        assert "Ukrainian" in texts

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
        assert page.locator("#edit-count").text_content() == "1"
        confirmed = []
        page.once("dialog", lambda dialog: (confirmed.append(True), dialog.accept()))
        page.locator("#col-header-left").click()
        page.wait_for_selector("#transcript-dropdown-left.open", timeout=5000)
        page.locator("#transcript-dropdown-left div", has_text="Hindi").click()
        page.wait_for_function(
            "document.querySelector('.cell.en') && document.querySelector('.cell.en').textContent.indexOf('पहला') !== -1",
            timeout=10000,
        )
        assert len(confirmed) == 1

    def test_edit_warning_cancel_keeps_language(self, server, page):
        """Cancelling confirm keeps current language."""
        self._goto_review(server, page)
        cell = page.locator(".cell.uk").first
        cell.click()
        cell.press_sequentially(" test", delay=20)
        cell.press("Tab")
        page.wait_for_timeout(300)
        page.once("dialog", lambda dialog: dialog.dismiss())
        page.locator("#col-header-left").click()
        page.wait_for_selector("#transcript-dropdown-left.open", timeout=5000)
        page.locator("#transcript-dropdown-left div", has_text="Hindi").click()
        page.wait_for_timeout(500)
        assert page.evaluate("reviewState.leftLang") == "en"

    def test_no_warning_without_edits(self, server, page):
        """No confirm dialog when switching language without edits."""
        self._goto_review(server, page)
        dialogs = []
        page.on("dialog", lambda dialog: (dialogs.append(True), dialog.accept()))
        page.locator("#col-header-left").click()
        page.wait_for_selector("#transcript-dropdown-left.open", timeout=5000)
        page.locator("#transcript-dropdown-left div", has_text="Hindi").click()
        page.wait_for_function(
            "document.querySelector('.cell.en') && document.querySelector('.cell.en').textContent.indexOf('पहला') !== -1",
            timeout=10000,
        )
        assert len(dialogs) == 0

    def test_edits_cleared_after_switch(self, server, page):
        """Edits are cleared after confirmed language switch."""
        self._goto_review(server, page)
        cell = page.locator(".cell.uk").first
        cell.click()
        cell.press_sequentially(" test", delay=20)
        cell.press("Tab")
        page.wait_for_timeout(300)
        assert page.locator("#edit-count").text_content() == "1"
        page.once("dialog", lambda dialog: dialog.accept())
        page.locator("#col-header-left").click()
        page.wait_for_selector("#transcript-dropdown-left.open", timeout=5000)
        page.locator("#transcript-dropdown-left div", has_text="Hindi").click()
        page.wait_for_function(
            "document.querySelector('.cell.en') && document.querySelector('.cell.en').textContent.indexOf('पहला') !== -1",
            timeout=10000,
        )
        assert page.locator("#edit-count").text_content() == "0"

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
