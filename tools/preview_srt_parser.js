// SRT parser for subtitle preview pages.
// This file is embedded inline by generate_preview.py and tested by Node.js.

function timeToMs(t) {
  var parts = t.split(':');
  var secMs = parts[2].split(',');
  return (
    parseInt(parts[0], 10) * 3600000 +
    parseInt(parts[1], 10) * 60000 +
    parseInt(secMs[0], 10) * 1000 +
    parseInt(secMs[1], 10)
  );
}

function parseSRT(text) {
  text = text.replace(/^\uFEFF/, ''); // strip BOM
  var blocks = text.trim().split(/\n\s*\n/);
  var result = [];
  for (var i = 0; i < blocks.length; i++) {
    var lines = blocks[i].trim().split('\n');
    if (lines.length < 3) continue;
    var tcLine = lines[1];
    var match = tcLine.match(
      /(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})/
    );
    if (!match) continue;
    result.push({
      index: parseInt(lines[0], 10),
      startMs: timeToMs(match[1]),
      endMs: timeToMs(match[2]),
      text: lines.slice(2).join('\n'),
    });
  }
  return result;
}

function findActiveSubtitle(subtitles, currentTimeMs) {
  for (var i = 0; i < subtitles.length; i++) {
    if (currentTimeMs >= subtitles[i].startMs && currentTimeMs < subtitles[i].endMs) {
      return subtitles[i];
    }
  }
  return null;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { timeToMs: timeToMs, parseSRT: parseSRT, findActiveSubtitle: findActiveSubtitle };
}
