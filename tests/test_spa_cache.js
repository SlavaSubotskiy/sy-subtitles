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

// --- extractTranscriptSha logic (extracted from buildManifest) ---
function extractTranscriptSha(treeEntries) {
  var result = {};
  treeEntries.forEach(function(entry) {
    var m = entry.path.match(/^talks\/([^/]+)\/transcript_([a-z][a-z_]*)\.txt$/);
    if (m) {
      if (!result[m[1]]) result[m[1]] = {};
      result[m[1]][m[2]] = entry.sha || '';
    }
  });
  return result;
}

// --- getTranscriptSha helper ---
function getTranscriptSha(talk, lang) {
  return (talk && talk._transcriptSha && talk._transcriptSha[lang]) || '';
}

// --- buildTranscriptUrl (mirrors buildSrtUrl pattern) ---
function buildTranscriptUrl(rawBase, talkId, lang, sha) {
  var url = rawBase + '/talks/' + talkId + '/transcript_' + lang + '.txt';
  if (sha) url += '?v=' + sha.substring(0, 8);
  return url;
}

// ============================================================
// Tests: extractTranscriptSha
// ============================================================
describe('extractTranscriptSha', () => {
  it('returns empty for no transcript entries', () => {
    var result = extractTranscriptSha([
      { path: 'talks/Talk/meta.yaml', sha: 'aaa' },
      { path: 'talks/Talk/Video/final/uk.srt', sha: 'bbb' },
    ]);
    assert.deepStrictEqual(result, {});
  });

  it('extracts sha for single transcript', () => {
    var result = extractTranscriptSha([
      { path: 'talks/Talk/transcript_en.txt', sha: 'en_sha' },
    ]);
    assert.deepStrictEqual(result, { 'Talk': { 'en': 'en_sha' } });
  });

  it('extracts sha for multiple languages', () => {
    var result = extractTranscriptSha([
      { path: 'talks/Talk/transcript_en.txt', sha: 'en_sha' },
      { path: 'talks/Talk/transcript_uk.txt', sha: 'uk_sha' },
      { path: 'talks/Talk/transcript_hi_corrected.txt', sha: 'hi_sha' },
    ]);
    assert.strictEqual(result['Talk']['en'], 'en_sha');
    assert.strictEqual(result['Talk']['uk'], 'uk_sha');
    assert.strictEqual(result['Talk']['hi_corrected'], 'hi_sha');
  });

  it('extracts sha for multiple talks', () => {
    var result = extractTranscriptSha([
      { path: 'talks/Talk-A/transcript_uk.txt', sha: 'sha_a' },
      { path: 'talks/Talk-B/transcript_uk.txt', sha: 'sha_b' },
    ]);
    assert.strictEqual(result['Talk-A']['uk'], 'sha_a');
    assert.strictEqual(result['Talk-B']['uk'], 'sha_b');
  });

  it('handles missing sha', () => {
    var result = extractTranscriptSha([
      { path: 'talks/Talk/transcript_en.txt' },
    ]);
    assert.strictEqual(result['Talk']['en'], '');
  });

  it('ignores non-transcript files', () => {
    var result = extractTranscriptSha([
      { path: 'talks/Talk/meta.yaml', sha: 'xxx' },
      { path: 'talks/Talk/Video/final/uk.srt', sha: 'yyy' },
      { path: 'talks/Talk/transcript_uk.txt', sha: 'zzz' },
    ]);
    assert.strictEqual(Object.keys(result['Talk']).length, 1);
    assert.strictEqual(result['Talk']['uk'], 'zzz');
  });
});

// ============================================================
// Tests: getTranscriptSha
// ============================================================
describe('getTranscriptSha', () => {
  it('returns sha when present', () => {
    var talk = { _transcriptSha: { 'uk': 'abc123' } };
    assert.strictEqual(getTranscriptSha(talk, 'uk'), 'abc123');
  });

  it('returns empty for missing language', () => {
    var talk = { _transcriptSha: { 'en': 'abc123' } };
    assert.strictEqual(getTranscriptSha(talk, 'uk'), '');
  });

  it('returns empty when _transcriptSha missing', () => {
    assert.strictEqual(getTranscriptSha({}, 'uk'), '');
  });

  it('returns empty for null talk', () => {
    assert.strictEqual(getTranscriptSha(null, 'uk'), '');
  });
});

