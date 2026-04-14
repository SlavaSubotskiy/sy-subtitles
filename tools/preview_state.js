// Pure helpers for preview-page marker/edit state. Mirrored inline
// into site/index.html; the browser runs the copy there.

function defaultPreviewState() {
  return { mode: 'marker', markers: [], edits: {} };
}

function newKeyFor(talkId, videoSlug) {
  return 'preview_' + talkId + '_' + videoSlug;
}

function legacyKeyFor(talkId, videoSlug) {
  return 'markers_preview_' + talkId + '_' + videoSlug;
}

function coerceState(raw) {
  var out = defaultPreviewState();
  if (!raw || typeof raw !== 'object') return out;
  if (raw.mode === 'edit' || raw.mode === 'marker') out.mode = raw.mode;
  if (Array.isArray(raw.markers)) out.markers = raw.markers;
  if (raw.edits && typeof raw.edits === 'object' && !Array.isArray(raw.edits)) {
    out.edits = raw.edits;
  }
  return out;
}

// Legacy markers_preview_* key is migrated on first read and then
// removed unconditionally once the new key exists.
function loadPreviewState(talkId, videoSlug, storage) {
  var newKey = newKeyFor(talkId, videoSlug);
  var legacyKey = legacyKeyFor(talkId, videoSlug);
  var rawNew = storage.getItem(newKey);

  if (rawNew != null) {
    var parsed;
    try {
      parsed = JSON.parse(rawNew);
    } catch (_) {
      parsed = null;
    }
    // New key is authoritative — legacy is stale garbage if still around.
    if (storage.getItem(legacyKey) != null) storage.removeItem(legacyKey);
    return coerceState(parsed);
  }

  var rawLegacy = storage.getItem(legacyKey);
  if (rawLegacy != null) {
    var legacyMarkers;
    try {
      legacyMarkers = JSON.parse(rawLegacy);
    } catch (_) {
      legacyMarkers = [];
    }
    if (!Array.isArray(legacyMarkers)) legacyMarkers = [];
    var migrated = defaultPreviewState();
    migrated.markers = legacyMarkers;
    storage.setItem(newKey, JSON.stringify(migrated));
    storage.removeItem(legacyKey);
    return migrated;
  }

  return defaultPreviewState();
}

function msToSrtTime(ms) {
  var h = Math.floor(ms / 3600000);
  var m = Math.floor((ms % 3600000) / 60000);
  var s = Math.floor((ms % 60000) / 1000);
  var mmm = ms % 1000;
  return (
    String(h).padStart(2, '0') +
    ':' +
    String(m).padStart(2, '0') +
    ':' +
    String(s).padStart(2, '0') +
    ',' +
    String(mmm).padStart(3, '0')
  );
}

function applyEditsToSrt(blocks, edits) {
  if (!blocks || !blocks.length) return '';
  var e = edits || {};
  var lines = [];
  for (var i = 0; i < blocks.length; i++) {
    var b = blocks[i];
    var text = Object.prototype.hasOwnProperty.call(e, i) ? e[i] : b.text;
    lines.push(String(i + 1));
    lines.push(msToSrtTime(b.startMs) + ' --> ' + msToSrtTime(b.endMs));
    lines.push(text);
    lines.push('');
  }
  return lines.join('\n');
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    defaultPreviewState: defaultPreviewState,
    loadPreviewState: loadPreviewState,
    applyEditsToSrt: applyEditsToSrt,
    msToSrtTime: msToSrtTime,
  };
}
