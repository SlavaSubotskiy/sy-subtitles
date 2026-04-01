"""E2E tests for the dynamic SPA preview (v2.html / preview-spa.html)."""

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

# Simulated GitHub Trees API response
MOCK_TREE = {
    "sha": "test123",
    "tree": [
        {"path": "talks/2001-01-01_Test-Talk/meta.yaml", "type": "blob"},
        {"path": "talks/2001-01-01_Test-Talk/transcript_en.txt", "type": "blob"},
        {"path": "talks/2001-01-01_Test-Talk/transcript_uk.txt", "type": "blob"},
        {"path": "talks/2001-01-01_Test-Talk/Test-Video/final/uk.srt", "type": "blob"},
        {"path": "talks/2001-01-01_Test-Talk/Test-Video/source/en.srt", "type": "blob"},
        # Test-Video-2 has NO uk.srt
        {"path": "talks/2001-01-01_Test-Talk/Test-Video-2/source/en.srt", "type": "blob"},
        # Talk without UK transcript
        {"path": "talks/2002-01-01_No-Uk/meta.yaml", "type": "blob"},
        {"path": "talks/2002-01-01_No-Uk/transcript_en.txt", "type": "blob"},
    ],
}


@pytest.fixture(scope="module")
def spa_path():
    return Path(__file__).parent.parent / "docs" / "preview-spa.html"


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

    # Clear cache before each page load
    pg.add_init_script("localStorage.removeItem('sy_tree_cache'); localStorage.removeItem('sy_app_version');")
    yield pg
    pg.close()
    ctx.close()


SPA_URL = "/preview-spa.html"


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