// ============================================================
// Tests: buildTranscriptUrl
// ============================================================
describe('buildTranscriptUrl', () => {
  var RAW = 'https://raw.githubusercontent.com/owner/repo/main';

  it('builds URL without sha', () => {
    var url = buildTranscriptUrl(RAW, 'talk', 'uk', '');
    assert.strictEqual(url, RAW + '/talks/talk/transcript_uk.txt');
    assert.ok(!url.includes('?v='));
  });

  it('appends sha cache-buster', () => {
    var url = buildTranscriptUrl(RAW, 'talk', 'en', 'abcdef1234567890');
    assert.strictEqual(url, RAW + '/talks/talk/transcript_en.txt?v=abcdef12');
  });

  it('different sha produces different URL', () => {
    var url1 = buildTranscriptUrl(RAW, 'talk', 'uk', 'aaaa1111');
    var url2 = buildTranscriptUrl(RAW, 'talk', 'uk', 'bbbb2222');
    assert.notStrictEqual(url1, url2);
  });

  it('handles hi_corrected language code', () => {
    var url = buildTranscriptUrl(RAW, 'talk', 'hi_corrected', 'abc');
    assert.ok(url.includes('transcript_hi_corrected.txt'));
  });
});

// --- extractSrtLangs logic (extracted from buildManifest) ---
function extractSrtLangs(treeEntries) {
  var result = {};
  treeEntries.forEach(function(entry) {
    var m = entry.path.match(/^talks\/([^/]+)\/([^/]+)\/final\/([a-z]{2})\.srt$/);
    if (m) {
      var tid = m[1], slug = m[2], lang = m[3];
      if (!result[tid]) result[tid] = {};
      if (!result[tid][slug]) result[tid][slug] = [];
      if (result[tid][slug].indexOf(lang) === -1) result[tid][slug].push(lang);
    }
  });
  return result;
}

// --- buildSrtUrlWithLang (replaces old buildSrtUrl for multi-lang) ---
function buildSrtUrlWithLang(rawBase, talkId, videoSlug, lang, srtSha) {
  var shaKey = videoSlug + '/' + lang;
  var sha = (srtSha && srtSha[shaKey]) || '';
  var url = rawBase + '/talks/' + talkId + '/' + videoSlug + '/final/' + lang + '.srt';
  if (sha) url += '?v=' + sha.substring(0, 8);
  return url;
}

// ============================================================
// Tests: extractSrtLangs
// ============================================================
describe('extractSrtLangs', () => {
  it('returns empty for no SRT entries', () => {
    var result = extractSrtLangs([
      { path: 'talks/Talk/meta.yaml' },
    ]);
    assert.deepStrictEqual(result, {});
  });

  it('extracts single language', () => {
    var result = extractSrtLangs([
      { path: 'talks/Talk/Vid/final/uk.srt', sha: 'abc' },
    ]);
    assert.deepStrictEqual(result['Talk']['Vid'], ['uk']);
  });

  it('extracts multiple languages for same video', () => {
    var result = extractSrtLangs([
      { path: 'talks/Talk/Vid/final/uk.srt', sha: 'a' },
      { path: 'talks/Talk/Vid/final/hi.srt', sha: 'b' },
      { path: 'talks/Talk/Vid/final/en.srt', sha: 'c' },
    ]);
    var langs = result['Talk']['Vid'].sort();
    assert.deepStrictEqual(langs, ['en', 'hi', 'uk']);
  });

  it('separate languages per video slug', () => {
    var result = extractSrtLangs([
      { path: 'talks/Talk/Vid1/final/uk.srt', sha: 'a' },
      { path: 'talks/Talk/Vid2/final/hi.srt', sha: 'b' },
    ]);
    assert.deepStrictEqual(result['Talk']['Vid1'], ['uk']);
    assert.deepStrictEqual(result['Talk']['Vid2'], ['hi']);
  });

  it('no duplicates', () => {
    var result = extractSrtLangs([
      { path: 'talks/Talk/Vid/final/uk.srt', sha: 'a' },
      { path: 'talks/Talk/Vid/final/uk.srt', sha: 'b' },
    ]);
    assert.strictEqual(result['Talk']['Vid'].length, 1);
  });

  it('ignores non-srt files', () => {
    var result = extractSrtLangs([
      { path: 'talks/Talk/Vid/final/uk.srt', sha: 'a' },
      { path: 'talks/Talk/Vid/work/uk.map', sha: 'b' },
      { path: 'talks/Talk/Vid/final/report.txt', sha: 'c' },
    ]);
    assert.deepStrictEqual(result['Talk']['Vid'], ['uk']);
  });
});

