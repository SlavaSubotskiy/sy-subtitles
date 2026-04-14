const { describe, it } = require('node:test');
const assert = require('node:assert');
const {
  defaultPreviewState,
  loadPreviewState,
  applyEditsToSrt,
} = require('../tools/preview_state');
const { findActiveSubtitleIdx } = require('../tools/preview_srt_parser');

// In-memory storage double — matches just enough of localStorage
// surface (getItem/setItem/removeItem) for loadPreviewState.
function makeStorage(initial) {
  const store = Object.assign({}, initial || {});
  return {
    data: store,
    getItem(k) {
      return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null;
    },
    setItem(k, v) {
      store[k] = String(v);
    },
    removeItem(k) {
      delete store[k];
    },
  };
}

describe('defaultPreviewState', () => {
  it('has marker mode and empty collections', () => {
    const s = defaultPreviewState();
    assert.strictEqual(s.mode, 'marker');
    assert.deepStrictEqual(s.markers, []);
    assert.deepStrictEqual(s.edits, {});
  });
  it('returns a fresh object each call', () => {
    const a = defaultPreviewState();
    const b = defaultPreviewState();
    a.markers.push({ time: 1, tc: '00:00:01', text: 'x', comment: '' });
    assert.strictEqual(b.markers.length, 0);
  });
});

describe('loadPreviewState — migration and precedence', () => {
  const talkId = '2001-01-01_Test';
  const videoSlug = 'v1';
  const newKey = 'preview_' + talkId + '_' + videoSlug;
  const legacyKey = 'markers_preview_' + talkId + '_' + videoSlug;

  it('returns default when neither key is present', () => {
    const storage = makeStorage();
    const state = loadPreviewState(talkId, videoSlug, storage);
    assert.strictEqual(state.mode, 'marker');
    assert.deepStrictEqual(state.markers, []);
    assert.deepStrictEqual(state.edits, {});
    // Default is not written back to storage until user mutates.
    assert.strictEqual(storage.getItem(newKey), null);
  });

  it('reads the new key and leaves storage untouched', () => {
    const payload = {
      mode: 'edit',
      markers: [{ time: 1, tc: '00:00:01', text: 'a', comment: '' }],
      edits: { uk: { 3: 'нове' } },
    };
    const storage = makeStorage({ [newKey]: JSON.stringify(payload) });
    const state = loadPreviewState(talkId, videoSlug, storage);
    assert.deepStrictEqual(state, payload);
    assert.strictEqual(storage.getItem(legacyKey), null);
  });

  it('migrates legacy markers-only key to new shape and removes legacy', () => {
    const legacyMarkers = [
      { time: 12.3, tc: '00:00:12', text: 'hi', comment: 'c1' },
      { time: 45.6, tc: '00:00:45', text: 'bye', comment: '' },
    ];
    const storage = makeStorage({
      [legacyKey]: JSON.stringify(legacyMarkers),
    });
    const state = loadPreviewState(talkId, videoSlug, storage);
    assert.strictEqual(state.mode, 'marker');
    assert.deepStrictEqual(state.markers, legacyMarkers);
    assert.deepStrictEqual(state.edits, {});
    assert.strictEqual(storage.getItem(legacyKey), null);
    const stored = JSON.parse(storage.getItem(newKey));
    assert.deepStrictEqual(stored.markers, legacyMarkers);
    assert.strictEqual(stored.mode, 'marker');
  });

  it('prefers new key when both exist and drops legacy', () => {
    const legacy = [{ time: 1, tc: '00:00:01', text: 'old', comment: '' }];
    const payload = {
      mode: 'edit',
      markers: [],
      edits: { uk: { 0: 'x' } },
    };
    const storage = makeStorage({
      [legacyKey]: JSON.stringify(legacy),
      [newKey]: JSON.stringify(payload),
    });
    const state = loadPreviewState(talkId, videoSlug, storage);
    assert.deepStrictEqual(state, payload);
    assert.strictEqual(storage.getItem(legacyKey), null);
  });

  it('falls back to default on corrupted new key', () => {
    const storage = makeStorage({ [newKey]: '{not-json' });
    const state = loadPreviewState(talkId, videoSlug, storage);
    assert.strictEqual(state.mode, 'marker');
    assert.deepStrictEqual(state.markers, []);
  });

  it('coerces missing fields from partial new payload', () => {
    const storage = makeStorage({
      [newKey]: JSON.stringify({ mode: 'edit' }),
    });
    const state = loadPreviewState(talkId, videoSlug, storage);
    assert.strictEqual(state.mode, 'edit');
    assert.deepStrictEqual(state.markers, []);
    assert.deepStrictEqual(state.edits, {});
  });
});

