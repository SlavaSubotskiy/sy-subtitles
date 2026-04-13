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


class TestEnterAndShortcuts:
    def test_enter_in_cell_blurs_and_plays(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
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
        page.click("#btn-expert-player")
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
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        page.evaluate("document.body.focus()")
        page.keyboard.press("Escape")
        page.wait_for_timeout(50)
        assert page.locator("#expert-player-bar").get_attribute("hidden") is not None

    def test_arrow_left_seeks_minus_five(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
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
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        page.evaluate("window._vimeoPlayer._setTime(7)")
        page.wait_for_timeout(1100)  # allow throttled persist (1s)

        page.reload()
        # After reload the SPA auto-detects saved SRT mode and calls
        # switchReviewMode internally — do NOT call it a second time here,
        # that would destroy() + re-init the player and wipe the state.
        page.wait_for_selector("#review-grid", timeout=10000)
        page.wait_for_selector(".cell.uk", timeout=10000)

        page.wait_for_selector("#expert-player-bar:not([hidden])", timeout=3000)
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        current = page.evaluate("window._vimeoPlayer._currentTime")
        assert abs(current - 7) < 0.1


class TestCleanup:
    def test_switching_videos_does_not_duplicate_player(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        page.evaluate("SPA.switchReviewMode('srt', 'Test-Video-2')")
        page.wait_for_timeout(300)

        assert page.locator("#mock-player").count() <= 1
        assert page.locator("#btn-expert-player").is_visible()

    def test_leaving_review_destroys_player(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
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
            var fn = ExpertPlayer._binarySearchByMs;
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
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        page.evaluate("window._vimeoPlayer.play()")
        page.wait_for_timeout(50)
        assert page.evaluate("window._vimeoPlayer._paused") is False

        page.click("#btn-expert-player")
        page.wait_for_timeout(50)
        assert page.evaluate("window._vimeoPlayer._paused") is True

    def test_focus_after_hide_does_not_touch_player(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        page.evaluate("window._vimeoPlayer.play()")
        page.click("#btn-expert-player")
        page.wait_for_timeout(50)

        page.evaluate("document.querySelector('#review-grid .cell-text').focus()")
        page.wait_for_timeout(50)
        assert not page.evaluate("document.getElementById('btn-follow').classList.contains('paused')")


class TestSmartPauseGuards:
    def test_manual_window_scroll_pauses_follow(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # Auto-scroll triggered by _setTime should NOT pause Follow.
        page.evaluate("window._vimeoPlayer._setTime(6)")
        page.wait_for_timeout(600)  # let isAutoScrolling guard (500ms) clear
        assert not page.evaluate("document.getElementById('btn-follow').classList.contains('paused')")

        # A subsequent user-initiated window scroll must pause Follow.
        page.evaluate("window.dispatchEvent(new Event('scroll'))")
        page.wait_for_timeout(50)
        assert page.evaluate("document.getElementById('btn-follow').classList.contains('paused')")

    def test_space_in_focused_cell_does_not_pause_player(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
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
        page.click("#btn-expert-player")
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
        page.click("#btn-expert-player")
        page.wait_for_timeout(50)
        # Bar stays hidden.
        assert page.locator("#expert-player-bar").get_attribute("hidden") is not None
        # Toast is visible with the localized message.
        toast = page.locator("#toast")
        assert toast.evaluate("el => el.classList.contains('show')")
        text = toast.text_content() or ""
        assert "Vimeo" in text


# ---------------------------------------------------------------------------
# Gap 1: Toggle Follow resume scrolls current row into view
# ---------------------------------------------------------------------------
class TestResumeFollow:
    def test_toggle_follow_resume_calls_scroll_into_view(self, server, page):  # noqa: F811
        """Resuming Follow (un-pausing) must call scrollIntoView on the current row."""
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # Drive to a known row so currentIdx is set.
        page.evaluate("window._vimeoPlayer._setTime(6)")
        page.wait_for_timeout(50)

        # Install a spy on scrollIntoView AFTER the initial scroll (triggered by _setTime above).
        page.evaluate(
            "window._sivCalled = false; Element.prototype.scrollIntoView = function(opts) { window._sivCalled = true; }"
        )

        # Pause Follow (first click).
        page.click("#btn-follow")
        assert page.evaluate("document.getElementById('btn-follow').classList.contains('paused')")

        # Resume Follow (second click) — should scroll current row into view.
        page.click("#btn-follow")
        assert not page.evaluate("document.getElementById('btn-follow').classList.contains('paused')")
        assert page.evaluate("window._sivCalled === true"), (
            "toggleFollow resume must call scrollIntoView on the current row"
        )


# ---------------------------------------------------------------------------
# Gap 2: Video switch rebuilds ukRows cache; highlighting works on new video
# ---------------------------------------------------------------------------
class TestVideoSwitchHighlight:
    def test_video_switch_creates_new_player_instance(self, server, page):  # noqa: F811
        """Switching to a different video slug must destroy and re-create the player."""
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # Remember the old player instance.
        page.evaluate("window._oldPlayer = window._vimeoPlayer")

        # Switch to Test-Video-2 (destroys ExpertPlayer, inits with new slug).
        page.evaluate("SPA.switchReviewMode('srt', 'Test-Video-2')")
        page.wait_for_selector(".cell.uk", timeout=10000)

        # Open the player on the new video.
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # A new player instance must have been created.
        is_new = page.evaluate("window._vimeoPlayer !== window._oldPlayer")
        assert is_new, "switchReviewMode must produce a new Vimeo Player instance"

    def test_highlight_works_after_video_switch(self, server, page):  # noqa: F811
        """After switching video, timeupdate on the new player must highlight a row."""
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # Switch to Test-Video-2.
        page.evaluate("SPA.switchReviewMode('srt', 'Test-Video-2')")
        page.wait_for_selector(".cell.uk", timeout=10000)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # Drive the new player's timeupdate.
        page.evaluate("window._vimeoPlayer._setTime(6)")
        page.wait_for_timeout(50)

        highlighted = page.evaluate(
            "Array.from(document.querySelectorAll('.cell.uk.current')).map(c => c.dataset.msStart)"
        )
        assert highlighted == ["6000"], "Highlight must work on new video after video switch"


# ---------------------------------------------------------------------------
# Gap 3: aria-label on the close button is localized
# ---------------------------------------------------------------------------
class TestAriaLabelI18n:
    def test_aria_label_uk(self, server, page):  # noqa: F811
        """In UK language mode the close button aria-label must be Ukrainian."""
        _goto_review_srt(page, server)

        # Force UK language (headless Chrome default is 'en').
        page.evaluate("""
            if (window.currentLang !== 'uk') {
                SPA.toggleLang();
            }
        """)
        page.wait_for_timeout(50)

        label = page.evaluate(
            "document.querySelector('.expert-controls button[data-i18n-aria-label]').getAttribute('aria-label')"
        )
        assert label == "Закрити плеєр", f"Expected Ukrainian label, got: {label!r}"

    def test_aria_label_en(self, server, page):  # noqa: F811
        """In EN language mode the close button aria-label must be English."""
        _goto_review_srt(page, server)

        # Force EN language.
        page.evaluate("""
            if (window.currentLang !== 'en') {
                SPA.toggleLang();
            }
        """)
        page.wait_for_timeout(50)

        label = page.evaluate(
            "document.querySelector('.expert-controls button[data-i18n-aria-label]').getAttribute('aria-label')"
        )
        assert label == "Close player", f"Expected English label, got: {label!r}"

    def test_aria_label_toggles_with_lang_switch(self, server, page):  # noqa: F811
        """Toggling language must flip the aria-label on the close button."""
        _goto_review_srt(page, server)

        # Record initial state, then toggle and verify it changes.
        before = page.evaluate(
            "document.querySelector('.expert-controls button[data-i18n-aria-label]').getAttribute('aria-label')"
        )
        page.evaluate("SPA.toggleLang()")
        page.wait_for_timeout(50)
        after = page.evaluate(
            "document.querySelector('.expert-controls button[data-i18n-aria-label]').getAttribute('aria-label')"
        )
        assert before != after, "aria-label must change when language is toggled"
        assert after in ("Закрити плеєр", "Close player")


# ---------------------------------------------------------------------------
# Gap 4: Re-open after hide preserves playhead (mount-once, reuse optimization)
# ---------------------------------------------------------------------------
class TestReopenPreservesPlayhead:
    def test_reopen_after_hide_preserves_current_time(self, server, page):  # noqa: F811
        """Hiding then re-showing the bar must reuse the existing player without reset."""
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # Seek to 8 seconds.
        page.evaluate("window._vimeoPlayer._setTime(8)")
        page.wait_for_timeout(50)

        # Hide (toggle off).
        page.click("#btn-expert-player")
        # Wait until bar gets the hidden attribute (element is in DOM but display:none via attr).
        page.wait_for_function("() => document.getElementById('expert-player-bar').hasAttribute('hidden')")

        # Show again (toggle on).
        page.click("#btn-expert-player")
        page.wait_for_selector("#expert-player-bar:not([hidden])", timeout=2000)

        # The mock player was not remounted — _currentTime must still be 8.
        current = page.evaluate("window._vimeoPlayer._currentTime")
        assert abs(current - 8) < 0.1, f"Player currentTime must be preserved after hide/show cycle, got {current}"


# ---------------------------------------------------------------------------
# Gap 5: Persist closed — saved open:false must not auto-mount on reload
# ---------------------------------------------------------------------------
class TestPersistClosed:
    def test_closed_state_survives_reload(self, server, page):  # noqa: F811
        """After closing the player and reloading, the bar must remain hidden."""
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # Close the player — persistNow() is called synchronously inside hide().
        page.click("#btn-expert-player")
        # Wait until bar gets the hidden attribute.
        page.wait_for_function("() => document.getElementById('expert-player-bar').hasAttribute('hidden')")

        # Wait for localStorage to be written (hide() calls persistNow() directly).
        page.wait_for_function("() => localStorage.getItem('sy.expert.2001-01-01_Test-Talk.Test-Video') !== null")

        # Verify the persisted value has open: false.
        saved_open = page.evaluate("""
            JSON.parse(localStorage.getItem('sy.expert.2001-01-01_Test-Talk.Test-Video')).open
        """)
        assert saved_open is False, f"Expected open:false in localStorage, got {saved_open!r}"

        page.reload()
        page.wait_for_selector("#review-grid", timeout=10000)
        page.wait_for_selector(".cell.uk", timeout=10000)

        # Bar must remain hidden after reload.
        assert page.locator("#expert-player-bar").get_attribute("hidden") is not None, (
            "Player bar must stay hidden when saved state has open:false"
        )
        # Mock player must NOT have been mounted.
        assert page.locator("#mock-player").count() == 0, "Mock player must not mount when saved state has open:false"


# ---------------------------------------------------------------------------
# Gap 6: Space on <select> does NOT toggle play/pause
# ---------------------------------------------------------------------------
class TestSpaceOnSelectNoToggle:
    def test_space_on_review_mode_select_does_not_pause(self, server, page):  # noqa: F811
        """Space key while a <select> is focused must not reach the global shortcut handler."""
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
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


# ---------------------------------------------------------------------------
# Gap 7: Clicking a cell without data-ms-start does NOT seek
# ---------------------------------------------------------------------------
class TestPlaceholderCellNoSeek:
    def test_cell_without_ms_start_does_not_seek(self, server, page):  # noqa: F811
        """Clicking a synthetic .cell.en without data-ms-start must not trigger seekTo."""
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
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


# ---------------------------------------------------------------------------
# Gap 8: Escape closes player only when focus is NOT in .cell-text
# ---------------------------------------------------------------------------
class TestEscapeFocusExemption:
    def test_escape_with_cell_focused_does_not_close(self, server, page):  # noqa: F811
        """Pressing Escape while a .cell-text is focused must NOT hide the player."""
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # Focus a cell-text (this also pauses follow, but that's expected).
        page.evaluate("document.querySelector('#review-grid .cell-text').focus()")
        page.wait_for_timeout(50)

        page.keyboard.press("Escape")
        page.wait_for_timeout(50)

        # Bar must still be visible (Escape yields to [contenteditable] focus).
        assert page.locator("#expert-player-bar").get_attribute("hidden") is None, (
            "Escape while .cell-text is focused must not close the player"
        )

    def test_escape_without_cell_focused_closes_player(self, server, page):  # noqa: F811
        """Pressing Escape with focus on body must hide the player."""
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        page.evaluate("document.body.focus()")
        page.keyboard.press("Escape")
        page.wait_for_timeout(50)

        assert page.locator("#expert-player-bar").get_attribute("hidden") is not None, (
            "Escape with body focus must close the player"
        )


# ---------------------------------------------------------------------------
# Gap 9: .current class persists across a re-highlight cycle (never 0 or 2)
# ---------------------------------------------------------------------------
class TestHighlightCycle:
    def test_exactly_one_current_after_time_change(self, server, page):  # noqa: F811
        """After two distinct _setTime calls, exactly one .cell.uk.current must exist."""
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # Highlight first row.
        page.evaluate("window._vimeoPlayer._setTime(1)")
        page.wait_for_timeout(50)
        count_after_first = page.evaluate("document.querySelectorAll('.cell.uk.current').length")
        assert count_after_first == 1, f"Expected 1 .current after _setTime(1), got {count_after_first}"

        # Move to second row.
        page.evaluate("window._vimeoPlayer._setTime(6)")
        page.wait_for_timeout(50)
        count_after_second = page.evaluate("document.querySelectorAll('.cell.uk.current').length")
        first_still_current = page.evaluate("""
            !! document.querySelector('.cell.uk[data-ms-start="1000"].current')
        """)
        assert count_after_second == 1, f"Expected exactly 1 .current after _setTime(6), got {count_after_second}"
        assert not first_still_current, "The first row must lose .current when the playhead moves to the second row"


# ---------------------------------------------------------------------------
# Gap 10: revertAllEdits re-renders grid; .current self-heals on next timeupdate
# ---------------------------------------------------------------------------
class TestRevertAllEditsHighlightRecovery:
    def test_current_recovers_after_revert_all(self, server, page):  # noqa: F811
        """After revertAllEdits rebuilds the grid, .current must self-heal on next timeupdate."""
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
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