// ============================================================
// Tests: buildSrtUrlWithLang
// ============================================================
describe('buildSrtUrlWithLang', () => {
  var RAW = 'https://raw.githubusercontent.com/o/r/main';

  it('builds uk URL', () => {
    var url = buildSrtUrlWithLang(RAW, 'talk', 'vid', 'uk', {});
    assert.ok(url.endsWith('/final/uk.srt'));
  });

  it('builds hi URL', () => {
    var url = buildSrtUrlWithLang(RAW, 'talk', 'vid', 'hi', {});
    assert.ok(url.endsWith('/final/hi.srt'));
  });

  it('appends sha for correct lang key', () => {
    var sha = { 'vid/uk': 'aaa11111', 'vid/hi': 'bbb22222' };
    var ukUrl = buildSrtUrlWithLang(RAW, 'talk', 'vid', 'uk', sha);
    var hiUrl = buildSrtUrlWithLang(RAW, 'talk', 'vid', 'hi', sha);
    assert.ok(ukUrl.includes('?v=aaa11111'));
    assert.ok(hiUrl.includes('?v=bbb22222'));
  });

  it('no sha when key missing', () => {
    var url = buildSrtUrlWithLang(RAW, 'talk', 'vid', 'en', { 'vid/uk': 'abc' });
    assert.ok(!url.includes('?v='));
  });

  it('no sha when srtSha is null', () => {
    var url = buildSrtUrlWithLang(RAW, 'talk', 'vid', 'uk', null);
    assert.ok(!url.includes('?v='));
  });
});

// ============================================================
// Tests: subtitle language selector visibility
// ============================================================
describe('subtitle language selector logic', () => {
  function shouldShowSelector(availLangs) {
    return availLangs.length > 1;
  }

  function getDefaultLang(availLangs) {
    return availLangs.indexOf('uk') !== -1 ? 'uk' : availLangs[0];
  }

  it('hides selector for single language', () => {
    assert.strictEqual(shouldShowSelector(['uk']), false);
  });

  it('shows selector for multiple languages', () => {
    assert.strictEqual(shouldShowSelector(['uk', 'hi']), true);
  });

  it('shows selector for three languages', () => {
    assert.strictEqual(shouldShowSelector(['uk', 'hi', 'en']), true);
  });

  it('default is uk when available', () => {
    assert.strictEqual(getDefaultLang(['hi', 'uk', 'en']), 'uk');
  });

  it('default is first when uk not available', () => {
    assert.strictEqual(getDefaultLang(['hi', 'en']), 'hi');
  });

  it('default for single language', () => {
    assert.strictEqual(getDefaultLang(['uk']), 'uk');
  });
});

