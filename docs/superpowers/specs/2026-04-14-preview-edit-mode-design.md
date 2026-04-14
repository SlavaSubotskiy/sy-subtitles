# Preview page: Marker ↔ Edit modes

**Status:** approved
**Date:** 2026-04-14
**Scope:** `site/index.html` (SPA preview view) + tests

## Goal

Extend the preview page with two switchable modes:

1. **Marker mode** (current behavior, default for new/migrated state)
   — drop a timestamped note on the current subtitle moment, collect a list,
   copy/export, create a GitHub issue with the marker set.
2. **Edit mode** (new) — edit the text of individual SRT blocks while
   watching the video. Edits accumulate locally per video and per language,
   and can be exported as a GitHub issue (Before/After) or opened in the
   GitHub web editor as a fully-rebuilt SRT (same flow the review page uses
   for its `Open in GitHub Editor` action).

No backend changes. All state is client-side in `localStorage`.

## Non-goals

- Timecode editing. Only block text is editable.
- Bulk import of edits from an issue/PR.
- Undo/history beyond "reset to original".
- Changes to SRT/whisper parsers, optimizer, or build pipeline.

## Layout

Preview `.header` becomes a single row that matches the review page
pattern: `<h1>` on the left, `.header-actions` on the right.

```
┌──────────────────────────────────────────────────────────────┐
│ ← Index · <title> [video▾]   [📌|✏️]  [action buttons ...]   │  .header
├──────────────────────────────────────────────────────────────┤
│ <iframe video>                                               │
│ <overlay>                                                    │
│ [00:00:00] [lang▾] [📌 Mark / ✏️ Edit] [⛶]                  │  .controls
├──────────────────────────────────────────────────────────────┤
│ ▼ Markers (N)   | Edits (N)                                  │
│   <rows>                                                     │
└──────────────────────────────────────────────────────────────┘
```

### `.header-actions` contents

Always visible:
- **Mode segmented control** `[📌 Markers | ✏️ Edit]` — two toggleable
  buttons, the active one highlighted. Not shown as a `<select>` since there
  are only two options.

Visible only in **marker** mode:
- `Copy all`
- `Create issue`
- `Clear all` — hidden unless `markers.length > 0`

Visible only in **edit** mode:
- `Create issue`
- `Open in GitHub Editor` (the PR flow)
- `Clear all` — hidden unless `edits[currentLang]` has any keys

### Player `.controls` (under the iframe)

Keeps: time display, lang select, Mark/Edit button, fullscreen.

The Mark/Edit button stays in player controls (per user decision). Its
label and handler depend on `previewState.mode`:
- marker mode → `📌 Mark` → `SPA.addMarker()`
- edit mode → `✏️ Edit` → `SPA.addEdit()`

### Video switcher (new)

A `<select id="preview-video-select">` is added inside the `<h1>` next to
the title (same pattern as `#review-mode-select` on the review page).

- Hidden (`display:none`) when `meta.videos.length <= 1`.
- Populated from `meta.videos` with `{value: slug, text: title}`.
- `onchange` → `location.hash = '#/preview/' + talkId + '/' + newSlug`.
  This triggers the normal route → `showPreview` re-entry, which loads the
  new video's own localStorage entry (state is per-video, not per-talk).

### List container

The existing `.markers > <details>` block is renamed `.preview-list`. Its
`<summary>` label toggles between "Markers (N)" and "Edits (N)" per mode.
The body swaps between a marker list and an edit list.

## State model

### Shape

```js
// localStorage key: preview_<talkId>_<videoSlug>
{
  mode: 'marker' | 'edit',
  markers: [
    { time: 12.34, tc: '00:00:12', text: '...', comment: '...' }
  ],
  edits: {
    uk: { 0: 'edited text', 5: '...' },
    en: { ... }
  }
}
```

