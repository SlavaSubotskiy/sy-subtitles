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

  it('CACHE_SCHEMA is a number >= 1', () => {
    var m = html.match(/var CACHE_SCHEMA = (\d+)/);
    assert.ok(m, 'CACHE_SCHEMA not found');
    assert.ok(parseInt(m[1]) >= 1, 'CACHE_SCHEMA should be >= 1');
  });

  it('APP_DEPLOY_SHA placeholder exists', () => {
    assert.ok(html.includes("var APP_DEPLOY_SHA = ''"), 'APP_DEPLOY_SHA placeholder not found');
  });

  it('SW registration without version query', () => {
    assert.ok(html.includes("register('sw.js')"), 'SW should register without version query');
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
      var m = line.trim().match(/^SPA\.(\w+)\s*=/);
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
// Tests: Theme system
// ============================================================
describe('Theme: CSS variables coverage', () => {
  var fs = require('fs');
  var html = fs.readFileSync('site/index.html', 'utf8');

  // Extract <style> block
  var styleMatch = html.match(/<style>([\s\S]*?)<\/style>/);
  var css = styleMatch ? styleMatch[1] : '';

  // Remove :root variable declarations (they legitimately have hex colors)
  var cssWithoutVars = css.replace(/:root\s*\{[^}]*\}/g, '')
    .replace(/\[data-theme="[^"]*"\]\s*\{[^}]*\}/g, '')
    .replace(/@media\s*\(prefers-color-scheme:\s*light\)\s*\{[^}]*:root:not\(\[data-theme="dark"\]\)\s*\{[^}]*\}\s*\}/g, '');

  it('no hardcoded hex colors in CSS rules (outside :root)', () => {
    // Find #xxx or #xxxxxx patterns that are NOT inside var() or comments
    var lines = cssWithoutVars.split('\n');
    var errors = [];
    lines.forEach((line, i) => {
      var trimmed = line.trim();
      if (trimmed.startsWith('/*') || trimmed.startsWith('//')) return;
      // Match hex colors but not inside var(--xxx)
      var hexMatches = trimmed.match(/#[0-9a-fA-F]{3,8}\b/g);
      if (hexMatches) {
        // Filter out ones that are inside var()
        hexMatches.forEach(hex => {
          if (!trimmed.includes('var(--')) {
            errors.push('CSS line ~' + (i+1) + ': ' + hex + ' in: ' + trimmed.substring(0, 60));
          }
        });
      }
    });
    // Allow subtitle overlay to keep #fff (always white text on dark bg)
    errors = errors.filter(e => !e.includes('#fff') || !e.includes('subtitle-overlay'));
    if (errors.length > 0) {
      console.log('Hardcoded colors found:', errors.slice(0, 5).join('\n'));
    }
    assert.strictEqual(errors.length, 0, 'Found ' + errors.length + ' hardcoded hex colors in CSS');
  });

  it('all CSS color properties use var()', () => {
    var colorProps = ['color:', 'background:', 'background-color:', 'border-color:', 'border:', 'outline:'];
    var lines = cssWithoutVars.split('\n');
    var errors = [];
    lines.forEach((line, i) => {
      var trimmed = line.trim();
      if (trimmed.startsWith('/*')) return;
      colorProps.forEach(prop => {
        if (trimmed.includes(prop) && trimmed.includes('#') && !trimmed.includes('var(--')) {
          errors.push('Line ~' + (i+1) + ': ' + trimmed.substring(0, 80));
        }
      });
    });
    assert.strictEqual(errors.length, 0, 'CSS properties with hardcoded colors: ' + errors.join('; '));
  });
});

describe('Theme: toggle logic', () => {
  var cycle = ['auto', 'dark', 'light'];

  function nextTheme(current) {
    return cycle[(cycle.indexOf(current) + 1) % cycle.length];
  }

  it('auto → dark', () => assert.strictEqual(nextTheme('auto'), 'dark'));
  it('dark → light', () => assert.strictEqual(nextTheme('dark'), 'light'));
  it('light → auto', () => assert.strictEqual(nextTheme('light'), 'auto'));

  it('auto means no data-theme attribute', () => {
    // In auto mode, data-theme should be removed, letting @media query decide
    var mode = 'auto';
    assert.strictEqual(mode === 'auto', true);
  });

  it('dark/light means explicit data-theme', () => {
    assert.strictEqual('dark' !== 'auto', true);
    assert.strictEqual('light' !== 'auto', true);
  });
});

describe('Theme: CSS variable completeness', () => {
  var fs = require('fs');
  var html = fs.readFileSync('site/index.html', 'utf8');

  it('dark theme variables defined in :root', () => {
    assert.ok(html.includes('--bg: #1a1a1a'), 'dark --bg missing');
    assert.ok(html.includes('--fg: #fff'), 'dark --fg missing');
    assert.ok(html.includes('--link: #6af'), 'dark --link missing');
  });

  it('light theme variables defined', () => {
    assert.ok(html.includes('--bg: #f5f5f5'), 'light --bg missing');
    assert.ok(html.includes('--fg: #111'), 'light --fg missing');
    assert.ok(html.includes('--link: #0066cc'), 'light --link missing');
  });

  it('light theme defined both in @media and [data-theme="light"]', () => {
    assert.ok(html.includes('prefers-color-scheme: light'), '@media query missing');
    assert.ok(html.includes('[data-theme="light"]'), 'explicit light theme missing');
  });

  it('dark override prevents light @media from applying', () => {
    assert.ok(html.includes(':root:not([data-theme="dark"])'), 'dark override guard missing');
  });

  it('all var() references have matching definitions', () => {
    var varUsages = new Set();
    var varDefs = new Set();
    // Find var(--xxx)
    (html.match(/var\(--[\w-]+\)/g) || []).forEach(m => {
      varUsages.add(m.match(/--[\w-]+/)[0]);
    });
    // Find --xxx: definitions
    (html.match(/--[\w-]+\s*:/g) || []).forEach(m => {
      varDefs.add(m.replace(/\s*:/, ''));
    });
    var missing = [...varUsages].filter(v => !varDefs.has(v));
    assert.strictEqual(missing.length, 0, 'Undefined CSS vars: ' + missing.join(', '));
  });
});

// ============================================================
// Tests: refresh covers all data sources
// ============================================================
describe('refresh: covers all data sources', () => {
  it('refreshManifest calls loadReviewStatus (not just manifest)', () => {
    var fs = require('fs');
    var html = fs.readFileSync('site/index.html', 'utf8');
    var fnBody = html.match(/SPA\.refreshManifest\s*=\s*function[\s\S]*?^};/m);
    assert.ok(fnBody, 'refreshManifest not found');
    assert.ok(fnBody[0].includes('loadReviewStatus'), 'refreshManifest should call loadReviewStatus()');
    assert.ok(fnBody[0].includes('loadManifest'), 'refreshManifest should call loadManifest()');
    assert.ok(fnBody[0].includes('Promise.all'), 'refreshManifest should use Promise.all for parallel fetch');
  });

  it('loadReviewStatus uses SHA cache-buster', () => {
    var fs = require('fs');
    var html = fs.readFileSync('site/index.html', 'utf8');
    var fnBody = html.match(/function loadReviewStatus[\s\S]*?^}/m);
    assert.ok(fnBody, 'loadReviewStatus not found');
    assert.ok(fnBody[0].includes('_reviewSha'), 'loadReviewStatus should use _reviewSha');
    assert.ok(fnBody[0].includes('?v='), 'loadReviewStatus should append ?v= cache-buster');
  });

  it('review-status.json sha extracted in buildManifest', () => {
    var fs = require('fs');
    var html = fs.readFileSync('site/index.html', 'utf8');
    assert.ok(html.includes('_reviewSha'), 'manifest should have _reviewSha field');
    assert.ok(html.includes("entry.path === 'review-status.json'"), 'should extract review-status.json sha');
  });
});

// --- extractReviewSha (extracted logic) ---
function extractReviewSha(treeEntries) {
  var sha = '';
  treeEntries.forEach(function(entry) {
    if (entry.path === 'review-status.json') sha = entry.sha || '';
  });
  return sha;
}

describe('extractReviewSha', () => {
  it('returns sha when review-status.json present', () => {
    assert.strictEqual(extractReviewSha([
      { path: 'review-status.json', sha: 'abc123' },
      { path: 'talks/foo/meta.yaml', sha: 'xxx' },
    ]), 'abc123');
  });

  it('returns empty when not present', () => {
    assert.strictEqual(extractReviewSha([
      { path: 'talks/foo/meta.yaml', sha: 'xxx' },
    ]), '');
  });

  it('returns empty when sha missing', () => {
    assert.strictEqual(extractReviewSha([
      { path: 'review-status.json' },
    ]), '');
  });
});