// ============================================================
// Tests: SPA code integrity (no use-before-declare)
// ============================================================
describe('SPA code integrity', () => {
  var fs = require('fs');
  var html = fs.readFileSync('site/index.html', 'utf8');
  var lines = html.split('\n');

  it('var SPA = {} exists', () => {
    assert.ok(lines.some(l => l.includes('var SPA = {}')), 'var SPA = {} not found');
  });

  it('no SPA.xxx assignment in JS before var SPA = {}', () => {
    var inScript = false;
    var spaDeclared = false;
    var errors = [];
    lines.forEach((line, i) => {
      var s = line.trim();
      if (s.includes('<script>') || s.startsWith('<script ')) inScript = true;
      if (s.includes('</script>')) inScript = false;
      if (s.includes('var SPA = {}')) spaDeclared = true;
      if (inScript && !spaDeclared && s.startsWith('SPA.')) {
        errors.push('line ' + (i+1) + ': ' + s.substring(0, 60));
      }
    });
    assert.strictEqual(errors.length, 0, 'SPA used before declaration: ' + errors.join('; '));
  });

  it('APP_VERSION is a string number', () => {
    var m = html.match(/var APP_VERSION = '(\d+)'/);
    assert.ok(m, 'APP_VERSION not found');
    assert.ok(parseInt(m[1]) >= 1, 'APP_VERSION should be >= 1');
  });

  it('SW registration includes APP_VERSION', () => {
    assert.ok(html.includes("register('sw.js?v=' + APP_VERSION)"), 'SW registration should pass APP_VERSION');
  });

  it('all SPA.xxx in onclick handlers have matching definitions', () => {
    // Extract onclick SPA.xxx calls
    var onclickCalls = new Set();
    lines.forEach(line => {
      var ms = line.match(/onclick="SPA\.(\w+)\(/g);
      if (ms) ms.forEach(m => {
        var name = m.match(/SPA\.(\w+)/)[1];
        onclickCalls.add(name);
      });
    });
    // Extract SPA.xxx = function definitions
    var definitions = new Set();
    lines.forEach(line => {
      var m = line.match(/^SPA\.(\w+)\s*=/);
      if (m) definitions.add(m[1]);
    });
    var missing = [...onclickCalls].filter(c => !definitions.has(c));
    assert.strictEqual(missing.length, 0, 'onclick references undefined SPA methods: ' + missing.join(', '));
  });

  it('no duplicate SPA.xxx definitions', () => {
    var defs = {};
    lines.forEach((line, i) => {
      var m = line.match(/^SPA\.(\w+)\s*=\s*function/);
      if (m) {
        var name = m[1];
        if (defs[name]) {
          assert.fail('Duplicate SPA.' + name + ' at lines ' + defs[name] + ' and ' + (i+1));
        }
        defs[name] = i + 1;
      }
    });
  });
});

// ============================================================
// Tests: Service Worker caching strategy
// ============================================================

function swIsImmutable(url) {
  var patterns = ['cdn.jsdelivr.net', 'player.vimeo.com/api', '/icon.png'];
  return patterns.some(function(p) { return url.includes(p); });
}
function swIsApiOrRaw(url) {
  return url.includes('api.github.com') || url.includes('raw.githubusercontent.com');
}
function swIsNavigation(url) {
  return url.endsWith('/') || url.endsWith('/index.html') || url.includes('sy-subtitles/#');
}
function swGetStrategy(url) {
  if (swIsNavigation(url) || swIsApiOrRaw(url)) return 'network-first';
  if (swIsImmutable(url)) return 'cache-first';
  return 'network-first';
}
function swCacheName(version) {
  return 'sy-subtitles-v' + (version || '0');
}

describe('SW: isImmutable', () => {
  it('CDN js-yaml is immutable', () => assert.strictEqual(swIsImmutable('https://cdn.jsdelivr.net/npm/js-yaml@4/dist/js-yaml.min.js'), true));
  it('Vimeo player API is immutable', () => assert.strictEqual(swIsImmutable('https://player.vimeo.com/api/player.js'), true));
  it('icon.png is immutable', () => assert.strictEqual(swIsImmutable('https://site.github.io/sy-subtitles/icon.png'), true));
  it('index.html is NOT immutable', () => assert.strictEqual(swIsImmutable('https://site.github.io/sy-subtitles/index.html'), false));
  it('API is NOT immutable', () => assert.strictEqual(swIsImmutable('https://api.github.com/repos/foo'), false));
  it('raw content is NOT immutable', () => assert.strictEqual(swIsImmutable('https://raw.githubusercontent.com/foo/uk.srt'), false));
});

describe('SW: isApiOrRaw', () => {
  it('GitHub API', () => assert.strictEqual(swIsApiOrRaw('https://api.github.com/repos/foo'), true));
  it('raw.githubusercontent', () => assert.strictEqual(swIsApiOrRaw('https://raw.githubusercontent.com/foo/file.srt'), true));
  it('index.html is not API', () => assert.strictEqual(swIsApiOrRaw('https://site.github.io/sy-subtitles/'), false));
});

describe('SW: isNavigation', () => {
  it('root path', () => assert.strictEqual(swIsNavigation('https://site.github.io/sy-subtitles/'), true));
  it('index.html', () => assert.strictEqual(swIsNavigation('https://site.github.io/sy-subtitles/index.html'), true));
  it('hash route', () => assert.strictEqual(swIsNavigation('https://site.github.io/sy-subtitles/#/preview/talk/vid'), true));
  it('icon is NOT navigation', () => assert.strictEqual(swIsNavigation('https://site.github.io/sy-subtitles/icon.png'), false));
  it('CDN is NOT navigation', () => assert.strictEqual(swIsNavigation('https://cdn.jsdelivr.net/npm/js-yaml@4'), false));
});

describe('SW: caching strategy per URL', () => {
  it('index.html → network-first', () => assert.strictEqual(swGetStrategy('https://site.github.io/sy-subtitles/index.html'), 'network-first'));
  it('root → network-first', () => assert.strictEqual(swGetStrategy('https://site.github.io/sy-subtitles/'), 'network-first'));
  it('API → network-first', () => assert.strictEqual(swGetStrategy('https://api.github.com/repos/foo/git/trees/main'), 'network-first'));
  it('raw SRT → network-first', () => assert.strictEqual(swGetStrategy('https://raw.githubusercontent.com/foo/uk.srt'), 'network-first'));
  it('CDN lib → cache-first', () => assert.strictEqual(swGetStrategy('https://cdn.jsdelivr.net/npm/js-yaml@4/dist/js-yaml.min.js'), 'cache-first'));
  it('icon → cache-first', () => assert.strictEqual(swGetStrategy('https://site.github.io/sy-subtitles/icon.png'), 'cache-first'));
  it('Vimeo embed → network-first', () => assert.strictEqual(swGetStrategy('https://player.vimeo.com/video/12345'), 'network-first'));
  it('Vimeo player API → cache-first', () => assert.strictEqual(swGetStrategy('https://player.vimeo.com/api/player.js'), 'cache-first'));
});

describe('SW: cache name versioning', () => {
  it('derives from version param', () => assert.strictEqual(swCacheName('10'), 'sy-subtitles-v10'));
  it('defaults to v0 for null', () => assert.strictEqual(swCacheName(null), 'sy-subtitles-v0'));
  it('defaults to v0 for undefined', () => assert.strictEqual(swCacheName(undefined), 'sy-subtitles-v0'));
  it('different versions → different names', () => assert.notStrictEqual(swCacheName('9'), swCacheName('10')));
  it('same version → same name', () => assert.strictEqual(swCacheName('10'), swCacheName('10')));
});

describe('SW: version sync with APP_VERSION', () => {
  it('registration URL contains version', () => {
    var APP_VERSION = '10';
    var url = new URL('sw.js?v=' + APP_VERSION, 'https://example.com');
    assert.strictEqual(url.searchParams.get('v'), APP_VERSION);
  });
  it('SW extracts version from self.location', () => {
    var url = new URL('https://example.com/sw.js?v=10');
    assert.strictEqual(url.searchParams.get('v'), '10');
  });
  it('version bump triggers old cache deletion', () => {
    var oldName = swCacheName('9');
    var newName = swCacheName('10');
    var keys = [oldName, newName, 'unrelated-cache'];
    var toDelete = keys.filter(function(k) { return k !== newName; });
    assert.deepStrictEqual(toDelete, [oldName, 'unrelated-cache']);
  });
  it('no version in URL defaults safely', () => {
    var url = new URL('https://example.com/sw.js');
    var v = url.searchParams.get('v');
    assert.strictEqual(swCacheName(v), 'sy-subtitles-v0');
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

  it('transcript URLs get cache-busted after push', () => {
    var talk = { _transcriptSha: { 'uk': 'old_sha_1111', 'en': 'old_sha_2222' } };
    var ukUrl1 = buildTranscriptUrl('https://raw.gh.com/o/r/main', 'talk', 'uk', getTranscriptSha(talk, 'uk'));
    assert.ok(ukUrl1.includes('?v=old_sha_'));

    // Simulate push: sha changes
    talk._transcriptSha['uk'] = 'new_sha_3333';
    var ukUrl2 = buildTranscriptUrl('https://raw.gh.com/o/r/main', 'talk', 'uk', getTranscriptSha(talk, 'uk'));
    assert.ok(ukUrl2.includes('?v=new_sha_'));
    assert.notStrictEqual(ukUrl1, ukUrl2);

    // EN didn't change — same URL
    var enUrl = buildTranscriptUrl('https://raw.gh.com/o/r/main', 'talk', 'en', getTranscriptSha(talk, 'en'));
    assert.ok(enUrl.includes('?v=old_sha_'));
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

// ============================================================
// Tests: refresh result messaging
// ============================================================
function refreshResultMessage(oldEtag, newEtag) {
  var changed = newEtag !== oldEtag;
  return changed ? '✓ Оновлено!' : '✓ Вже актуально';
}

describe('refresh result messaging', () => {
  it('shows "Оновлено!" when etag changed', () => {
    assert.strictEqual(refreshResultMessage('"old-etag"', '"new-etag"'), '✓ Оновлено!');
  });

  it('shows "Вже актуально" when etag same', () => {
    assert.strictEqual(refreshResultMessage('"same"', '"same"'), '✓ Вже актуально');
  });

  it('shows "Оновлено!" when old etag was null (first load)', () => {
    assert.strictEqual(refreshResultMessage(null, '"new"'), '✓ Оновлено!');
  });

  it('shows "Оновлено!" when old etag was undefined', () => {
    assert.strictEqual(refreshResultMessage(undefined, '"new"'), '✓ Оновлено!');
  });

  it('shows "Вже актуально" when both null (edge case)', () => {
    assert.strictEqual(refreshResultMessage(null, null), '✓ Вже актуально');
  });
});