describe('findActiveSubtitleIdx', () => {
  const subs = [
    { index: 1, startMs: 1000, endMs: 5000, text: 'First' },
    { index: 2, startMs: 6000, endMs: 10000, text: 'Second' },
  ];

  it('returns 0 at start of first block', () => {
    assert.strictEqual(findActiveSubtitleIdx(subs, 1000), 0);
  });
  it('returns 0 in middle of first block', () => {
    assert.strictEqual(findActiveSubtitleIdx(subs, 3000), 0);
  });
  it('returns -1 at exact end (exclusive)', () => {
    assert.strictEqual(findActiveSubtitleIdx(subs, 5000), -1);
  });
  it('returns -1 in gap between blocks', () => {
    assert.strictEqual(findActiveSubtitleIdx(subs, 5500), -1);
  });
  it('returns 1 inside second block', () => {
    assert.strictEqual(findActiveSubtitleIdx(subs, 7000), 1);
  });
  it('returns -1 before all', () => {
    assert.strictEqual(findActiveSubtitleIdx(subs, 0), -1);
  });
  it('returns -1 after all', () => {
    assert.strictEqual(findActiveSubtitleIdx(subs, 15000), -1);
  });
  it('handles empty array', () => {
    assert.strictEqual(findActiveSubtitleIdx([], 1000), -1);
  });
});

describe('applyEditsToSrt', () => {
  const blocks = [
    { index: 1, startMs: 1000, endMs: 5000, text: 'First' },
    { index: 2, startMs: 6000, endMs: 10000, text: 'Second' },
    { index: 3, startMs: 11000, endMs: 15000, text: 'Third' },
  ];

  it('empty edits rebuild identical SRT', () => {
    const out = applyEditsToSrt(blocks, {});
    const expected = [
      '1',
      '00:00:01,000 --> 00:00:05,000',
      'First',
      '',
      '2',
      '00:00:06,000 --> 00:00:10,000',
      'Second',
      '',
      '3',
      '00:00:11,000 --> 00:00:15,000',
      'Third',
      '',
    ].join('\n');
    assert.strictEqual(out, expected);
  });

  it('replaces one block text', () => {
    const out = applyEditsToSrt(blocks, { 1: 'Перший' });
    assert.match(out, /\n2\n00:00:06,000 --> 00:00:10,000\nПерший\n/);
    // Other blocks untouched.
    assert.match(out, /\nFirst\n/);
    assert.match(out, /\nThird\n/);
  });

  it('replaces multiple blocks', () => {
    const out = applyEditsToSrt(blocks, { 0: 'A', 2: 'C' });
    const lines = out.split('\n');
    assert.strictEqual(lines[2], 'A');
    assert.strictEqual(lines[10], 'C');
  });

  it('preserves multiline edits', () => {
    const out = applyEditsToSrt(blocks, { 0: 'Line 1\nLine 2' });
    assert.ok(
      out.startsWith('1\n00:00:01,000 --> 00:00:05,000\nLine 1\nLine 2\n'),
      'expected multiline edit at block 0, got: ' + out.slice(0, 80),
    );
  });

  it('ignores edits with indices outside block range', () => {
    const out = applyEditsToSrt(blocks, { 99: 'ghost' });
    assert.doesNotMatch(out, /ghost/);
    // Result equals empty-edits case.
    assert.strictEqual(out, applyEditsToSrt(blocks, {}));
  });

  it('edit equal to original is effectively a noop', () => {
    const out = applyEditsToSrt(blocks, { 0: 'First' });
    assert.strictEqual(out, applyEditsToSrt(blocks, {}));
  });

  it('returns empty string for empty blocks', () => {
    assert.strictEqual(applyEditsToSrt([], {}), '');
  });

  it('keeps sequential numbering starting at 1', () => {
    const out = applyEditsToSrt(blocks, {});
    const lines = out.split('\n');
    assert.strictEqual(lines[0], '1');
    assert.strictEqual(lines[4], '2');
    assert.strictEqual(lines[8], '3');
  });
});
