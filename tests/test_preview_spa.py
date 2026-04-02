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

SAMPLE_EN = "Talk Language: English\n\nFirst paragraph.\n\nSecond paragraph.\n"
SAMPLE_UK = "Мова промови: англійська\n\nПерший абзац.\n\nДругий абзац.\n"

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
MOCK_TREE = {
    "sha": "test123",
    "tree": [
        {"path": "talks/2001-01-01_Test-Talk/Test-Video/final/uk.srt", "type": "blob"},
        {"path": "talks/2001-01-01_Test-Talk/Test-Video/source/en.srt", "type": "blob"},
        {"path": "talks/2001-01-01_Test-Talk/Test-Video-2/source/en.srt", "type": "blob"},
        {"path": "talks/2001-01-01_Test-Talk/meta.yaml", "type": "blob"},
        {"path": "talks/2001-01-01_Test-Talk/transcript_en.txt", "type": "blob"},
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

    # Mock SRT
    pg.route(
        "**/raw.githubusercontent.com/**/uk.srt",
        lambda route: route.fulfill(
            status=200,
            content_type="text/plain",
            body=SAMPLE_SRT,
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
    pg.add_init_script("localStorage.removeItem('sy_tree_cache'); localStorage.removeItem('sy_app_version');")
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

    def test_video_without_srt_no_preview(self, server, page):
        """Test-Video-2 has no uk.srt — should NOT have preview link."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        # Test-Video should have link, Test-Video-2 should not
        links = page.locator("a[href*='preview']").all()
        link_texts = [el.text_content() for el in links]
        assert "Test Video" in link_texts
        assert "Test Video 2" not in link_texts

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
        cache = page.evaluate("localStorage.getItem('sy_tree_cache')")
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
        cache = page.evaluate("localStorage.getItem('sy_tree_cache')")
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
    """Tests for search and filter on index page."""

    def test_search_input_visible(self, server, page):
        """Search input should be visible after talks load."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        assert page.locator("#search-input").is_visible()

    def test_search_filters_talks(self, server, page):
        """Typing in search should filter talks by title."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        all_count = page.locator(".talk-item").count()
        assert all_count >= 2
        page.fill("#search-input", "No-Uk")
        page.wait_for_timeout(300)
        filtered = page.locator(".talk-item").count()
        assert filtered == 1

    def test_search_no_results(self, server, page):
        """Search with no match should show zero talks."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        page.fill("#search-input", "xyznonexistent")
        page.wait_for_timeout(300)
        assert page.locator(".talk-item").count() == 0

    def test_filter_buttons_exist(self, server, page):
        """Filter buttons should be visible."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        assert page.locator(".filter-btn").count() == 4

    def test_filter_needs_review(self, server, page):
        """Filtering by 'needs review' should show only pending talks."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        page.click(".filter-btn[data-filter='needs-review']")
        page.wait_for_timeout(200)
        badges = page.locator(".review-badge").all()
        for badge in badges:
            assert "needs-review" in (badge.get_attribute("class") or "")

    def test_filter_all_resets(self, server, page):
        """Clicking 'All' should reset filter."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        all_count = page.locator(".talk-item").count()
        page.click(".filter-btn[data-filter='needs-review']")
        page.wait_for_timeout(200)
        page.click(".filter-btn[data-filter='all']")
        page.wait_for_timeout(200)
        assert page.locator(".talk-item").count() == all_count


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
        page.click("a[href*='review']")
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

    def test_pending_badge_shown(self, server, page):
        """Talk with review:pending status should show 'needs review' badge."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        badge = page.locator(".review-badge.needs-review")
        assert badge.count() >= 1
        assert "needs review" in badge.first.text_content()

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
        pg.add_init_script("localStorage.removeItem('sy_tree_cache'); localStorage.removeItem('sy_app_version');")
        pg.goto(f"{server}/index.html")
        pg.wait_for_selector(".talk-item", timeout=10000)
        badge = pg.locator(".review-badge.in-review")
        assert badge.count() >= 1
        assert "YogiReviewer" in badge.first.text_content()
        pg.close()
        ctx.close()

    def test_approved_badge(self, server, page, browser):
        """Talk with approved status should show green badge."""
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
        pg.add_init_script("localStorage.removeItem('sy_tree_cache'); localStorage.removeItem('sy_app_version');")
        pg.goto(f"{server}/index.html")
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
        pg.add_init_script("localStorage.removeItem('sy_tree_cache'); localStorage.removeItem('sy_app_version');")
        pg.goto(f"{server}/index.html")
        pg.wait_for_selector(".talk-item", timeout=10000)
        # Page loads fine, no badges shown
        assert pg.locator(".review-badge").count() == 0
        assert pg.locator(".talk-item").count() >= 1
        pg.close()
        ctx.close()

    def test_talk_without_status_no_badge(self, server, page):
        """Talk not in review-status.json should have no badge."""
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        # No-Uk talk has no status entry
        items = page.locator(".talk-item").all()
        for item in items:
            text = item.text_content()
            if "No-Uk" in text or "2002" in text:
                assert item.locator(".review-badge").count() == 0


class TestCaching:
    def test_cache_written_to_localStorage(self, server, page):
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        cache = page.evaluate("localStorage.getItem('sy_tree_cache')")
        assert cache is not None
        data = json.loads(cache)
        assert "talks" in data

    def test_app_version_stored(self, server, page):
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        version = page.evaluate("localStorage.getItem('sy_app_version')")
        assert version is not None

    def test_cached_manifest_has_hasSrt(self, server, page):
        goto_spa(page, server)
        page.wait_for_selector(".talk-item", timeout=10000)
        cache = json.loads(page.evaluate("localStorage.getItem('sy_tree_cache')"))
        talk = next(t for t in cache["talks"] if t["id"] == "2001-01-01_Test-Talk")
        video = next(v for v in talk["videos"] if v["slug"] == "Test-Video")
        assert video["hasSrt"] is True
        video2 = next(v for v in talk["videos"] if v["slug"] == "Test-Video-2")
        assert video2["hasSrt"] is False
