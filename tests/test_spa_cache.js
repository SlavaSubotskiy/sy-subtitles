const { describe, it, beforeEach, mock } = require('node:test');
const assert = require('node:assert');

// ============================================================
// Extract and test SPA cache/freshness logic
// ============================================================

// --- updateLastModifiedUI logic (extracted) ---
function formatLastModified(lastModified, now) {
  if (!lastModified) return '';
  var d = new Date(lastModified);
  if (isNaN(d.getTime())) return '';
  var diffMs = now - d;
  var diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'щойно';
  if (diffMin < 60) return diffMin + ' хв тому';
  if (diffMin < 1440) return Math.floor(diffMin / 60) + ' год тому';
  return d.toLocaleDateString('uk-UA', { day: 'numeric', month: 'short' });
}

// --- SRT URL with cache-buster logic (extracted) ---
function buildSrtUrl(rawBase, talkId, videoSlug, srtSha) {
  var url = rawBase + '/talks/' + talkId + '/' + videoSlug + '/final/uk.srt';
  if (srtSha) url += '?v=' + srtSha.substring(0, 8);
  return url;
}

// --- buildManifest sha extraction logic (extracted) ---
function extractSrtSha(treeEntries) {
  var result = {};
  treeEntries.forEach(function(entry) {
    var m = entry.path.match(/^talks\/([^/]+)\/([^/]+)\/final\/uk\.srt$/);
    if (m) {
      if (!result[m[1]]) result[m[1]] = {};
      result[m[1]][m[2]] = entry.sha || '';
    }
  });
  return result;
}

// ============================================================
// Tests: formatLastModified
// ============================================================
describe('formatLastModified', () => {
  it('returns empty string for null/undefined', () => {
    assert.strictEqual(formatLastModified(null, Date.now()), '');
    assert.strictEqual(formatLastModified(undefined, Date.now()), '');
    assert.strictEqual(formatLastModified('', Date.now()), '');
  });

  it('returns empty string for invalid date', () => {
    assert.strictEqual(formatLastModified('not-a-date', Date.now()), '');
  });

  it('returns "щойно" for <1 minute ago', () => {
    var now = new Date('2026-04-08T10:00:00Z');
    var lastMod = 'Tue, 08 Apr 2026 10:00:00 GMT';
    assert.strictEqual(formatLastModified(lastMod, now), 'щойно');
  });

  it('returns "щойно" for 30 seconds ago', () => {
    var now = new Date('2026-04-08T10:00:30Z');
    var lastMod = 'Tue, 08 Apr 2026 10:00:00 GMT';
    assert.strictEqual(formatLastModified(lastMod, now), 'щойно');
  });

  it('returns minutes for 1-59 minutes', () => {
    var now = new Date('2026-04-08T10:05:00Z');
    var lastMod = 'Tue, 08 Apr 2026 10:00:00 GMT';
    assert.strictEqual(formatLastModified(lastMod, now), '5 хв тому');
  });

  it('returns minutes for exactly 1 minute', () => {
    var now = new Date('2026-04-08T10:01:00Z');
    var lastMod = 'Tue, 08 Apr 2026 10:00:00 GMT';
    assert.strictEqual(formatLastModified(lastMod, now), '1 хв тому');
  });

  it('returns hours for 1-23 hours', () => {
    var now = new Date('2026-04-08T13:00:00Z');
    var lastMod = 'Tue, 08 Apr 2026 10:00:00 GMT';
    assert.strictEqual(formatLastModified(lastMod, now), '3 год тому');
  });

  it('returns hours for exactly 1 hour', () => {
    var now = new Date('2026-04-08T11:00:00Z');
    var lastMod = 'Tue, 08 Apr 2026 10:00:00 GMT';
    assert.strictEqual(formatLastModified(lastMod, now), '1 год тому');
  });

  it('returns date for >24 hours', () => {
    var now = new Date('2026-04-10T10:00:00Z');
    var lastMod = 'Tue, 08 Apr 2026 10:00:00 GMT';
    var result = formatLastModified(lastMod, now);
    // Should contain "8" and a month abbreviation
    assert.ok(result.includes('8'), 'should contain day 8, got: ' + result);
  });
});

