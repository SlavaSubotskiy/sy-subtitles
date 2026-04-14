# Expert Mode: Edit Subtitles While Watching Video — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an "expert" editing mode to `view-review` that displays a sticky Vimeo player above the existing grid, with bidirectional sync — playback highlights and auto-scrolls to the current row, and clicking a row seeks playback.

**Architecture:** A single new JS module `ExpertPlayer` co-located inside `site/index.html`. It mounts a sticky bar with a Vimeo iframe, subscribes to the Vimeo SDK's `timeupdate` event, binary-searches `reviewState.alignedRows` to map playhead to current row, and manages show/hide/follow state with `localStorage` persistence per `{talkId, videoSlug}`. Integrates with the existing `SPA.switchReviewMode` hook; visible only in SRT source mode.

**Tech Stack:** Vanilla JS (no framework), existing Vimeo Player SDK (already loaded in `<head>`), CSS variables from the existing dark/light theme, Python pytest + `playwright.sync_api` for E2E, existing `tests/fixtures/mock_vimeo_player.js` stub (already exposes `_setTime(seconds)` timeupdate driver).

**Spec:** `docs/superpowers/specs/2026-04-13-expert-edit-with-video-design.md`

---

## File Structure

**Modified:**
- `site/index.html` — all code (DOM, CSS, JS, i18n) added in-place. Single-file SPA by existing convention.

**Created:**
- `tests/test_expert_player.py` — new Playwright E2E + inline binary-search unit test, following `tests/test_preview_spa.py` patterns.

**Potentially extended:**
- `tests/fixtures/mock_vimeo_player.js` — only if we discover the existing stub misses a method ExpertPlayer needs. Already has: `play`, `pause`, `getPaused`, `getCurrentTime`, `setCurrentTime`, `on`, `_setTime(seconds)` → fires `timeupdate`. This should be sufficient.

All work happens on a feature branch (e.g. `feature/expert-edit-player`). The first task creates the branch and the test scaffold so subsequent tasks have somewhere to land TDD.

---

## Task 1: Branch + test scaffold

**Files:**
- Create: `tests/test_expert_player.py`
- Read for reference: `tests/test_preview_spa.py:90-220` (fixtures), `tests/test_preview_spa.py:774-870` (review view tests)

- [ ] **Step 1.1: Create feature branch**

```bash
git checkout -b feature/expert-edit-player
```

- [ ] **Step 1.2: Create test file with shared fixtures reused from test_preview_spa**

Write `tests/test_expert_player.py`:

```python
"""E2E tests for Expert Mode (edit subtitles while watching video).

Re-uses the server/mock_player_js/browser/page fixtures from
test_preview_spa via direct import. Runs standalone with
``pytest tests/test_expert_player.py``.
"""

from __future__ import annotations

import pytest

from tests.test_preview_spa import (  # noqa: F401  — re-exported fixtures
    SPA_URL,
    browser,
    goto_spa,
    mock_player_js,
    page,
    server,
)


def _goto_review_srt(page, server):
    """Navigate to review view and switch to SRT source."""
    goto_spa(page, server, "#/review/2001-01-01_Test-Talk")
    page.wait_for_selector("#review-grid", timeout=10000)
    page.select_option("#review-mode-select", "srt:Test-Video")
    page.wait_for_selector(".cell.uk", timeout=10000)


class TestExpertButtonVisibility:
    def test_button_hidden_in_transcript_mode(self, server, page):
        goto_spa(page, server, "#/review/2001-01-01_Test-Talk")
        page.wait_for_selector("#review-grid", timeout=10000)
        assert not page.locator("#btn-expert-player").is_visible()

    def test_button_visible_in_srt_mode(self, server, page):
        _goto_review_srt(page, server)
        assert page.locator("#btn-expert-player").is_visible()
```

- [ ] **Step 1.3: Run the new test to verify it fails**

Run: `pytest tests/test_expert_player.py -v`

