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


class TestCellDataMsStart:
    def test_srt_cells_have_data_ms_start(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        counts = page.evaluate("""
          () => {
            var cells = document.querySelectorAll('#review-grid .cell');
            var withAttr = 0;
            cells.forEach(c => { if (c.dataset.msStart) withAttr++; });
            return { total: cells.length, withAttr: withAttr };
          }
        """)
        assert counts["total"] > 0
        assert counts["withAttr"] == counts["total"]


class TestButtonVisibilityTransitions:
    def test_button_hides_when_switching_from_srt_to_transcript(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        assert page.locator("#btn-expert-player").is_visible()
        page.evaluate("SPA.switchReviewMode('transcript')")
        page.wait_for_timeout(200)
        assert not page.locator("#btn-expert-player").is_visible()


class TestPlayerMount:
    def test_clicking_show_mounts_vimeo_iframe(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        assert page.locator("#expert-player-bar").is_visible()

    def test_clicking_toggle_twice_does_not_duplicate(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        page.click("#btn-expert-player")  # hide
        page.click("#btn-expert-player")  # show again
        assert page.locator("#mock-player").count() == 1


class TestBinarySearch:
    def test_binary_search_cases(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        result = page.evaluate("""
          () => {
            var rows = [
              { uk: { startMs: 1000 } },
              { uk: { startMs: 5000 } },
              { uk: { startMs: 9000 } },
              { uk: { startMs: 13000 } },
            ];
            var fn = ExpertPlayer._binarySearchByMs;
            return {
              before:  fn(rows, 0),
              atFirst: fn(rows, 1000),
              between: fn(rows, 6000),
              atExact: fn(rows, 9000),
              past:    fn(rows, 20000),
              empty:   fn([], 100),
            };
          }
        """)
        assert result == {
            "before": -1,
            "atFirst": 0,
            "between": 1,
            "atExact": 2,
            "past": 3,
            "empty": -1,
        }


class TestHighlight:
    def test_timeupdate_highlights_current_row(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # SAMPLE_SRT (from tests/test_preview_spa.py): UK row 2 starts at 6000 ms.
        page.evaluate("window._vimeoPlayer._setTime(6)")
        page.wait_for_timeout(50)

        highlighted = page.evaluate("""
          () => Array.from(
            document.querySelectorAll('.cell.uk.current')
          ).map(c => c.dataset.msStart)
        """)
        assert highlighted == ["6000"]


class TestClickToSeek:
    def test_click_en_cell_seeks_player(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # SAMPLE_EN_SRT (from test_preview_spa): row 2 starts at 4500 ms.
        page.evaluate("""
          () => {
            var cells = document.querySelectorAll('#review-grid .cell.en');
            cells[1].click();
          }
        """)
        current = page.evaluate("window._vimeoPlayer._currentTime")
        assert abs(current - 4.5) < 0.01

    def test_click_cell_label_seeks_player(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        page.evaluate("""
          () => {
            document.querySelectorAll('#review-grid .cell-label')[0].click();
          }
        """)
        current = page.evaluate("window._vimeoPlayer._currentTime")
        assert abs(current - 1.0) < 0.01

    def test_click_uk_text_does_not_seek(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        before = page.evaluate("window._vimeoPlayer._currentTime")
        page.evaluate("""
          () => document.querySelector('#review-grid .cell.uk .cell-text').click()
        """)
        after = page.evaluate("window._vimeoPlayer._currentTime")
        assert before == after


class TestFollowSmartPause:
    def test_focus_cell_pauses_follow_and_player(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        page.evaluate("window._vimeoPlayer.play()")

        page.evaluate("""
          () => document.querySelector('#review-grid .cell-text').focus()
        """)
        page.wait_for_timeout(50)

        paused = page.evaluate("window._vimeoPlayer._paused")
        btn_state = page.evaluate("document.getElementById('btn-follow').classList.contains('paused')")
        assert paused is True
        assert btn_state is True

    def test_toggle_follow_button_resumes(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        page.evaluate("""
          () => document.querySelector('#review-grid .cell-text').focus()
        """)
        page.wait_for_timeout(50)
        assert page.evaluate("document.getElementById('btn-follow').classList.contains('paused')")
        page.click("#btn-follow")
        assert not page.evaluate("document.getElementById('btn-follow').classList.contains('paused')")