- `mode` is persisted per video.
- `markers` is a flat list, independent of SRT language (as today).
- `edits` is keyed by language (`srt-lang-select` value), then by the
  0-based index of the block in the parsed SRT for that language.

### Migration

When `showPreview(talkId, videoSlug)` runs:

1. If `preview_<talkId>_<videoSlug>` exists → parse and use.
2. Else if legacy `markers_preview_<talkId>_<videoSlug>` exists →
   build `{mode: 'marker', markers: <legacy>, edits: {}}`, write the new
   key, delete the legacy key.
3. Else → default `{mode: 'marker', markers: [], edits: {}}`.

### In-memory

```js
previewState.mode     // 'marker' | 'edit'
previewState.markers  // as today
previewState.edits    // { <lang>: { <idx>: text } }
```

`savePreviewState()` replaces `saveMarkers()` and writes the whole object.
It is called after any mutation to markers, edits, or mode.

## Behavior

### Mode switch

`SPA.setPreviewMode(newMode)`:
1. No-op if already in `newMode`.
2. Update `previewState.mode`, `savePreviewState()`.
3. Toggle segmented-control active class.
4. Update `.controls` Mark/Edit button label and handler.
5. Swap visible button group in `.header-actions`.
6. Update list summary label and count, re-render list.
7. Update `Clear all` visibility.

### Marker mode

Unchanged from current behavior. The current `SPA.addMarker`,
`SPA.copyMarkers`, `SPA.createPreviewIssue` (marker variant),
`SPA.clearMarkers`, `renderMarkers()` stay.

### Edit mode — add

`SPA.addEdit()`:
1. `lang = previewState.srtLang` (current `srt-lang-select`).
2. `blocks = SPA.srtByLang[lang]`. If absent → toast `no_srt`, return.
3. `idx = findActiveSubtitleIdx(blocks, currentTimeMs)`.
   If `-1` → toast `no_active_subtitle`, return.
4. `previewState.player.pause()`.
5. If `edits[lang][idx]` already exists → `renderEditList()`
   (no duplicate), then focus the existing row's contenteditable and
   place cursor at end.
6. Else → `edits[lang][idx] = blocks[idx].text` (initial text = original),
   `renderEditList()`, focus the new row.
7. `savePreviewState()`, `updateClearBtn()`.

### Edit row DOM

```html
<li class="edit-item" data-idx="{idx}">
  <span class="tc">00:01:23</span>
  <div class="orig">{original block text}</div>
  <div class="edited" contenteditable="true" data-idx="{idx}"
       oninput="SPA.onEditInput({idx}, this)"
       onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();this.blur();SPA.resumePlayer();}">
    {current edit text}
  </div>
  <button class="del" onclick="SPA.deleteEdit({idx})">×</button>
</li>
```

The `.tc` click seeks the player to the block start (reuses marker
`seek-to-time` helper).

### Edit row — input handling

`SPA.onEditInput(idx, el)`:
- `text = el.innerText`
- `orig = SPA.srtByLang[currentLang][idx].text`
- If `text === orig` → `delete edits[currentLang][idx]`, remove `.edited`
  class from the row.
- Else → `edits[currentLang][idx] = text`, add `.edited` class.
- `savePreviewState()`, `updateClearBtn()`.
- **Does not** re-render the list (cursor preservation).

### Enter / resume / seek

- `Enter` (without Shift) inside `.edited` → `blur()` → `resumePlayer()`.
- `Shift+Enter` → literal newline (multiline edit allowed).
- Arrow keys seek the video **only when focus is outside** a
  contenteditable (existing `isTyping` guard).
- `M` / `m` → in marker mode calls `addMarker`, in edit mode calls
  `addEdit`. Guard: ignored if focus is in a contenteditable or input.
- Space → play/pause as today (guard the same way).
- `F` → fullscreen as today.

### Edit row — delete

`SPA.deleteEdit(idx)`:
- `delete edits[currentLang][idx]`, remove the `<li>` from DOM.
- `savePreviewState()`, `updateClearBtn()`.