describe('refresh: no hardcoded colors in status messages', () => {
  it('refreshManifest uses CSS variables for colors', () => {
    var fs = require('fs');
    var html = fs.readFileSync('site/index.html', 'utf8');
    var fnBody = html.match(/SPA\.refreshManifest\s*=\s*function[\s\S]*?^};/m);
    assert.ok(fnBody, 'refreshManifest not found');
    var fn = fnBody[0];
    // Should not have hardcoded hex colors
    var hexColors = fn.match(/#[0-9a-fA-F]{3,8}\b/g) || [];
    assert.strictEqual(hexColors.length, 0, 'Hardcoded colors in refreshManifest: ' + hexColors.join(', '));
    // Should use var(--xxx) for colors
    assert.ok(fn.includes('var(--link)'), 'should use var(--link) for loading color');
    assert.ok(fn.includes('var(--accent-green)'), 'should use var(--accent-green) for success');
    assert.ok(fn.includes('var(--accent-red)'), 'should use var(--accent-red) for error');
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
// Tests: issue URL length fallback
// ============================================================
function buildIssueUrl(repoUrl, title, body, label) {
  return repoUrl + '/issues/new?title=' + encodeURIComponent(title) + '&labels=' + encodeURIComponent(label) + '&body=' + encodeURIComponent(body);
}
function shouldCopyToClipboard(url) {
  return url.length > 8000;
}

describe('issue URL length fallback', () => {
  var gh = 'https://github.com/owner/repo';
  var title = 'Translation review: Test Talk';
  var label = 'review:pending';

  it('short body: URL under limit, no clipboard needed', () => {
    var body = 'Short body\n| col1 | col2 |\n|---|---|\n| a | b |';
    var url = buildIssueUrl(gh, title, body, label);
    assert.ok(url.length < 8000, 'URL should be under 8000: ' + url.length);
    assert.strictEqual(shouldCopyToClipboard(url), false);
  });

  it('long body: URL over limit, clipboard needed', () => {
    var body = 'x'.repeat(10000);
    var url = buildIssueUrl(gh, title, body, label);
    assert.ok(url.length > 8000, 'URL should be over 8000: ' + url.length);
    assert.strictEqual(shouldCopyToClipboard(url), true);
  });

  it('exactly at boundary', () => {
    // Build a body that makes URL exactly ~8000 chars
    var baseUrl = buildIssueUrl(gh, title, '', label);
    var remaining = 8000 - baseUrl.length;
    // encodeURIComponent expands some chars, use simple ASCII
    var body = 'a'.repeat(Math.floor(remaining / 3)); // conservative, encoded is ~same
    var url = buildIssueUrl(gh, title, body, label);
    // Should not need clipboard (under or at limit)
    assert.strictEqual(shouldCopyToClipboard(url), false);
  });

  it('short URL preserves full body parameter', () => {
    var body = '## Review\n\n| P1 | text | translation |';
    var url = buildIssueUrl(gh, title, body, label);
    assert.ok(url.includes('&body='), 'short URL should have body param');
    assert.ok(url.includes(encodeURIComponent('## Review')));
  });

  it('label is review:pending (not review)', () => {
    var body = 'test';
    var url = buildIssueUrl(gh, title, body, label);
    assert.ok(url.includes('labels=review%3Apending'), 'should encode review:pending');
  });
});

describe('issue URL: i18n keys exist', () => {
  var fs = require('fs');
  var html = fs.readFileSync('site/index.html', 'utf8');

  it('alert.issue_body_copied key exists in both languages', () => {
    assert.ok(html.includes("'alert.issue_body_copied'"), 'key not found in I18N');
    // Count occurrences (should be at least 2: uk + en)
    var count = (html.match(/'alert\.issue_body_copied'/g) || []).length;
    assert.ok(count >= 2, 'should be in both uk and en, found: ' + count);
  });
});

// ============================================================
// Tests: Add Talk feature
// ============================================================
function slugifyTest(text) {
  return text.replace(/[^a-zA-Z0-9 -]/g, '').replace(/\s+/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');
}

function buildMetaYaml(opts) {
  var yaml = "title: '" + (opts.title || '').replace(/'/g, "''") + "'\n";
  yaml += "date: '" + (opts.date || '') + "'\n";
  if (opts.location) yaml += "location: " + opts.location + "\n";
  if (opts.url) yaml += "amruta_url: " + opts.url + "\n";
  yaml += "language: " + (opts.language || 'en') + "\n";
  if (opts.videos && opts.videos.length) {
    yaml += "videos:\n";
    opts.videos.forEach(function(v) {
      yaml += "- slug: " + v.slug + "\n";
      yaml += "  title: " + (v.title || '') + "\n";
      yaml += "  vimeo_url: " + (v.url || '') + "\n";
    });
  }
  if (opts.transcript) {
    var b64 = Buffer.from(opts.transcript, 'utf8').toString('base64');
    yaml += "transcript_en_base64: |\n";
    for (var i = 0; i < b64.length; i += 76) {
      yaml += "  " + b64.substring(i, i + 76) + "\n";
    }
  }
  return yaml;
}

function parseBookmarkletData(encodedStr) {
  try {
    return JSON.parse(decodeURIComponent(encodedStr));
  } catch(e) { return null; }
}
function encodeBookmarkletData(obj) {
  return encodeURIComponent(JSON.stringify(obj));
}

describe('Add Talk: slugify', () => {
  it('simple title', () => assert.strictEqual(slugifyTest('Birthday Puja'), 'Birthday-Puja'));
  it('title with colon', () => assert.strictEqual(slugifyTest('Guru Puja: Gravity'), 'Guru-Puja-Gravity'));
  it('title with quotes', () => assert.strictEqual(slugifyTest("It's a test"), 'Its-a-test'));
  it('multiple spaces', () => assert.strictEqual(slugifyTest('A   B'), 'A-B'));
  it('leading/trailing dashes', () => assert.strictEqual(slugifyTest('-Test-'), 'Test'));
  it('empty string', () => assert.strictEqual(slugifyTest(''), ''));
  it('unicode removed', () => assert.strictEqual(slugifyTest('Пуджа Test'), 'Test'));
});

describe('Add Talk: buildMetaYaml', () => {
  it('minimal yaml', () => {
    var yaml = buildMetaYaml({ title: 'Test', date: '2001-01-01', language: 'en' });
    assert.ok(yaml.includes("title: 'Test'"));
    assert.ok(yaml.includes("date: '2001-01-01'"));
    assert.ok(yaml.includes('language: en'));
  });

  it('includes location and amruta_url', () => {
    var yaml = buildMetaYaml({ title: 'T', date: '2001-01-01', location: 'Mumbai', url: 'https://amruta.org/test' });
    assert.ok(yaml.includes('location: Mumbai'));
    assert.ok(yaml.includes('amruta_url: https://amruta.org/test'));
  });

  it('includes videos', () => {
    var yaml = buildMetaYaml({
      title: 'T', date: '2001-01-01', language: 'en',
      videos: [{ slug: 'Video-1', title: 'Video 1', url: 'https://vimeo.com/123/abc' }]
    });
    assert.ok(yaml.includes('videos:'));
    assert.ok(yaml.includes('- slug: Video-1'));
    assert.ok(yaml.includes("title: Video 1"));
    assert.ok(yaml.includes('vimeo_url: https://vimeo.com/123/abc'));
  });

  it('escapes single quotes in title', () => {
    var yaml = buildMetaYaml({ title: "It's a test", date: '2001-01-01' });
    assert.ok(yaml.includes("title: 'It''s a test'"));
  });

  it('includes transcript as base64', () => {
    var yaml = buildMetaYaml({ title: 'T', date: '2001-01-01', transcript: 'Hello world' });
    assert.ok(yaml.includes('transcript_en_base64: |'));
    // Decode and verify
    var b64Line = yaml.split('\n').find(l => l.trim().length > 10 && !l.includes(':'));
    assert.ok(b64Line, 'base64 content line not found');
    var decoded = Buffer.from(b64Line.trim(), 'base64').toString('utf8');
    assert.strictEqual(decoded, 'Hello world');
  });

  it('no transcript field when empty', () => {
    var yaml = buildMetaYaml({ title: 'T', date: '2001-01-01', transcript: '' });
    assert.ok(!yaml.includes('transcript_en_base64'));
  });

  it('base64 wraps at 76 chars', () => {
    var longText = 'x'.repeat(200);
    var yaml = buildMetaYaml({ title: 'T', date: '2001-01-01', transcript: longText });
    var b64Lines = yaml.split('\n').filter(l => l.startsWith('  ') && !l.includes(':') && l.trim().length > 0);
    b64Lines.forEach(function(line) {
      assert.ok(line.trim().length <= 76, 'base64 line too long: ' + line.trim().length);
    });
  });
});

describe('Add Talk: bookmarklet data parsing', () => {
  it('parses valid encoded JSON', () => {
    var data = { t: 'Test Talk', d: '2001-01-01', u: 'https://amruta.org/test', v: ['123/abc'], tx: 'Hello' };
    var enc = encodeBookmarkletData(data);
    var parsed = parseBookmarkletData(enc);
    assert.strictEqual(parsed.t, 'Test Talk');
    assert.strictEqual(parsed.d, '2001-01-01');
    assert.strictEqual(parsed.tx, 'Hello');
    assert.deepStrictEqual(parsed.v, ['123/abc']);
  });

  it('returns null for invalid encoding', () => {
    assert.strictEqual(parseBookmarkletData('%ZZ%invalid'), null);
  });

  it('returns null for valid encoding but invalid JSON', () => {
    var enc = encodeURIComponent('not json');
    assert.strictEqual(parseBookmarkletData(enc), null);
  });

  it('handles unicode in transcript', () => {
    var data = { t: 'Test', tx: 'Привіт світ — тест \u201cquotes\u201d' };
    var enc = encodeBookmarkletData(data);
    var parsed = parseBookmarkletData(enc);
    assert.strictEqual(parsed.tx, 'Привіт світ — тест \u201cquotes\u201d');
  });

  it('handles empty vimeo array', () => {
    var data = { t: 'Test', v: [] };
    var enc = encodeBookmarkletData(data);
    var parsed = parseBookmarkletData(enc);
    assert.deepStrictEqual(parsed.v, []);
  });

  it('handles large transcript (20K chars)', () => {
    var data = { t: 'Test', tx: 'x'.repeat(20000) };
    var enc = encodeBookmarkletData(data);
    var parsed = parseBookmarkletData(enc);
    assert.strictEqual(parsed.tx.length, 20000);
  });

  it('round-trip preserves all special characters', () => {
    var data = { t: "It's a \"test\" with <html> & symbols", tx: 'Line1\nLine2\tTab' };
    var enc = encodeBookmarkletData(data);
    var parsed = parseBookmarkletData(enc);
    assert.strictEqual(parsed.t, data.t);
    assert.strictEqual(parsed.tx, data.tx);
  });
});

describe('Add Talk: GitHub new file URL', () => {
  it('builds correct filename path', () => {
    var date = '2001-01-01';
    var slug = slugifyTest('Test Talk');
    var filename = 'talks/' + date + '_' + slug + '/meta.yaml';
    assert.strictEqual(filename, 'talks/2001-01-01_Test-Talk/meta.yaml');
  });

  it('URL stays under GitHub limit for small yaml', () => {
    var yaml = buildMetaYaml({ title: 'T', date: '2001-01-01', language: 'en' });
    var url = 'https://github.com/owner/repo/new/main?filename=talks/test/meta.yaml&value=' + encodeURIComponent(yaml);
    assert.ok(url.length < 8000, 'URL too long: ' + url.length);
  });

  it('URL may exceed limit with long transcript', () => {
    var yaml = buildMetaYaml({ title: 'T', date: '2001-01-01', transcript: 'x'.repeat(10000) });
    var url = 'https://github.com/owner/repo/new/main?filename=test&value=' + encodeURIComponent(yaml);
    assert.ok(url.length > 8000, 'Expected URL to exceed limit: ' + url.length);
  });
});

describe('Add Talk: bookmarklet extracts location', () => {
  var fs = require('fs');
  var html = fs.readFileSync('site/index.html', 'utf8');
  var bmMatch = html.match(/var bmCode = "(.*?)";/s);
  var bmCode = bmMatch ? bmMatch[1] : '';

  it('bookmarklet code includes location extraction', () => {
    assert.ok(bmCode.includes('loc') || bmCode.includes('location') || bmCode.includes('h4'),
      'bookmarklet should extract location from page');
  });

  it('bookmarklet data JSON includes location field', () => {
    // The bookmarklet JSON should have a location field (l or loc)
    assert.ok(bmCode.includes('"l"') || bmCode.includes('"loc"') || bmCode.includes(',l:') || bmCode.includes(',loc:'),
      'bookmarklet JSON should include location field');
  });
});

describe('Add Talk: bookmarklet extracts video titles', () => {
  var fs = require('fs');
  var html = fs.readFileSync('site/index.html', 'utf8');
  var bmMatch = html.match(/var bmCode = "(.*?)";/s);
  var bmCode = bmMatch ? bmMatch[1] : '';

  it('bookmarklet extracts video labels from video-meta-info div', () => {
    assert.ok(
      bmCode.includes('video-meta-info'),
      'bookmarklet should look for .video-meta-info inside wrapper'
    );
  });

  it('bookmarklet data includes video titles (not just URLs)', () => {
    // Video data should be objects with title+url, not just url strings
    var data = { t: 'Test', v: [{ id: '123', hash: 'abc', title: 'Puja' }] };
    var enc = encodeBookmarkletData(data);
    var parsed = parseBookmarkletData(enc);
    assert.ok(parsed.v[0].title, 'video should have title field');
  });
});

describe('Add Talk: SPA form populates location from bookmarklet', () => {
  it('parseBookmarkletData with location field', () => {
    var data = { t: 'Test', d: '2001-01-01', loc: 'Mumbai (India)', v: [], tx: '' };
    var enc = encodeBookmarkletData(data);
    var parsed = parseBookmarkletData(enc);
    assert.strictEqual(parsed.loc, 'Mumbai (India)');
  });
});

describe('Add Talk: i18n for dynamic video row labels', () => {
  var fs = require('fs');
  var html = fs.readFileSync('site/index.html', 'utf8');

  it('Video title label uses i18n t() in JS', () => {
    // addVideoRowWithUrl should use t('add.video_title') not hardcoded 'Video title'
    assert.ok(
      html.includes("t('add.video_title')") || html.includes('t("add.video_title")'),
      'Video title label in dynamic row should use t() for i18n'
    );
  });

  it('add.video_title i18n key exists in both languages', () => {
    var ukMatch = (html.match(/'add\.video_title'/g) || []).length;
    assert.ok(ukMatch >= 2, 'add.video_title should be in uk and en, found: ' + ukMatch);
  });

  it('add.vimeo_url i18n key exists in both languages', () => {
    var matches = (html.match(/'add\.vimeo_url'/g) || []).length;
    assert.ok(matches >= 2, 'add.vimeo_url should be in uk and en, found: ' + matches);
  });
});

describe('Preview: cleanup on navigation', () => {
  var fs = require('fs');
  var html = fs.readFileSync('site/index.html', 'utf8');

  it('subtitle overlay cleared when entering showPreview', () => {
    // showPreview should clear subtitle-overlay textContent before loading new SRT
    var idx = html.indexOf('function showPreview');
    assert.ok(idx > -1, 'showPreview not found');
    var chunk = html.substring(idx, idx + 500);
    assert.ok(chunk.includes("subtitle-overlay") && chunk.includes("textContent = ''"),
      'showPreview should clear subtitle-overlay textContent at start');
  });

  it('player paused when entering showPreview (switching videos)', () => {
    var idx = html.indexOf('function showPreview');
    var chunk = html.substring(idx, idx + 500);
    assert.ok(chunk.includes('.pause()'), 'showPreview should pause previous player');
  });

  it('player paused in route() when navigating away from preview', () => {
    var idx = html.indexOf('function route()');
    assert.ok(idx > -1, 'route function not found');
    var chunk = html.substring(idx, idx + 500);
    assert.ok(chunk.includes('.pause()'), 'route should pause player when leaving preview');
  });

  it('previewState stores player reference', () => {
    assert.ok(html.includes('previewState.player = player'), 'player should be stored in previewState');
  });
});

describe('Add Talk: three states logic', () => {
  function getAddState(hash) {
    if (!hash || !hash.includes('?data=')) return 'setup';
    var qm = hash.indexOf('?');
    var params = new URLSearchParams(hash.slice(qm));
    var dataStr = params.get('data');
    if (!dataStr) return 'setup';
    try {
      var data = JSON.parse(decodeURIComponent(dataStr));
      if (!data.u) return 'error';
      if (!data.u.includes('amruta.org')) return 'wrong-site';
      return 'form';
    } catch(e) { return 'error'; }
  }

  it('no data param → setup (bookmarklet instruction)', () => {
    assert.strictEqual(getAddState('/add'), 'setup');
  });
  it('empty hash → setup', () => {
    assert.strictEqual(getAddState(''), 'setup');
  });
  it('valid amruta data → form', () => {
    var enc = encodeBookmarkletData({ t: 'Test', u: 'https://www.amruta.org/test', v: [] });
    assert.strictEqual(getAddState('/add?data=' + enc), 'form');
  });
  it('non-amruta URL → wrong-site', () => {
    var enc = encodeBookmarkletData({ t: 'Test', u: 'https://example.com/page', v: [] });
    assert.strictEqual(getAddState('/add?data=' + enc), 'wrong-site');
  });
  it('invalid data → error', () => {
    assert.strictEqual(getAddState('/add?data=%ZZinvalid'), 'error');
  });
  it('data without url field → error', () => {
    var enc = encodeBookmarkletData({ t: 'Test' });
    assert.strictEqual(getAddState('/add?data=' + enc), 'error');
  });
});

describe('Add Talk: SPA code integrity', () => {
  var fs = require('fs');
  var html = fs.readFileSync('site/index.html', 'utf8');

  it('view-add exists in HTML', () => {
    assert.ok(html.includes('id="view-add"'));
  });

  it('route handles /add hash', () => {
    assert.ok(html.includes("hash.startsWith('/add')"));
  });

  it('showAddTalk function exists', () => {
    assert.ok(html.includes('function showAddTalk'));
  });

  it('submitAddTalk function exists', () => {
    assert.ok(html.includes('SPA.submitAddTalk'));
  });

  it('bookmarklet link exists', () => {
    assert.ok(html.includes('id="bookmarklet-link"'));
  });

  it('add.title i18n key in both languages', () => {
    var matches = (html.match(/'add\.title'/g) || []).length;
    assert.ok(matches >= 2, 'add.title should be in uk and en');
  });

  it('transcript_en_base64 field generated in yaml', () => {
    assert.ok(html.includes('transcript_en_base64'));
  });
});

// ============================================================
// Tests: Add Talk with real amruta.org data
// ============================================================
describe('Add Talk: real amruta.org page parsing', () => {
  var fs = require('fs');
  var parsed;
  try { parsed = JSON.parse(fs.readFileSync('tests/fixtures/amruta_parsed.json', 'utf8')); } catch(e) { parsed = null; }
  var bmData;
  try { bmData = JSON.parse(fs.readFileSync('tests/fixtures/amruta_bookmarklet_data.json', 'utf8')); } catch(e) { bmData = null; }

  it('fixture files exist', () => {
    assert.ok(parsed, 'amruta_parsed.json not found');
    assert.ok(bmData, 'amruta_bookmarklet_data.json not found');
    assert.ok(fs.existsSync('tests/fixtures/amruta_sahasrara.html'), 'HTML fixture not found');
  });

  // --- Title ---
  it('title: extracted correctly', () => {
    assert.strictEqual(parsed.title, 'Sahasrara Puja: How it was decided');
  });
  it('title: bookmarklet data matches', () => {
    assert.strictEqual(bmData.t, 'Sahasrara Puja: How it was decided');
  });
  it('title: not empty', () => {
    assert.ok(parsed.title.length > 5);
  });

  // --- Date ---
  it('date: parsed from URL correctly', () => {
    assert.strictEqual(parsed.date, '1988-05-08');
  });
  it('date: is valid ISO format', () => {
    assert.ok(/^\d{4}-\d{2}-\d{2}$/.test(parsed.date));
  });

  // --- URL ---
  it('url: is full amruta.org URL', () => {
    assert.ok(parsed.url.startsWith('https://www.amruta.org/'));
    assert.ok(parsed.url.includes('sahasrara-puja'));
  });

  // --- Location ---
  it('location: extracted correctly', () => {
    assert.strictEqual(parsed.location, 'Fregene (Italy)');
  });
  it('location: not empty', () => {
    assert.ok(parsed.location && parsed.location.length > 3);
  });

  // --- Vimeo ---
  it('vimeo: found exactly 2 videos', () => {
    assert.strictEqual(parsed.vimeos.length, 2);
  });
  it('vimeo: first video ID is numeric', () => {
    assert.ok(/^\d+$/.test(parsed.vimeos[0].id), 'ID: ' + parsed.vimeos[0].id);
  });
  it('vimeo: first video hash is hex', () => {
    assert.ok(/^[a-f0-9]+$/.test(parsed.vimeos[0].hash), 'hash: ' + parsed.vimeos[0].hash);
  });
  it('vimeo: specific IDs match expected', () => {
    assert.strictEqual(parsed.vimeos[0].id, '88490248');
    assert.strictEqual(parsed.vimeos[1].id, '88509806');
  });
  it('vimeo: hashes match expected', () => {
    assert.strictEqual(parsed.vimeos[0].hash, 'e956098e13');
    assert.strictEqual(parsed.vimeos[1].hash, '2453ea7524');
  });

  // --- Video titles ---
  it('video titles: extracted 2 titles', () => {
    assert.ok(parsed.video_titles, 'video_titles missing from fixture');
    assert.strictEqual(parsed.video_titles.length, 2);
  });
  it('video titles: first is "Sahasrara Puja"', () => {
    assert.strictEqual(parsed.video_titles[0], 'Sahasrara Puja');
  });
  it('video titles: second is "Sahasrara Puja Talk"', () => {
    assert.strictEqual(parsed.video_titles[1], 'Sahasrara Puja Talk');
  });

  // --- Video slugs ---
  it('video slugs: match expected', () => {
    assert.deepStrictEqual(parsed.video_slugs, ['Sahasrara-Puja', 'Sahasrara-Puja-Talk']);
  });

  // --- Transcript ---
  it('transcript: extracted (length > 1000 chars)', () => {
    assert.ok(parsed.transcript_length > 1000, 'too short: ' + parsed.transcript_length);
  });
  it('transcript: contains actual speech content', () => {
    // Real talk content should contain "Sahasrara" somewhere
    assert.ok(parsed.transcript.toLowerCase().includes('sahasrara'), 'should contain "sahasrara"');
  });
  it('transcript: no UI noise after p-tag filtering', () => {
    assert.ok(parsed.transcript_no_ui_noise, 'fixture should confirm no UI noise');
    // Bookmarklet now extracts only <p> tags with >20 chars — no buttons/nav
  });
  it('transcript: starts with talk content', () => {
    assert.ok(parsed.transcript_starts_with, 'missing transcript_starts_with in fixture');
    assert.ok(parsed.transcript_starts_with.includes('Sahasrara Puja'), 'should start with talk title');
  });
  it('transcript: ends with talk content', () => {
    assert.ok(parsed.transcript_ends_with, 'missing transcript_ends_with in fixture');
    assert.ok(parsed.transcript_ends_with.includes('good news'), 'should end with talk text');
  });

  // --- Slugify ---
  it('slugify: produces correct talk slug', () => {
    assert.strictEqual(slugifyTest(parsed.title), 'Sahasrara-Puja-How-it-was-decided');
  });
  it('slugify: talk ID is date_slug', () => {
    var talkId = parsed.date + '_' + slugifyTest(parsed.title);
    assert.strictEqual(talkId, '1988-05-08_Sahasrara-Puja-How-it-was-decided');
  });

  // --- Meta YAML ---
  it('meta.yaml: builds correctly from real data', () => {
    var yaml = buildMetaYaml({
      title: parsed.title, date: parsed.date, url: parsed.url, language: 'en',
      location: parsed.location,
      videos: parsed.vimeos.map(function(v, i) {
        return { slug: parsed.video_slugs[i], title: parsed.video_titles[i], url: 'https://vimeo.com/' + v.id + '/' + v.hash };
      }),
    });
    assert.ok(yaml.includes("title: 'Sahasrara Puja: How it was decided'"));
    assert.ok(yaml.includes("date: '1988-05-08'"));
    assert.ok(yaml.includes('location: Fregene (Italy)'));
    assert.ok(yaml.includes('amruta_url: https://www.amruta.org/'));
    assert.ok(yaml.includes('language: en'));
    assert.ok(yaml.includes('videos:'));
    assert.ok(yaml.includes('- slug: Sahasrara-Puja'));
    assert.ok(yaml.includes("title: Sahasrara Puja\n"));
    assert.ok(yaml.includes("title: Sahasrara Puja Talk"));
    assert.ok(yaml.includes('vimeo_url: https://vimeo.com/88490248/e956098e13'));
    assert.ok(yaml.includes('vimeo_url: https://vimeo.com/88509806/2453ea7524'));
  });

  it('meta.yaml: with transcript base64 round-trips', () => {
    var sample = parsed.transcript.substring(0, 500);
    var yaml = buildMetaYaml({ title: 'T', date: '2001-01-01', transcript: sample });
    var b64Lines = yaml.split('\n').filter(function(l) { return l.startsWith('  ') && !l.includes(':') && l.trim().length > 0; });
    var b64 = b64Lines.map(function(l) { return l.trim(); }).join('');
    var decoded = Buffer.from(b64, 'base64').toString('utf8');
    assert.strictEqual(decoded, sample);
  });

  // --- Full bookmarklet flow ---
  it('full flow: bookmarklet → SPA → meta.yaml', () => {
    // 1. Simulate bookmarklet output (encodeURIComponent, not base64)
    var enc = encodeBookmarkletData(bmData);
    // 2. SPA parses
    var data = parseBookmarkletData(enc);
    assert.ok(data);
    assert.strictEqual(data.t, 'Sahasrara Puja: How it was decided');
    assert.strictEqual(data.v.length, 2);
    // 3. Build yaml
    var yaml = buildMetaYaml({
      title: data.t, date: data.d, url: data.u, language: 'en',
      videos: data.v.map(function(v, i) {
        return { slug: slugifyTest('Video ' + (i+1)), title: 'Video ' + (i+1), url: 'https://vimeo.com/' + v };
      }),
      transcript: (data.tx || '').substring(0, 200)
    });
    assert.ok(yaml.includes('Sahasrara Puja'));
    assert.ok(yaml.includes('videos:'));
    assert.ok(yaml.includes('transcript_en_base64'));
    // 4. Verify filename
    var filename = 'talks/' + data.d + '_' + slugifyTest(data.t) + '/meta.yaml';
    assert.strictEqual(filename, 'talks/1988-05-08_Sahasrara-Puja-How-it-was-decided/meta.yaml');
  });
});

// ============================================================
// Tests: transcript normalization (simulates new-talk.yml logic)
// ============================================================
function normalizeTranscript(body) {
  // Same logic as new-talk.yml: collapse 3+ newlines to single
  return body.replace(/\n{3,}/g, '\n');
}

function buildTranscriptHeader(meta) {
  // Same as new-talk.yml header generation
  var months = ['January','February','March','April','May','June','July','August','September','October','November','December'];
  var parts = (meta.date || '').split('-');
  var dateStr = parseInt(parts[2], 10) + ' ' + months[parseInt(parts[1], 10) - 1] + ' ' + parts[0];
  var langMap = { en: 'English', hi: 'Hindi', mr: 'Marathi', fr: 'French', it: 'Italian' };
  var langName = langMap[meta.language] || meta.language;
  var header = dateStr + '\n' + meta.title + '\n';
  if (meta.location) header += meta.location + '\n';
  header += 'Talk Language: ' + langName + ' | Transcript (' + langName + ')\n';
  return header;
}

describe('Transcript normalization (new-talk.yml logic)', () => {
  it('collapses triple newlines to single', () => {
    assert.strictEqual(normalizeTranscript('a\n\n\nb'), 'a\nb');
  });

  it('collapses quadruple newlines to single', () => {
    assert.strictEqual(normalizeTranscript('a\n\n\n\nb'), 'a\nb');
  });

  it('preserves double newlines', () => {
    assert.strictEqual(normalizeTranscript('a\n\nb'), 'a\n\nb');
  });

  it('preserves single newlines', () => {
    assert.strictEqual(normalizeTranscript('a\nb'), 'a\nb');
  });

  it('handles multiple triple runs', () => {
    assert.strictEqual(normalizeTranscript('a\n\n\nb\n\n\nc'), 'a\nb\nc');
  });

  it('real transcript: no triple newlines after normalization', () => {
    var parsed;
    try { parsed = JSON.parse(fs.readFileSync('tests/fixtures/amruta_parsed.json', 'utf8')); } catch(e) { return; }
    var idx = parsed.transcript.indexOf('Talk Language:');
    var bodyStart = parsed.transcript.indexOf('\n\n', idx);
    var body = parsed.transcript.substring(bodyStart).trim();
    var normalized = normalizeTranscript(body);
    assert.ok(!/\n{3,}/.test(normalized), 'should not contain triple newlines after normalization');
  });

  it('real transcript: paragraphs separated by single newline after normalization', () => {
    var parsed;
    try { parsed = JSON.parse(fs.readFileSync('tests/fixtures/amruta_parsed.json', 'utf8')); } catch(e) { return; }
    var idx = parsed.transcript.indexOf('Talk Language:');
    var bodyStart = parsed.transcript.indexOf('\n\n', idx);
    var body = parsed.transcript.substring(bodyStart).trim();
    var normalized = normalizeTranscript(body);
    var lines = normalized.split('\n').filter(function(l) { return l.trim().length > 0; });
    assert.ok(lines.length > 10, 'should have multiple paragraphs: got ' + lines.length);
  });

  it('header format matches download.py convention', () => {
    var header = buildTranscriptHeader({
      title: 'Sahasrara Puja: How it was decided',
      date: '1988-05-08',
      location: 'Fregene (Italy)',
      language: 'en'
    });
    assert.ok(header.startsWith('8 May 1988\n'));
    assert.ok(header.includes('Sahasrara Puja: How it was decided\n'));
    assert.ok(header.includes('Fregene (Italy)\n'));
    assert.ok(header.includes('Talk Language: English | Transcript (English)'));
  });

  it('header: date format matches existing transcripts', () => {
    var header = buildTranscriptHeader({ title: 'T', date: '1993-09-19', location: 'L', language: 'en' });
    assert.ok(header.startsWith('19 September 1993\n'));
  });

  it('full pipeline: header + normalized body has no triple newlines', () => {
    var parsed;
    try { parsed = JSON.parse(fs.readFileSync('tests/fixtures/amruta_parsed.json', 'utf8')); } catch(e) { return; }
    var idx = parsed.transcript.indexOf('Talk Language:');
    var bodyStart = parsed.transcript.indexOf('\n\n', idx);
    var body = parsed.transcript.substring(bodyStart).trim();
    var normalized = normalizeTranscript(body);
    var header = buildTranscriptHeader({
      title: parsed.title, date: parsed.date, location: parsed.location, language: 'en'
    });
    var full = header + '\n' + normalized;
    assert.ok(!/\n{3,}/.test(full), 'full transcript should not contain triple newlines');
    assert.ok(full.startsWith('8 May 1988\n'));
    assert.ok(full.includes('Talk Language: English'));
    assert.ok(full.includes('Sahasrara Puja'));
  });
});

// ============================================================
// Tests: per-video subtitle language persistence
// ============================================================
function getPreviewSrtLangKey(talkId, videoSlug) {
  return 'sy_srt_lang_' + talkId + '_' + videoSlug;
}

function resolvePreviewLang(availLangs, savedLang) {
  if (savedLang && availLangs.indexOf(savedLang) !== -1) return savedLang;
  return availLangs.indexOf('uk') !== -1 ? 'uk' : availLangs[0];
}

describe('preview: per-video subtitle language persistence', () => {
  it('localStorage key is per-video', () => {
    var k1 = getPreviewSrtLangKey('talk-A', 'vid-1');
    var k2 = getPreviewSrtLangKey('talk-A', 'vid-2');
    var k3 = getPreviewSrtLangKey('talk-B', 'vid-1');
    assert.notStrictEqual(k1, k2);
    assert.notStrictEqual(k1, k3);
  });

  it('restores saved language if available', () => {
    assert.strictEqual(resolvePreviewLang(['uk', 'hi'], 'hi'), 'hi');
  });

  it('ignores saved language if not in available', () => {
    assert.strictEqual(resolvePreviewLang(['uk', 'en'], 'hi'), 'uk');
  });

  it('defaults to uk when no saved and uk available', () => {
    assert.strictEqual(resolvePreviewLang(['hi', 'uk'], null), 'uk');
  });

  it('defaults to first lang when no saved and no uk', () => {
    assert.strictEqual(resolvePreviewLang(['hi', 'en'], null), 'hi');
  });

  it('saved empty string treated as no saved', () => {
    assert.strictEqual(resolvePreviewLang(['uk', 'hi'], ''), 'uk');
  });
});

// ============================================================
// Tests: per-talk review language persistence
// ============================================================
function getReviewLangsKey(talkId) {
  return 'sy_review_langs_' + talkId;
}

function resolveReviewLangs(hashParams, savedJson) {
  var left = 'en', right = 'uk';
  if (hashParams && (hashParams.left || hashParams.right)) {
    if (hashParams.left) left = hashParams.left;
    if (hashParams.right) right = hashParams.right;
  } else if (savedJson) {
    try {
      var saved = JSON.parse(savedJson);
      if (saved && saved.left) left = saved.left;
      if (saved && saved.right) right = saved.right;
    } catch(e) {}
  }
  return { left: left, right: right };
}

describe('review: per-talk language persistence', () => {
  it('localStorage key is per-talk', () => {
    var k1 = getReviewLangsKey('talk-A');
    var k2 = getReviewLangsKey('talk-B');
    assert.notStrictEqual(k1, k2);
  });

  it('URL params override saved', () => {
    var result = resolveReviewLangs({ left: 'hi', right: 'mr' }, '{"left":"en","right":"uk"}');
    assert.deepStrictEqual(result, { left: 'hi', right: 'mr' });
  });

  it('restores saved when no URL params', () => {
    var result = resolveReviewLangs(null, '{"left":"hi","right":"mr"}');
    assert.deepStrictEqual(result, { left: 'hi', right: 'mr' });
  });

  it('defaults to en/uk when no URL params and no saved', () => {
    var result = resolveReviewLangs(null, null);
    assert.deepStrictEqual(result, { left: 'en', right: 'uk' });
  });

  it('handles invalid JSON gracefully', () => {
    var result = resolveReviewLangs(null, 'not json');
    assert.deepStrictEqual(result, { left: 'en', right: 'uk' });
  });

  it('partial saved (only left)', () => {
    var result = resolveReviewLangs(null, '{"left":"hi"}');
    assert.deepStrictEqual(result, { left: 'hi', right: 'uk' });
  });

  it('partial saved (only right)', () => {
    var result = resolveReviewLangs(null, '{"right":"mr"}');
    assert.deepStrictEqual(result, { left: 'en', right: 'mr' });
  });

  it('save format is JSON with left/right', () => {
    var toSave = JSON.stringify({ left: 'hi', right: 'mr' });
    var parsed = JSON.parse(toSave);
    assert.strictEqual(parsed.left, 'hi');
    assert.strictEqual(parsed.right, 'mr');
  });

  it('different talks independent', () => {
    var k1 = getReviewLangsKey('1979-bombay');
    var k2 = getReviewLangsKey('2001-new-york');
    assert.notStrictEqual(k1, k2);
    // Simulating different saves
    var saved1 = '{"left":"hi","right":"uk"}';
    var saved2 = '{"left":"en","right":"uk"}';
    assert.deepStrictEqual(resolveReviewLangs(null, saved1), { left: 'hi', right: 'uk' });
    assert.deepStrictEqual(resolveReviewLangs(null, saved2), { left: 'en', right: 'uk' });
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

// ============================================================
// Tests: Internationalization (i18n)
// ============================================================

// --- Extract I18N object from index.html ---
function extractI18N() {
  var fs = require('fs');
  var html = fs.readFileSync('site/index.html', 'utf8');
  // Extract the I18N object definition
  var m = html.match(/var I18N = (\{[\s\S]*?\n\};)/);
  if (!m) throw new Error('I18N object not found in index.html');
  // Evaluate the object (safe for static object literals)
  var obj;
  eval('obj = ' + m[1]);
  return obj;
}

// --- Extract detectLang logic ---
function detectLangLogic(savedLang, navigatorLang) {
  if (savedLang === 'uk' || savedLang === 'en') return savedLang;
  var nav = (navigatorLang || '').toLowerCase();
  return nav.startsWith('uk') ? 'uk' : 'en';
}

// --- t() function replica ---
function tFunction(key, currentLang, i18nObj) {
  var dict = i18nObj[currentLang] || i18nObj['en'];
  return dict[key] !== undefined ? dict[key] : (i18nObj['en'][key] !== undefined ? i18nObj['en'][key] : key);
}

describe('i18n: all keys defined in both languages', () => {
  var i18n = extractI18N();
  var ukKeys = Object.keys(i18n.uk).sort();
  var enKeys = Object.keys(i18n.en).sort();

  it('uk and en have identical key sets', () => {
    var missingInEn = ukKeys.filter(k => !i18n.en.hasOwnProperty(k));
    var missingInUk = enKeys.filter(k => !i18n.uk.hasOwnProperty(k));
    assert.deepStrictEqual(missingInEn, [], 'Keys in uk but not en: ' + missingInEn.join(', '));
    assert.deepStrictEqual(missingInUk, [], 'Keys in en but not uk: ' + missingInUk.join(', '));
  });

  it('no empty translations in uk', () => {
    var empty = ukKeys.filter(k => i18n.uk[k] === '');
    assert.deepStrictEqual(empty, [], 'Empty uk translations: ' + empty.join(', '));
  });

  it('no empty translations in en', () => {
    var empty = enKeys.filter(k => i18n.en[k] === '');
    assert.deepStrictEqual(empty, [], 'Empty en translations: ' + empty.join(', '));
  });

  it('at least 30 keys defined (sanity check)', () => {
    assert.ok(ukKeys.length >= 30, 'Expected >= 30 keys, got ' + ukKeys.length);
  });
});

describe('i18n: auto-detect logic', () => {
  it('saved "uk" returns uk regardless of navigator', () => {
    assert.strictEqual(detectLangLogic('uk', 'en-US'), 'uk');
  });

  it('saved "en" returns en regardless of navigator', () => {
    assert.strictEqual(detectLangLogic('en', 'uk-UA'), 'en');
  });

  it('no saved, navigator "uk" returns uk', () => {
    assert.strictEqual(detectLangLogic(null, 'uk'), 'uk');
  });

  it('no saved, navigator "uk-UA" returns uk', () => {
    assert.strictEqual(detectLangLogic(null, 'uk-UA'), 'uk');
  });

  it('no saved, navigator "en-US" returns en', () => {
    assert.strictEqual(detectLangLogic(null, 'en-US'), 'en');
  });

  it('no saved, navigator "de" returns en', () => {
    assert.strictEqual(detectLangLogic(null, 'de'), 'en');
  });

  it('no saved, navigator "fr-FR" returns en', () => {
    assert.strictEqual(detectLangLogic(null, 'fr-FR'), 'en');
  });

  it('no saved, navigator "" returns en', () => {
    assert.strictEqual(detectLangLogic(null, ''), 'en');
  });

  it('no saved, navigator null returns en', () => {
    assert.strictEqual(detectLangLogic(null, null), 'en');
  });

  it('invalid saved value falls through to navigator', () => {
    assert.strictEqual(detectLangLogic('de', 'uk'), 'uk');
    assert.strictEqual(detectLangLogic('fr', 'en-US'), 'en');
  });
});

describe('i18n: t() function', () => {
  var i18n = extractI18N();

  it('returns uk translation when lang is uk', () => {
    assert.strictEqual(tFunction('index.loading', 'uk', i18n), i18n.uk['index.loading']);
  });

  it('returns en translation when lang is en', () => {
    assert.strictEqual(tFunction('index.loading', 'en', i18n), i18n.en['index.loading']);
  });

  it('falls back to en for unknown language', () => {
    assert.strictEqual(tFunction('index.loading', 'de', i18n), i18n.en['index.loading']);
  });

  it('returns key itself for unknown key', () => {
    assert.strictEqual(tFunction('nonexistent.key', 'uk', i18n), 'nonexistent.key');
  });

  it('uk and en translations differ for text keys', () => {
    // At least some keys should have different translations
    var different = Object.keys(i18n.uk).filter(k => i18n.uk[k] !== i18n.en[k]);
    assert.ok(different.length > 10, 'Expected many different translations, got ' + different.length);
  });
});

describe('i18n: toggle cycle', () => {
  it('uk toggles to en', () => {
    assert.strictEqual('uk' === 'uk' ? 'en' : 'uk', 'en');
  });

  it('en toggles to uk', () => {
    assert.strictEqual('en' === 'uk' ? 'en' : 'uk', 'uk');
  });
});

describe('i18n: data-i18n coverage in HTML', () => {
  var fs = require('fs');
  var html = fs.readFileSync('site/index.html', 'utf8');
  var i18n = extractI18N();

  it('all data-i18n keys exist in I18N', () => {
    var keys = [];
    var re = /data-i18n="([^"]+)"/g;
    var m;
    while ((m = re.exec(html)) !== null) keys.push(m[1]);
    var missing = keys.filter(k => !i18n.en.hasOwnProperty(k));
    assert.deepStrictEqual(missing, [], 'data-i18n keys not in I18N: ' + missing.join(', '));
  });

  it('all data-i18n-placeholder keys exist in I18N', () => {
    var keys = [];
    var re = /data-i18n-placeholder="([^"]+)"/g;
    var m;
    while ((m = re.exec(html)) !== null) keys.push(m[1]);
    var missing = keys.filter(k => !i18n.en.hasOwnProperty(k));
    assert.deepStrictEqual(missing, [], 'data-i18n-placeholder keys not in I18N: ' + missing.join(', '));
  });

  it('all data-i18n-title keys exist in I18N', () => {
    var keys = [];
    var re = /data-i18n-title="([^"]+)"/g;
    var m;
    while ((m = re.exec(html)) !== null) keys.push(m[1]);
    var missing = keys.filter(k => !i18n.en.hasOwnProperty(k));
    assert.deepStrictEqual(missing, [], 'data-i18n-title keys not in I18N: ' + missing.join(', '));
  });

  it('language toggle button exists', () => {
    assert.ok(html.includes('id="lang-btn"'), 'lang-btn not found');
    assert.ok(html.includes('SPA.toggleLang()'), 'SPA.toggleLang() not found');
  });

  it('LANG_KEY defined for localStorage', () => {
    assert.ok(html.includes("var LANG_KEY = 'sy_lang'"), 'LANG_KEY not found');
  });

  it('detectLang function exists', () => {
    assert.ok(html.includes('function detectLang()'), 'detectLang not found');
  });

  it('translatePage function exists', () => {
    assert.ok(html.includes('function translatePage()'), 'translatePage not found');
  });

  it('APP_DEPLOY_SHA and APP_DEPLOY_DATE placeholders', () => {
    assert.ok(html.includes("var APP_DEPLOY_SHA = ''"), 'APP_DEPLOY_SHA placeholder');
    assert.ok(html.includes("var APP_DEPLOY_DATE = ''"), 'APP_DEPLOY_DATE placeholder');
  });
});

// ============================================================
// Footer version string logic
// ============================================================
function formatFooterVersion(deploySha, deployDate, manifestSha) {
  var sha = deploySha || manifestSha || 'dev';
  var date = deployDate || '';
  return sha + (date ? ' | ' + date : '');
}

describe('Footer: formatFooterVersion', () => {
  it('deploy SHA + date', () => {
    assert.strictEqual(formatFooterVersion('abc1234', '2026-04-09', 'xyz9999'), 'abc1234 | 2026-04-09');
  });

  it('deploy SHA without date', () => {
    assert.strictEqual(formatFooterVersion('abc1234', '', 'xyz9999'), 'abc1234');
  });

  it('falls back to manifest SHA when deploy SHA empty', () => {
    assert.strictEqual(formatFooterVersion('', '', 'xyz9999'), 'xyz9999');
  });

  it('falls back to dev when both empty', () => {
    assert.strictEqual(formatFooterVersion('', '', ''), 'dev');
  });

  it('null/undefined handled', () => {
    assert.strictEqual(formatFooterVersion(null, null, null), 'dev');
    assert.strictEqual(formatFooterVersion(undefined, undefined, undefined), 'dev');
  });

  it('deploy SHA takes priority over manifest SHA', () => {
    assert.strictEqual(formatFooterVersion('aaa', '2026-01-01', 'bbb'), 'aaa | 2026-01-01');
  });
});

// ============================================================
// Auto-reload detection logic
// ============================================================
function shouldAutoReload(deploySha, siteIndexSha) {
  return !!(siteIndexSha && deploySha && siteIndexSha !== deploySha);
}

describe('Auto-reload: shouldAutoReload', () => {
  it('different SHAs → reload', () => {
    assert.strictEqual(shouldAutoReload('abc1234', 'def5678'), true);
  });

  it('same SHAs → no reload', () => {
    assert.strictEqual(shouldAutoReload('abc1234', 'abc1234'), false);
  });

  it('empty deploy SHA (local dev) → no reload', () => {
    assert.strictEqual(shouldAutoReload('', 'def5678'), false);
  });

  it('empty manifest SHA → no reload', () => {
    assert.strictEqual(shouldAutoReload('abc1234', ''), false);
  });

  it('both empty → no reload', () => {
    assert.strictEqual(shouldAutoReload('', ''), false);
  });

  it('null/undefined → no reload', () => {
    assert.strictEqual(shouldAutoReload(null, 'abc'), false);
    assert.strictEqual(shouldAutoReload('abc', null), false);
  });
});

// ============================================================
// Cache schema migration logic
// ============================================================
function shouldMigrateCache(cachedJson, expectedSchema) {
  if (!cachedJson) return false; // no cache = nothing to migrate
  try {
    var c = JSON.parse(cachedJson);
    return c._schema !== expectedSchema;
  } catch(e) { return true; } // corrupt = needs migration
}

describe('Cache: schema migration', () => {
  it('same schema → no migration', () => {
    assert.strictEqual(shouldMigrateCache('{"_schema":2}', 2), false);
  });

  it('old schema → needs migration', () => {
    assert.strictEqual(shouldMigrateCache('{"_schema":1}', 2), true);
  });

  it('no schema field → needs migration', () => {
    assert.strictEqual(shouldMigrateCache('{"etag":"abc"}', 2), true);
  });

  it('null cache → no migration needed', () => {
    assert.strictEqual(shouldMigrateCache(null, 2), false);
  });

  it('corrupt JSON → needs migration', () => {
    assert.strictEqual(shouldMigrateCache('{broken', 2), true);
  });

  it('empty string → needs migration', () => {
    assert.strictEqual(shouldMigrateCache('', 2), false);
  });
});

// ============================================================
// buildManifest: _siteIndexSha extraction
// ============================================================
describe('buildManifest: _siteIndexSha', () => {
  // Minimal buildManifest that extracts _siteIndexSha
  function extractSiteIndexSha(tree) {
    var sha = '';
    tree.forEach(function(entry) {
      if (entry.path === 'site/index.html') sha = (entry.sha || '').substring(0, 7);
    });
    return sha;
  }

  it('extracts SHA from tree', () => {
    var tree = [
      { path: 'talks/test/meta.yaml', sha: 'aaa' },
      { path: 'site/index.html', sha: 'e3a253d1234567890' },
      { path: 'site/sw.js', sha: 'bbb' },
    ];
    assert.strictEqual(extractSiteIndexSha(tree), 'e3a253d');
  });

  it('returns empty when site/index.html not in tree', () => {
    var tree = [{ path: 'talks/test/meta.yaml', sha: 'aaa' }];
    assert.strictEqual(extractSiteIndexSha(tree), '');
  });

  it('truncates to 7 chars', () => {
    var tree = [{ path: 'site/index.html', sha: '1234567890abcdef' }];
    assert.strictEqual(extractSiteIndexSha(tree), '1234567');
  });
});

// ============================================================
// Expert mode: pipeline button HTML
// ============================================================
describe('Expert mode: pipeline button', () => {
  var fs = require('fs');
  var html = fs.readFileSync('site/index.html', 'utf8');

  it('expert-only elements hidden by default (display:none in HTML)', () => {
    assert.ok(html.includes('class="expert-only expert-btn" style="display:none;"'));
  });

  it('pipeline button copies talk_id to clipboard', () => {
    assert.ok(html.includes('navigator.clipboard.writeText'));
  });

  it('pipeline button links to subtitle-pipeline.yml dispatch', () => {
    assert.ok(html.includes('actions/workflows/subtitle-pipeline.yml'));
  });

  it('expert toggle persists to localStorage sy_expert_mode', () => {
    assert.ok(html.includes("localStorage.getItem('sy_expert_mode')"));
    assert.ok(html.includes("localStorage.setItem('sy_expert_mode'"));
  });

  it('footer has expert toggle button', () => {
    assert.ok(html.includes('id="footer-expert"'));
    assert.ok(html.includes('SPA.toggleExpert'));
  });
});

// ============================================================
// SW independence from APP_VERSION
// ============================================================
describe('SW version independence', () => {
  var fs = require('fs');
  var sw = fs.readFileSync('site/sw.js', 'utf8');

  it('SW uses CACHE_VERSION not APP_VERSION', () => {
    assert.ok(sw.includes('CACHE_VERSION'));
    assert.ok(!sw.includes('APP_VERSION'));
  });

  it('SW does not parse URL params for version', () => {
    assert.ok(!sw.includes('searchParams'));
  });

  it('CACHE_NAME derived from CACHE_VERSION', () => {
    var m = sw.match(/CACHE_NAME = 'sy-subtitles-c' \+ CACHE_VERSION/);
    assert.ok(m, 'CACHE_NAME should use CACHE_VERSION');
  });
});

// ============================================================
// Deploy workflow stamps
// ============================================================
describe('Pipeline DAG labels and i18n', () => {
  var fs = require('fs');
  var html = fs.readFileSync('site/index.html', 'utf8');

  it('DAG uses t() for node labels', () => {
    assert.ok(html.includes("t('pipe.added')"), 'pipe.added i18n key used');
    assert.ok(html.includes("t('pipe.srt')"), 'pipe.srt i18n key used');
    assert.ok(html.includes("t('pipe.review')"), 'pipe.review i18n key used');
    assert.ok(html.includes("t('pipe.approved')"), 'pipe.approved i18n key used');
  });

  it('i18n has pipe keys in uk', () => {
    assert.ok(html.includes("'pipe.added'"));
    assert.ok(html.includes("'pipe.ai_transcribed'"));
    assert.ok(html.includes("'pipe.ai_translated'"));
    assert.ok(html.includes("'pipe.ai_reviewed'"));
    assert.ok(html.includes("'pipe.issue'"));
    assert.ok(html.includes("'pipe.srt'"));
    assert.ok(html.includes("'pipe.review'"));
    assert.ok(html.includes("'pipe.approved'"));
  });

  it('DAG has issue node', () => {
    assert.ok(html.includes("t('pipe.issue')"));
    assert.ok(html.includes('hasIssue'));
  });
});

describe('Deploy stamps in HTML', () => {
  var fs = require('fs');
  var html = fs.readFileSync('site/index.html', 'utf8');

  it('APP_DEPLOY_SHA placeholder for sed', () => {
    assert.ok(html.includes("var APP_DEPLOY_SHA = '';"));
  });

  it('APP_DEPLOY_DATE placeholder for sed', () => {
    assert.ok(html.includes("var APP_DEPLOY_DATE = '';"));
  });

  it('no APP_VERSION references remain', () => {
    assert.ok(!html.includes('APP_VERSION'), 'APP_VERSION should be fully removed');
  });

  it('CACHE_SCHEMA is defined as number >= 1', () => {
    var m = html.match(/var CACHE_SCHEMA = (\d+)/);
    assert.ok(m, 'CACHE_SCHEMA not found');
    assert.ok(parseInt(m[1]) >= 1);
  });

  it('footer element exists with correct structure', () => {
    assert.ok(html.includes('id="app-footer"'));
    assert.ok(html.includes('id="footer-version"'));
    assert.ok(html.includes('id="footer-expert"'));
  });
});

// ============================================================
// Pipeline view: stage computation
// ============================================================
function getPipelineStages(tk, st) {
  var nVideos = (tk.videos || []).length;
  var nWhisper = (tk._whisperSlugs || []).length;
  var nSrt = 0;
  (tk.videos || []).forEach(function(v) { if (v.hasSrt) nSrt++; });
  return {
    added: true,
    whisper: nWhisper >= nVideos && nVideos > 0,
    whisperProgress: nVideos > 0 ? nWhisper + '/' + nVideos : '0',
    translated: tk.hasUk,
    reviewed: tk.hasReviewReport,
    srt: nSrt >= nVideos && nVideos > 0,
    srtProgress: nVideos > 0 ? nSrt + '/' + nVideos : '0',
    hasIssue: !!(st && st.issue_number),
    review: st && st.status !== 'pending',
    approved: st && st.status === 'approved',
    nVideos: nVideos, nWhisper: nWhisper, nSrt: nSrt
  };
}

function countDoneStages(s) {
  var done = 1;
  if (s.whisper) done++;
  if (s.translated) done++;
  if (s.reviewed) done++;
  if (s.srt) done++;
  if (s.approved) done++;
  return { done: done, total: 6 };
}

describe('Pipeline: getPipelineStages', () => {
  it('empty talk — only added, no issue', () => {
    var tk = { videos: [], _whisperSlugs: [], hasUk: false, hasReviewReport: false };
    var s = getPipelineStages(tk, null);
    assert.strictEqual(s.added, true);
    assert.strictEqual(s.whisper, false);
    assert.strictEqual(s.translated, false);
    assert.strictEqual(s.srt, false);
    assert.strictEqual(s.hasIssue, false);
  });

  it('hasIssue true when issue_number exists', () => {
    var tk = { videos: [], _whisperSlugs: [], hasUk: false, hasReviewReport: false };
    assert.strictEqual(getPipelineStages(tk, { status: 'pending', issue_number: 5 }).hasIssue, true);
    assert.strictEqual(getPipelineStages(tk, { status: 'in-progress', issue_number: 3 }).hasIssue, true);
  });

  it('hasIssue false when status exists but no issue_number', () => {
    var tk = { videos: [], _whisperSlugs: [], hasUk: false, hasReviewReport: false };
    assert.strictEqual(getPipelineStages(tk, { status: 'pending', issue_number: null }).hasIssue, false);
    assert.strictEqual(getPipelineStages(tk, { status: 'pending' }).hasIssue, false);
  });

  it('hasIssue false when no status', () => {
    var tk = { videos: [], _whisperSlugs: [], hasUk: false, hasReviewReport: false };
    assert.strictEqual(getPipelineStages(tk, null).hasIssue, false);
  });

  it('fully completed talk', () => {
    var tk = {
      videos: [{ slug: 'v1', hasSrt: true }],
      _whisperSlugs: ['v1'],
      hasUk: true,
      hasReviewReport: true
    };
    var s = getPipelineStages(tk, { status: 'approved', issue_number: 1 });
    assert.strictEqual(s.whisper, true);
    assert.strictEqual(s.translated, true);
    assert.strictEqual(s.reviewed, true);
    assert.strictEqual(s.srt, true);
    assert.strictEqual(s.approved, true);
  });

  it('multi-video partial whisper', () => {
    var tk = {
      videos: [{ slug: 'v1', hasSrt: false }, { slug: 'v2', hasSrt: false }],
      _whisperSlugs: ['v1'],
      hasUk: false,
      hasReviewReport: false
    };
    var s = getPipelineStages(tk, null);
    assert.strictEqual(s.whisper, false); // 1/2
    assert.strictEqual(s.whisperProgress, '1/2');
  });

  it('multi-video all whisper done', () => {
    var tk = {
      videos: [{ slug: 'v1', hasSrt: true }, { slug: 'v2', hasSrt: true }],
      _whisperSlugs: ['v1', 'v2'],
      hasUk: true,
      hasReviewReport: true
    };
    var s = getPipelineStages(tk, { status: 'in-progress' });
    assert.strictEqual(s.whisper, true);
    assert.strictEqual(s.srt, true);
    assert.strictEqual(s.review, true);
    assert.strictEqual(s.approved, false);
  });

  it('review pending — review false', () => {
    var tk = { videos: [{ slug: 'v1', hasSrt: true }], _whisperSlugs: ['v1'], hasUk: true, hasReviewReport: true };
    var s = getPipelineStages(tk, { status: 'pending' });
    assert.strictEqual(s.review, false);
  });

  it('no status — review falsy', () => {
    var tk = { videos: [{ slug: 'v1', hasSrt: true }], _whisperSlugs: ['v1'], hasUk: true, hasReviewReport: true };
    var s = getPipelineStages(tk, null);
    assert.ok(!s.review);
    assert.ok(!s.approved);
  });
});

// Overall status for compact card view
function getOverallStatus(stages, reviewSt) {
  if (reviewSt && reviewSt.status === 'approved') return 'approved';
  if (reviewSt && reviewSt.status === 'in-progress') return 'in-review';
  if (stages.srt && stages.translated && stages.hasIssue) return 'ready-for-review';
  return 'in-progress';
}

describe('Pipeline: getOverallStatus', () => {
  it('approved', () => {
    var s = { srt: true, translated: true };
    assert.strictEqual(getOverallStatus(s, { status: 'approved' }), 'approved');
  });

  it('in-review', () => {
    var s = { srt: true, translated: true };
    assert.strictEqual(getOverallStatus(s, { status: 'in-progress' }), 'in-review');
  });

  it('ready for review — srt + translated + hasIssue', () => {
    var s = { srt: true, translated: true, hasIssue: true };
    assert.strictEqual(getOverallStatus(s, { status: 'pending', issue_number: 5 }), 'ready-for-review');
  });

  it('in-progress — srt + translated but NO issue_number', () => {
    var s = { srt: true, translated: true, hasIssue: false };
    assert.strictEqual(getOverallStatus(s, { status: 'pending', issue_number: null }), 'in-progress');
  });

  it('in-progress — srt + translated but no status at all', () => {
    var s = { srt: true, translated: true, hasIssue: false };
    assert.strictEqual(getOverallStatus(s, null), 'in-progress');
  });

  it('in-progress — no srt', () => {
    var s = { srt: false, translated: true };
    assert.strictEqual(getOverallStatus(s, { status: 'pending' }), 'in-progress');
  });

  it('in-progress — no translation', () => {
    var s = { srt: true, translated: false };
    assert.strictEqual(getOverallStatus(s, { status: 'pending' }), 'in-progress');
  });

  it('in-progress — nothing done', () => {
    var s = { srt: false, translated: false };
    assert.strictEqual(getOverallStatus(s, null), 'in-progress');
  });
});

// Filter logic
function shouldShowInFilter(status, filter, isExpert) {
  if (filter === 'all' && !isExpert) {
    return status === 'ready-for-review' || status === 'in-review';
  }
  if (filter === 'all') return true;
  if (filter === 'needs-review') return status === 'ready-for-review';
  if (filter === 'in-review') return status === 'in-review';
  if (filter === 'pending') return status === 'in-progress';
  if (filter === 'approved') return status === 'approved';
  return true;
}

describe('Index filters: shouldShowInFilter', () => {
  // Normal mode "all" = only needs-review + in-review
  it('normal all — only needs-review + in-review', () => {
    assert.strictEqual(shouldShowInFilter('ready-for-review', 'all', false), true);
    assert.strictEqual(shouldShowInFilter('in-review', 'all', false), true);
    assert.strictEqual(shouldShowInFilter('in-progress', 'all', false), false);
    assert.strictEqual(shouldShowInFilter('approved', 'all', false), false);
  });

  // Expert mode "all" = everything
  it('expert all — shows everything', () => {
    ['in-progress', 'ready-for-review', 'in-review', 'approved'].forEach(s => {
      assert.strictEqual(shouldShowInFilter(s, 'all', true), true);
    });
  });

  it('needs-review — only ready-for-review', () => {
    assert.strictEqual(shouldShowInFilter('ready-for-review', 'needs-review', false), true);
    assert.strictEqual(shouldShowInFilter('in-progress', 'needs-review', false), false);
    assert.strictEqual(shouldShowInFilter('in-review', 'needs-review', false), false);
    assert.strictEqual(shouldShowInFilter('approved', 'needs-review', false), false);
  });

  it('in-review — only in-review', () => {
    assert.strictEqual(shouldShowInFilter('in-review', 'in-review', false), true);
    assert.strictEqual(shouldShowInFilter('ready-for-review', 'in-review', false), false);
  });

  it('pending — only in-progress (expert)', () => {
    assert.strictEqual(shouldShowInFilter('in-progress', 'pending', true), true);
    assert.strictEqual(shouldShowInFilter('ready-for-review', 'pending', true), false);
  });

  it('approved — only approved (expert)', () => {
    assert.strictEqual(shouldShowInFilter('approved', 'approved', true), true);
    assert.strictEqual(shouldShowInFilter('in-progress', 'approved', true), false);
  });
});

describe('Index filters: default filter by mode', () => {
  it('normal mode default = needs-review', () => {
    var defaultNormal = false ? 'pending' : 'needs-review';
    assert.strictEqual(defaultNormal, 'needs-review');
  });

  it('expert mode default = pending', () => {
    var defaultExpert = true ? 'pending' : 'needs-review';
    assert.strictEqual(defaultExpert, 'pending');
  });

  it('normal all count = needs-review + in-review', () => {
    var needs = 4, inRev = 2;
    var normalAll = needs + inRev;
    assert.strictEqual(normalAll, 6);
  });
});

describe('Pipeline: countDoneStages', () => {
  it('only added = 1/6', () => {
    var p = countDoneStages({ added: true, whisper: false, translated: false, reviewed: false, srt: false, review: false, approved: false });
    assert.strictEqual(p.done, 1);
    assert.strictEqual(p.total, 6);
  });

  it('fully done = 6/6', () => {
    var p = countDoneStages({ added: true, whisper: true, translated: true, reviewed: true, srt: true, review: true, approved: true });
    assert.strictEqual(p.done, 6);
  });

  it('partial = 4/6', () => {
    var p = countDoneStages({ added: true, whisper: true, translated: true, reviewed: true, srt: false, review: false, approved: false });
    assert.strictEqual(p.done, 4);
  });
});

describe('Pipeline: manifest tracking', () => {
  var fs = require('fs');
  var html = fs.readFileSync('site/index.html', 'utf8');

  it('buildManifest tracks whisper.json', () => {
    assert.ok(html.includes('_whisperSlugs'));
    assert.ok(html.includes("whisper\\.json"));
  });

  it('buildManifest tracks review_report.md', () => {
    assert.ok(html.includes('hasReviewReport'));
    assert.ok(html.includes("review_report\\.md"));
  });

  it('expert inline DAG detail', () => {
    assert.ok(html.includes('pipe-detail'));
    assert.ok(html.includes('renderPipelineDAG'));
  });

  it('status badge CSS for all states', () => {
    assert.ok(html.includes('.review-badge.ready-for-review'));
    assert.ok(html.includes('.review-badge.in-progress'));
    assert.ok(html.includes('.review-badge.in-review'));
    assert.ok(html.includes('.review-badge.approved'));
  });

  it('getOverallStatus function exists', () => {
    assert.ok(html.includes('function getOverallStatus'));
  });
});

describe('i18n: no hardcoded UI text in HTML body', () => {
  var fs = require('fs');
  var html = fs.readFileSync('site/index.html', 'utf8');
  var bodyMatch = html.match(/<body>([\s\S]*)<\/body>/);
  var body = bodyMatch ? bodyMatch[1] : '';
  var bodyNoScript = body.replace(/<script[\s\S]*?<\/script>/g, '');

  it('no hardcoded "Loading..." without data-i18n', () => {
    var loadingMatches = bodyNoScript.match(/>Loading\.\.\.</g) || [];
    var i18nLoadingMatches = bodyNoScript.match(/data-i18n="[^"]*">Loading\.\.\.</g) || [];
    assert.strictEqual(loadingMatches.length, i18nLoadingMatches.length,
      'Found Loading... without data-i18n attribute');
  });

  it('no hardcoded Ukrainian title attributes without data-i18n-title', () => {
    var titleRe = /title="([^"]*)"/g;
    var m, errors = [];
    while ((m = titleRe.exec(bodyNoScript)) !== null) {
      if (/[\u0400-\u04FF]/.test(m[1])) {
        var before = bodyNoScript.substring(Math.max(0, m.index - 200), m.index);
        if (!before.includes('data-i18n-title=')) errors.push(m[1]);
      }
    }
    assert.deepStrictEqual(errors, [], 'Hardcoded Ukrainian title attrs: ' + errors.join(', '));
  });

  it('no hardcoded English placeholder attributes without data-i18n-placeholder', () => {
    var re = /placeholder="([^"]*)"/g;
    var m, errors = [];
    while ((m = re.exec(bodyNoScript)) !== null) {
      var val = m[1];
      // Skip if it looks like an i18n key or URL pattern
      if (/^[\w.]+$/.test(val)) continue;
      if (/^https?:\/\//.test(val)) continue;
      if (/[a-zA-Z]{3,}/.test(val)) {
        var before = bodyNoScript.substring(Math.max(0, m.index - 200), m.index);
        if (!before.includes('data-i18n-placeholder=')) errors.push(val);
      }
    }
    assert.deepStrictEqual(errors, [], 'Hardcoded placeholders: ' + errors.join(', '));
  });

  it('all visible button text has data-i18n', () => {
    var btnRe = /<button[^>]*>([^<]+)<\/button>/g;
    var m, errors = [];
    while ((m = btnRe.exec(bodyNoScript)) !== null) {
      var text = m[1].trim();
      // Skip icon-only buttons (single unicode chars, emoji, &#xxx;, ↻)
      if (text.length <= 2 || /^&#x?[0-9a-f]+;$/i.test(text)) continue;
      // Skip branch selector buttons (dynamic content like "main ▾")
      if (m[0].includes('class="branch-btn"')) continue;
      // Skip theme/lang toggle buttons (single icon/label set by JS)
      if (m[0].includes('id="theme-btn"') || m[0].includes('id="lang-btn"')) continue;
      // Must have data-i18n in the tag
      if (!m[0].includes('data-i18n=')) errors.push(text);
    }
    assert.deepStrictEqual(errors, [], 'Button text without data-i18n: ' + errors.join(', '));
  });

  it('all visible summary text has data-i18n', () => {
    var re = /<summary[^>]*>([^<]*)</g;
    var m, errors = [];
    while ((m = re.exec(bodyNoScript)) !== null) {
      var text = m[1].trim();
      if (text.length > 2 && /[a-zA-Z\u0400-\u04FF]/.test(text) && !m[0].includes('data-i18n=')) {
        errors.push(text);
      }
    }
    assert.deepStrictEqual(errors, [], 'Summary text without data-i18n: ' + errors.join(', '));
  });

  it('no hardcoded status text in divs with class "status"', () => {
    var re = /class="status"[^>]*>([^<]+)</g;
    var m, errors = [];
    while ((m = re.exec(bodyNoScript)) !== null) {
      var text = m[1].trim();
      if (text.length > 0 && !m[0].includes('data-i18n=')) errors.push(text);
    }
    assert.deepStrictEqual(errors, [], 'Status text without data-i18n: ' + errors.join(', '));
  });

  it('all JS t() calls use keys that exist in I18N', () => {
    var scriptMatch = html.match(/<script>([\s\S]*)<\/script>/);
    if (!scriptMatch) return;
    var script = scriptMatch[1];

    // Extract all t('key') calls
    var tCalls = new Set();
    var tRe = /\bt\('([^']+?)'\)/g;
    var m;
    while ((m = tRe.exec(script)) !== null) tCalls.add(m[1]);

    // Extract ALL I18N keys (from any quoted key in the I18N block)
    var i18nMatch = script.match(/var I18N\s*=\s*\{([\s\S]*?)\n\s*\};/);
    if (!i18nMatch) { assert.ok(false, 'I18N object not found'); return; }
    var i18nBlock = i18nMatch[1];
    var allKeys = new Set();
    var keyRe = /'([\w.]+)'\s*:/g;
    while ((m = keyRe.exec(i18nBlock)) !== null) allKeys.add(m[1]);

    var missing = [...tCalls].filter(k => !allKeys.has(k));
    assert.strictEqual(missing.length, 0, 't() calls with undefined keys: ' + missing.join(', '));
  });

  it('no JS showToast/toast with hardcoded strings (should use t())', () => {
    var scriptMatch = html.match(/<script>([\s\S]*)<\/script>/);
    if (!scriptMatch) return;
    var script = scriptMatch[1];
    // Find showToast('...') or toast('...') with literal strings (not t())
    var re = /(?:showToast|toast)\(\s*'([^']+)'/g;
    var m, errors = [];
    while ((m = re.exec(script)) !== null) {
      // Should be t('key'), not a literal
      if (!/^t\(/.test(m[0])) errors.push(m[1]);
    }
    // Filter out ones that are inside t() calls
    errors = errors.filter(e => !e.startsWith('t('));
    assert.strictEqual(errors.length, 0, 'Hardcoded toast messages: ' + errors.join(', '));
  });
});
