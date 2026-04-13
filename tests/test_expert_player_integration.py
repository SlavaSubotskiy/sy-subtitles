"""Integration tests that hit real Vimeo (no SDK mock).

These tests load the real player.vimeo.com SDK and embed a real Vimeo
video inside the test harness. They require outbound network access to
vimeo.com from the test runner.

Stability policy: if the video at TEST_VIMEO_URL is removed upstream,
replace it with another project-public talk from talks/*/meta.yaml and
update this comment.

Current stable video: Mahashivaratri Puja 1979, vimeo.com/916194756/a4fda18b19
from talks/1979-02-25_Puja-In-Pune-Marathi/meta.yaml.
"""

from __future__ import annotations

import json
import os

import pytest

from tests.test_preview_spa import (  # noqa: F401  — re-exported fixtures
    MOCK_REVIEW_STATUS,
    MOCK_TREE,
    SAMPLE_EN,
    SAMPLE_EN_SRT,
    SAMPLE_HI,
    SAMPLE_SRT,
    SAMPLE_UK,
    SPA_URL,
    browser,
    goto_spa,
    server,
    spa_path,
)

# Real Vimeo URL — project-public video from the existing corpus.
# Video: Mahashivaratri Puja 1979 (Puja in Pune, Marathi)
TEST_VIMEO_URL = "https://vimeo.com/916194756/a4fda18b19"

# Gate: set SY_E2E_REAL_VIMEO=0 to skip real-network tests in environments
# where outbound Vimeo access is blocked (e.g. restricted corporate CI).
# GitHub Actions Ubuntu runners have unrestricted outbound HTTPS by default,
# so these run unconditionally unless explicitly opted out.
_SKIP_REAL = os.environ.get("SY_E2E_REAL_VIMEO", "1") == "0"
_SKIP_REASON = "SY_E2E_REAL_VIMEO=0 — real Vimeo network access disabled"

REAL_VIMEO_META = f"""title: 'Test Talk: Subtitle Preview'
date: '2001-01-01'
location: Test Location
videos:
- slug: Test-Video
  title: Test Video
  vimeo_url: {TEST_VIMEO_URL}
- slug: Test-Video-2
  title: Test Video 2
  vimeo_url: {TEST_VIMEO_URL}
"""


@pytest.fixture
def real_vimeo_page(browser, server):  # noqa: F811
    """Page fixture like `page` but WITHOUT mocking player.vimeo.com.

    Uses the real Vimeo SDK from CDN.  All GitHub API calls are still mocked
    so we only need outbound access to *.vimeo.com.
    """
    ctx = browser.new_context()
    pg = ctx.new_page()

    # Mock GitHub Trees API (same shape as test_preview_spa)
    pg.route(
        "**/api.github.com/**",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            headers={"ETag": '"test-etag"'},
            body=json.dumps(MOCK_TREE),
        ),
    )

    # Mock meta.yaml — override with real Vimeo URL so the SPA embeds a real iframe.
    pg.route(
        "**/raw.githubusercontent.com/**/meta.yaml",
        lambda route: route.fulfill(
            status=200,
            content_type="text/plain",
            body=REAL_VIMEO_META,
        ),
    )

    # Mock SRTs
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
    pg.route(
        "**/raw.githubusercontent.com/**/review-status.json",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(MOCK_REVIEW_STATUS),
        ),
    )

    # NOTE: do NOT mock player.vimeo.com — we let the real SDK load from CDN.
    pg.add_init_script("localStorage.removeItem('sy_tree_cache__main');")
    yield pg
    pg.close()
    ctx.close()


def _goto_review_srt_real(page, server):  # noqa: F811
    """Navigate to the review view and switch to SRT mode (real-Vimeo variant)."""
    goto_spa(page, server, "#/review/2001-01-01_Test-Talk")
    page.wait_for_selector("#review-grid", timeout=15000)
    page.evaluate("SPA.switchReviewMode('srt', 'Test-Video')")
    page.wait_for_selector(".cell.uk", timeout=15000)


