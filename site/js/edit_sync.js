// Edit auto-sync: replicates a talk's edit-bearing localStorage entries to a
// state file on a deterministic GitHub branch (draft PR), so signed-in users
// get background persistence and cross-device continuation.
//
// Single source: loaded via <script src="js/edit_sync.js"> in site/index.html
// AND required by the Node test suite — no inline mirror.
//
// Model: the "sync document" is {version, revision, updatedAt, client, talkId,
// entries} where entries maps the exact localStorage keys (review_<talk>,
// review_srt_<talk>_*, preview_<talk>_*) to their parsed values. Safety comes
// from a per-item three-way merge against the last-synced base plus the
// Contents-API sha acting as compare-and-swap (409 on a concurrent writer).

// State file lives OUTSIDE talks/ on purpose: no workflow paths-filter
// (ci.yml, sync-subtitles.yml, deploy-pages.yml) matches .review-sync/**,
// so sync commits trigger zero CI runs. A `target` scopes the sync to one
// edited file (v3): each target gets its own branch/state file/PR, so
// unrelated work products (a transcript vs a video's SRT) never share a PR.
function syncFilePath(talkId, target) {
  return target ? '.review-sync/' + talkId + '/' + target + '.json'
    : '.review-sync/' + talkId + '.json';
}

// localStorage key of the sync base: the last successfully synced doc + its
// blob sha (the CAS token) + the attached PR coordinates. Target-scoped keys
// use `__` (the target slug already contains single hyphens).
function syncBaseKey(talkId, target) {
  return target ? 'sy_sync_base_' + talkId + '__' + target : 'sy_sync_base_' + talkId;
}

// --- file-scoped sync targets ----------------------------------------------
// A target names ONE edited file within a talk and the localStorage keys that
// build it. The video-SRT target is SHARED by the preview and the review-SRT
// views of the same video+final-lang (they now write the same canonical block
// store), so those two modes converge on one PR instead of fighting over the
// file. Markers/preview-mode carry no committed file and stay out of the
// file-scoped sync (still local + in "Copy backup").
function srtSyncTarget(talkId, videoSlug, lang) {
  var canon = 'srt_edits_' + talkId + '_' + videoSlug + '_' + lang;
  var legacyPrefix = 'review_srt_' + talkId + '_' + videoSlug + '_';
  var suffix = '_' + lang;
  return {
    slug: videoSlug + '-' + lang,
    filter: function (key) {
      if (key === canon) return true;
      return key.indexOf(legacyPrefix) === 0 && key.slice(-suffix.length) === suffix;
    },
  };
}

function transcriptSyncTarget(talkId, lang) {
  var reviewKey = 'review_' + talkId;
  return {
    // The transcript review key is rightLang-agnostic (a pre-existing SPA
    // quirk); the slug carries the active lang so the branch/file are named
    // for the transcript actually being committed.
    slug: 'transcript-' + lang,
    filter: function (key) { return key === reviewKey; },
  };
}

// The sync-space predicate: ONLY the edit-bearing keys. UI-state keys
// (sy_review_*, sy.preview_pos.*, sy.sync_player.*) never sync.
function isSyncSpaceKey(key, talkId) {
  return key === 'review_' + talkId
    || key.indexOf('review_srt_' + talkId + '_') === 0
    || key.indexOf('preview_' + talkId + '_') === 0
    || key.indexOf('srt_edits_' + talkId + '_') === 0;
}

// Canonical per-block stores (js/edit_store.js) are a bare {blockIdx: text}
// map, unlike the {marks/markers/edits} wrappers of the other entries.
function isCanonicalKey(key) { return String(key).indexOf('srt_edits_') === 0; }

// An entry with no marks, no markers and no edits carries nothing worth
// syncing (e.g. everything was reverted) — treated as absent. `key` selects
// the entry's shape (canonical block map vs marks/markers/edits wrapper).
function entryIsEmpty(entry, key) {
  if (!entry) return true;
  if (isCanonicalKey(key)) return !Object.keys(entry).length;
  if (Object.keys(entry.marks || {}).length) return false;
  if ((entry.markers || []).length) return false;
  var edits = entry.edits || {};
  var keys = Object.keys(edits);
  for (var i = 0; i < keys.length; i++) {
    var v = edits[keys[i]];
    if (typeof v === 'string') return false;               // review: {idx: text}
    if (v && Object.keys(v).length) return false;          // preview: {lang: {idx: text}}
  }
  return true;
}

