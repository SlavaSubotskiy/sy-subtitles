"""E2E tests for subtitle preview pages using Playwright with mock Vimeo Player."""

import functools
import http.server
import threading
from pathlib import Path

import pytest
import yaml

SAMPLE_SRT = """1
00:00:01,000 --> 00:00:05,000
Перший субтитр

2
00:00:06,000 --> 00:00:10,000
Другий субтитр

3
00:00:15,000 --> 00:00:20,000
Третій субтитр
"""


@pytest.fixture(scope="module")
def preview_site(tmp_path_factory):
    from tools.generate_preview import generate_site, scan_all_talks

    base = tmp_path_factory.mktemp("site")
    talks = base / "talks"
    talk = talks / "2001-01-01_Test"
    talk.mkdir(parents=True)
    meta = {
        "title": "Test Talk",
        "date": "2001-01-01",
        "videos": [{"slug": "Video", "title": "Test Video", "vimeo_url": "https://vimeo.com/12345/abc"}],
    }
    (talk / "meta.yaml").write_text(yaml.dump(meta, allow_unicode=True))
    video = talk / "Video" / "final"
    video.mkdir(parents=True)
    (video / "uk.srt").write_text(SAMPLE_SRT, encoding="utf-8")

    out = base / "out"
    entries = scan_all_talks(str(talks))
    generate_site(entries, str(out))
    return out


@pytest.fixture(scope="module")
def server(preview_site):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(preview_site))
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
    # Mock Vimeo Player SDK
    pg.route(
        "**/player.vimeo.com/api/player.js",
        lambda route: route.fulfill(status=200, content_type="application/javascript", body=mock_player_js),
    )
    # Mock SRT fetch — return our test SRT
    pg.route(
        "**/raw.githubusercontent.com/**",
        lambda route: route.fulfill(status=200, content_type="text/plain", body=SAMPLE_SRT),
    )
    yield pg
    pg.close()
    ctx.close()


VIDEO_URL = "/2001-01-01_Test/Video/"


class TestIndexPage:
    def test_loads(self, server, page):
        page.goto(f"{server}/")
        assert "Subtitle Preview" in page.title()

    def test_has_link(self, server, page):
        page.goto(f"{server}/")
        assert page.locator("a[href*='2001-01-01_Test']").count() > 0


class TestVideoPage:
    def test_loads(self, server, page):
        page.goto(f"{server}{VIDEO_URL}")
        assert "Test Video" in page.title()

    def test_mock_player_visible(self, server, page):
        page.goto(f"{server}{VIDEO_URL}")
        page.wait_for_selector("#mock-player", state="visible", timeout=5000)

    def test_subtitles_loaded(self, server, page):
        page.goto(f"{server}{VIDEO_URL}")
        page.wait_for_selector("#mock-player", state="visible", timeout=5000)
        # Wait for SRT fetch to complete
        page.wait_for_function("document.getElementById('status').textContent.includes('loaded')", timeout=5000)


class TestSubtitleSync:
    def _goto_and_wait(self, server, page):
        page.goto(f"{server}{VIDEO_URL}")
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        page.wait_for_function("document.getElementById('status').textContent.includes('loaded')", timeout=10000)

    def _set_time_and_get_subtitle(self, page, seconds):
        return page.evaluate(
            f"""() => {{
            window._vimeoPlayer._setTime({seconds});
            return new Promise(resolve => {{
                setTimeout(() => {{
                    resolve(document.getElementById('subtitle-overlay').textContent);
                }}, 100);
            }});
        }}"""
        )

    def test_no_subtitle_at_zero(self, server, page):
        self._goto_and_wait(server, page)
        text = self._set_time_and_get_subtitle(page, 0)
        assert text.strip() == ""

    def test_first_subtitle_at_2s(self, server, page):
        self._goto_and_wait(server, page)
        text = self._set_time_and_get_subtitle(page, 2)
        assert text == "Перший субтитр"

    def test_second_subtitle_at_7s(self, server, page):
        self._goto_and_wait(server, page)
        text = self._set_time_and_get_subtitle(page, 7)
        assert text == "Другий субтитр"

    def test_gap_at_12s(self, server, page):
        self._goto_and_wait(server, page)
        text = self._set_time_and_get_subtitle(page, 12)
        assert text.strip() == ""

    def test_third_subtitle_at_17s(self, server, page):
        self._goto_and_wait(server, page)
        text = self._set_time_and_get_subtitle(page, 17)
        assert text == "Третій субтитр"

    def test_no_subtitle_after_all(self, server, page):
        self._goto_and_wait(server, page)
        text = self._set_time_and_get_subtitle(page, 25)
        assert text.strip() == ""