Expected: two tests collected. `test_button_hidden_in_transcript_mode` may PASS accidentally (element doesn't exist → `is_visible()` is False). `test_button_visible_in_srt_mode` must FAIL.

- [ ] **Step 1.4: Commit the failing test**

```bash
git add tests/test_expert_player.py
git commit -m "test: scaffold expert player E2E test file"
```

---

## Task 2: Add i18n keys, new DOM, new CSS (skeleton, no behavior)

**Files:**
- Modify: `site/index.html` (CSS block around line 283, review-view header around line 347, translations around lines 601 and 686)

- [ ] **Step 2.1: Add i18n keys to the UK translations block**

Find the UK translations block (around line 601, `'btn.revert_all': ...`) and append after the existing button keys:

```js
    'btn.show_video': '\u25B6 \u041F\u043E\u043A\u0430\u0437\u0430\u0442\u0438 \u0432\u0456\u0434\u0435\u043E',
    'btn.hide_video': '\u2715 \u0421\u0445\u043E\u0432\u0430\u0442\u0438 \u0432\u0456\u0434\u0435\u043E',
    'btn.follow': '\u21C5 \u0421\u043B\u0456\u0434\u0443\u0432\u0430\u0442\u0438',
    'title.show_video': '\u0412\u0456\u0434\u043A\u0440\u0438\u0442\u0438 \u043F\u043B\u0435\u0454\u0440 \u0434\u043B\u044F \u0441\u0438\u043D\u0445\u0440\u043E\u043D\u0456\u0437\u043E\u0432\u0430\u043D\u043E\u0433\u043E \u0440\u0435\u0434\u0430\u0433\u0443\u0432\u0430\u043D\u043D\u044F',
    'title.follow': '\u0410\u0432\u0442\u043E\u043C\u0430\u0442\u0438\u0447\u043D\u043E \u043F\u0440\u043E\u043A\u0440\u0443\u0447\u0443\u0432\u0430\u0442\u0438 \u0434\u043E \u043F\u043E\u0442\u043E\u0447\u043D\u043E\u0433\u043E \u0440\u044F\u0434\u043A\u0430',
    'title.expert_seek': '\u041A\u043B\u0456\u043A \u043F\u043E \u0442\u0430\u0439\u043C\u043A\u043E\u0434\u0443 \u0430\u0431\u043E \u0430\u043D\u0433\u043B. \u0440\u044F\u0434\u043A\u0443 \u2014 \u043F\u0435\u0440\u0435\u043C\u043E\u0442\u0430\u0442\u0438 \u0432\u0456\u0434\u0435\u043E',
    'toast.vimeo_unavailable': '\u041F\u043B\u0435\u0454\u0440 Vimeo \u043D\u0435\u0434\u043E\u0441\u0442\u0443\u043F\u043D\u0438\u0439',
```

(Match the existing `\u` escape style used elsewhere in the UK block.)

- [ ] **Step 2.2: Add mirrored EN translations**

Find the EN block (around line 686, starts with `'btn.mark': '\u{1F4CC} Mark'`) and append after the existing button keys:

```js
    'btn.show_video': '\u25B6 Show video',
    'btn.hide_video': '\u2715 Hide video',
    'btn.follow': '\u21C5 Follow',
    'title.show_video': 'Open player for synced editing',
    'title.follow': 'Auto-scroll to current row',
    'title.expert_seek': 'Click timecode or English row to seek',
    'toast.vimeo_unavailable': 'Vimeo player unavailable',
```

- [ ] **Step 2.3: Add the `Show video` button inside `view-review` header-actions**

Find:
```html
      <button onclick="SPA.revertAllEdits()" id="btn-revert-all" style="display:none" data-i18n="btn.revert_all">Revert all</button>
```

Insert ABOVE that line:
```html
      <button id="btn-expert-player" class="chip" style="display:none"
              onclick="ExpertPlayer.toggle()"
              data-i18n-title="title.show_video"
              data-i18n="btn.show_video">&#x25B6; Show video</button>
```

- [ ] **Step 2.4: Add the sticky player bar DOM between `.header` and `#review-grid`**

Find `<div id="review-status" class="status" data-i18n="review.loading">` inside `view-review`. Insert ABOVE that line:

```html
  <div id="expert-player-bar" class="expert-bar" hidden>
    <div class="expert-video-wrap">
      <div id="expert-player"></div>
    </div>
    <div class="expert-controls">
      <span id="expert-time">00:00:00</span>
      <button id="btn-follow" class="chip"
              onclick="ExpertPlayer.toggleFollow()"
              data-i18n-title="title.follow"
              data-i18n="btn.follow">&#x21C5; Follow</button>
      <button class="chip" onclick="ExpertPlayer.hide()" aria-label="Close video">&#x2715;</button>
    </div>
  </div>
```

- [ ] **Step 2.5: Add the new CSS block**

Find the existing `/* --- Fullscreen preview mode --- */` comment (around line 272). Insert ABOVE it:

```css
/* --- Expert player (sticky, view-review only) --- */
.expert-bar {
  position: sticky; top: 0; z-index: 20;
  background: var(--bg2); border-bottom: 1px solid var(--border);
  max-height: 25vh;
}
.expert-video-wrap {
  aspect-ratio: 4/3;
  max-height: 25vh;
  background: #000;
  margin: 0 auto;
}
.expert-video-wrap iframe { width: 100%; height: 100%; border: 0; }
.expert-controls {
  position: absolute; top: 6px; right: 8px;
  display: flex; gap: 6px; align-items: center;
  font-family: monospace; font-size: 12px; color: var(--fg5);
}
.expert-bar[hidden] { display: none; }
.cell.uk.current { box-shadow: inset 3px 0 0 var(--link); }
#view-review.expert-mode .cell.en,
#view-review.expert-mode .cell-label { cursor: pointer; }
#view-review.expert-mode .cell.en:hover { background: var(--cell-hover); }
#btn-follow.paused { opacity: 0.5; }

@media (max-width: 768px) {
  .expert-video-wrap { max-height: 22vh; }
  .expert-bar { max-height: 22vh; }
}
```

- [ ] **Step 2.6: Run existing tests to ensure no regression**

Run: `pytest tests/test_preview_spa.py -x -q`

Expected: all existing tests still pass. The new `onclick` handlers reference `ExpertPlayer` which doesn't exist yet, but they won't fire (button has `display:none`), so no JS error.

- [ ] **Step 2.7: Commit the skeleton**

```bash
git add site/index.html
git commit -m "feat(expert): add DOM skeleton, CSS, and i18n for expert player"
```

---

## Task 3: Wire `data-ms-start` in `renderReviewSrt`

**Files:**
- Modify: `site/index.html:1870-1942` (`renderReviewSrt` function)

- [ ] **Step 3.1: Write the failing test**

Append to `tests/test_expert_player.py`:

```python
class TestCellDataMsStart:
    def test_srt_cells_have_data_ms_start(self, server, page):
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
```

- [ ] **Step 3.2: Run the test, confirm it fails**

Run: `pytest tests/test_expert_player.py::TestCellDataMsStart -v`

Expected: FAIL — `withAttr == 0`.

- [ ] **Step 3.3: Implement**

In `renderReviewSrt` (site/index.html around line 1870), find the EN cell creation block:

```js
      var leftDiv = document.createElement('div');
      leftDiv.className = 'cell en';
      if (enSpan > 1) leftDiv.style.gridRow = 'span ' + enSpan;
      leftDiv.innerHTML = cellLabel(enTc).html + esc(row.en.text);
      grid.appendChild(leftDiv);
```

Add one line after `leftDiv.className = 'cell en';`:

```js
      leftDiv.dataset.msStart = row.en.startMs;
```

Repeat for the `else if (!enKey)` placeholder branch — use `row.uk.startMs` as fallback so seek still works on placeholder cells:

```js
      leftDiv.dataset.msStart = row.uk ? row.uk.startMs : 0;
```

For the UK cell creation block, right after `rightDiv.className = 'cell uk' + ...`, add:

```js
      rightDiv.dataset.msStart = row.uk.startMs;
```

And in its `else if (!ukKey)` placeholder:

```js
      rightDiv.dataset.msStart = row.en ? row.en.startMs : 0;
```

- [ ] **Step 3.4: Run test, confirm PASS**

Run: `pytest tests/test_expert_player.py::TestCellDataMsStart -v`

Expected: PASS.

- [ ] **Step 3.5: Commit**

```bash
git add site/index.html tests/test_expert_player.py
git commit -m "feat(expert): expose data-ms-start on review cells"
```

---

## Task 4: `ExpertPlayer` module skeleton + visibility hook

**Files:**
- Modify: `site/index.html` — add new IIFE before the existing `SPA` declaration; modify `SPA.switchReviewMode` (~line 1675); add route-leave hook.

- [ ] **Step 4.1: Write the failing test for SRT-mode visibility**

Append to `tests/test_expert_player.py`:

```python
class TestButtonVisibilityTransitions:
    def test_button_hides_when_switching_from_srt_to_transcript(self, server, page):
        _goto_review_srt(page, server)
        assert page.locator("#btn-expert-player").is_visible()
        page.select_option("#review-mode-select", "transcript")
        page.wait_for_timeout(200)
        assert not page.locator("#btn-expert-player").is_visible()
```

- [ ] **Step 4.2: Run, confirm failure**

Run: `pytest tests/test_expert_player.py::TestButtonVisibilityTransitions -v`

Expected: FAIL — button always hidden (no code to show it yet).

- [ ] **Step 4.3: Add the `ExpertPlayer` module skeleton**

Find the first occurrence of `var SPA = ` or `SPA = SPA || {};` in `site/index.html`. Insert ABOVE it:

```js
/* ============================================================
 * ExpertPlayer — sticky Vimeo player + bidirectional sync with
 * the review grid. Active only in view-review + SRT source mode.
 * Spec: docs/superpowers/specs/2026-04-13-expert-edit-with-video-design.md
 * ============================================================ */
var ExpertPlayer = (function() {
  var state = null;
  var btnExpert = null;
  var btnFollow = null;
  var bar = null;
  var mount = null;
  var timeEl = null;
  var persistTimer = null;

  function freshState(talkId, videoSlug) {
    return {
      open: false, follow: true, followPaused: false,
      lastTime: 0, currentIdx: null,
      player: null, isAutoScrolling: false,
      talkId: talkId, videoSlug: videoSlug,
    };
  }

  function storageKey(talkId, videoSlug) {
    return 'sy.expert.' + talkId + '.' + videoSlug;
  }

  function loadPersisted(talkId, videoSlug) {
    try {
      var raw = localStorage.getItem(storageKey(talkId, videoSlug));
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  }

  function persistNow() {
    if (!state) return;
    try {
      localStorage.setItem(storageKey(state.talkId, state.videoSlug), JSON.stringify({
        open: state.open, follow: state.follow, lastTime: state.lastTime,
      }));
    } catch (e) { /* quota / private mode — ignore */ }
  }

  function throttledPersist() {
    if (persistTimer) return;
    persistTimer = setTimeout(function() { persistTimer = null; persistNow(); }, 1000);
  }

  function cacheDom() {
    btnExpert = document.getElementById('btn-expert-player');
    btnFollow = document.getElementById('btn-follow');
    bar       = document.getElementById('expert-player-bar');
    mount     = document.getElementById('expert-player');
    timeEl    = document.getElementById('expert-time');
  }

  function clearMount() {
    if (!mount) return;
    while (mount.firstChild) mount.removeChild(mount.firstChild);
  }

  function init(talkId, videoSlug) {
    cacheDom();
    state = freshState(talkId, videoSlug);
    var saved = loadPersisted(talkId, videoSlug);
    if (saved) {
      state.follow = saved.follow !== false;
      state.lastTime = saved.lastTime || 0;
    }
    if (btnExpert) btnExpert.style.display = '';
    var view = document.getElementById('view-review');
    if (view) view.classList.add('expert-mode');
    if (saved && saved.open) setTimeout(show, 0);  // Task 10 uses this guard
  }

  function destroy() {
    if (!state) return;
    hide();
    clearMount();
    state = null;
    if (btnExpert) btnExpert.style.display = 'none';
    var view = document.getElementById('view-review');
    if (view) view.classList.remove('expert-mode');
  }

  function toggle() { if (!state) return; state.open ? hide() : show(); }

  function show() {
    if (!state) return;
    // Mount Vimeo in Task 5 — Task 4 only reveals the bar.
    if (bar) bar.removeAttribute('hidden');
    state.open = true;
    persistNow();
  }

  function hide() {
    if (!state) return;
    if (bar) bar.setAttribute('hidden', '');
    state.open = false;
    persistNow();
  }

  function toggleFollow() {
    if (!state) return;
    state.followPaused = !state.followPaused;
    if (btnFollow) btnFollow.classList.toggle('paused', state.followPaused);
  }

  return {
    init: init, destroy: destroy, toggle: toggle,
    show: show, hide: hide, toggleFollow: toggleFollow,
  };
})();
```

- [ ] **Step 4.4: Hook into `SPA.switchReviewMode`**

Find `SPA.switchReviewMode = function(mode, videoSlug) {` (around site/index.html:1675). At the END of the function body, before the closing `};`, add:

```js
  // Expert player hook — always destroy first (no-op if not initialized),
  // then re-init if we landed in SRT source mode.
  ExpertPlayer.destroy();
  if (mode === 'srt') {
    ExpertPlayer.init(reviewState.talkId, videoSlug);
  }
```

If the variable holding the talk id is named differently in that scope (e.g. `reviewState.talk.id` or a local), use that name instead.

- [ ] **Step 4.5: Hook route-leave destroy**

Find the router — search for `hashchange` or `function route` or wherever `document.getElementById('view-review').classList.add('active')` is matched by a transition elsewhere. Add:

```js
window.addEventListener('hashchange', function() {
  if (!/^#\/review\//.test(location.hash)) {
    ExpertPlayer.destroy();
  }
});
```

Place it after `ExpertPlayer` IIFE so the function exists when the listener is registered. Alternatively, if the router has an explicit "leaving view-review" branch, call `ExpertPlayer.destroy()` there instead and skip the hashchange listener.

- [ ] **Step 4.6: Run visibility tests**

Run: `pytest tests/test_expert_player.py::TestExpertButtonVisibility tests/test_expert_player.py::TestButtonVisibilityTransitions -v`

Expected: all PASS.

- [ ] **Step 4.7: Commit**

```bash
git add site/index.html tests/test_expert_player.py
git commit -m "feat(expert): ExpertPlayer module skeleton + SRT-mode visibility"
```

---

## Task 5: Mount Vimeo player on `show()`

**Files:**
- Modify: `site/index.html` — expand `show()`, add `mountPlayer`, `extractVimeoId`.

- [ ] **Step 5.1: Write the failing test**

Append to `tests/test_expert_player.py`:

```python
class TestPlayerMount:
    def test_clicking_show_mounts_vimeo_iframe(self, server, page):
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        assert page.locator("#expert-player-bar").is_visible()

    def test_clicking_toggle_twice_does_not_duplicate(self, server, page):
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        page.click("#btn-expert-player")  # hide
        page.click("#btn-expert-player")  # show again
        assert page.locator("#mock-player").count() == 1
```

- [ ] **Step 5.2: Run, confirm failure**

Run: `pytest tests/test_expert_player.py::TestPlayerMount -v`

Expected: FAIL — `show()` only reveals the bar, doesn't mount.

- [ ] **Step 5.3: Implement `mountPlayer` + defensive guards**

Inside the `ExpertPlayer` IIFE, replace the placeholder `show()`:

```js
  function show() {
    if (!state) return;
    if (!window.Vimeo) {
      if (typeof SPA !== 'undefined' && SPA.toast) SPA.toast(t('toast.vimeo_unavailable'));
      return;
    }
    if (!state.player) mountPlayer();
    if (bar) bar.removeAttribute('hidden');
    state.open = true;
    persistNow();
  }

  function extractVimeoId(url) {
    // Matches https://vimeo.com/12345/abc OR https://player.vimeo.com/video/12345?h=abc
    var m = (url || '').match(/vimeo\.com\/(?:video\/)?(\d+)/);
    return m ? m[1] : null;
  }

  function mountPlayer() {
    var videos = (reviewState && reviewState.videos) || [];
    var video = videos.find(function(v) { return v.slug === state.videoSlug; });
    if (!video || !video.vimeo_url) return;
    var vimeoId = extractVimeoId(video.vimeo_url);
    if (!vimeoId) return;

    clearMount();
    var iframe = document.createElement('iframe');
    iframe.allow = 'autoplay; fullscreen';
    iframe.setAttribute('allowfullscreen', '');
    iframe.src = 'https://player.vimeo.com/video/' + vimeoId;
    mount.appendChild(iframe);

    try {
      state.player = new Vimeo.Player(iframe);
      if (state.lastTime > 0) state.player.setCurrentTime(state.lastTime / 1000);
    } catch (e) {
      console.warn('[ExpertPlayer] Vimeo init error:', e);
      state.player = null;
    }
  }
```

If `reviewState.videos` is not the correct accessor for the current talk's videos list, check `SPA.switchReviewMode` or nearby code for the right variable name and substitute it. The mock serves `SAMPLE_META` with two videos; `video.vimeo_url` is `https://vimeo.com/12345/abc`.

- [ ] **Step 5.4: Run tests**

Run: `pytest tests/test_expert_player.py::TestPlayerMount -v`

Expected: both PASS. The mock's `Vimeo.Player` constructor replaces the iframe with `#mock-player`.

- [ ] **Step 5.5: Commit**

```bash
git add site/index.html tests/test_expert_player.py
git commit -m "feat(expert): mount Vimeo player on show"
```

---

## Task 6: Binary search + highlight current row on timeupdate

**Files:**
- Modify: `site/index.html` — add `binarySearchByMs`, `highlightRow`, `onTimeUpdate`, `scrollRowIntoView`, `formatTime`; wire `onTimeUpdate` in `mountPlayer`.

- [ ] **Step 6.1: Write the failing binary-search unit test**

Append:

```python
class TestBinarySearch:
    def test_binary_search_cases(self, server, page):
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
            "before":  -1,
            "atFirst": 0,
            "between": 1,
            "atExact": 2,
            "past":    3,
            "empty":   -1,
        }
```

- [ ] **Step 6.2: Run, confirm failure**

Run: `pytest tests/test_expert_player.py::TestBinarySearch -v`

Expected: FAIL — `_binarySearchByMs` undefined.

- [ ] **Step 6.3: Implement and expose**

Add inside the IIFE:

```js
  function binarySearchByMs(rows, ms) {
    // Returns the largest idx with rows[idx].uk.startMs <= ms.
    // Returns -1 for empty array or ms before first row.
    if (!rows || rows.length === 0) return -1;
    if (ms < rows[0].uk.startMs) return -1;
    var lo = 0, hi = rows.length - 1, ans = -1;
    while (lo <= hi) {
      var mid = (lo + hi) >> 1;
      if (rows[mid].uk.startMs <= ms) { ans = mid; lo = mid + 1; }
      else hi = mid - 1;
    }
    return ans;
  }
```

Update the IIFE's `return` to expose it:

```js
  return {
    init: init, destroy: destroy, toggle: toggle,
    show: show, hide: hide, toggleFollow: toggleFollow,
    _binarySearchByMs: binarySearchByMs,  // test hook
  };
```

- [ ] **Step 6.4: Run binary-search test, confirm PASS**

Run: `pytest tests/test_expert_player.py::TestBinarySearch -v`

Expected: PASS.

- [ ] **Step 6.5: Write the failing highlight test**

Append:

```python
class TestHighlight:
    def test_timeupdate_highlights_current_row(self, server, page):
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # SAMPLE_SRT row 2 starts at 6000 ms; set player to 6s.
        page.evaluate("window._vimeoPlayer._setTime(6)")
        page.wait_for_timeout(50)

        highlighted = page.evaluate("""
          () => Array.from(
            document.querySelectorAll('.cell.uk.current')
          ).map(c => c.dataset.msStart)
        """)
        assert highlighted == ["6000"]
```

- [ ] **Step 6.6: Run, confirm failure**

Run: `pytest tests/test_expert_player.py::TestHighlight -v`

Expected: FAIL — no `.current` applied.

- [ ] **Step 6.7: Implement `onTimeUpdate`, `highlightRow`, `scrollRowIntoView`, `formatTime`**

Inside the IIFE:

```js
  function onTimeUpdate(data) {
    if (!state) return;
    state.lastTime = Math.round((data && data.seconds || 0) * 1000);
    if (timeEl) timeEl.textContent = formatTime(state.lastTime);
    var rows = (reviewState && reviewState.alignedRows) || [];
    var idx = binarySearchByMs(rows, state.lastTime);
    if (idx !== state.currentIdx) highlightRow(idx);
    throttledPersist();
  }

  function highlightRow(idx) {
    var prev = document.querySelector('#review-grid .cell.uk.current');
    if (prev) prev.classList.remove('current');
    state.currentIdx = idx;
    if (idx < 0) return;
    var rows = (reviewState && reviewState.alignedRows) || [];
    var row = rows[idx];
    if (!row || !row.uk) return;
    var target = document.querySelector(
      '#review-grid .cell.uk[data-ms-start="' + row.uk.startMs + '"]'
    );
    if (target) {
      target.classList.add('current');
      if (state.follow && !state.followPaused) scrollRowIntoView(target);
    }
  }

  function scrollRowIntoView(el) {
    state.isAutoScrolling = true;
    try { el.scrollIntoView({ block: 'center', behavior: 'smooth' }); }
    catch (e) { el.scrollIntoView(); }
    setTimeout(function() { state.isAutoScrolling = false; }, 500);
  }

  function formatTime(ms) {
    var s = Math.floor(ms / 1000);
    var h = Math.floor(s / 3600);
    var m = Math.floor((s % 3600) / 60);
    var sec = s % 60;
    function pad(n) { return n < 10 ? '0' + n : '' + n; }
    return pad(h) + ':' + pad(m) + ':' + pad(sec);
  }
```

Wire the event in `mountPlayer`, right after `state.player = new Vimeo.Player(iframe);`:

```js
      state.player.on('timeupdate', onTimeUpdate);
```

- [ ] **Step 6.8: Run highlight test, confirm PASS**

Run: `pytest tests/test_expert_player.py::TestHighlight -v`

Expected: PASS.

- [ ] **Step 6.9: Commit**

```bash
git add site/index.html tests/test_expert_player.py
git commit -m "feat(expert): binary search + highlight current row on timeupdate"
```

---

## Task 7: Click-to-seek on `.cell-label` and `.cell.en`

**Files:**
- Modify: `site/index.html` — delegated click handler, `seekTo`, attach/detach in init/destroy.

- [ ] **Step 7.1: Write failing tests**

Append:

```python
class TestClickToSeek:
    def test_click_en_cell_seeks_player(self, server, page):
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        # SAMPLE_EN_SRT row 2 starts at 4500 ms.
        page.evaluate("""
          () => {
            var cells = document.querySelectorAll('#review-grid .cell.en');
            cells[1].click();
          }
        """)
        current = page.evaluate("window._vimeoPlayer._currentTime")
        assert abs(current - 4.5) < 0.01

    def test_click_cell_label_seeks_player(self, server, page):
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

    def test_click_uk_text_does_not_seek(self, server, page):
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        before = page.evaluate("window._vimeoPlayer._currentTime")
        page.evaluate("""
          () => document.querySelector('#review-grid .cell.uk .cell-text').click()
        """)
        after = page.evaluate("window._vimeoPlayer._currentTime")
        assert before == after
```

- [ ] **Step 7.2: Run, confirm failures**

Run: `pytest tests/test_expert_player.py::TestClickToSeek -v`

Expected: first two FAIL, third PASSes by accident (no seek wiring → no change).

- [ ] **Step 7.3: Implement**

Inside the IIFE:

```js
  var gridClickHandler = null;

  function onGridClick(e) {
    if (!state || !state.player) return;
    if (e.target.closest('.cell-text')) return;  // editing area
    var isLabel = !!e.target.closest('.cell-label');
    var cell = e.target.closest('.cell');
    if (!cell) return;
    if (!isLabel && !cell.classList.contains('en')) return;
    var ms = Number(cell.dataset.msStart);
    if (Number.isNaN(ms)) return;
    seekTo(ms);
  }

  function seekTo(ms) {
    if (!state || !state.player) return;
    try { state.player.setCurrentTime(ms / 1000); } catch (_) {}
    state.followPaused = false;
    if (btnFollow) btnFollow.classList.remove('paused');
  }
```

In `init()`, after caching DOM:

```js
    var grid = document.getElementById('review-grid');
    if (grid) {
      gridClickHandler = onGridClick;
      grid.addEventListener('click', gridClickHandler);
    }
```

In `destroy()`:

```js
    var grid = document.getElementById('review-grid');
    if (grid && gridClickHandler) grid.removeEventListener('click', gridClickHandler);
    gridClickHandler = null;
```

- [ ] **Step 7.4: Run tests**

Run: `pytest tests/test_expert_player.py::TestClickToSeek -v`

Expected: all three PASS.

- [ ] **Step 7.5: Commit**

```bash
git add site/index.html tests/test_expert_player.py
git commit -m "feat(expert): click-to-seek on cell label and EN cells"
```

---

## Task 8: Follow-mode smart pause (focus + manual scroll)

**Files:**
- Modify: `site/index.html` — focusin listener, window scroll listener, toggleFollow resume logic.

- [ ] **Step 8.1: Write failing tests**

Append:

```python
class TestFollowSmartPause:
    def test_focus_cell_pauses_follow_and_player(self, server, page):
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        page.evaluate("window._vimeoPlayer.play()")

        page.evaluate("""
          () => document.querySelector('#review-grid .cell-text').focus()
        """)
        page.wait_for_timeout(50)

        paused = page.evaluate("window._vimeoPlayer._paused")
        btn_state = page.evaluate(
            "document.getElementById('btn-follow').classList.contains('paused')"
        )
        assert paused is True
        assert btn_state is True

    def test_toggle_follow_button_resumes(self, server, page):
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        page.evaluate("""
          () => document.querySelector('#review-grid .cell-text').focus()
        """)
        page.wait_for_timeout(50)
        assert page.evaluate(
            "document.getElementById('btn-follow').classList.contains('paused')"
        )
        page.click("#btn-follow")
        assert not page.evaluate(
            "document.getElementById('btn-follow').classList.contains('paused')"
        )
```

- [ ] **Step 8.2: Run, confirm failures**

Run: `pytest tests/test_expert_player.py::TestFollowSmartPause -v`

Expected: both FAIL.

- [ ] **Step 8.3: Implement focus and scroll listeners**

Inside the IIFE:

```js
  function onGridFocusIn(e) {
    if (!state) return;
    if (!e.target.matches || !e.target.matches('.cell-text')) return;
    state.followPaused = true;
    if (btnFollow) btnFollow.classList.add('paused');
    if (state.player) { try { state.player.pause(); } catch (_) {} }
  }

  function onWindowScroll() {
    if (!state || !state.open) return;
    if (state.isAutoScrolling || state.followPaused) return;
    state.followPaused = true;
    if (btnFollow) btnFollow.classList.add('paused');
  }
```

In `init()`, alongside the click listener:

```js
    if (grid) grid.addEventListener('focusin', onGridFocusIn);
    window.addEventListener('scroll', onWindowScroll, { passive: true });
```

In `destroy()`:

```js
    if (grid) grid.removeEventListener('focusin', onGridFocusIn);
    window.removeEventListener('scroll', onWindowScroll);
```

Replace the placeholder `toggleFollow` with the resume-aware version:

```js
  function toggleFollow() {
    if (!state) return;
    state.followPaused = !state.followPaused;
    if (btnFollow) btnFollow.classList.toggle('paused', state.followPaused);
    if (!state.followPaused && state.currentIdx != null && state.currentIdx >= 0) {
      var rows = (reviewState && reviewState.alignedRows) || [];
      var row = rows[state.currentIdx];
      if (row && row.uk) {
        var target = document.querySelector(
          '#review-grid .cell.uk[data-ms-start="' + row.uk.startMs + '"]'
        );
        if (target) scrollRowIntoView(target);
      }
    }
  }
```

- [ ] **Step 8.4: Run tests**

Run: `pytest tests/test_expert_player.py::TestFollowSmartPause -v`

Expected: both PASS.

- [ ] **Step 8.5: Commit**

```bash
git add site/index.html tests/test_expert_player.py
git commit -m "feat(expert): smart-pause Follow on focus and manual scroll"
```

---

## Task 9: Enter-to-commit and global keyboard shortcuts

**Files:**
- Modify: `site/index.html` — grid keydown + global keydown.

- [ ] **Step 9.1: Write failing tests**

Append:

```python
class TestEnterAndShortcuts:
    def test_enter_in_cell_blurs_and_plays(self, server, page):
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

        assert page.evaluate(
            "document.activeElement.classList.contains('cell-text')"
        ) is False
        assert page.evaluate("window._vimeoPlayer._paused") is False

    def test_space_toggles_play_pause(self, server, page):
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

    def test_escape_closes_player(self, server, page):
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        page.evaluate("document.body.focus()")
        page.keyboard.press("Escape")
        page.wait_for_timeout(50)
        assert (
            page.locator("#expert-player-bar").get_attribute("hidden") is not None
        )

    def test_arrow_left_seeks_minus_five(self, server, page):
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        page.evaluate("window._vimeoPlayer._setTime(20)")
        page.wait_for_timeout(50)
        page.evaluate("document.body.focus()")
        page.keyboard.press("ArrowLeft")
        page.wait_for_timeout(50)
        assert abs(page.evaluate("window._vimeoPlayer._currentTime") - 15) < 0.01
```

- [ ] **Step 9.2: Run, confirm failures**

Run: `pytest tests/test_expert_player.py::TestEnterAndShortcuts -v`

Expected: all four FAIL.

- [ ] **Step 9.3: Implement**

Inside the IIFE:

```js
  function onGridKeydown(e) {
    if (!state) return;
    if (e.key !== 'Enter') return;
    if (e.isComposing || e.keyCode === 229) return;  // IME commit
    if (!e.target.matches || !e.target.matches('.cell-text')) return;
    e.preventDefault();
    e.target.blur();
    state.followPaused = false;
    if (btnFollow) btnFollow.classList.remove('paused');
    if (state.player) { try { state.player.play(); } catch (_) {} }
  }

  function onGlobalKeydown(e) {
    if (!state || !state.open) return;
    var ae = document.activeElement;
    if (ae && ae.matches && ae.matches('.cell-text')) return;  // editing — let keys pass
    switch (e.key) {
      case ' ':
      case 'k':
        e.preventDefault();
        togglePlayPause();
        break;
      case 'ArrowLeft':
      case 'j':
        e.preventDefault();
        seekTo(Math.max(0, state.lastTime - 5000));
        break;
      case 'ArrowRight':
      case 'l':
        e.preventDefault();
        seekTo(state.lastTime + 5000);
        break;
      case 'Escape':
        e.preventDefault();
        hide();
        break;
    }
  }

  function togglePlayPause() {
    if (!state || !state.player) return;
    state.player.getPaused().then(function(paused) {
      if (paused) state.player.play(); else state.player.pause();
    });
  }
```

Attach in `init()`:

```js
    if (grid) grid.addEventListener('keydown', onGridKeydown);
    document.addEventListener('keydown', onGlobalKeydown);
```

Detach in `destroy()`:

```js
    if (grid) grid.removeEventListener('keydown', onGridKeydown);
    document.removeEventListener('keydown', onGlobalKeydown);
```

- [ ] **Step 9.4: Run tests**

Run: `pytest tests/test_expert_player.py::TestEnterAndShortcuts -v`

Expected: all four PASS.

- [ ] **Step 9.5: Commit**

```bash
git add site/index.html tests/test_expert_player.py
git commit -m "feat(expert): Enter-commit + Space/JKL/arrows/Esc shortcuts"
```

---

## Task 10: Persistence across reload

**Files:**
- Modify: `site/index.html` — verify restore path works end-to-end. (Skeleton from Task 4 already writes/reads; this task just proves it under real conditions.)

- [ ] **Step 10.1: Write the failing test**

Append:

```python
class TestPersistence:
    def test_open_state_survives_reload(self, server, page):
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        page.evaluate("window._vimeoPlayer._setTime(7)")
        page.wait_for_timeout(1100)  # allow throttled persist (1s)

        page.reload()
        page.wait_for_selector("#review-grid", timeout=10000)
        page.select_option("#review-mode-select", "srt:Test-Video")
        page.wait_for_selector(".cell.uk", timeout=10000)

        page.wait_for_selector("#expert-player-bar:not([hidden])", timeout=3000)
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)
        current = page.evaluate("window._vimeoPlayer._currentTime")
        assert abs(current - 7) < 0.1
```

- [ ] **Step 10.2: Run, confirm failure**

Run: `pytest tests/test_expert_player.py::TestPersistence -v`

Expected: FAIL if the existing page fixture clears `sy.expert.*` or if the throttled persist didn't fire or if `init()` auto-show runs before `reviewState.videos` is populated.

- [ ] **Step 10.3: Diagnose and fix**

Check in order:

1. **Does the page fixture wipe expert state on reload?** Look at `tests/test_preview_spa.py` `page` fixture — it only clears `sy_tree_cache__main`. Good.
2. **Did the throttled persist fire?** Add a temporary `console.log` in `persistNow` or inspect `localStorage` between `_setTime(7)` and `reload()`:
   `page.wait_for_timeout(1100)` then `stored = page.evaluate("localStorage.getItem('sy.expert.2001-01-01_Test-Talk.Test-Video')")`. Should be non-null JSON with `lastTime:7000` and `open:true`. If not, check `onTimeUpdate` is firing (is the mock's `_setTime` actually calling the `timeupdate` callback? Yes — verified in `mock_vimeo_player.js`.)
3. **Does auto-show happen before `reviewState` populates?** The skeleton uses `setTimeout(show, 0)` in `init()` exactly for this reason. If it still races, bump to `setTimeout(show, 10)` or call `show()` after `switchReviewMode` finishes. Prefer a deterministic signal: in `SPA.switchReviewMode`, call `ExpertPlayer.init` AFTER `reviewState.videos` and `reviewState.alignedRows` are set.
4. **Does `mountPlayer` use the restored `state.lastTime`?** It already does:
   `if (state.lastTime > 0) state.player.setCurrentTime(state.lastTime / 1000);`

If diagnostics show the init call runs before `reviewState` is populated, fix the order in `switchReviewMode` by moving `ExpertPlayer.init` call to AFTER the existing SRT-mode rendering completes. No new code, just reordering.

- [ ] **Step 10.4: Run test**

Run: `pytest tests/test_expert_player.py::TestPersistence -v`

Expected: PASS.

- [ ] **Step 10.5: Commit**

```bash
git add site/index.html tests/test_expert_player.py
git commit -m "feat(expert): restore open and lastTime across reloads"
```

---

## Task 11: Video switch + route-leave cleanup

**Files:**
- Modify: `site/index.html` — audit hooks from Task 4, tighten `destroy()`.

- [ ] **Step 11.1: Write failing tests**

Append:

```python
class TestCleanup:
    def test_switching_videos_does_not_duplicate_player(self, server, page):
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        page.select_option("#review-mode-select", "srt:Test-Video-2")
        page.wait_for_timeout(300)

        assert page.locator("#mock-player").count() <= 1
        assert page.locator("#btn-expert-player").is_visible()

    def test_leaving_review_destroys_player(self, server, page):
        _goto_review_srt(page, server)
        page.click("#btn-expert-player")
        page.wait_for_selector("#mock-player", state="visible", timeout=3000)

        page.evaluate("location.hash = '#/'")
        page.wait_for_selector(".talk-item", timeout=5000)
        assert page.locator("#mock-player").count() == 0
```

- [ ] **Step 11.2: Run, confirm failures**

Run: `pytest tests/test_expert_player.py::TestCleanup -v`

Expected: one or both FAIL depending on how thorough Task 4 hooks were.

- [ ] **Step 11.3: Tighten `destroy()`**

Update `destroy()` inside the IIFE:

```js
  function destroy() {
    if (!state) return;
    hide();
    if (state.player) {
      try { state.player.destroy(); } catch (_) {}  // no-op on mock
    }
    clearMount();
    var grid = document.getElementById('review-grid');
    if (grid && gridClickHandler) grid.removeEventListener('click', gridClickHandler);
    if (grid) grid.removeEventListener('focusin', onGridFocusIn);
    if (grid) grid.removeEventListener('keydown', onGridKeydown);
    window.removeEventListener('scroll', onWindowScroll);
    document.removeEventListener('keydown', onGlobalKeydown);
    gridClickHandler = null;
    state = null;
    if (btnExpert) btnExpert.style.display = 'none';
    var view = document.getElementById('view-review');
    if (view) view.classList.remove('expert-mode');
  }
```

Confirm the Task 4 hashchange listener fires on `location.hash = '#/'` — it should (hashchange event always fires for JS-driven hash mutation). If the router uses an explicit view-leave function, add `ExpertPlayer.destroy()` there instead and remove the hashchange listener.

- [ ] **Step 11.4: Run tests**

Run: `pytest tests/test_expert_player.py::TestCleanup -v`

Expected: both PASS.

- [ ] **Step 11.5: Commit**

```bash
git add site/index.html tests/test_expert_player.py
git commit -m "feat(expert): cleanup on video switch and route leave"
```

---

## Task 12: Full-suite regression + manual smoke

- [ ] **Step 12.1: Run the expert player test file end-to-end**

Run: `pytest tests/test_expert_player.py -v`

Expected: every test PASSes (~20 tests total across Tasks 1–11).

- [ ] **Step 12.2: Run the preview SPA suite (regression)**

Run: `pytest tests/test_preview_spa.py -q`

Expected: zero regressions.

- [ ] **Step 12.3: Run the full Python test suite**

Run: `pytest tests/ -q -x`

Expected: all tests pass.

- [ ] **Step 12.4: Manual smoke — dark theme, desktop**

```bash
python -m http.server --directory site 8000 &
open http://127.0.0.1:8000/#/review/<pick-a-real-talk-id>
```

Checklist:
- Switch to SRT source → `▶ Показати відео` appears.
- Click it → sticky bar appears above grid, real Vimeo loads.
- Play → current UK row gets blue left-edge, grid scrolls to keep it centered.
- Click an EN row → seeks, keeps playing.
- Click a timecode label → seeks.
- Focus a UK cell to edit → playback pauses, Follow gets dim.
- Press `Enter` in the cell → blurs, playback resumes.
- `Space` play/pause. `←/→` ±5s. `Esc` closes bar.
- Reload → bar reopens at the same time.
- Switch to another video in dropdown → player reloads for new video, state isolated.
- Switch to transcript source → button and bar disappear cleanly.
- Navigate back to index → no lingering iframe.

- [ ] **Step 12.5: Manual smoke — light theme**

Toggle the theme button. Spot-check `.current`, `.edited`, `.marked`, and `.current + .marked` composition.

- [ ] **Step 12.6: Manual smoke — mobile viewport**

In devtools, iPhone SE (375×667). Repeat the desktop checklist. Verify the bar is 22vh and doesn't crowd the grid.

- [ ] **Step 12.7: Final push**

```bash
gh auth status  # confirm SlavaSubotskiy active
git push -u origin feature/expert-edit-player
```

- [ ] **Step 12.8: Open PR**

```bash
gh pr create --title "feat: expert mode — edit subtitles while watching video" --body "$(cat <<'EOF'
## Summary
- Adds a sticky Vimeo player to view-review (SRT source mode only), opened via a new "Show video" button in the header.
- Bidirectional sync: playback highlights the current row with auto-scroll (Follow mode with smart-pause on focus/scroll); clicking a timecode or English row seeks playback.
- Player state persists per {talkId, videoSlug} in localStorage.
- Keyboard: Space/K play-pause, Left/J and Right/L seek +/-5s, Enter in a cell commits and resumes playback, Esc closes player.

Design doc: `docs/superpowers/specs/2026-04-13-expert-edit-with-video-design.md`

## Test plan
- [x] `pytest tests/test_expert_player.py`
- [x] `pytest tests/test_preview_spa.py` (no regressions)
- [x] Manual desktop dark/light, iPhone SE viewport
- [x] Real Vimeo video in real talk

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review

**Spec coverage (cross-check against `2026-04-13-expert-edit-with-video-design.md`):**

| Spec item                                                 | Task         |
|-----------------------------------------------------------|--------------|
| SRT-only visibility                                       | Task 4       |
| Hidden by default, toggle via `▶ Show video`              | Task 2, 4, 5 |
| Sticky 25vh bar, 4:3 aspect, 22vh mobile                  | Task 2       |
| `data-ms-start` on cells                                  | Task 3       |
| `ExpertPlayer` module with lifecycle                      | Task 4–5     |
| Vimeo mount on first show                                 | Task 5       |
| Binary search + highlight current row                     | Task 6       |
| Click-to-seek on `.cell-label` + `.cell.en`               | Task 7       |
| Follow smart-pause on focus / manual scroll / toggle      | Task 8       |
| Enter-commit + `Space/K/J/L/←/→/Esc` shortcuts            | Task 9       |
| Persist `{open, follow, lastTime}` per `{talkId, videoSlug}` | Task 10   |
| Video switch + route-leave cleanup                        | Task 11      |
| i18n UK + EN                                              | Task 2       |
| `.current` via inset box-shadow (compose with `.marked`)  | Task 2       |
| E2E tests including the binary-search unit case           | Tasks 1–11   |
| Manual sanity in both themes and mobile                   | Task 12      |
| Defensive `if (!window.Vimeo)` + toast                    | Task 5       |

All spec items mapped.

**Placeholder scan:** no TBDs, no "add validation here", no "similar to above". Every step shows the code it needs.

**Type consistency:** `state` shape defined once in `freshState()` and consistent throughout. Method names (`show`, `hide`, `destroy`, `toggle`, `toggleFollow`, `seekTo`, `onTimeUpdate`, `highlightRow`, `scrollRowIntoView`, `mountPlayer`, `onGridClick`, `onGridFocusIn`, `onGridKeydown`, `onGlobalKeydown`, `togglePlayPause`, `binarySearchByMs`, `formatTime`, `extractVimeoId`, `persistNow`, `throttledPersist`, `loadPersisted`, `storageKey`, `freshState`, `cacheDom`, `clearMount`) — all referenced consistently across tasks.

**Scope:** single plan, one feature, ~350–500 net LOC in `site/index.html` + one new test file. Stays inside a single implementation cycle.