// ============================================================
// Tests: buildSrtUrl
// ============================================================
describe('buildSrtUrl', () => {
  var RAW = 'https://raw.githubusercontent.com/owner/repo/main';

  it('builds URL without sha', () => {
    var url = buildSrtUrl(RAW, '2001-07-29_Talk', 'Video-Slug', '');
    assert.strictEqual(url, RAW + '/talks/2001-07-29_Talk/Video-Slug/final/uk.srt');
  });

  it('builds URL without sha when null', () => {
    var url = buildSrtUrl(RAW, '2001-07-29_Talk', 'Video-Slug', null);
    assert.strictEqual(url, RAW + '/talks/2001-07-29_Talk/Video-Slug/final/uk.srt');
  });

  it('builds URL without sha when undefined', () => {
    var url = buildSrtUrl(RAW, '2001-07-29_Talk', 'Video-Slug', undefined);
    assert.strictEqual(url, RAW + '/talks/2001-07-29_Talk/Video-Slug/final/uk.srt');
  });

  it('appends sha cache-buster (first 8 chars)', () => {
    var url = buildSrtUrl(RAW, 'talk', 'video', 'abcdef1234567890abcdef');
    assert.strictEqual(url, RAW + '/talks/talk/video/final/uk.srt?v=abcdef12');
  });

  it('handles short sha', () => {
    var url = buildSrtUrl(RAW, 'talk', 'video', 'abc');
    assert.strictEqual(url, RAW + '/talks/talk/video/final/uk.srt?v=abc');
  });

  it('different sha produces different URL', () => {
    var url1 = buildSrtUrl(RAW, 'talk', 'video', 'aaaa1111');
    var url2 = buildSrtUrl(RAW, 'talk', 'video', 'bbbb2222');
    assert.notStrictEqual(url1, url2);
  });
});

// ============================================================
// Tests: extractSrtSha
// ============================================================
describe('extractSrtSha', () => {
  it('returns empty for no SRT entries', () => {
    var result = extractSrtSha([
      { path: 'talks/2001_Talk/meta.yaml', sha: 'aaa' },
      { path: 'talks/2001_Talk/transcript_en.txt', sha: 'bbb' },
    ]);
    assert.deepStrictEqual(result, {});
  });

  it('extracts sha for single SRT', () => {
    var result = extractSrtSha([
      { path: 'talks/2001_Talk/Video-1/final/uk.srt', sha: 'abc123' },
    ]);
    assert.deepStrictEqual(result, { '2001_Talk': { 'Video-1': 'abc123' } });
  });

  it('extracts sha for multiple videos in one talk', () => {
    var result = extractSrtSha([
      { path: 'talks/2001_Talk/Video-1/final/uk.srt', sha: 'sha1' },
      { path: 'talks/2001_Talk/Video-2/final/uk.srt', sha: 'sha2' },
    ]);
    assert.deepStrictEqual(result, {
      '2001_Talk': { 'Video-1': 'sha1', 'Video-2': 'sha2' }
    });
  });

  it('extracts sha for multiple talks', () => {
    var result = extractSrtSha([
      { path: 'talks/Talk-A/Vid/final/uk.srt', sha: 'sha_a' },
      { path: 'talks/Talk-B/Vid/final/uk.srt', sha: 'sha_b' },
    ]);
    assert.strictEqual(Object.keys(result).length, 2);
    assert.strictEqual(result['Talk-A']['Vid'], 'sha_a');
    assert.strictEqual(result['Talk-B']['Vid'], 'sha_b');
  });

  it('handles missing sha gracefully', () => {
    var result = extractSrtSha([
      { path: 'talks/Talk/Vid/final/uk.srt' },
    ]);
    assert.strictEqual(result['Talk']['Vid'], '');
  });

  it('ignores non-SRT files', () => {
    var result = extractSrtSha([
      { path: 'talks/Talk/Vid/final/en.srt', sha: 'xxx' },
      { path: 'talks/Talk/Vid/work/uk.map', sha: 'yyy' },
      { path: 'talks/Talk/Vid/final/uk.srt', sha: 'zzz' },
    ]);
    assert.strictEqual(Object.keys(result['Talk']).length, 1);
    assert.strictEqual(result['Talk']['Vid'], 'zzz');
  });
});