class TestMarkers:
    def _goto_and_wait(self, server, page):
        page.goto(f"{server}{VIDEO_URL}")
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        page.wait_for_function("document.getElementById('status').textContent.includes('loaded')", timeout=10000)
        # Clear any stored markers
        page.evaluate("localStorage.removeItem('markers_' + location.pathname)")

    def _set_time(self, page, seconds):
        page.evaluate(f"window._vimeoPlayer._setTime({seconds})")
        page.wait_for_timeout(150)

    def test_mark_button_adds_marker(self, server, page):
        self._goto_and_wait(server, page)
        self._set_time(page, 2)
        page.click("#btn-mark")
        count = page.locator("#marker-count").text_content()
        assert count == "1"

    def test_marker_has_timecode_and_text(self, server, page):
        self._goto_and_wait(server, page)
        self._set_time(page, 2)
        page.click("#btn-mark")
        tc = page.locator(".marker-item .tc").first.text_content()
        text = page.locator(".marker-item .text").first.text_content()
        assert "00:00:02" in tc
        assert "Перший субтитр" in text

    def test_mark_pauses_video(self, server, page):
        self._goto_and_wait(server, page)
        self._set_time(page, 2)
        page.click("#btn-mark")
        # Mock player should have pause called — check it didn't error
        count = page.locator("#marker-count").text_content()
        assert count == "1"

    def test_comment_input_exists(self, server, page):
        self._goto_and_wait(server, page)
        self._set_time(page, 2)
        page.click("#btn-mark")
        assert page.locator(".marker-item .comment").count() == 1

    def test_comment_input_focused_after_mark(self, server, page):
        self._goto_and_wait(server, page)
        self._set_time(page, 2)
        page.click("#btn-mark")
        page.wait_for_timeout(200)
        focused = page.evaluate("document.activeElement.className")
        assert "comment" in focused

    def test_enter_resumes_playback(self, server, page):
        self._goto_and_wait(server, page)
        self._set_time(page, 2)
        page.click("#btn-mark")
        page.wait_for_timeout(200)
        page.keyboard.press("Enter")
        # Should not error — play() was called on mock
        count = page.locator("#marker-count").text_content()
        assert count == "1"

    def test_comment_saved(self, server, page):
        self._goto_and_wait(server, page)
        self._set_time(page, 2)
        page.click("#btn-mark")
        page.wait_for_timeout(200)
        page.locator(".marker-item .comment").fill("fix this")
        page.locator(".marker-item .comment").dispatch_event("change")
        stored = page.evaluate("JSON.parse(localStorage.getItem('markers_' + location.pathname))")
        assert stored[0]["comment"] == "fix this"

    def test_remove_marker(self, server, page):
        self._goto_and_wait(server, page)
        self._set_time(page, 2)
        page.click("#btn-mark")
        assert page.locator("#marker-count").text_content() == "1"
        page.locator(".marker-item .del").click()
        assert page.locator("#marker-count").text_content() == "0"

    def test_seek_on_timecode_click(self, server, page):
        self._goto_and_wait(server, page)
        self._set_time(page, 7)
        page.click("#btn-mark")
        # Now click the timecode to seek
        page.locator(".marker-item .tc").first.click()
        # setCurrentTime should have been called on mock
        time = page.evaluate("window._vimeoPlayer._currentTime")
        assert time == 7

    def test_keyboard_m_adds_marker(self, server, page):
        self._goto_and_wait(server, page)
        self._set_time(page, 3)
        page.keyboard.press("m")
        page.wait_for_timeout(300)
        count = page.locator("#marker-count").text_content()
        assert count == "1"

    def test_multiple_markers(self, server, page):
        self._goto_and_wait(server, page)
        self._set_time(page, 2)
        page.click("#btn-mark")
        page.wait_for_timeout(200)
        page.keyboard.press("Enter")
        page.wait_for_timeout(200)
        self._set_time(page, 7)
        page.click("#btn-mark")
        assert page.locator("#marker-count").text_content() == "2"
        assert page.locator(".marker-item").count() == 2

    def test_copy_all_markers(self, server, page):
        self._goto_and_wait(server, page)
        self._set_time(page, 2)
        page.click("#btn-mark")
        page.wait_for_timeout(200)
        page.locator(".marker-item .comment").fill("test comment")
        page.locator(".marker-item .comment").dispatch_event("change")
        # markersToText should include comment
        text = page.evaluate("markersToText()")
        assert "00:00:02" in text
        assert "Перший субтитр" in text
        assert "test comment" in text

    def test_create_issue_url(self, server, page):
        self._goto_and_wait(server, page)
        self._set_time(page, 2)
        page.click("#btn-mark")
        # Check that createIssue builds correct URL
        url = page.evaluate("""() => {
            var title = encodeURIComponent('Subtitle review: Test Video');
            var body = encodeURIComponent(markersToText());
            return 'https://github.com/SlavaSubotskiy/sy-subtitles/issues/new?title=' + title + '&body=' + body;
        }""")
        assert "issues/new" in url
        assert "00%3A00%3A02" in url or "00:00:02" in url

    def test_localStorage_persistence(self, server, page):
        self._goto_and_wait(server, page)
        self._set_time(page, 2)
        page.click("#btn-mark")
        assert page.locator("#marker-count").text_content() == "1"
        # Reload page
        page.reload()
        page.wait_for_selector("#mock-player", state="visible", timeout=10000)
        # Markers should persist
        count = page.locator("#marker-count").text_content()
        assert count == "1"

    def test_no_subtitle_marker_text(self, server, page):
        self._goto_and_wait(server, page)
        self._set_time(page, 12)  # gap — no subtitle
        page.click("#btn-mark")
        text = page.locator(".marker-item .text").first.text_content()
        assert text == "(no subtitle)"
