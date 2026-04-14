"""E2E tests for the synced video player in the review view.

Re-uses the server/mock_player_js/browser/page fixtures from
test_preview_spa via direct import. Runs standalone with
``pytest tests/test_sync_player.py``.
"""

from __future__ import annotations

import json

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
    """Navigate to review view and switch to SRT source."""
    goto_spa(page, server, "#/review/2001-01-01_Test-Talk")
    page.wait_for_selector("#review-grid", timeout=20000)
    page.evaluate("SPA.switchReviewMode('srt', 'Test-Video')")
    page.wait_for_selector(".cell.uk", timeout=20000)
    # Poll: under parallel load SyncPlayer.init may unhide the button
    # after switchReviewMode has already returned. CI runners sometimes
    # stall on page init, so use a generous timeout here.
    page.wait_for_function(
        "() => { var b = document.getElementById('btn-sync-player'); return b && b.style.display !== 'none'; }",
        timeout=20000,
    )


def _drag_resize_handle(page, dy_px):  # noqa: F811
    """Mouse-drag the sync-player resize handle by dy_px (positive = down)."""
    box = page.evaluate("""
      () => {
        var h = document.getElementById('sync-player-resize').getBoundingClientRect();
        return { x: h.left + h.width / 2, y: h.top + h.height / 2 };
      }
    """)
    page.mouse.move(box["x"], box["y"])
    page.mouse.down()
    page.mouse.move(box["x"], box["y"] + dy_px, steps=8)
    page.mouse.up()
    page.wait_for_timeout(50)