// ============================================================
// Tests: 304 cache scenario (lastModified preserved)
// ============================================================
describe('304 cache scenario', () => {
  // Simulate cache object from localStorage (old format, no lastModified)
  function makeOldCache() {
    return { etag: '"old-etag"', timestamp: Date.now() - 60000, talks: [] };
  }

  // Simulate cache with lastModified
  function makeNewCache() {
    return { etag: '"new-etag"', lastModified: 'Tue, 08 Apr 2026 10:00:00 GMT', timestamp: Date.now(), talks: [] };
  }

  it('old cache without lastModified returns empty label', () => {
    var cache = makeOldCache();
    // formatLastModified receives cache.lastModified which is undefined
    assert.strictEqual(formatLastModified(cache.lastModified, Date.now()), '');
  });

  it('new cache with lastModified returns valid label', () => {
    var cache = makeNewCache();
    var now = new Date('2026-04-08T10:05:00Z');
    assert.strictEqual(formatLastModified(cache.lastModified, now), '5 хв тому');
  });

  it('304 response should update lastModified on old cache', () => {
    // Simulate what happens on 304: we update cache.lastModified from response header
    var cache = makeOldCache();
    assert.strictEqual(cache.lastModified, undefined);

    // Simulate 304 handler
    var lm304 = 'Tue, 08 Apr 2026 12:00:00 GMT';
    if (lm304) cache.lastModified = lm304;

    assert.strictEqual(cache.lastModified, lm304);
    var now = new Date('2026-04-08T12:03:00Z');
    assert.strictEqual(formatLastModified(cache.lastModified, now), '3 хв тому');
  });

  it('cache-buster changes when sha changes', () => {
    var RAW = 'https://raw.githubusercontent.com/owner/repo/main';
    var url1 = buildSrtUrl(RAW, 'talk', 'video', 'aaa11111');
    var url2 = buildSrtUrl(RAW, 'talk', 'video', 'bbb22222');
    assert.notStrictEqual(url1, url2);
    // Both should have ?v= parameter
    assert.ok(url1.includes('?v=aaa11111'), url1);
    assert.ok(url2.includes('?v=bbb22222'), url2);
  });

  it('same sha produces same URL (cache hit)', () => {
    var RAW = 'https://raw.githubusercontent.com/owner/repo/main';
    var url1 = buildSrtUrl(RAW, 'talk', 'video', 'abc12345');
    var url2 = buildSrtUrl(RAW, 'talk', 'video', 'abc12345');
    assert.strictEqual(url1, url2);
  });
});

// ============================================================
// Tests: edge cases for freshness display
// ============================================================
describe('freshness display edge cases', () => {
  it('manifest without lastModified shows empty (graceful)', () => {
    assert.strictEqual(formatLastModified(undefined, Date.now()), '');
  });

  it('manifest with empty string lastModified shows empty', () => {
    assert.strictEqual(formatLastModified('', Date.now()), '');
  });

  it('exactly 59 minutes shows minutes not hours', () => {
    var now = new Date('2026-04-08T10:59:00Z');
    var lastMod = 'Tue, 08 Apr 2026 10:00:00 GMT';
    assert.strictEqual(formatLastModified(lastMod, now), '59 хв тому');
  });

  it('exactly 60 minutes shows 1 hour', () => {
    var now = new Date('2026-04-08T11:00:00Z');
    var lastMod = 'Tue, 08 Apr 2026 10:00:00 GMT';
    assert.strictEqual(formatLastModified(lastMod, now), '1 год тому');
  });

  it('exactly 23 hours shows hours not date', () => {
    var now = new Date('2026-04-09T09:00:00Z');
    var lastMod = 'Tue, 08 Apr 2026 10:00:00 GMT';
    assert.strictEqual(formatLastModified(lastMod, now), '23 год тому');
  });

  it('exactly 24 hours shows date', () => {
    var now = new Date('2026-04-09T10:00:00Z');
    var lastMod = 'Tue, 08 Apr 2026 10:00:00 GMT';
    var result = formatLastModified(lastMod, now);
    assert.ok(result.includes('8'), 'should show day 8, got: ' + result);
    assert.ok(!result.includes('год'), 'should not show hours, got: ' + result);
  });

  it('no sha means no cache-buster (first load or missing)', () => {
    var RAW = 'https://raw.githubusercontent.com/o/r/main';
    var url = buildSrtUrl(RAW, 'talk', 'video', '');
    assert.ok(!url.includes('?v='), 'should not have ?v= for empty sha');
    url = buildSrtUrl(RAW, 'talk', 'video', null);
    assert.ok(!url.includes('?v='), 'should not have ?v= for null sha');
  });
});

// ============================================================
// Tests: getSrtSha helper (lookup from talk object)
// ============================================================
function getSrtSha(talk, videoSlug) {
  return (talk && talk._srtSha && talk._srtSha[videoSlug]) || '';
}

