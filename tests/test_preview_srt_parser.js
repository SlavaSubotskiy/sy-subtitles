const { describe, it } = require('node:test');
const assert = require('node:assert');
const { timeToMs, parseSRT, findActiveSubtitle } = require('../tools/preview_srt_parser');

describe('timeToMs', () => {
  it('parses zero', () => {
    assert.strictEqual(timeToMs('00:00:00,000'), 0);
  });
  it('parses milliseconds', () => {
    assert.strictEqual(timeToMs('00:00:00,500'), 500);
  });
  it('parses seconds', () => {
    assert.strictEqual(timeToMs('00:00:05,000'), 5000);
  });
  it('parses minutes', () => {
    assert.strictEqual(timeToMs('00:02:00,000'), 120000);
  });
  it('parses hours', () => {
    assert.strictEqual(timeToMs('01:00:00,000'), 3600000);
  });
  it('parses complex time', () => {
    assert.strictEqual(timeToMs('01:02:03,456'), 3723456);
  });
});

describe('parseSRT', () => {
  it('parses standard SRT', () => {
    const srt = `1
00:00:01,000 --> 00:00:05,000
Hello world

2
00:00:06,000 --> 00:00:10,000
Second block`;
    const result = parseSRT(srt);
    assert.strictEqual(result.length, 2);
    assert.strictEqual(result[0].index, 1);
    assert.strictEqual(result[0].startMs, 1000);
    assert.strictEqual(result[0].endMs, 5000);
    assert.strictEqual(result[0].text, 'Hello world');
    assert.strictEqual(result[1].index, 2);
    assert.strictEqual(result[1].text, 'Second block');
  });

  it('handles BOM', () => {
    const srt = '\uFEFF1\n00:00:01,000 --> 00:00:02,000\nText';
    const result = parseSRT(srt);
    assert.strictEqual(result.length, 1);
    assert.strictEqual(result[0].index, 1);
  });

  it('handles empty input', () => {
    assert.strictEqual(parseSRT('').length, 0);
    assert.strictEqual(parseSRT('  ').length, 0);
  });

  it('handles single block', () => {
    const srt = '1\n00:00:00,000 --> 00:00:01,000\nOnly one';
    assert.strictEqual(parseSRT(srt).length, 1);
  });

  it('handles Ukrainian text', () => {
    const srt = '1\n00:00:01,000 --> 00:00:05,000\nПривіт світе';
    const result = parseSRT(srt);
    assert.strictEqual(result[0].text, 'Привіт світе');
  });
});

describe('findActiveSubtitle', () => {
  const subs = [
    { index: 1, startMs: 1000, endMs: 5000, text: 'First' },
    { index: 2, startMs: 6000, endMs: 10000, text: 'Second' },
  ];

  it('finds active at start', () => {
    assert.strictEqual(findActiveSubtitle(subs, 1000).text, 'First');
  });

  it('finds active in middle', () => {
    assert.strictEqual(findActiveSubtitle(subs, 3000).text, 'First');
  });

  it('returns null at exact end', () => {
    assert.strictEqual(findActiveSubtitle(subs, 5000), null);
  });

  it('returns null in gap', () => {
    assert.strictEqual(findActiveSubtitle(subs, 5500), null);
  });

  it('finds second block', () => {
    assert.strictEqual(findActiveSubtitle(subs, 7000).text, 'Second');
  });

  it('returns null before all', () => {
    assert.strictEqual(findActiveSubtitle(subs, 0), null);
  });

  it('returns null after all', () => {
    assert.strictEqual(findActiveSubtitle(subs, 15000), null);
  });

  it('handles empty array', () => {
    assert.strictEqual(findActiveSubtitle([], 1000), null);
  });
});
