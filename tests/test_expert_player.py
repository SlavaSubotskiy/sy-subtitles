"""E2E tests for Expert Mode (edit subtitles while watching video).

Re-uses the server/mock_player_js/browser/page fixtures from
test_preview_spa via direct import. Runs standalone with
``pytest tests/test_expert_player.py``.
"""

from __future__ import annotations

from tests.test_preview_spa import (  # noqa: F401  — re-exported fixtures
    SPA_URL,
    browser,
    goto_spa,
    mock_player_js,
    page,
    server,
    spa_path,
)


def _goto_review_srt(page, server):  # noqa: F811
    """Navigate to review view and switch to SRT source.

    Uses SPA.switchReviewMode() directly because the current option value
    format is 'srt' + data-video attribute, not 'srt:Test-Video'.
    (The plan assumed a format change not yet implemented; this matches
    all existing tests in test_preview_spa.py.)
    """
    goto_spa(page, server, "#/review/2001-01-01_Test-Talk")
    page.wait_for_selector("#review-grid", timeout=10000)
    page.evaluate("SPA.switchReviewMode('srt', 'Test-Video')")
    page.wait_for_selector(".cell.uk", timeout=10000)


class TestExpertButtonVisibility:
    def test_button_hidden_in_transcript_mode(self, server, page):  # noqa: F811
        goto_spa(page, server, "#/review/2001-01-01_Test-Talk")
        page.wait_for_selector("#review-grid", timeout=10000)
        assert not page.locator("#btn-expert-player").is_visible()

    def test_button_visible_in_srt_mode(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        assert page.locator("#btn-expert-player").is_visible()