class TestSyncPlayerButtonVisibility:
    def test_button_hidden_in_transcript_mode(self, server, page):  # noqa: F811
        goto_spa(page, server, "#/review/2001-01-01_Test-Talk")
        page.wait_for_selector("#review-grid", timeout=10000)
        assert not page.locator("#btn-sync-player").is_visible()

    def test_button_visible_in_srt_mode(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        assert page.locator("#btn-sync-player").is_visible()


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
        assert page.locator("#btn-sync-player").is_visible()
        page.evaluate("SPA.switchReviewMode('transcript')")
        page.wait_for_timeout(200)
        assert not page.locator("#btn-sync-player").is_visible()


class TestPlayerMount:
    def test_clicking_show_mounts_vimeo_iframe(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        assert page.locator("#sync-player-bar").is_visible()

    def test_clicking_toggle_twice_does_not_duplicate(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        page.click("#btn-sync-player")  # hide
        page.click("#btn-sync-player")  # show again
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
            var fn = SyncPlayer._binarySearchByMs;
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
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        page.evaluate("window._vimeoPlayer._setTime(6)")
        page.wait_for_timeout(50)

        highlighted = page.evaluate("""
          () => Array.from(
            document.querySelectorAll('.cell.uk.current')
          ).map(c => c.dataset.msStart)
        """)
        assert highlighted == ["6000"]

    def test_timeupdate_highlights_en_row_independently(self, server, page):  # noqa: F811
        """EN column gets its own .current based on EN start times,
        independent of the UK column."""
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # SAMPLE_EN_SRT row 2 starts at 4500 ms, row 3 at 8500 ms.
        page.evaluate("window._vimeoPlayer._setTime(5)")  # between EN row 2 (4.5s) and EN row 3 (8.5s)
        page.wait_for_timeout(50)

        en_highlighted = page.evaluate("""
          () => Array.from(
            document.querySelectorAll('.cell.en.current')
          ).map(c => c.dataset.msStart)
        """)
        # At t=5s the active EN row is row 2 (startMs 4500).
        assert en_highlighted == ["4500"]

    def test_en_and_uk_highlight_together(self, server, page):  # noqa: F811
        """Both columns should have exactly one .current each at any playback time."""
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        page.evaluate("window._vimeoPlayer._setTime(6)")
        page.wait_for_timeout(50)

        counts = page.evaluate("""
          () => ({
            uk: document.querySelectorAll('.cell.uk.current').length,
            en: document.querySelectorAll('.cell.en.current').length,
          })
        """)
        assert counts == {"uk": 1, "en": 1}


class TestClickToSeek:
    def test_click_en_cell_seeks_player(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

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
        page.click("#btn-sync-player")
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
        page.click("#btn-sync-player")
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
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        page.evaluate("window._vimeoPlayer.play()")

        page.evaluate("""
          () => document.querySelector('#review-grid .cell-text').focus()
        """)
        page.wait_for_timeout(50)

        paused = page.evaluate("window._vimeoPlayer._paused")
        btn_state = page.evaluate("SyncPlayer._isFollowPaused()")
        assert paused is True
        assert btn_state is True

    def test_player_play_resumes_follow(self, server, page):  # noqa: F811
        """Follow is tied to the player's play state: playing the video resumes follow."""
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        page.evaluate("""
          () => document.querySelector('#review-grid .cell-text').focus()
        """)
        page.wait_for_timeout(50)
        assert page.evaluate("SyncPlayer._isFollowPaused()")
        page.evaluate("window._vimeoPlayer.play()")
        page.wait_for_timeout(50)
        assert not page.evaluate("SyncPlayer._isFollowPaused()")


class TestEnterAndShortcuts:
    def test_enter_in_cell_blurs_and_plays(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        page.evaluate("""
          () => document.querySelector('#review-grid .cell-text').focus()
        """)
        page.wait_for_timeout(50)
        assert page.evaluate("window._vimeoPlayer._paused") is True

        page.keyboard.press("Enter")
        page.wait_for_timeout(50)

        assert page.evaluate("document.activeElement.classList.contains('cell-text')") is False
        assert page.evaluate("window._vimeoPlayer._paused") is False

    def test_space_toggles_play_pause(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        page.evaluate("window._vimeoPlayer.play()")
        page.wait_for_timeout(50)
        assert page.evaluate("window._vimeoPlayer._paused") is False

        page.evaluate("document.body.focus()")
        page.keyboard.press(" ")
        page.wait_for_timeout(100)
        assert page.evaluate("window._vimeoPlayer._paused") is True

    def test_escape_closes_player(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        page.evaluate("document.body.focus()")
        page.keyboard.press("Escape")
        page.wait_for_timeout(50)
        assert page.locator("#sync-player-bar").get_attribute("hidden") is not None

    def test_arrow_left_seeks_minus_five(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        page.evaluate("window._vimeoPlayer._setTime(20)")
        page.wait_for_timeout(50)
        page.evaluate("document.body.focus()")
        page.keyboard.press("ArrowLeft")
        page.wait_for_timeout(50)
        assert abs(page.evaluate("window._vimeoPlayer._currentTime") - 15) < 0.01


class TestPersistence:
    def test_open_state_survives_reload(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        page.evaluate("window._vimeoPlayer._setTime(7)")
        page.wait_for_timeout(1100)  # allow throttled persist (1s)

        page.reload()
        # After reload the SPA auto-detects saved SRT mode and calls
        # switchReviewMode internally — do NOT call it a second time here,
        # that would destroy() + re-init the player and wipe the state.
        page.wait_for_selector("#review-grid", timeout=10000)
        page.wait_for_selector(".cell.uk", timeout=10000)

        page.wait_for_selector("#sync-player-bar:not([hidden])", timeout=3000)
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        current = page.evaluate("window._vimeoPlayer._currentTime")
        assert abs(current - 7) < 0.1


class TestCleanup:
    def test_switching_videos_does_not_duplicate_player(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        page.evaluate("SPA.switchReviewMode('srt', 'Test-Video-2')")
        page.wait_for_timeout(300)

        assert page.locator("#mock-player").count() <= 1
        assert page.locator("#btn-sync-player").is_visible()

    def test_leaving_review_destroys_player(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        page.evaluate("location.hash = '#/'")
        page.wait_for_selector(".talk-item", timeout=5000)
        assert page.locator("#mock-player").count() == 0


class TestFinalReviewFixes:
    def test_binary_search_skips_null_uk_rows(self, server, page):  # noqa: F811
        """alignedRows can contain rows with uk=null (EN-only)."""
        _goto_review_srt(page, server)
        result = page.evaluate("""
          () => {
            var rows = [
              { uk: null, en: { startMs: 500 } },
              { uk: { startMs: 1000 } },
              { uk: null, en: { startMs: 3000 } },
              { uk: { startMs: 5000 } },
            ];
            var filtered = rows.filter(r => r && r.uk);
            var fn = SyncPlayer._binarySearchByMs;
            return {
              filteredLen: filtered.length,
              atFirst: fn(filtered, 1000),
              past:    fn(filtered, 10000),
            };
          }
        """)
        assert result == {"filteredLen": 2, "atFirst": 0, "past": 1}

    def test_hide_pauses_player(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        page.evaluate("window._vimeoPlayer.play()")
        page.wait_for_timeout(50)
        assert page.evaluate("window._vimeoPlayer._paused") is False

        page.click("#btn-sync-player")
        page.wait_for_timeout(50)
        assert page.evaluate("window._vimeoPlayer._paused") is True

    def test_focus_after_hide_does_not_touch_player(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        page.evaluate("window._vimeoPlayer.play()")
        page.click("#btn-sync-player")
        page.wait_for_timeout(50)

        page.evaluate("document.querySelector('#review-grid .cell-text').focus()")
        page.wait_for_timeout(50)
        assert not page.evaluate("SyncPlayer._isFollowPaused()")


class TestSmartPauseGuards:
    def test_manual_window_scroll_pauses_follow(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # Auto-scroll triggered by _setTime should NOT pause Follow.
        page.evaluate("window._vimeoPlayer._setTime(6)")
        page.wait_for_timeout(1100)  # let isAutoScrolling guard (1000ms) clear
        assert not page.evaluate("SyncPlayer._isFollowPaused()")

        # A subsequent user-initiated window scroll must pause Follow.
        page.evaluate("window.dispatchEvent(new Event('scroll'))")
        page.wait_for_timeout(50)
        assert page.evaluate("SyncPlayer._isFollowPaused()")

    def test_space_in_focused_cell_does_not_pause_player(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        page.evaluate("window._vimeoPlayer.play()")
        # Focus pauses the player via smart-pause; resume so we can verify Space doesn't re-pause.
        page.evaluate("document.querySelector('#review-grid .cell-text').focus()")
        page.wait_for_timeout(50)
        page.evaluate("window._vimeoPlayer.play()")
        page.wait_for_timeout(50)
        assert page.evaluate("window._vimeoPlayer._paused") is False

        page.keyboard.press(" ")
        page.wait_for_timeout(50)
        # Space must reach the textarea, not the global shortcut handler.
        assert page.evaluate("window._vimeoPlayer._paused") is False
        assert page.evaluate("document.activeElement.classList.contains('cell-text')") is True

    def test_arrow_left_in_focused_cell_does_not_seek(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        page.evaluate("window._vimeoPlayer._setTime(20)")
        page.evaluate("document.querySelector('#review-grid .cell-text').focus()")
        page.wait_for_timeout(50)

        page.keyboard.press("ArrowLeft")
        page.wait_for_timeout(50)
        assert abs(page.evaluate("window._vimeoPlayer._currentTime") - 20) < 0.01


class TestFailOpen:
    def test_show_without_vimeo_sdk_surfaces_toast(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        # Simulate SDK missing (adblock, network failure, CSP) right before user click.
        page.evaluate("delete window.Vimeo")
        page.click("#btn-sync-player")
        page.wait_for_timeout(50)
        # Bar stays hidden.
        assert page.locator("#sync-player-bar").get_attribute("hidden") is not None
        # Toast is visible with the localized message.
        toast = page.locator("#toast")
        assert toast.evaluate("el => el.classList.contains('show')")
        text = toast.text_content() or ""
        assert "Vimeo" in text


class TestResumeFollow:
    def test_player_play_resume_calls_scroll_into_view(self, server, page):  # noqa: F811
        """Resuming Follow via player.play() must scroll the current row into view."""
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # Drive to a known row so currentIdx is set, then wait out the
        # auto-scroll guard before installing the spy.
        page.evaluate("window._vimeoPlayer._setTime(6)")
        page.wait_for_timeout(1100)

        # Spy on the scroll method actually used by scrollRowIntoView
        # (window.scrollTo, not Element.scrollIntoView). Install AFTER the
        # initial auto-scroll so we only count the resume-driven call.
        page.evaluate("""
          () => {
            window._stCalls = 0;
            var orig = window.scrollTo.bind(window);
            window.scrollTo = function() { window._stCalls++; return orig.apply(window, arguments); };
          }
        """)

        # Pause Follow by focusing a cell-text (smart-pause path).
        page.evaluate("document.querySelector('#review-grid .cell-text').focus()")
        page.wait_for_timeout(50)
        assert page.evaluate("SyncPlayer._isFollowPaused()")

        # Resume Follow by playing the video — pause→play event resumes follow.
        page.evaluate("window._vimeoPlayer.play()")
        page.wait_for_timeout(50)
        assert not page.evaluate("SyncPlayer._isFollowPaused()")
        assert page.evaluate("window._stCalls > 0"), "play event must scroll current row into view on resume"


class TestVideoSwitchHighlight:
    def test_video_switch_creates_new_player_instance(self, server, page):  # noqa: F811
        """Switching to a different video slug must destroy and re-create the player."""
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # Remember the old player instance.
        page.evaluate("window._oldPlayer = window._vimeoPlayer")

        # Switch to Test-Video-2 (destroys SyncPlayer, inits with new slug).
        page.evaluate("SPA.switchReviewMode('srt', 'Test-Video-2')")
        page.wait_for_selector(".cell.uk", timeout=10000)

        # Open the player on the new video.
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # A new player instance must have been created.
        is_new = page.evaluate("window._vimeoPlayer !== window._oldPlayer")
        assert is_new, "switchReviewMode must produce a new Vimeo Player instance"

    def test_highlight_works_after_video_switch(self, server, page):  # noqa: F811
        """After switching video, timeupdate on the new player must highlight a row."""
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # Switch to Test-Video-2.
        page.evaluate("SPA.switchReviewMode('srt', 'Test-Video-2')")
        page.wait_for_selector(".cell.uk", timeout=10000)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # Drive the new player's timeupdate.
        page.evaluate("window._vimeoPlayer._setTime(6)")
        page.wait_for_timeout(50)

        highlighted = page.evaluate(
            "Array.from(document.querySelectorAll('.cell.uk.current')).map(c => c.dataset.msStart)"
        )
        assert highlighted == ["6000"], "Highlight must work on new video after video switch"


class TestToggleButtonTextSwap:
    def test_button_text_swaps_between_show_and_hide(self, server, page):  # noqa: F811
        """The single toggle button shows 'Show video' when closed and 'Hide video' when open."""
        _goto_review_srt(page, server)
        # Closed → "Show video".
        text_closed = page.evaluate("document.getElementById('btn-sync-player').textContent")
        assert "Show" in text_closed or "\u041f\u043e\u043a\u0430\u0437" in text_closed, (
            f"Expected show-text initially, got: {text_closed!r}"
        )

        # Open the player.
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        text_open = page.evaluate("document.getElementById('btn-sync-player').textContent")
        assert "Hide" in text_open or "\u0421\u0445\u043e\u0432\u0430\u0442\u0438" in text_open, (
            f"Expected hide-text after open, got: {text_open!r}"
        )

        # Close again → back to "Show video".
        page.click("#btn-sync-player")
        page.wait_for_function("() => document.getElementById('sync-player-bar').hasAttribute('hidden')")
        text_closed_again = page.evaluate("document.getElementById('btn-sync-player').textContent")
        assert text_closed_again == text_closed, f"Expected text to revert on close, got: {text_closed_again!r}"

    def test_button_title_swaps_between_show_and_hide(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        title_closed = page.evaluate("document.getElementById('btn-sync-player').title")
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        title_open = page.evaluate("document.getElementById('btn-sync-player').title")
        assert title_closed != title_open, f"title must swap on toggle: closed={title_closed!r} open={title_open!r}"


class TestReopenPreservesPlayhead:
    def test_reopen_after_hide_preserves_current_time(self, server, page):  # noqa: F811
        """Hiding then re-showing the bar must reuse the existing player without reset."""
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # Seek to 8 seconds.
        page.evaluate("window._vimeoPlayer._setTime(8)")
        page.wait_for_timeout(50)

        # Hide (toggle off).
        page.click("#btn-sync-player")
        # Wait until bar gets the hidden attribute (element is in DOM but display:none via attr).
        page.wait_for_function("() => document.getElementById('sync-player-bar').hasAttribute('hidden')")

        # Show again (toggle on).
        page.click("#btn-sync-player")
        page.wait_for_selector("#sync-player-bar:not([hidden])", timeout=2000)

        # The mock player was not remounted — _currentTime must still be 8.
        current = page.evaluate("window._vimeoPlayer._currentTime")
        assert abs(current - 8) < 0.1, f"Player currentTime must be preserved after hide/show cycle, got {current}"


class TestPersistClosed:
    def test_closed_state_survives_reload(self, server, page):  # noqa: F811
        """After closing the player and reloading, the bar must remain hidden."""
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # Close the player — persistNow() is called synchronously inside hide().
        page.click("#btn-sync-player")
        # Wait until bar gets the hidden attribute.
        page.wait_for_function("() => document.getElementById('sync-player-bar').hasAttribute('hidden')")

        # Wait for localStorage to be written (hide() calls persistNow() directly).
        page.wait_for_function("() => localStorage.getItem('sy.sync_player.2001-01-01_Test-Talk.Test-Video') !== null")

        # Verify the persisted value has open: false.
        saved_open = page.evaluate("""
            JSON.parse(localStorage.getItem('sy.sync_player.2001-01-01_Test-Talk.Test-Video')).open
        """)
        assert saved_open is False, f"Expected open:false in localStorage, got {saved_open!r}"

        page.reload()
        page.wait_for_selector("#review-grid", timeout=10000)
        page.wait_for_selector(".cell.uk", timeout=10000)

        # Bar must remain hidden after reload.
        assert page.locator("#sync-player-bar").get_attribute("hidden") is not None, (
            "Player bar must stay hidden when saved state has open:false"
        )
        # Mock player must NOT have been mounted.
        assert page.locator("#mock-player").count() == 0, "Mock player must not mount when saved state has open:false"


class TestSpaceOnSelectNoToggle:
    def test_space_on_review_mode_select_does_not_pause(self, server, page):  # noqa: F811
        """Space key while a <select> is focused must not reach the global shortcut handler."""
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # Start playing.
        page.evaluate("window._vimeoPlayer.play()")
        page.wait_for_timeout(50)
        assert page.evaluate("window._vimeoPlayer._paused") is False

        # Focus the mode select (it is visible in SRT mode).
        page.evaluate("document.getElementById('review-mode-select').focus()")
        page.wait_for_timeout(50)

        # Press Space — must be consumed by the select, not the global handler.
        page.keyboard.press(" ")
        page.wait_for_timeout(100)
        assert page.evaluate("window._vimeoPlayer._paused") is False, "Space on <select> must not toggle play/pause"


class TestPlaceholderCellNoSeek:
    def test_cell_without_ms_start_does_not_seek(self, server, page):  # noqa: F811
        """Clicking a synthetic .cell.en without data-ms-start must not trigger seekTo."""
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # Check whether the real grid already has placeholder cells.
        has_en_placeholder = page.evaluate("""
            () => {
                var ens = document.querySelectorAll('#review-grid .cell.en');
                for (var i = 0; i < ens.length; i++) {
                    if (!ens[i].dataset.msStart) return true;
                }
                return false;
            }
        """)

        if has_en_placeholder:
            # Real placeholder exists; click it and assert no seek.
            before = page.evaluate("window._vimeoPlayer._currentTime")
            page.evaluate("""
                () => {
                    var placeholder = Array.from(
                        document.querySelectorAll('#review-grid .cell.en')
                    ).find(c => !c.dataset.msStart);
                    if (placeholder) placeholder.click();
                }
            """)
            after = page.evaluate("window._vimeoPlayer._currentTime")
            assert before == after
        else:
            # No real placeholders: insert a synthetic one without data-ms-start
            # to exercise the guard in onGridClick (Number.isNaN(ms) → return).
            before = page.evaluate("window._vimeoPlayer._currentTime")
            page.evaluate("""
                () => {
                    var grid = document.getElementById('review-grid');
                    var fake = document.createElement('div');
                    fake.className = 'cell en';
                    // Deliberately NO data-ms-start attribute
                    grid.appendChild(fake);
                    fake.click();
                    fake.remove();
                }
            """)
            after = page.evaluate("window._vimeoPlayer._currentTime")
            assert before == after, "Clicking a .cell.en without data-ms-start must not seek the player"


class TestEscapeFocusExemption:
    def test_escape_with_cell_focused_does_not_close(self, server, page):  # noqa: F811
        """Pressing Escape while a .cell-text is focused must NOT hide the player."""
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # Focus a cell-text (this also pauses follow, but that's expected).
        page.evaluate("document.querySelector('#review-grid .cell-text').focus()")
        page.wait_for_timeout(50)

        page.keyboard.press("Escape")
        page.wait_for_timeout(50)

        # Bar must still be visible (Escape yields to [contenteditable] focus).
        assert page.locator("#sync-player-bar").get_attribute("hidden") is None, (
            "Escape while .cell-text is focused must not close the player"
        )

    def test_escape_without_cell_focused_closes_player(self, server, page):  # noqa: F811
        """Pressing Escape with focus on body must hide the player."""
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        page.evaluate("document.body.focus()")
        page.keyboard.press("Escape")
        page.wait_for_timeout(50)

        assert page.locator("#sync-player-bar").get_attribute("hidden") is not None, (
            "Escape with body focus must close the player"
        )


class TestHighlightCycle:
    def test_exactly_one_current_after_time_change(self, server, page):  # noqa: F811
        """After two distinct _setTime calls, exactly one .cell.uk.current must exist."""
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # Highlight first row and wait for the class to actually attach.
        page.evaluate("window._vimeoPlayer._setTime(1)")
        page.wait_for_function(
            "() => document.querySelector('.cell.uk[data-ms-start=\\\"1000\\\"].current') !== null",
            timeout=5000,
        )
        assert page.evaluate("document.querySelectorAll('.cell.uk.current').length") == 1, (
            "Expected exactly 1 .current after _setTime(1)"
        )

        # Move to second row and wait for the switch to take effect.
        page.evaluate("window._vimeoPlayer._setTime(6)")
        page.wait_for_function(
            "() => document.querySelector('.cell.uk[data-ms-start=\\\"6000\\\"].current') !== null",
            timeout=5000,
        )
        assert page.evaluate("document.querySelectorAll('.cell.uk.current').length") == 1, (
            "Expected exactly 1 .current after _setTime(6)"
        )
        assert not page.evaluate("!! document.querySelector('.cell.uk[data-ms-start=\\\"1000\\\"].current')"), (
            "First row must lose .current when playhead moves to second row"
        )


class TestRevertAllEditsHighlightRecovery:
    def test_current_recovers_after_revert_all(self, server, page):  # noqa: F811
        """After revertAllEdits rebuilds the grid, .current must self-heal on next timeupdate."""
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # Highlight the second row.
        page.evaluate("window._vimeoPlayer._setTime(6)")
        page.wait_for_timeout(50)
        assert page.evaluate("document.querySelectorAll('.cell.uk.current').length") == 1

        # Make a trivial edit so revertAllEdits has something to revert.
        page.evaluate("""
            () => {
                var ct = document.querySelector('#review-grid .cell-text');
                if (ct) {
                    ct.textContent = ct.textContent + ' x';
                    ct.dispatchEvent(new Event('input', { bubbles: true }));
                }
            }
        """)
        page.wait_for_timeout(50)

        # Revert all edits — this calls renderReview() which rebuilds the DOM.
        page.click("#btn-revert-all")
        page.wait_for_timeout(100)

        # After the rebuild, drive another timeupdate at nearly the same position.
        page.evaluate("window._vimeoPlayer._setTime(6.01)")
        page.wait_for_timeout(50)

        count = page.evaluate("document.querySelectorAll('.cell.uk.current').length")
        assert count == 1, f".current must self-heal after revertAllEdits + timeupdate, got {count}"

    def test_en_current_recovers_after_revert_all(self, server, page):  # noqa: F811
        """Parallel of the UK self-heal test for the EN column."""
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        page.evaluate("window._vimeoPlayer._setTime(6)")
        page.wait_for_timeout(50)
        assert page.evaluate("document.querySelectorAll('.cell.en.current').length") == 1

        page.evaluate("""
          () => {
            var ct = document.querySelector('#review-grid .cell-text');
            if (ct) {
              ct.textContent = ct.textContent + ' x';
              ct.dispatchEvent(new Event('input', { bubbles: true }));
            }
          }
        """)
        page.click("#btn-revert-all")
        page.wait_for_timeout(100)

        page.evaluate("window._vimeoPlayer._setTime(6.01)")
        page.wait_for_timeout(50)

        count = page.evaluate("document.querySelectorAll('.cell.en.current').length")
        assert count == 1, f"EN .current must self-heal after revertAllEdits, got {count}"


class TestSeekToClearsPausedEagerly:
    def test_paused_cleared_synchronously_without_awaiting_seek(self, server, page):  # noqa: F811
        """seekTo must clear .paused before/regardless of setCurrentTime resolving.

        Verified by replacing setCurrentTime with a never-resolving promise:
        if seekTo deferred its class update to .then(), .paused would stay
        set indefinitely.
        """
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        result = page.evaluate("""
          () => {
            // 1. Pause Follow via a manual scroll event.
            window.dispatchEvent(new Event('scroll'));
            var paused1 = SyncPlayer._isFollowPaused();
            // 2. Override setCurrentTime so seek will never resolve.
            window._vimeoPlayer.setCurrentTime = function() { return new Promise(function() {}); };
            // 3. Click an EN cell → seekTo. Must clear followPaused immediately.
            document.querySelectorAll('#review-grid .cell.en')[1].click();
            var paused2 = SyncPlayer._isFollowPaused();
            return { afterPause: paused1, afterSeek: paused2 };
          }
        """)
        assert result["afterPause"] is True, "Follow should be paused after first click"
        assert result["afterSeek"] is False, (
            "seekTo must clear .paused synchronously even when the seek promise never resolves"
        )

    def test_paused_cleared_on_arrow_key_seek(self, server, page):  # noqa: F811
        """ArrowLeft/Right global shortcut routes through seekTo and must resume Follow."""
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        page.evaluate("window._vimeoPlayer._setTime(20)")
        page.wait_for_timeout(50)

        # Pause Follow.
        page.evaluate("document.querySelector('#review-grid .cell-text').focus()")
        page.wait_for_timeout(50)
        page.evaluate("document.activeElement.blur(); document.body.focus();")
        assert page.evaluate("SyncPlayer._isFollowPaused()")

        # ArrowLeft → seekTo(-5s).
        page.keyboard.press("ArrowLeft")
        page.wait_for_timeout(50)
        assert not page.evaluate("SyncPlayer._isFollowPaused()"), "ArrowLeft (seekTo) must clear .paused"


class TestMobileViewport:
    def test_mobile_defaults_sync_player_bar_to_22vh(self, server, page):  # noqa: F811
        page.set_viewport_size({"width": 375, "height": 812})
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        height = page.evaluate("getComputedStyle(document.getElementById('sync-player-bar')).height")
        # 22vh of 812 = 178.64px. The new :root var default applies the mobile
        # override unless the user has dragged to a custom height.
        assert height.endswith("px"), f"Expected px value, got {height!r}"
        val = float(height[:-2])
        assert 177 < val < 180, f"Expected ~178.64px (22vh of 812) on mobile viewport, got {height!r}"


class TestCurrentBoxShadow:
    def test_current_row_has_inset_box_shadow(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        page.evaluate("window._vimeoPlayer._setTime(6)")
        page.wait_for_timeout(50)
        shadow = page.evaluate("""
          () => {
            var el = document.querySelector('.cell.uk.current');
            return el ? getComputedStyle(el).boxShadow : null;
          }
        """)
        assert shadow, "No .cell.uk.current element found"
        # Expect inset + some non-zero value (exact color varies by theme).
        assert "inset" in shadow, f"Expected inset box-shadow on .current cell, got {shadow!r}"


class TestHighlightComposition:
    def test_current_marked_edited_compose(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # Drive timeupdate to row 0 (startMs=1000) so it gets .current.
        page.evaluate("window._vimeoPlayer._setTime(1)")
        page.wait_for_timeout(50)

        # Edit the first cell-text — triggers .edited on its parent .cell.uk.
        page.evaluate("""
          () => {
            var ct = document.querySelector('#review-grid .cell-text');
            ct.textContent = ct.textContent + ' x';
            ct.dispatchEvent(new Event('input', { bubbles: true }));
          }
        """)
        page.wait_for_timeout(50)

        # Focus the first cell-text and press Ctrl+M to toggle .marked.
        page.evaluate("document.querySelector('#review-grid .cell-text').focus()")
        page.wait_for_timeout(30)
        page.keyboard.press("Control+m")
        page.wait_for_timeout(50)

        # Re-drive timeupdate so .current is re-applied after potential rerender.
        page.evaluate("window._vimeoPlayer._setTime(1.1)")
        page.wait_for_timeout(50)

        has_composition = page.evaluate("""
          () => Array.from(document.querySelectorAll('#review-grid .cell.uk')).some(
            el => el.classList.contains('current') &&
                  el.classList.contains('edited') &&
                  el.classList.contains('marked')
          )
        """)
        assert has_composition, "No cell has current+edited+marked simultaneously. Classes on first uk cell: " + str(
            page.evaluate("Array.from(document.querySelector('#review-grid .cell.uk').classList)")
        )


class TestThemeToggle:
    def test_current_box_shadow_persists_through_theme_toggle(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        page.evaluate("window._vimeoPlayer._setTime(6)")
        page.wait_for_timeout(50)

        # Force the theme cycle to a known dark state regardless of system preference.
        # cycleTheme rotates auto→dark→light→auto; starting from unknown,
        # we force 'dark' by setting localStorage directly then re-applying.
        page.evaluate("""
          () => {
            localStorage.setItem('sy_theme', 'dark');
            document.documentElement.setAttribute('data-theme', 'dark');
          }
        """)
        page.wait_for_timeout(50)

        dark_shadow = page.evaluate("getComputedStyle(document.querySelector('.cell.uk.current')).boxShadow")
        assert "inset" in dark_shadow, f"Expected inset box-shadow in dark theme, got {dark_shadow!r}"

        # Cycle to light theme.
        page.evaluate("SPA.cycleTheme()")  # dark → light
        page.wait_for_timeout(50)

        light_shadow = page.evaluate("getComputedStyle(document.querySelector('.cell.uk.current')).boxShadow")
        assert "inset" in light_shadow, f"Expected inset box-shadow in light theme, got {light_shadow!r}"

        assert dark_shadow != light_shadow, (
            f"Expected different shadow colors per theme: dark={dark_shadow!r}, light={light_shadow!r}"
        )


class TestResizeBar:
    def test_desktop_default_is_25vh(self, server, page):  # noqa: F811
        page.set_viewport_size({"width": 1280, "height": 800})
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        h = page.evaluate("getComputedStyle(document.getElementById('sync-player-bar')).height")
        assert h.endswith("px")
        val = float(h[:-2])
        # 25vh of 800 = 200px (+/- rounding)
        assert 199 < val < 201, f"Expected ~200px default, got {h!r}"

    def test_drag_handle_grows_bar(self, server, page):  # noqa: F811
        page.set_viewport_size({"width": 1280, "height": 800})
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        # 240 / 800 * 100 = 30vh, so 25 + 30 = 55vh of 800 = 440px.
        _drag_resize_handle(page, 240)
        h = page.evaluate("getComputedStyle(document.getElementById('sync-player-bar')).height")
        val = float(h[:-2])
        assert 435 < val < 445, f"Expected ~440px after 30vh drag, got {h!r}"

    def test_drag_is_clamped_to_75vh_max(self, server, page):  # noqa: F811
        page.set_viewport_size({"width": 1280, "height": 800})
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        _drag_resize_handle(page, 2000)
        h = page.evaluate("getComputedStyle(document.getElementById('sync-player-bar')).height")
        val = float(h[:-2])
        # 75vh of 800 = 600px
        assert 599 < val < 601, f"Expected clamp to ~600px (75vh), got {h!r}"

    def test_drag_is_clamped_to_25vh_min(self, server, page):  # noqa: F811
        page.set_viewport_size({"width": 1280, "height": 800})
        _goto_review_srt(page, server)
        page.wait_for_selector("#btn-sync-player", state="visible", timeout=5000)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        _drag_resize_handle(page, -2000)
        h = page.evaluate("getComputedStyle(document.getElementById('sync-player-bar')).height")
        val = float(h[:-2])
        # 25vh of 800 = 200px
        assert 199 < val < 201, f"Expected clamp to ~200px (25vh) min, got {h!r}"

    def test_resize_persists_across_reload(self, server, page):  # noqa: F811
        page.set_viewport_size({"width": 1280, "height": 800})
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        _drag_resize_handle(page, 160)  # +20vh -> 45vh = 360px

        raw = page.evaluate("localStorage.getItem('sy.sync_player.2001-01-01_Test-Talk.Test-Video')")
        assert raw is not None
        saved = json.loads(raw)
        assert 44 < saved["barHeightVh"] < 46, f"Expected ~45vh, got {saved['barHeightVh']}"

        # Reload and verify height is restored.
        page.reload()
        page.wait_for_selector("#review-grid", timeout=10000)
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        h = page.evaluate("getComputedStyle(document.getElementById('sync-player-bar')).height")
        val = float(h[:-2])
        assert 355 < val < 365, f"Expected ~360px restored, got {h!r}"

    def test_resize_persists_per_video(self, server, page):  # noqa: F811
        """Each video has its own barHeightVh; switching videos does not leak."""
        page.set_viewport_size({"width": 1280, "height": 800})
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        # Grow Test-Video to 55vh
        _drag_resize_handle(page, 240)

        # Switch to Test-Video-2 — should fall back to the default (25vh = 200px).
        page.evaluate("SPA.switchReviewMode('srt', 'Test-Video-2')")
        page.wait_for_selector(".cell.uk", timeout=10000)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        h = page.evaluate("getComputedStyle(document.getElementById('sync-player-bar')).height")
        val = float(h[:-2])
        assert 199 < val < 201, f"Test-Video-2 should default to 200px, got {h!r}"

    def test_resize_resumes_follow(self, server, page):  # noqa: F811
        """After dragging the handle, Follow auto-resumes even if the user
        had previously paused it (by focusing a cell or manually scrolling)."""
        page.set_viewport_size({"width": 1280, "height": 800})
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # Pause Follow by focusing a cell.
        page.evaluate("document.querySelector('#review-grid .cell-text').focus()")
        page.wait_for_timeout(50)
        assert page.evaluate("SyncPlayer._isFollowPaused()")

        # Drag the handle to force a resize.
        _drag_resize_handle(page, 120)

        # .paused class must be cleared after pointerup.
        assert not page.evaluate("SyncPlayer._isFollowPaused()"), "resize should auto-resume Follow"


class TestResizeDragLifecycle:
    def test_drag_classes_active_only_during_drag(self, server, page):  # noqa: F811
        page.set_viewport_size({"width": 1280, "height": 800})
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        def state():
            return page.evaluate("""
              () => ({
                body: document.body.classList.contains('sync-player-resizing'),
                handle: document.getElementById('sync-player-resize').classList.contains('dragging'),
              })
            """)

        assert state() == {"body": False, "handle": False}

        box = page.evaluate("""
          () => {
            var h = document.getElementById('sync-player-resize').getBoundingClientRect();
            return { x: h.left + h.width / 2, y: h.top + h.height / 2 };
          }
        """)
        page.mouse.move(box["x"], box["y"])
        page.mouse.down()
        page.mouse.move(box["x"], box["y"] + 80, steps=4)
        assert state() == {"body": True, "handle": True}
        page.mouse.up()
        assert state() == {"body": False, "handle": False}

    def test_right_click_does_not_start_drag(self, server, page):  # noqa: F811
        page.set_viewport_size({"width": 1280, "height": 800})
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # Simulate a right-click pointerdown (button=2) on the handle.
        page.evaluate("""
          () => {
            var h = document.getElementById('sync-player-resize');
            var r = h.getBoundingClientRect();
            h.dispatchEvent(new PointerEvent('pointerdown', {
              button: 2, buttons: 2, pointerId: 1, pointerType: 'mouse',
              clientX: r.left + r.width / 2, clientY: r.top + r.height / 2,
              bubbles: true, cancelable: true,
            }));
          }
        """)
        assert not page.evaluate("document.body.classList.contains('sync-player-resizing')")
        assert not page.evaluate("document.getElementById('sync-player-resize').classList.contains('dragging')")

    def test_destroy_mid_drag_clears_global_styles(self, server, page):  # noqa: F811
        page.set_viewport_size({"width": 1280, "height": 800})
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        box = page.evaluate("""
          () => {
            var h = document.getElementById('sync-player-resize').getBoundingClientRect();
            return { x: h.left + h.width / 2, y: h.top + h.height / 2 };
          }
        """)
        page.mouse.move(box["x"], box["y"])
        page.mouse.down()
        page.mouse.move(box["x"], box["y"] + 60, steps=3)
        assert page.evaluate("document.body.classList.contains('sync-player-resizing')")

        # Navigate away mid-drag. destroy() must clean up global drag styles.
        page.evaluate("location.hash = '#/'")
        page.wait_for_selector(".talk-item", timeout=5000)
        page.mouse.up()

        assert not page.evaluate("document.body.classList.contains('sync-player-resizing')")


class TestPlayerFillsBar:
    def test_mount_fills_bar_height(self, server, page):  # noqa: F811
        page.set_viewport_size({"width": 1280, "height": 800})
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        # Bar default 25vh of 800 = 200px. The mock replacement must fill
        # that — not clamp to some intrinsic fallback.
        dims = page.evaluate("""
          () => {
            var m = document.getElementById('mock-player').getBoundingClientRect();
            var bar = document.getElementById('sync-player-bar').getBoundingClientRect();
            return { mH: m.height, mW: m.width, barH: bar.height, barW: bar.width };
          }
        """)
        # Mock should be at least ~180px tall (bar minus handle 8px, minus
        # rounding). If #sync-player-mount has no size, mock falls back to its
        # 40px min-height and this test fails.
        assert dims["mH"] > 180, f"Mock player too small: {dims!r}"
        assert abs(dims["mW"] - dims["barW"]) < 2, f"Mock width must match bar: {dims!r}"

    def test_mount_grows_when_bar_is_dragged(self, server, page):  # noqa: F811
        page.set_viewport_size({"width": 1280, "height": 800})
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        before = page.evaluate("document.getElementById('mock-player').getBoundingClientRect().height")
        # Drag the handle down 240px → +30vh → 55vh bar = 440px.
        _drag_resize_handle(page, 240)
        after = page.evaluate("document.getElementById('mock-player').getBoundingClientRect().height")
        # Mock should grow with the bar. Expected roughly +240px; allow slack.
        assert after - before > 200, f"Player did not grow with bar drag: before={before}, after={after}"


class TestFollowCenteringBelowBar:
    @staticmethod
    def _install_long_srt(page):  # noqa: F811
        """Override uk.srt with 60 rows so there's real scrolling to do."""
        lines = []
        for i in range(1, 61):
            s_ms = i * 2000
            e_ms = s_ms + 1800
            s_tc = f"00:00:{s_ms // 1000:02d},{s_ms % 1000:03d}"
            e_tc = f"00:00:{e_ms // 1000:02d},{e_ms % 1000:03d}"
            lines.append(f"{i}\n{s_tc} --> {e_tc}\nUK row {i}\n")
        long_srt = "\n".join(lines) + "\n"
        en_lines = []
        for i in range(1, 61):
            s_ms = i * 2000
            e_ms = s_ms + 1800
            s_tc = f"00:00:{s_ms // 1000:02d},{s_ms % 1000:03d}"
            e_tc = f"00:00:{e_ms // 1000:02d},{e_ms % 1000:03d}"
            en_lines.append(f"{i}\n{s_tc} --> {e_tc}\nEN row {i}\n")
        long_en = "\n".join(en_lines) + "\n"
        page.route(
            "**/raw.githubusercontent.com/**/uk.srt",
            lambda r: r.fulfill(status=200, content_type="text/plain", body=long_srt),
        )
        page.route(
            "**/raw.githubusercontent.com/**/en.srt",
            lambda r: r.fulfill(status=200, content_type="text/plain", body=long_en),
        )

    def _dims(self, page):  # noqa: F811
        return page.evaluate("""
          () => {
            var cur = document.querySelector('.cell.uk.current');
            var bar = document.getElementById('sync-player-bar');
            if (!cur || !bar) return null;
            var cr = cur.getBoundingClientRect();
            var br = bar.getBoundingClientRect();
            return {
              rowTop: cr.top, rowBottom: cr.bottom,
              rowHeight: cr.height,
              barTop: br.top, barBottom: br.bottom, barHeight: br.height,
              viewportH: window.innerHeight, scrollY: window.scrollY,
            };
          }
        """)

    def test_row_below_bar_default_height(self, server, page):  # noqa: F811
        self._install_long_srt(page)
        page.set_viewport_size({"width": 1280, "height": 800})
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # Drive to row 10 (startMs = 20000). Far enough that scrolling is
        # required even at default bar height.
        page.evaluate("window._vimeoPlayer._setTime(20)")
        page.wait_for_timeout(1100)

        d = self._dims(page)
        assert d is not None
        assert d["rowTop"] >= d["barBottom"] - 1, f"Row hidden behind bar: {d!r}"
        assert d["rowBottom"] <= d["viewportH"] + 1, f"Row past bottom of viewport: {d!r}"

    def test_row_below_bar_after_55vh_resize(self, server, page):  # noqa: F811
        self._install_long_srt(page)
        page.set_viewport_size({"width": 1280, "height": 800})
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        _drag_resize_handle(page, 240)  # +30vh -> 55vh bar = 440px

        page.evaluate("window._vimeoPlayer._setTime(20)")  # row 10
        page.wait_for_timeout(1100)

        d = self._dims(page)
        assert d is not None
        assert d["rowTop"] >= d["barBottom"] - 1, f"Row hidden behind 55vh bar: {d!r}"
        assert d["rowBottom"] <= d["viewportH"] + 1, f"Row past bottom of viewport: {d!r}"
        # And roughly centered in the below-bar area:
        visible_center = d["barBottom"] + (d["viewportH"] - d["barBottom"]) / 2
        row_center = d["rowTop"] + d["rowHeight"] / 2
        assert abs(row_center - visible_center) < d["rowHeight"] + 5, (
            f"Row not centered below bar: row_center={row_center}, visible_center={visible_center}, d={d!r}"
        )

    def test_row_below_bar_at_max_75vh(self, server, page):  # noqa: F811
        """At the max bar height (75vh = 600px), only 200px remains for rows — the
        row must still not escape off the bottom."""
        self._install_long_srt(page)
        page.set_viewport_size({"width": 1280, "height": 800})
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        _drag_resize_handle(page, 2000)  # clamp to 75vh = 600px

        page.evaluate("window._vimeoPlayer._setTime(40)")  # row 20
        page.wait_for_timeout(1100)

        d = self._dims(page)
        assert d is not None
        assert d["rowTop"] >= d["barBottom"] - 1, f"Row hidden behind 75vh bar: {d!r}"
        assert d["rowBottom"] <= d["viewportH"] + 1, f"Row past bottom of viewport: {d!r}"

    def test_row_stable_across_successive_timeupdates(self, server, page):  # noqa: F811
        """Multiple timeupdate events in sequence should not accumulate scroll drift."""
        self._install_long_srt(page)
        page.set_viewport_size({"width": 1280, "height": 800})
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        for t_sec in [6, 10, 14, 18, 22, 26, 30]:
            page.evaluate(f"window._vimeoPlayer._setTime({t_sec})")
            page.wait_for_timeout(1100)
            d = self._dims(page)
            assert d is not None, f"no current at t={t_sec}"
            assert d["rowTop"] >= d["barBottom"] - 1, f"At t={t_sec}s: row hidden behind bar: {d!r}"
            assert d["rowBottom"] <= d["viewportH"] + 1, f"At t={t_sec}s: row past bottom of viewport: {d!r}"

    def test_row_below_bar_at_mobile_22vh(self, server, page):  # noqa: F811
        """Centering math must work at mobile viewport (22vh ≈ 179px bar)."""
        self._install_long_srt(page)
        page.set_viewport_size({"width": 375, "height": 812})
        _goto_review_srt(page, server)
        page.click("#btn-sync-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        page.evaluate("window._vimeoPlayer._setTime(20)")
        page.wait_for_timeout(1100)

        d = self._dims(page)
        assert d is not None
        assert d["rowTop"] >= d["barBottom"] - 1, f"Row hidden behind 22vh mobile bar: {d!r}"
        assert d["rowBottom"] <= d["viewportH"] + 1, f"Row past bottom of viewport: {d!r}"