### Language switch

`srt-lang-select` onchange already updates overlay state. Extend it: if
`previewState.mode === 'edit'`, re-render the edit list with
`edits[newLang]`.

### Clear all

`SPA.clearAll()` (context-aware):
- marker mode → confirm dialog → `markers = []` → save → re-render.
- edit mode → confirm dialog → `edits[currentLang] = {}` → save → re-render.
  **Only the current language is cleared.** Edits for other languages are
  not touched.

### `Create issue` (edit mode)

`SPA.createPreviewIssue()` learns the mode:
- marker mode → current behavior (unchanged).
- edit mode → generate an issue body with a Before/After table for each
  `edits[currentLang][idx]`, showing block timecode, original, edited.
  Label `review:pending`, same URL-length fallback (clipboard) as the
  review page.

### `Open in GitHub Editor` (edit mode)

`SPA.openPreviewEditor()`:
1. `blocks = SPA.srtByLang[currentLang]`
2. Rebuild an SRT string: for each block, substitute
   `edits[currentLang][idx]` where present, keep block numbering and
   original timecodes.
3. Target path:
   `talks/<talkId>/<videoSlug>/final/<currentLang>.srt`
4. Open `https://github.com/<REPO>/edit/main/<path>?value=<encoded>`.
   This is the same mechanism the review page uses
   (`SPA.openEditor` at `site/index.html:2690`).

## Tests (TDD)

### Node unit tests — `tests/test_preview_state.js` (new)

- `describe('previewState shape')`
  - default empty → `{mode:'marker', markers:[], edits:{}}`
  - JSON round-trip preserves shape
- `describe('migrateLegacyMarkers')`
  - legacy only → new object with `markers` copied, legacy removed
  - new only → legacy untouched, new wins
  - both → new wins, legacy removed
  - neither → default
- `describe('applyEditsToSrt')`
  - empty edits → original SRT (byte-equal)
  - one edit replaces one block
  - edit equal to original → noop
  - multiline edit preserved in output
  - block numbering and timecodes unchanged

### Playwright tests — extend `tests/test_preview_spa.py`

Mode / layout:
1. `test_mode_default_marker`
2. `test_mode_toggle_updates_buttons_and_list`
3. `test_mode_persisted_per_video`
4. `test_mode_per_video_independent`
5. `test_legacy_marker_migration`
6. `test_video_switcher_hidden_for_single_video`
7. `test_video_switcher_visible_for_multi_video`

Marker mode regression:
8. `test_add_marker_still_works`

Edit mode:
9. `test_add_edit_creates_item_and_focuses`
10. `test_add_edit_existing_idx_focuses_not_duplicates`
11. `test_add_edit_no_active_subtitle_shows_toast`
12. `test_edit_text_persists_to_storage`
13. `test_edit_reset_to_original_removes_entry`
14. `test_edit_enter_resumes_video`
15. `test_edit_per_language_isolation`
16. `test_edit_delete_row_removes_from_storage`

Clear / actions:
17. `test_clear_all_marker_mode`
18. `test_clear_all_edit_mode_current_lang_only`
19. `test_clear_btn_hidden_when_empty`

PR / Issue:
20. `test_openeditor_builds_srt_from_edits`
21. `test_create_issue_edit_mode_generates_before_after`

Keyboard:
22. `test_keyboard_m_edit_mode_calls_addEdit`
23. `test_keyboard_arrows_seek_when_not_in_contenteditable`

Commands:
```
node --test tests/test_preview_state.js tests/test_preview_srt_parser.js tests/test_spa_cache.js
pytest tests/test_preview_spa.py -v
```

## Delivery

- Branch: `feature/preview-edit-mode` off `main`.
- TDD-ordered commits: test → impl → test → ...
- Local dev server: `python3 -m http.server --directory site 8000`.
- PR after all tests green. PR description includes both mode screenshots
  and a test checklist.