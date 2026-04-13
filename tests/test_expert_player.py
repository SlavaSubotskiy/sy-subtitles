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


# ---------------------------------------------------------------------------
# Smoke: A1 — Mobile viewport caps .expert-bar at 22vh
# ---------------------------------------------------------------------------
class TestMobileViewport:
    def test_mobile_defaults_expert_bar_to_22vh(self, server, page):  # noqa: F811
        page.set_viewport_size({"width": 375, "height": 812})
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        height = page.evaluate("getComputedStyle(document.getElementById('expert-player-bar')).height")
        # 22vh of 812 = 178.64px. The new :root var default applies the mobile
        # override unless the user has dragged to a custom height.
        assert height.endswith("px"), f"Expected px value, got {height!r}"
        val = float(height[:-2])
        assert 177 < val < 180, f"Expected ~178.64px (22vh of 812) on mobile viewport, got {height!r}"


# ---------------------------------------------------------------------------
# Smoke: A2 — .current cell has inset box-shadow at runtime
# ---------------------------------------------------------------------------
class TestCurrentBoxShadow:
    def test_current_row_has_inset_box_shadow(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
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


# ---------------------------------------------------------------------------
# Smoke: A3 — .current + .marked + .edited compose on the same cell
# ---------------------------------------------------------------------------
class TestHighlightComposition:
    def test_current_marked_edited_compose(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
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


# ---------------------------------------------------------------------------
# Smoke: A4 — .current indicator survives a theme toggle (dark → light)
# ---------------------------------------------------------------------------
class TestThemeToggle:
    def test_current_box_shadow_persists_through_theme_toggle(self, server, page):  # noqa: F811
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
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

        # The --link token differs: dark=#6af light=#0066cc, so shadows should differ.
        assert dark_shadow != light_shadow, (
            f"Expected different shadow colors per theme: dark={dark_shadow!r}, light={light_shadow!r}"
        )


# ---------------------------------------------------------------------------
# Resize: default height, drag to grow, persistence across reload, clamping
# ---------------------------------------------------------------------------
class TestResizeBar:
    def test_desktop_default_is_25vh(self, server, page):  # noqa: F811
        page.set_viewport_size({"width": 1280, "height": 800})
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        h = page.evaluate("getComputedStyle(document.getElementById('expert-player-bar')).height")
        assert h.endswith("px")
        val = float(h[:-2])
        # 25vh of 800 = 200px (+/- rounding)
        assert 199 < val < 201, f"Expected ~200px default, got {h!r}"

    def test_drag_handle_grows_bar(self, server, page):  # noqa: F811
        page.set_viewport_size({"width": 1280, "height": 800})
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        # Simulate a pointer drag of the handle from its current location
        # downward by 240px — 240 / 800 * 100 = 30vh, so new height = 55vh = 440px.
        box = page.evaluate("""
          () => {
            var h = document.getElementById('expert-resize').getBoundingClientRect();
            return { x: h.left + h.width / 2, y: h.top + h.height / 2 };
          }
        """)
        page.mouse.move(box["x"], box["y"])
        page.mouse.down()
        page.mouse.move(box["x"], box["y"] + 240, steps=8)
        page.mouse.up()
        page.wait_for_timeout(50)
        h = page.evaluate("getComputedStyle(document.getElementById('expert-player-bar')).height")
        val = float(h[:-2])
        assert 435 < val < 445, f"Expected ~440px after 30vh drag, got {h!r}"

    def test_drag_is_clamped_to_75vh_max(self, server, page):  # noqa: F811
        page.set_viewport_size({"width": 1280, "height": 800})
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        # Drag way beyond the viewport — should clamp at 75vh = 600px.
        box = page.evaluate("""
          () => {
            var h = document.getElementById('expert-resize').getBoundingClientRect();
            return { x: h.left + h.width / 2, y: h.top + h.height / 2 };
          }
        """)
        page.mouse.move(box["x"], box["y"])
        page.mouse.down()
        page.mouse.move(box["x"], box["y"] + 2000, steps=10)
        page.mouse.up()
        page.wait_for_timeout(50)
        h = page.evaluate("getComputedStyle(document.getElementById('expert-player-bar')).height")
        val = float(h[:-2])
        # 75vh of 800 = 600px
        assert 599 < val < 601, f"Expected clamp to ~600px (75vh), got {h!r}"

    def test_drag_is_clamped_to_25vh_min(self, server, page):  # noqa: F811
        page.set_viewport_size({"width": 1280, "height": 800})
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        box = page.evaluate("""
          () => {
            var h = document.getElementById('expert-resize').getBoundingClientRect();
            return { x: h.left + h.width / 2, y: h.top + h.height / 2 };
          }
        """)
        page.mouse.move(box["x"], box["y"])
        page.mouse.down()
        page.mouse.move(box["x"], box["y"] - 2000, steps=10)
        page.mouse.up()
        page.wait_for_timeout(50)
        h = page.evaluate("getComputedStyle(document.getElementById('expert-player-bar')).height")
        val = float(h[:-2])
        # 25vh of 800 = 200px
        assert 199 < val < 201, f"Expected clamp to ~200px (25vh) min, got {h!r}"

    def test_resize_persists_across_reload(self, server, page):  # noqa: F811
        page.set_viewport_size({"width": 1280, "height": 800})
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        box = page.evaluate("""
          () => {
            var h = document.getElementById('expert-resize').getBoundingClientRect();
            return { x: h.left + h.width / 2, y: h.top + h.height / 2 };
          }
        """)
        page.mouse.move(box["x"], box["y"])
        page.mouse.down()
        page.mouse.move(box["x"], box["y"] + 160, steps=8)  # +20vh -> 45vh = 360px
        page.mouse.up()
        page.wait_for_timeout(50)

        # Persisted JSON must contain barHeightVh ~45
        raw = page.evaluate("localStorage.getItem('sy.expert.2001-01-01_Test-Talk.Test-Video')")
        assert raw is not None
        import json as _json

        saved = _json.loads(raw)
        assert 44 < saved["barHeightVh"] < 46, f"Expected ~45vh, got {saved['barHeightVh']}"

        # Reload and verify height is restored.
        page.reload()
        page.wait_for_selector("#review-grid", timeout=10000)
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        h = page.evaluate("getComputedStyle(document.getElementById('expert-player-bar')).height")
        val = float(h[:-2])
        assert 355 < val < 365, f"Expected ~360px restored, got {h!r}"

    def test_resize_persists_per_video(self, server, page):  # noqa: F811
        """Each video has its own barHeightVh; switching videos does not leak."""
        page.set_viewport_size({"width": 1280, "height": 800})
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        # Grow Test-Video to 55vh
        box = page.evaluate("""
          () => {
            var h = document.getElementById('expert-resize').getBoundingClientRect();
            return { x: h.left + h.width / 2, y: h.top + h.height / 2 };
          }
        """)
        page.mouse.move(box["x"], box["y"])
        page.mouse.down()
        page.mouse.move(box["x"], box["y"] + 240, steps=8)
        page.mouse.up()
        page.wait_for_timeout(50)

        # Switch to Test-Video-2 — should fall back to the default (25vh = 200px).
        page.evaluate("SPA.switchReviewMode('srt', 'Test-Video-2')")
        page.wait_for_selector(".cell.uk", timeout=10000)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        h = page.evaluate("getComputedStyle(document.getElementById('expert-player-bar')).height")
        val = float(h[:-2])
        assert 199 < val < 201, f"Test-Video-2 should default to 200px, got {h!r}"


# ---------------------------------------------------------------------------
# Regression: the mounted player must grow with the bar (not stay at
# intrinsic iframe height). Catches the "#expert-player has no size,
# iframe collapses to 150px" bug.
# ---------------------------------------------------------------------------
class TestPlayerFillsBar:
    def test_mount_fills_bar_height(self, server, page):  # noqa: F811
        page.set_viewport_size({"width": 1280, "height": 800})
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        # Bar default 25vh of 800 = 200px. The mock replacement must fill
        # that — not clamp to some intrinsic fallback.
        dims = page.evaluate("""
          () => {
            var m = document.getElementById('mock-player').getBoundingClientRect();
            var bar = document.getElementById('expert-player-bar').getBoundingClientRect();
            return { mH: m.height, mW: m.width, barH: bar.height, barW: bar.width };
          }
        """)
        # Mock should be at least ~180px tall (bar minus handle 8px, minus
        # rounding). If #expert-player has no size, mock falls back to its
        # 40px min-height and this test fails.
        assert dims["mH"] > 180, f"Mock player too small: {dims!r}"
        assert abs(dims["mW"] - dims["barW"]) < 2, f"Mock width must match bar: {dims!r}"

    def test_mount_grows_when_bar_is_dragged(self, server, page):  # noqa: F811
        page.set_viewport_size({"width": 1280, "height": 800})
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        before = page.evaluate("document.getElementById('mock-player').getBoundingClientRect().height")
        # Drag the handle down 240px → +30vh → 55vh bar = 440px.
        box = page.evaluate("""
          () => {
            var h = document.getElementById('expert-resize').getBoundingClientRect();
            return { x: h.left + h.width / 2, y: h.top + h.height / 2 };
          }
        """)
        page.mouse.move(box["x"], box["y"])
        page.mouse.down()
        page.mouse.move(box["x"], box["y"] + 240, steps=8)
        page.mouse.up()
        page.wait_for_timeout(50)
        after = page.evaluate("document.getElementById('mock-player').getBoundingClientRect().height")
        # Mock should grow with the bar. Expected roughly +240px; allow slack.
        assert after - before > 200, f"Player did not grow with bar drag: before={before}, after={after}"