@pytest.mark.skipif(_SKIP_REAL, reason=_SKIP_REASON)
class TestRealVimeoIntegration:
    def test_real_vimeo_sdk_loads(self, server, real_vimeo_page):  # noqa: F811
        """Real player.vimeo.com/api/player.js must load and expose Vimeo.Player."""
        _goto_review_srt_real(real_vimeo_page, server)
        sdk_present = real_vimeo_page.evaluate("typeof Vimeo !== 'undefined' && typeof Vimeo.Player === 'function'")
        assert sdk_present, "Vimeo.Player must be defined after page load (real SDK)"

    def test_real_vimeo_iframe_mounts_on_show(self, server, real_vimeo_page):  # noqa: F811
        """Clicking Show video must create a real iframe pointing at player.vimeo.com."""
        _goto_review_srt_real(real_vimeo_page, server)
        real_vimeo_page.click("#btn-expert-player")
        # Wait for the real iframe to be appended (no #mock-player in real mode).
        real_vimeo_page.wait_for_selector("#expert-player iframe", state="attached", timeout=15000)
        src = real_vimeo_page.evaluate("document.querySelector('#expert-player iframe').src")
        assert "player.vimeo.com/video/" in src, f"Expected player.vimeo.com URL, got {src!r}"
        assert "916194756" in src, f"Expected video ID in iframe src, got {src!r}"

    def test_real_vimeo_player_becomes_ready(self, server, real_vimeo_page):  # noqa: F811
        """Vimeo.Player.ready() must resolve on a real embed (SDK handshake)."""
        _goto_review_srt_real(real_vimeo_page, server)
        real_vimeo_page.click("#btn-expert-player")
        real_vimeo_page.wait_for_selector("#expert-player iframe", state="attached", timeout=15000)
        # Create a second Vimeo.Player handle against the same iframe and await ready().
        # The production code's own player instance is separate; both work against the
        # same iframe and the Vimeo SDK handles the multiplexing.
        # Wrap the async promise in a JS-level timeout to avoid hanging indefinitely.
        ready = real_vimeo_page.evaluate("""
          async () => {
            var iframe = document.querySelector('#expert-player iframe');
            if (!iframe) return 'no-iframe';
            var player = new Vimeo.Player(iframe);
            var timeout = new Promise(function(_, rej) {
              setTimeout(function() { rej(new Error('timeout')); }, 28000);
            });
            try {
              await Promise.race([player.ready(), timeout]);
              return true;
            } catch (e) {
              return String(e);
            }
          }
        """)
        assert ready is True, f"Real Vimeo player.ready() did not resolve: {ready!r}"

    def test_real_vimeo_setCurrentTime_moves_playhead(self, server, real_vimeo_page):  # noqa: F811
        """setCurrentTime on a ready real player must move the playhead."""
        _goto_review_srt_real(real_vimeo_page, server)
        real_vimeo_page.click("#btn-expert-player")
        real_vimeo_page.wait_for_selector("#expert-player iframe", state="attached", timeout=15000)
        result = real_vimeo_page.evaluate("""
          async () => {
            var iframe = document.querySelector('#expert-player iframe');
            var player = new Vimeo.Player(iframe);
            var timeout = new Promise(function(_, rej) {
              setTimeout(function() { rej(new Error('timeout')); }, 28000);
            });
            await Promise.race([player.ready(), timeout]);
            await player.setCurrentTime(5);
            return await player.getCurrentTime();
          }
        """)
        assert isinstance(result, int | float), f"Expected numeric time, got {result!r}"
        assert abs(result - 5) < 1.0, f"Expected ~5s after setCurrentTime(5), got {result}"

    def test_real_vimeo_iframe_fills_bar(self, server, real_vimeo_page):  # noqa: F811
        """Real Vimeo iframe must fill the sticky bar, not collapse to 150px."""
        real_vimeo_page.set_viewport_size({"width": 1280, "height": 800})
        _goto_review_srt_real(real_vimeo_page, server)
        real_vimeo_page.click("#btn-expert-player")
        real_vimeo_page.wait_for_selector("#expert-player iframe", state="attached", timeout=15000)
        dims = real_vimeo_page.evaluate(
            """() => {
              var ifr = document.querySelector('#expert-player iframe').getBoundingClientRect();
              var bar = document.getElementById('expert-player-bar').getBoundingClientRect();
              return { ifrH: ifr.height, ifrW: ifr.width, barH: bar.height, barW: bar.width };
            }"""
        )
        # Default 25vh of 800 = 200px. Minus 8px handle → ~192px content.
        assert dims["ifrH"] > 180, f"Real iframe collapsed (layout bug): {dims!r}"
        assert abs(dims["ifrW"] - dims["barW"]) < 2, f"Iframe width must match bar: {dims!r}"