describe('getSrtSha', () => {
  it('returns sha when present', () => {
    var talk = { _srtSha: { 'Video-1': 'abc123def456' } };
    assert.strictEqual(getSrtSha(talk, 'Video-1'), 'abc123def456');
  });

  it('returns empty when video not in map', () => {
    var talk = { _srtSha: { 'Video-1': 'abc123' } };
    assert.strictEqual(getSrtSha(talk, 'Video-2'), '');
  });

  it('returns empty when _srtSha is empty', () => {
    var talk = { _srtSha: {} };
    assert.strictEqual(getSrtSha(talk, 'Video-1'), '');
  });

  it('returns empty when _srtSha is missing', () => {
    var talk = {};
    assert.strictEqual(getSrtSha(talk, 'Video-1'), '');
  });

  it('returns empty when talk is null', () => {
    assert.strictEqual(getSrtSha(null, 'Video-1'), '');
  });

  it('returns empty when talk is undefined', () => {
    assert.strictEqual(getSrtSha(undefined, 'Video-1'), '');
  });
});

// ============================================================
// Tests: refreshManifest cache clearing logic
// ============================================================
describe('refreshManifest cache clearing', () => {
  it('deleting etag from cache forces fresh fetch', () => {
    var cache = { etag: '"old"', lastModified: 'Mon, 07 Apr 2026 10:00:00 GMT', timestamp: 1000, talks: [] };
    delete cache.etag;
    assert.strictEqual(cache.etag, undefined);
    assert.strictEqual(cache.lastModified, 'Mon, 07 Apr 2026 10:00:00 GMT'); // preserved
  });

  it('deleting etag from null cache does not throw', () => {
    var cache = null;
    assert.doesNotThrow(function() {
      if (cache) delete cache.etag;
    });
  });

  it('cache without etag sends no If-None-Match header', () => {
    var cache = { timestamp: 1000, talks: [] };
    var headers = {};
    if (cache && cache.etag) headers['If-None-Match'] = cache.etag;
    assert.strictEqual(Object.keys(headers).length, 0);
  });

  it('cache with etag sends If-None-Match header', () => {
    var cache = { etag: '"abc"', timestamp: 1000, talks: [] };
    var headers = {};
    if (cache && cache.etag) headers['If-None-Match'] = cache.etag;
    assert.strictEqual(headers['If-None-Match'], '"abc"');
  });
});

// ============================================================
// Tests: integration scenario (full flow)
// ============================================================
describe('full cache flow scenarios', () => {
  it('first visit: no cache, no sha, no lastModified', () => {
    var cache = null;
    var sha = getSrtSha(null, 'Video');
    var label = formatLastModified(cache ? cache.lastModified : undefined, Date.now());
    var url = buildSrtUrl('https://raw.gh.com/o/r/main', 'talk', 'Video', sha);

    assert.strictEqual(sha, '');
    assert.strictEqual(label, '');
    assert.ok(!url.includes('?v='));
  });

  it('after fresh load: sha present, lastModified set', () => {
    var cache = {
      etag: '"fresh"',
      lastModified: 'Tue, 08 Apr 2026 15:00:00 GMT',
      timestamp: Date.now(),
      talks: [{ id: 'talk', _srtSha: { 'Video': 'deadbeef12345678' } }]
    };
    var talk = cache.talks[0];
    var sha = getSrtSha(talk, 'Video');
    var now = new Date('2026-04-08T15:02:00Z');
    var label = formatLastModified(cache.lastModified, now);
    var url = buildSrtUrl('https://raw.gh.com/o/r/main', 'talk', 'Video', sha);

    assert.strictEqual(sha, 'deadbeef12345678');
    assert.strictEqual(label, '2 хв тому');
    assert.ok(url.includes('?v=deadbeef'));
  });

  it('after push: new sha, new lastModified, new URL', () => {
    // Before push
    var oldSha = 'aaaa1111bbbb2222';
    var urlBefore = buildSrtUrl('https://raw.gh.com/o/r/main', 'talk', 'Video', oldSha);

    // After push (sha changed)
    var newSha = 'cccc3333dddd4444';
    var urlAfter = buildSrtUrl('https://raw.gh.com/o/r/main', 'talk', 'Video', newSha);

    assert.notStrictEqual(urlBefore, urlAfter);
    assert.ok(urlBefore.includes('?v=aaaa1111'));
    assert.ok(urlAfter.includes('?v=cccc3333'));
  });

  it('304 with old cache gets lastModified updated', () => {
    var oldCache = { etag: '"old"', timestamp: 1000, talks: [] };
    // No lastModified field (old format)
    assert.strictEqual(formatLastModified(oldCache.lastModified, Date.now()), '');

    // 304 response updates it
    oldCache.lastModified = 'Tue, 08 Apr 2026 14:00:00 GMT';
    var now = new Date('2026-04-08T14:10:00Z');
    assert.strictEqual(formatLastModified(oldCache.lastModified, now), '10 хв тому');
  });
});