// Read the talk's sync-space entries out of localStorage. Unparseable or
// empty values are skipped. An optional `keyFilter` scopes the read to one
// target (v3); without it, every sync-space key is collected (used by the
// "Copy backup" action, which backs up the whole talk).
function collectSyncEntries(talkId, storage, keyFilter) {
  var entries = {};
  for (var i = 0; i < storage.length; i++) {
    var key = storage.key(i);
    if (!key || !isSyncSpaceKey(key, talkId)) continue;
    if (keyFilter && !keyFilter(key)) continue;
    var parsed;
    try { parsed = JSON.parse(storage.getItem(key)); } catch (e) { continue; }
    if (entryIsEmpty(parsed, key)) continue;
    entries[key] = parsed;
  }
  return entries;
}

// Write merged entries back into localStorage; sync-space keys absent from
// the doc are removed (a delete that won the merge). Returns the keys whose
// stored value actually changed, so the caller can re-render only then. The
// same optional `keyFilter` scopes BOTH the write set and the stale-deletion
// scan to one target — critical so a target-scoped engine never deletes a
// sibling target's local edits.
function applySyncEntries(talkId, entries, storage, keyFilter) {
  var changed = [];
  var present = {};
  var stale = [];
  for (var i = 0; i < storage.length; i++) {
    var key = storage.key(i);
    if (key && isSyncSpaceKey(key, talkId) && (!keyFilter || keyFilter(key))) {
      present[key] = true; if (!(key in entries)) stale.push(key);
    }
  }
  Object.keys(entries).forEach(function (key) {
    var next = JSON.stringify(entries[key]);
    if (storage.getItem(key) !== next) {
      storage.setItem(key, next);
      changed.push(key);
    }
  });
  stale.forEach(function (key) {
    storage.removeItem(key);
    changed.push(key);
  });
  return changed;
}

// --- flatten/unflatten: entries -> a flat map of leaf items ----------------
// Flat key = JSON array [entryKey, ...path] (JSON so arbitrary text in marker
// identities cannot collide with a separator). Leaf value = JSON string.
// Items: marks.<idx>, edits.<idx> (review), edits.<lang>.<idx> (preview),
// mode, markers keyed by identity time|text (whole marker object as value).

function markerIdentity(m) { return String(m && m.time) + '|' + String((m && m.text) || ''); }

function flattenDoc(entries) {
  var flat = {};
  Object.keys(entries || {}).forEach(function (entryKey) {
    var e = entries[entryKey] || {};
    if (isCanonicalKey(entryKey)) {
      Object.keys(e).forEach(function (idx) {
        flat[JSON.stringify([entryKey, 'blocks', idx])] = JSON.stringify(e[idx]);
      });
      return;
    }
    var marks = e.marks || {};
    Object.keys(marks).forEach(function (idx) {
      flat[JSON.stringify([entryKey, 'marks', idx])] = JSON.stringify(marks[idx]);
    });
    var edits = e.edits || {};
    Object.keys(edits).forEach(function (k) {
      var v = edits[k];
      if (v !== null && typeof v === 'object') {
        Object.keys(v).forEach(function (idx) {
          flat[JSON.stringify([entryKey, 'edits', k, idx])] = JSON.stringify(v[idx]);
        });
      } else {
        flat[JSON.stringify([entryKey, 'edits', k])] = JSON.stringify(v);
      }
    });
    if (e.mode !== undefined) {
      flat[JSON.stringify([entryKey, 'mode'])] = JSON.stringify(e.mode);
    }
    (e.markers || []).forEach(function (m) {
      flat[JSON.stringify([entryKey, 'markers', markerIdentity(m)])] = JSON.stringify(m);
    });
  });
  return flat;
}

