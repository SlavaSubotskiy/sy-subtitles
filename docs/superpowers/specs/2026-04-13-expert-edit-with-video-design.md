# Expert mode: edit subtitles while watching video

**Status:** Design approved, ready for implementation plan
**Author:** SlavaSubotskiy (with brainstorm agent)
**Date:** 2026-04-13

## Goal

Add an "expert" editing mode to `view-review` in `site/index.html` that lets a
reviewer edit Ukrainian subtitles while watching the corresponding video, with
bidirectional sync between the currently-playing row and the grid.

Chosen layout: **sticky Vimeo player on top of the existing review grid**
(option B from the brainstorm; options A "toolbar tab" and C "split view" were
rejected).

## Non-goals

- New page / separate route. Expert mode lives inside `view-review`.
- Resize handle, multi-speed playback, or fullscreen player. The existing
  `view-preview.fs-mode` handles immersive playback.
- Timing edits (shifting start/end). Users edit text; timecodes are read-only
  references provided by the builder pipeline.
- Transcript mode. Expert mode only applies when reviewer is on the SRT
  source (transcripts have no timecodes).

## User flow

1. User opens a talk's review page, switches left/right source to SRT.
2. A new `▶ Показати відео` button appears in `.header-actions`.
3. User clicks it; a sticky bar appears below the header containing a 4:3
   Vimeo player (max-height 25vh), a time display, a `⇅ Слідувати` toggle,
   and a close button.
4. Play starts on demand (normal Vimeo controls). As the video plays,
   the currently-spoken row in the grid gets highlighted with `.cell.uk.current`
   and scrolls into view (center) — Follow mode.
5. Clicking the `.cell-label` (timecode) on either column, or anywhere on
   a `.cell.en`, seeks the player to that row's start time and re-enables
   Follow.
6. Clicking a `.cell-text` to edit pauses the player, pauses Follow, and
   preserves the existing contenteditable behavior. Pressing Enter in the
   cell blurs, resumes playback, and restores shortcuts.
7. User can close the player; preference and last playback position are
   persisted to localStorage per `{talkId, videoSlug}`.
8. On next visit (same talk + video), if player was left open, it reopens
   automatically at `lastTime`.

## Out-of-flow constraints (from brainstorm)

- Expert button is visible **only** in SRT source mode.
- Player is **hidden by default**; opens on explicit user toggle.
- Player uses **4:3 aspect ratio** (talks from amruta.org are 4:3).
- Player is sticky at top of `view-review`, `max-height: 25vh` on desktop,
  `22vh` on mobile. Same behavior on mobile — no hiding, no fallback.
- Click-to-seek targets: `.cell-label` (both columns) + whole `.cell.en`.
  `.cell.uk` remains exclusively editable; clicking it does **not** seek.
- Follow mode auto-pauses on `.cell-text` focus or manual grid scroll;
  resumes on seek or `⇅ Follow` toggle.
- Closing the player pauses playback and `display:none`s the bar. The Vimeo
  iframe and its internal state are preserved for fast reopening.
- Shortcuts (active only while player is open AND focus is not in
  `.cell-text`): `Space`/`K` play-pause, `←`/`J` seek -5s, `→`/`L` seek +5s,
  `Esc` close player.
- `Enter` inside `.cell-text` (expert mode only) prevents default
  `<br>` insertion, blurs the field, and resumes playback.
- Clicking into `.cell-text` pauses the player (symmetric to Enter).
- localStorage schema: key `sy.expert.{talkId}.{videoSlug}` → JSON
  `{open: bool, follow: bool, lastTime: number}`.

## Architecture

### One new module: `ExpertPlayer`

A singleton object literal co-located with the rest of `site/index.html`'s
SPA code (same file, same style, no new build artifacts). ~250 lines of JS.

**Lifecycle:**

```
init(talkId, videoSlug)  // read localStorage; optionally auto-show
show()                   // create iframe if needed, wire events, reveal bar
hide()                   // pause, display:none, persist
destroy()                // remove iframe, reset state (on route leave / video switch)
toggle()                 // show/hide
```

**State:**

```js
{
  open: false,
  follow: true,
  followPaused: false,  // transient: focus / manual scroll
  lastTime: 0,          // ms; last known playhead position
  currentIdx: null,     // index into reviewState.alignedRows
  player: null,         // Vimeo.Player instance
  isAutoScrolling: false, // guard to prevent follow-pause loop
  talkId: null,
  videoSlug: null,
}
```

**Event wiring:**

- Vimeo `timeupdate` → `onTimeUpdate(data)` → binary-search idx in
  `reviewState.alignedRows`, update `.cell.uk.current`, maybe scrollIntoView,
  persist `lastTime` (throttled 1 s).
- Delegated click on `#review-grid` → if target matches `.cell-label` or is
  inside `.cell.en`, read `data-ms-start` on the enclosing `.cell` and
  `seekTo(ms)`.
- Delegated `focusin` on `#review-grid` → if `.cell-text`:
  `followPaused = true`, `player.pause()`.
- Delegated `keydown` on `#review-grid` → if `.cell-text` + `Enter` +
  not composing: `preventDefault()`, `blur()`, `player.play()`.
- `window` scroll (the whole `view-review` scrolls with the page, there is
  no internal scroll container) → if `!isAutoScrolling`, `followPaused =
  true`, `#btn-follow` gains `.paused`.
- Global `keydown` (attached when player opens, removed on hide) →
  `Space/K/J/L/←/→/Esc` as specified, ignored while focus in `.cell-text`.

### Integration points with existing code

1. **`renderReviewSrt()`** (site/index.html, ~line 1870). When creating EN
   and UK cells, also set `dataset.msStart` to `row.en.startMs` or
   `row.uk.startMs` respectively. No other behavior changes in this function.
2. **`SPA.switchReviewMode(mode, videoSlug)`** (~line 1675). In the `mode ===
   'srt'` branch: show `#btn-expert-player`, call
   `ExpertPlayer.init(talkId, videoSlug)`. In the transcript branch: hide the
   button, call `ExpertPlayer.destroy()`.
3. **Route leave** (hashchange to non-review). Call
   `ExpertPlayer.destroy()` to release the iframe.
4. **`.header-actions` markup** in `view-review`. Add
   `<button id="btn-expert-player">` before `Create Issue`.
5. **New DOM block** inserted between `.header` and `#review-grid`:
   `<div id="expert-player-bar" hidden>` containing the player mount,
   time display, Follow toggle, close button.
6. **Visual state composition.** `.cell.uk.current` uses `box-shadow: inset
   3px 0 0 var(--link)` instead of `border-left` so it stacks cleanly with
   `.marked` (which owns `border-left`). Both indicators render.

### New DOM

```html
<!-- inside view-review .header-actions, before "Create Issue" -->
<button id="btn-expert-player" class="chip"
        onclick="ExpertPlayer.toggle()"
        data-i18n-title="title.show_video"
        data-i18n="btn.show_video">▶ Show video</button>

<!-- immediately after .header, before #review-grid -->
<div id="expert-player-bar" class="expert-bar" hidden>
  <div class="expert-video-wrap">
    <div id="expert-player"></div>
  </div>
  <div class="expert-controls">
    <span id="expert-time">00:00:00</span>
    <button id="btn-follow" class="chip"
            onclick="ExpertPlayer.toggleFollow()"
            data-i18n-title="title.follow"
            data-i18n="btn.follow">⇅ Follow</button>
    <button class="chip" onclick="ExpertPlayer.hide()"
            aria-label="Close video">✕</button>
  </div>
</div>
```

### New CSS (added to existing `<style>` block)

```css
/* --- Expert player --- */
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

## Data flow

### Player → Grid (highlight current row)

```
Vimeo.timeupdate(seconds)
  → ms = Math.round(seconds * 1000)
  → idx = binarySearchByMs(reviewState.alignedRows, ms)
      // find largest idx where row.uk.startMs <= ms; -1 if ms < first.
      // O(log n), stable to repeated startMs across spanned cells.
  → if idx !== state.currentIdx:
      remove .cell.uk.current from previous (if any)
      add    .cell.uk.current to new        (if idx >= 0)
      if state.follow && !state.followPaused && idx >= 0:
          scrollRowIntoView(idx, { block: 'center', behavior: 'smooth' })
  → state.currentIdx = idx
  → throttledPersist(lastTime)  // every 1000 ms