function unflattenDoc(flat) {
  var entries = {};
  Object.keys(flat).forEach(function (flatKey) {
    var path = JSON.parse(flatKey);
    var entryKey = path[0], kind = path[1];
    var e = entries[entryKey];
    if (!e) e = entries[entryKey] = { marks: {}, edits: {}, markers: [], blocks: {} };
    var value = JSON.parse(flat[flatKey]);
    if (kind === 'blocks') {
      e.blocks[path[2]] = value;
    } else if (kind === 'marks') {
      e.marks[path[2]] = value;
    } else if (kind === 'edits') {
      if (path.length === 4) {
        if (!e.edits[path[2]]) e.edits[path[2]] = {};
        e.edits[path[2]][path[3]] = value;
      } else {
        e.edits[path[2]] = value;
      }
    } else if (kind === 'mode') {
      e.mode = value;
    } else if (kind === 'markers') {
      e.markers.push(value);
    }
  });
  Object.keys(entries).forEach(function (entryKey) {
    var e = entries[entryKey];
    e.markers.sort(function (a, b) { return (a.time || 0) - (b.time || 0); });
    // Normalize to the EXACT shape (fields and order) the app itself stores
    // (savePreviewState: {mode, markers, edits}; saveReview: {marks, edits})
    // — the "unchanged" fast path and change detection compare JSON strings,
    // so a byte-different equal doc would cause pointless pushes/re-renders.
    // A merge can leave an entry with no items (every edit deleted) — drop it.
    var isPreview = entryKey.indexOf('preview_') === 0;
    var norm = isCanonicalKey(entryKey) ? e.blocks
      : isPreview
        ? { mode: e.mode === undefined ? 'marker' : e.mode, markers: e.markers, edits: e.edits }
        : { marks: e.marks, edits: e.edits };
    if (entryIsEmpty(norm, entryKey)) delete entries[entryKey];
    else entries[entryKey] = norm;
  });
  return entries;
}

// Per-item three-way merge. For each leaf item:
//   local == remote            -> either (agreement, incl. both absent)
//   local == base              -> remote's version (only remote changed)
//   otherwise                  -> local's version (local changed; on a true
//                                 conflict local wins and the re-push carries
//                                 it to the other device)
// Deletions are just absence — no tombstones needed with a base snapshot.
function mergeSyncDocs(baseEntries, localEntries, remoteEntries) {
  var bf = flattenDoc(baseEntries || {});
  var lf = flattenDoc(localEntries || {});
  var rf = flattenDoc(remoteEntries || {});
  var keys = {};
  [bf, lf, rf].forEach(function (m) { Object.keys(m).forEach(function (k) { keys[k] = true; }); });
  var out = {};
  Object.keys(keys).forEach(function (k) {
    var b = bf[k], l = lf[k], r = rf[k];
    var v;
    if (l === r) v = l;
    else if (l === b) v = r;
    else v = l;
    if (v !== undefined) out[k] = v;
  });
  function differs(m) {
    var ka = Object.keys(out), kb = Object.keys(m);
    if (ka.length !== kb.length) return true;
    for (var i = 0; i < ka.length; i++) { if (m[ka[i]] !== out[ka[i]]) return true; }
    return false;
  }
  return {
    entries: unflattenDoc(out),
    changedVsLocal: differs(lf),
    changedVsRemote: differs(rf),
  };
}

function makeSyncDoc(talkId, entries, revision, client, nowIso) {
  return {
    version: 1,
    revision: revision,
    updatedAt: nowIso,
    client: client,
    talkId: talkId,
    entries: entries,
  };
}

// ---------------------------------------------------------------------------
// Sync engine: debounce, compare-and-swap pushes, draft-PR bootstrap, pulls.
// Everything injectable (gh client object, storage, timers, clock) so the
// Node suite drives it without HTTP or real time.
// ---------------------------------------------------------------------------
function createSyncEngine(opts) {
  var api = opts.api, token = opts.token, talkId = opts.talkId;
  var storage = opts.storage, gh = opts.gh, fetchImpl = opts.fetchImpl;
  var setT = opts.setTimeoutFn || setTimeout;
  var clearT = opts.clearTimeoutFn || clearTimeout;
  var now = opts.now || function () { return Date.now(); };
  var isOffline = opts.isOffline || function () { return false; };
  var onStatus = opts.onStatus || function () {};
  var onRemoteApplied = opts.onRemoteApplied || function () {};
  var branch = opts.branch;
  var baseBranch = opts.base || 'main';
  var owner = opts.owner;
  var login = opts.login;
  var target = opts.target || null;               // v3 file-scope (or null = whole talk)
  var entryFilter = opts.entryFilter || null;     // key predicate for this target
  var path = syncFilePath(talkId, target);
  // Bind the filter into the collect/apply helpers so every call site is
  // scoped to this engine's target.
  function collect() { return collectSyncEntries(talkId, storage, entryFilter); }
  function apply(entries) { return applySyncEntries(talkId, entries, storage, entryFilter); }

  var DEBOUNCE_MS = 15000;   // push this long after the LAST edit
  var COALESCE_MS = 1500;    // push shortly after a field blur
  var PULL_THROTTLE_MS = 60000;
  var MAX_PUT_ATTEMPTS = 3;

  // Base meta = last synced doc + CAS sha + PR coordinates; survives reloads.
  var meta = null;
  try { meta = JSON.parse(storage.getItem(syncBaseKey(talkId, target))); } catch (e) { /* corrupted -> fresh */ }
  if (!meta || meta.branch !== branch) {
    meta = { doc: {}, sha: null, revision: 0, prNumber: null, prUrl: null, nodeId: null,
      prDraft: null, fileShas: {}, branch: branch };
  }
  if (!meta.fileShas) meta.fileShas = {};
  // Rebuilds the real edited files for the currently open view (wiring
  // provides it); their commits make the draft PR diff human-readable.
  var buildFiles = opts.buildFiles || function () { return []; };

  // Last gate before rebuilt file bytes reach GitHub. Collaborators still hold
  // edits containing NBSP in localStorage from before the input fields were
  // fixed, so this is not redundant with the SPA's edit handlers. The typeof
  // guard keeps this module loadable where the twin is not present.
  var sanitize = opts.sanitize
    || (typeof sanitizeInvisible === 'function' ? sanitizeInvisible : null);

  var clientId = opts.clientId || (function () {
    var c = storage.getItem('sy_sync_client');
    if (!c) { c = Math.random().toString(36).slice(2, 8); storage.setItem('sy_sync_client', c); }
    return c;
  })();

  var status = 'idle';
  var lastError = null;
  var dirty = false;
  var editSeq = 0;
  var debounceId = null, coalesceId = null;
  var lastPullAt = 0;
  var inflight = null;
  var disposed = false;
  // Set for the whole of finalize(). It owns the chip's tone while it runs, so
  // a pull() landing in the middle (focus / visibilitychange fire one, and
  // tabbing away to GitHub during a finalize is the likeliest thing a user
  // does here) must not paint 'synced' over the progress — nor over a finalize
  // that is about to fail.
  var finalizing = false;

  function info() {
    return { status: status, prUrl: meta.prUrl, prNumber: meta.prNumber, nodeId: meta.nodeId,
      prDraft: meta.prDraft, branch: branch, dirty: dirty, error: lastError };
  }
  function setStatus(s, err) { status = s; lastError = err || null; onStatus(s, info()); }
  function saveMeta() { storage.setItem(syncBaseKey(talkId, target), JSON.stringify(meta)); }

  function parseRemote(file) {
    var doc = null;
    try { doc = JSON.parse(file.content); } catch (e) { /* treat as empty */ }
    return {
      entries: (doc && doc.entries) || {},
      revision: (doc && doc.revision) || 0,
      sha: file.sha,
    };
  }

  function armDebounce() {
    if (debounceId !== null) clearT(debounceId);
    debounceId = setT(function () { debounceId = null; flush(); }, DEBOUNCE_MS);
  }

  function notifyEdit() {
    if (disposed) return;
    dirty = true;
    editSeq += 1;
    armDebounce();
    if (status === 'synced' || status === 'idle' || status === 'ready') setStatus('pending');
  }

  function flushSoon() {
    if (disposed || !dirty) return;
    if (coalesceId !== null) clearT(coalesceId);
    coalesceId = setT(function () { coalesceId = null; flush(); }, COALESCE_MS);
  }

  function flush(fopts) {
    // force bypasses the dirty gate: the recovery path ("Retry now") must be
    // able to re-run the PR-creation tail even after the state itself pushed.
    if (disposed || (!dirty && !(fopts && fopts.force))) return Promise.resolve();
    if (inflight) return inflight.then(function () { return flush(fopts); });
    inflight = doFlush(fopts)
      .then(function () { inflight = null; }, function () { inflight = null; });
    return inflight;
  }

  function clearDirty() {
    dirty = false;
    if (debounceId !== null) { clearT(debounceId); debounceId = null; }
  }

  // Reset to a pristine, un-synced base — a later edit lazily re-creates the
  // branch/PR from scratch. Reassigns the closure's meta so every reader sees it.
  function resetBase() {
    meta = { doc: {}, sha: null, revision: 0, prNumber: null, prUrl: null, nodeId: null,
      prDraft: null, fileShas: {}, branch: branch };
    saveMeta();
  }

  // Everything was reverted locally. Before destroying the shared branch, pull
  // its current state and three-way merge: a concurrent device may have synced
  // edits we never pulled. If the merged result is still empty, close the PR +
  // delete the branch and go idle (the chip hides); if it carries edits, keep
  // the PR and re-arm a normal flush to push the merged doc back. seqAtStart
  // guards a re-edit that lands mid-teardown (undo -> redo): it must re-create
  // from the pristine base, never be dropped under a lying 'idle'. Idempotent:
  // closePull swallows an already-gone PR, deleteRef an already-gone branch.
  function teardown(seqAtStart) {
    setStatus('syncing');
    function fail(e) {
      if (disposed) return;
      var msg = e && e.message;
      var st = e && e.status;
      if (isOffline(e)) { setStatus('pending', { kind: 'offline', message: msg }); return; }
      setStatus('error', { kind: 'sync', message: msg || String(e), httpStatus: st });
    }
    return gh.getFileContent(api, token, path, branch, fetchImpl).then(function (file) {
      if (disposed) return;
      if (file) {
        var remote = parseRemote(file);
        var merged = mergeSyncDocs(meta.doc || {}, collect(), remote.entries);
        var changedKeys = apply(merged.entries);
        if (changedKeys.length) onRemoteApplied(changedKeys);
        meta.doc = remote.entries;
        meta.sha = remote.sha;
        meta.revision = Math.max(meta.revision || 0, remote.revision || 0);
        saveMeta();
        if (Object.keys(merged.entries).length) {
          // A concurrent device's edits survive on the remote — don't tear the
          // PR down; re-arm a flush so the merged doc is pushed back.
          dirty = true;
          editSeq += 1;
          armDebounce();
          setStatus('pending');
          return;
        }
      }
      var prNumber = meta.prNumber;
      var chain = prNumber
        ? gh.closePull(api, token, prNumber, fetchImpl)
        : Promise.resolve();
      return chain
        .then(function () { return gh.deleteRef(api, token, branch, fetchImpl); })
        .then(function () {
          if (disposed) return;
          resetBase();
          if (editSeq === seqAtStart) {
            clearDirty();
            setStatus('idle');
          } else {
            // A re-edit landed mid-teardown: its dirty flag + armed debounce are
            // intact, so it re-creates from the pristine base. Keep the chip
            // honest ('pending'), never 'idle'.
            setStatus('pending');
          }
        });
    }).catch(fail);
  }

  // GitHub reports a PUT/GET against a deleted branch as 404 "Branch <name> not
  // found". It means the sync branch was removed out from under us — a manual PR
  // close + branch delete on github.com, or a teardown on another device (a
  // closed PR's branch is gone). The cached prNumber/sha are stale; the cure is
  // to wipe the branch-dependent state and re-create from scratch.
  function isBranchGone(e) {
    return !!(e && e.status === 404 && /branch .*not found/i.test(e.message || ''));
  }

  function doFlush(fopts, healed) {
    var keepalive = fopts && fopts.keepalive;
    var seqAtStart = editSeq;
    var local = collect();
    if (!Object.keys(local).length) {
      // Everything was reverted. If a PR/state was already synced, tear it
      // down ("no edits = no PR"); otherwise just stay idle without a request —
      // attach() covers remote adoption and a mode toggle must not cost one.
      if (meta.prNumber || meta.sha !== null) return teardown(seqAtStart);
      clearDirty();
      if (status !== 'idle') setStatus('idle');
      return Promise.resolve();
    }
    setStatus('syncing');
    var attempt = 0;

    // Fold a freshly fetched remote doc into local state: three-way merge,
    // write remote-won items into storage, advance the base to the remote.
    function integrateRemote(remote) {
      var merged = mergeSyncDocs(meta.doc || {}, collect(), remote.entries);
      var changedKeys = apply(merged.entries);
      if (changedKeys.length) onRemoteApplied(changedKeys);
      meta.doc = remote.entries;
      meta.sha = remote.sha;
      meta.revision = Math.max(meta.revision || 0, remote.revision || 0);
      local = merged.entries;
    }

    // First push of this session (or right after a finalize): adopt whatever
    // the sync branch already holds, re-attach its PR, or create the branch.
    function ensureRemoteBase() {
      if (meta.sha !== null) return Promise.resolve();
      return gh.getFileContent(api, token, path, branch, fetchImpl).then(function (file) {
        if (file) { integrateRemote(parseRemote(file)); return; }
        // A known PR means the branch exists and the state file was removed
        // by a finalize — the push below simply recreates it.
        if (meta.prNumber) return;
        return gh.findOpenPrByHead(api, token, owner, branch, fetchImpl).then(function (pr) {
          if (pr) {
            // existing PR on the deterministic branch (finalized on another
            // device, or the state file was lost) — reuse it
            meta.prNumber = pr.number; meta.prUrl = pr.html_url; meta.nodeId = pr.node_id;
            meta.prDraft = pr.draft !== false;
            saveMeta();
            return;
          }
          return gh.getBranchHeadSha(api, token, baseBranch, fetchImpl).then(function (sha) {
            return gh.createRef(api, token, branch, sha, fetchImpl).catch(function (e) {
              if (e && e.status === 422) return; // branch already exists — fine
              throw e;
            });
          });
        });
      });
    }

    // A submitted (ready) PR silently returns to draft when editing resumes —
    // new commits must never land on a PR that looks review-ready.
    function ensureDraft() {
      if (disposed || !meta.prNumber || meta.prDraft !== false) return Promise.resolve();
      return gh.convertPullToDraft(token, meta.nodeId, fetchImpl).then(function () {
        meta.prDraft = true;
        saveMeta();
      });
    }

    // Commit the rebuilt real files (the open view's transcript/SRT) so the
    // PR diff stays human-readable. Blob shas are cached per path; a stale
    // sha (409/422) is refreshed once and retried.
    function pushFiles() {
      if (disposed) return Promise.resolve();
      // Invisible characters ONLY: `content` is a whole rebuilt file, and the
      // field-level rule would collapse its newlines and destroy the SRT.
      var files = (buildFiles() || []).map(function (f) {
        return sanitize ? { path: f.path, content: sanitize(f.content) } : f;
      });
      var chain = Promise.resolve();
      files.forEach(function (file) {
        chain = chain.then(function () {
          var known = meta.fileShas[file.path]
            ? Promise.resolve(meta.fileShas[file.path])
            : gh.getFileSha(api, token, file.path, branch, fetchImpl);
          return known.then(function (sha) {
            function put(shaToUse) {
              return gh.putFile(api, token, {
                path: file.path, branch: branch,
                message: 'sync: ' + talkId + ' edits',
                content: file.content, sha: shaToUse || undefined,
                keepalive: keepalive,
              }, fetchImpl);
            }
            return put(sha).catch(function (e) {
              if (e && (e.status === 409 || e.status === 422)) {
                return gh.getFileSha(api, token, file.path, branch, fetchImpl).then(put);
              }
              throw e;
            });
          }).then(function (res) {
            meta.fileShas[file.path] = (res && res.content && res.content.sha) || null;
            saveMeta();
          });
        });
      });
      return chain;
    }

    function push() {
      if (disposed) return Promise.resolve();
      attempt += 1;
      var revision = (meta.revision || 0) + 1;
      var doc = makeSyncDoc(talkId, local, revision, clientId, new Date(now()).toISOString());
      return gh.putFile(api, token, {
        path: path,
        branch: branch,
        message: 'sync: edit state for ' + talkId,
        content: JSON.stringify(doc, null, 2) + '\n',
        sha: meta.sha || undefined,
        keepalive: keepalive,
      }, fetchImpl).then(function (res) {
        meta.doc = local;
        meta.sha = (res && res.content && res.content.sha) || null;
        meta.revision = revision;
        if (editSeq === seqAtStart) clearDirty();
        saveMeta();
      }, function (e) {
        // CAS: someone else wrote the file since our base sha. Refresh, merge,
        // retry — the sha is the lock, the merge preserves both sides.
        if (e && e.status === 409 && attempt < MAX_PUT_ATTEMPTS) {
          return gh.getFileContent(api, token, path, branch, fetchImpl).then(function (file) {
            if (file) integrateRemote(parseRemote(file));
            else meta.sha = null;
            return push();
          });
        }
        throw e;
      });
    }

    function ensurePr() {
      if (disposed || meta.prNumber) return Promise.resolve();
      var title = 'Edit sync: ' + talkId + ' (' + login + ')';
      var body = 'Automated **draft** PR carrying in-progress review/preview edits from the SPA.\n\n'
        + '- State file: `' + path + '`\n'
        + '- Branch: `' + branch + '`\n\n'
        + 'It is updated in the background while the user edits, and is flipped to '
        + 'ready-for-review (real files committed, state file removed) when the user '
        + 'finalizes from the app. Do not merge while draft.';
      function adopt(pr) {
        meta.prNumber = pr.number; meta.prUrl = pr.html_url; meta.nodeId = pr.node_id;
        meta.prDraft = pr.draft !== false;
        saveMeta();
      }
      return gh.createPull(api, token,
        { head: branch, base: baseBranch, title: title, body: body, draft: true }, fetchImpl)
        .then(adopt, function (e) {
          if (e && e.status === 422 && /draft/i.test(e.message || '')) {
            return gh.createPull(api, token,
              { head: branch, base: baseBranch, title: title, body: body }, fetchImpl).then(adopt);
          }
          if (e && e.status === 422 && /already exists/i.test(e.message || '')) {
            return gh.findOpenPrByHead(api, token, owner, branch, fetchImpl)
              .then(function (pr) { if (pr) adopt(pr); });
          }
          throw e;
        });
    }

    return ensureRemoteBase().then(function () {
      if (disposed) return;
      // Same doc as the last push (e.g. an edit typed and reverted): no PUT,
      // but still make sure the PR exists (its creation may have failed).
      var unchanged = meta.sha !== null
        && JSON.stringify(local) === JSON.stringify(meta.doc || {});
      var step = unchanged
        ? Promise.resolve()
        : ensureDraft().then(push).then(pushFiles);
      return step.then(ensurePr).then(function () {
        if (disposed) return;
        if (unchanged && editSeq === seqAtStart) clearDirty();
        // A finalize that pre-flushed owns the chip until it is done: 'synced'
        // here would flash a green "done" three requests too early.
        if (!finalizing) setStatus('synced');
      });
    }).catch(function (e) {
      if (disposed) return;
      // Self-heal a branch deleted out from under us (closed PR + deleted branch,
      // externally or on another device): wipe the stale branch/PR coordinates
      // and re-create the branch, state file and a fresh draft PR. One retry only
      // — `healed` guards against a loop if the re-create somehow 404s again.
      if (isBranchGone(e) && !healed) {
        resetBase();
        return doFlush(fopts, true);
      }
      throw e;
    }).catch(function (e) {
      if (disposed) return;
      // A rejected promise can carry a falsy reason, so read through e defensively.
      var msg = e && e.message;
      var status = e && e.status;
      if (isOffline(e)) { setStatus('pending', { kind: 'offline', message: msg }); return; }
      if (status === 401) { setStatus('error', { kind: 'auth', message: msg }); return; }
      setStatus('error', { kind: 'sync', message: msg || String(e), httpStatus: status });
    });
  }

  function pull(force) {
    if (disposed) return Promise.resolve();
    var t = now();
    if (!force && t - lastPullAt < PULL_THROTTLE_MS) return Promise.resolve();
    lastPullAt = t;
    return gh.getFileContent(api, token, path, branch, fetchImpl).then(function (file) {
      if (!file) {
        // No remote state yet (the sync branch/file has not been created). If we
        // already hold un-synced local edits — e.g. the user re-opened a page
        // they had edited in a previous session and never typed again, so no
        // notifyEdit() fires — arm a push so the first sync still creates the
        // branch + state file + draft PR instead of waiting for a fresh edit.
        var pending = mergeSyncDocs(meta.doc || {}, collect(), {});
        if (pending.changedVsRemote) {
          dirty = true;
          editSeq += 1;
          armDebounce();
          setStatus('pending');
        }
        return;
      }
      if (file.sha === meta.sha) {
        if (!dirty && !finalizing && status !== 'synced') setStatus('synced');
        return;
      }
      var remote = parseRemote(file);
      var merged = mergeSyncDocs(meta.doc || {}, collect(), remote.entries);
      var changedKeys = apply(merged.entries);
      if (changedKeys.length) onRemoteApplied(changedKeys);
      meta.doc = remote.entries;
      meta.sha = remote.sha;
      meta.revision = Math.max(meta.revision || 0, remote.revision || 0);
      saveMeta();
      if (merged.changedVsRemote) {
        // Local still differs (dirty edits or a merge the remote lacks) —
        // schedule a push so the other device converges.
        dirty = true;
        editSeq += 1;
        armDebounce();
        setStatus('pending');
      } else if (!dirty && !finalizing) {
        setStatus('synced');
      }
    }).catch(function (e) {
      // A rejected promise can carry a falsy reason, so read status defensively.
      var status = e && e.status;
      if (status === 401) { setStatus('error', { kind: 'auth', message: e && e.message }); return; }
      // Offline / transient pull failures are silent: the next focus retries.
    });
  }

  // On talk open: adopt the remote state and re-attach the PR coordinates
  // (cached in the base meta, else looked up by the deterministic head —
  // a finalized-on-another-device PR surfaces here as the 'ready' state).
  function attach() {
    if (disposed) return Promise.resolve();
    return pull(true).then(function () {
      if (meta.prNumber) {
        if (meta.prDraft === false && !dirty && status !== 'ready') setStatus('ready');
        return;
      }
      return gh.findOpenPrByHead(api, token, owner, branch, fetchImpl).then(function (pr) {
        if (!pr) return;
        meta.prNumber = pr.number; meta.prUrl = pr.html_url; meta.nodeId = pr.node_id;
        meta.prDraft = pr.draft !== false;
        saveMeta();
        if (meta.prDraft === false && !dirty) setStatus('ready');
        else onStatus(status, info());
      }).catch(function () { /* PR lookup is cosmetic — never fail attach */ });
    });
  }

  // Finalize: push anything pending, remove the state file from the branch
  // and flip the draft PR to ready-for-review. Fully reversible — the next
  // edit re-drafts the PR and recreates the state (see ensureDraft).
  // The resting tone this engine should be wearing, computed from what is
  // actually true right now. A finalize that fails cannot replay a status it
  // snapshotted on the way in: its own pre-flush may have pushed everything
  // (so 'pending' would be a lie no debounce ever clears) or may have been
  // mid-flight (so the snapshot is a transient 'syncing' and the chip spins
  // forever). An error already on the chip is a diagnosis — never overwrite it.
  function restingStatus() {
    if (status === 'error') return null;
    if (dirty) return 'pending';
    return meta.prDraft === false ? 'ready' : 'synced';
  }

  function finalize() {
    if (disposed || !meta.prNumber) return Promise.reject(new Error('no sync PR to finalize'));
    // The UI lock should prevent this, but the engine holds its own invariant:
    // two overlapping runs would have the first's tail clear `finalizing` while
    // the second is still working.
    if (finalizing) return Promise.reject(new Error('already finalizing'));
    // The chip is the only feedback this action has — it is fired from a
    // dropdown item that closes itself — so claim the progress tone BEFORE the
    // first call goes out. The claim is a flag, not the status string: pull()
    // and the pre-flush both write that string, and a guard keyed on it would
    // be skipped, leaving the chip claiming "synced" for a PR nobody finalized.
    finalizing = true;
    setStatus('syncing');
    var pre = dirty ? flush() : Promise.resolve();
    return pre.then(function () {
      return gh.getFileContent(api, token, path, branch, fetchImpl);
    }).then(function (file) {
      if (file) {
        return gh.deleteFile(api, token, {
          path: path, branch: branch,
          message: 'sync: finalize ' + talkId, sha: file.sha,
        }, fetchImpl);
      }
    }).then(function () {
      return gh.markPullReady(token, meta.nodeId, fetchImpl);
    }).then(function () {
      meta.prDraft = false;
      meta.sha = null; // the state file is gone; the next push recreates it
      saveMeta();
      finalizing = false;
      // Guarded like every other tail: once destroyed this chip belongs to
      // whatever talk the user opened instead.
      if (!disposed) setStatus('ready');
      return { number: meta.prNumber, html_url: meta.prUrl };
    }).catch(function (e) {
      finalizing = false;
      if (!disposed) {
        var back = restingStatus();
        if (back) setStatus(back);
      }
      throw e;
    });
  }

  // Tear down: no further timers or status emissions. Returns a promise that
  // resolves once any in-flight flush settles — finalize awaits it so a PUT
  // in the air cannot race its read-then-delete of the state file.
  function destroy() {
    disposed = true;
    if (debounceId !== null) { clearT(debounceId); debounceId = null; }
    if (coalesceId !== null) { clearT(coalesceId); coalesceId = null; }
    return inflight || Promise.resolve();
  }

  return {
    notifyEdit: notifyEdit,
    flushSoon: flushSoon,
    flush: flush,
    pull: pull,
    attach: attach,
    finalize: finalize,
    destroy: destroy,
    getInfo: info,
  };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    syncFilePath: syncFilePath,
    syncBaseKey: syncBaseKey,
    srtSyncTarget: srtSyncTarget,
    transcriptSyncTarget: transcriptSyncTarget,
    isSyncSpaceKey: isSyncSpaceKey,
    entryIsEmpty: entryIsEmpty,
    collectSyncEntries: collectSyncEntries,
    applySyncEntries: applySyncEntries,
    flattenDoc: flattenDoc,
    unflattenDoc: unflattenDoc,
    mergeSyncDocs: mergeSyncDocs,
    makeSyncDoc: makeSyncDoc,
    createSyncEngine: createSyncEngine,
  };
}