```

### Grid → Player (click-to-seek)

```
click (delegated on #review-grid)
  → if target.closest('.cell-label') OR target.closest('.cell.en')
    → cell = target.closest('.cell')
    → ms = Number(cell.dataset.msStart)
    → player.setCurrentTime(ms / 1000)
    → state.followPaused = false   // seek = user wants sync
    → btn-follow.classList.remove('paused')
```

### Smart Follow pause

```
focusin on .cell-text       → followPaused = true, player.pause()
keydown Enter on .cell-text → preventDefault, blur, player.play()
scroll on review grid       → if !isAutoScrolling → followPaused = true
click #btn-follow           → followPaused = !followPaused
                                if resuming: scrollRowIntoView(currentIdx)
seek (see above)            → followPaused = false
```

### Auto-scroll loop guard

```
scrollRowIntoView:
  state.isAutoScrolling = true
  el.scrollIntoView({ block: 'center', behavior: 'smooth' })
  setTimeout(() => state.isAutoScrolling = false, 500)
```

### Video switch

```
SPA.switchReviewMode('srt', newVideoSlug)
  → ExpertPlayer.destroy()
  → ExpertPlayer.init(talkId, newVideoSlug)
  → if localStorage says open: ExpertPlayer.show()
```

### Persistence (debounced 1000 ms)

```
localStorage['sy.expert.{talkId}.{videoSlug}'] =
  JSON.stringify({ open, follow, lastTime })
```

## Visual state composition

`.current` is a pure indicator (no background of its own). It sets only
`box-shadow: inset 3px 0 0 var(--link)`. The existing `.marked` / `.edited`
backgrounds remain the source of truth for row intent.

| Class combo              | Background           | Left indicator                                         |
|--------------------------|----------------------|--------------------------------------------------------|
| base                     | —                    | —                                                      |
| `.current`               | —                    | `inset 3px 0 0 var(--link)` (shadow)                   |
| `.edited`                | `--cell-edited-bg`   | —                                                      |
| `.marked`                | `--mark-bg`          | `3px solid var(--issue-border)` (border-left)          |
| `.current + .marked`     | `--mark-bg`          | border-left (purple) + inset shadow (blue) — both show |
| `.current + .edited`     | `--cell-edited-bg`   | inset shadow                                           |
| `.editing` (focus)       | `--cell-edit-bg`     | inset shadow if also current                           |

No state is lost because `.current` and `.marked` use different CSS
properties (`box-shadow` vs `border-left`), so they compose without
collision.

## Edge cases

1. `reviewState.alignedRows` empty or missing → button hidden.
2. `ms` before first row / between blocks → binary search returns previous
   row; if none, `currentIdx = null`, nothing highlighted, no scroll jump.
3. `.cell-label` click while editing → blur current cell (standard browser
   behavior), seek, Follow resumes.
4. Video switch while player is open → full `destroy()` + fresh `init()` +
   possibly `show()` based on the new video's localStorage.
5. Mode switch from `srt` → `transcript` → button hides, `destroy()`.
6. hashchange to non-review view → route hook calls `destroy()`.
7. Vimeo SDK missing (adblock, network failure) →
   `if (!window.Vimeo) { toast(t('toast.vimeo_unavailable')); return; }`
   button stays visible but shows the toast on click.
8. `Ctrl+Z` in contenteditable → untouched; standard behavior.
9. IME composition (`e.isComposing || e.keyCode === 229`) → Enter handler
   skips so input method commit is not broken.
10. `lastTime` exceeds video length → Vimeo clamps; on error, log and start
    from 0.
11. `Revert all` (existing feature) rebuilds the grid → after rebuild,
    reapply `.cell.uk.current` to `alignedRows[currentIdx]`.
12. User opens expert mode on a talk with multiple videos → each video has
    its own localStorage entry, independent state.

## i18n additions

Add to both `uk` and `en` blocks in the `translations` object in
`site/index.html`:

| Key                        | UK                                                         | EN                                    |
|---                          |---                                                         |---                                    |
| `btn.show_video`           | `▶ Показати відео`                                         | `▶ Show video`                        |
| `btn.hide_video`           | `✕ Сховати відео`                                          | `✕ Hide video`                        |
| `btn.follow`               | `⇅ Слідувати`                                              | `⇅ Follow`                            |
| `title.show_video`         | `Відкрити плеєр для синхронізованого редагування`          | `Open player for synced editing`      |
| `title.follow`             | `Автоматично прокручувати до поточного рядка`              | `Auto-scroll to current row`          |
| `title.expert_seek`        | `Клік по таймкоду або англ. рядку — перемотати відео`      | `Click timecode or English row to seek` |
| `toast.vimeo_unavailable`  | `Плеєр Vimeo недоступний`                                  | `Vimeo player unavailable`            |

## Vimeo SDK

Already loaded globally in `<head>` (`site/index.html:11`). No lazy-load
needed, no new `<script>` tag. `new Vimeo.Player(iframe)` is available as
soon as the document parses. Defensive guard: `if (!window.Vimeo)` before
instantiation, toast + abort on failure.

## Testing

### Playwright E2E (new file `tests/test_expert_player.py`)

Follow the pattern of the existing `tests/test_preview_spa.py` — Python
pytest + `playwright.sync_api`, served statically from `site/`, with the
Vimeo iframe stubbed so tests don't hit the network. The stub exposes
`play()`, `pause()`, `getCurrentTime()`, `setCurrentTime()`, and a
`dispatchTimeUpdate(seconds)` helper driven from test code.

Scenarios:

1. Navigate to a review page. Switch source to SRT. Assert
   `#btn-expert-player` is visible.
2. Switch source to transcript. Assert button is hidden.
3. Switch back to SRT, click `▶ Show video`. Assert `#expert-player-bar`
   is visible and iframe is mounted.
4. Click the first EN cell. Assert the stub recorded
   `setCurrentTime(expected_seconds)` (±0.01 s of a fixture value).
5. Reload the page. Assert player is open again and the stub was called
   with `setCurrentTime(lastTime)` from localStorage.
6. Focus a `.cell-text`. Drive `dispatchTimeUpdate` past several rows.
   Assert `.cell.uk.current` did not move (followPaused).
7. Press Enter inside `.cell-text`. Assert the element is blurred and the
   stub recorded `play()`.
8. Press Space with `<body>` focused. Assert stub recorded alternating
   play/pause.
9. Press `Esc`. Assert the bar has `[hidden]` set.

### Binary-search unit test

Covered inline in `tests/test_expert_player.py` via a single synchronous
Playwright page that evaluates `ExpertPlayer.binarySearchByMs` against a
hand-written `alignedRows` fixture. Cases: empty array, `ms` before
first row, `ms` between two rows, `ms` on exact start boundary, `ms`
past last row, rows with repeated `startMs` (spanned cells).

### Visual regression

Manual only: check `.current + .marked + .edited + .editing` composition
in dark and light themes; verify player position on desktop (1440×900) and
mobile (iPhone SE viewport, 375×667).

## Scope control (YAGNI)

**In:** toggle, seek, highlight, smart follow, per-video persist, 4 shortcuts,
Enter-commit-and-resume, click-pauses-player, 4:3 aspect, sticky 25vh
desktop / 22vh mobile, EN+UK columns unchanged, i18n for UK and EN.

**Out:** resize handle, fullscreen, speed control, overlay-over-video, audio
waveform, per-word highlighting, custom keymap, subtitle timing edits,
multi-video timeline sync.

## Files to touch

- `site/index.html` — all changes (DOM, CSS, JS). Single-file SPA by design.
- `tests/test_expert_player.py` — new Playwright E2E + inline binary-search
  unit coverage, following `tests/test_preview_spa.py` pattern.

## Implementation sequence (for the plan step)

1. Add new DOM, CSS, i18n keys (no behavior yet) — page renders unchanged.
2. Wire `data-ms-start` in `renderReviewSrt` — no visible change.
3. Implement `ExpertPlayer` module with show/hide/toggle + Vimeo mount.
4. Wire into `SPA.switchReviewMode` and route-leave.
5. Add click-to-seek delegated listener + visual `.current` class logic.
6. Add Follow mode, smart pause on focus/scroll, scroll-into-view guard.
7. Add Enter-commit, click-pauses-player, global keyboard shortcuts.
8. localStorage persistence (throttled) + restore on init.
9. E2E tests.
10. Manual check on both themes, desktop + mobile viewports.
