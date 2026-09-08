const { describe, it } = require('node:test');
const assert = require('node:assert');
const {
  syncFilePath, syncBaseKey, collectSyncEntries, applySyncEntries,
  mergeSyncDocs, makeSyncDoc, flattenDoc, unflattenDoc,
  srtSyncTarget, transcriptSyncTarget,
} = require('../site/js/edit_sync');

const TALK = '1979-09-27_Shri-Kundalini-Shakti-And-Shri-Jesus-Bombay';

// Minimal localStorage double (same surface the module touches).
function memStorage(init) {
  const m = new Map(Object.entries(init || {}));
  return {
    get length() { return m.size; },
    key(i) { const k = Array.from(m.keys()); return i < k.length ? k[i] : null; },
    getItem(k) { return m.has(k) ? m.get(k) : null; },
    setItem(k, v) { m.set(k, String(v)); },
    removeItem(k) { m.delete(k); },
  };
}

describe('names', () => {
  it('syncFilePath and syncBaseKey are talk-scoped', () => {
    assert.strictEqual(syncFilePath(TALK), '.review-sync/' + TALK + '.json');
    assert.strictEqual(syncBaseKey(TALK), 'sy_sync_base_' + TALK);
  });
  it('target-scoped paths/keys nest the target', () => {
    assert.strictEqual(syncFilePath(TALK, 'video1-uk'), '.review-sync/' + TALK + '/video1-uk.json');
    assert.strictEqual(syncBaseKey(TALK, 'video1-uk'), 'sy_sync_base_' + TALK + '__video1-uk');
  });
});

describe('sync targets (file-scoped)', () => {
  it('srtSyncTarget claims the canonical block store and same-final-lang legacy leftovers', () => {
    const tgt = srtSyncTarget(TALK, 'video1', 'uk');
    assert.strictEqual(tgt.slug, 'video1-uk');
    assert.ok(tgt.filter('srt_edits_' + TALK + '_video1_uk'));
    assert.ok(tgt.filter('review_srt_' + TALK + '_video1_en_uk'));
    assert.ok(tgt.filter('review_srt_' + TALK + '_video1_hi_uk'));
    // other lang / other video / preview markers / canonical of another lang
    assert.ok(!tgt.filter('srt_edits_' + TALK + '_video1_de'));
    assert.ok(!tgt.filter('review_srt_' + TALK + '_video1_en_de'));
    assert.ok(!tgt.filter('srt_edits_' + TALK + '_video2_uk'));
    assert.ok(!tgt.filter('preview_' + TALK + '_video1'));
    assert.ok(!tgt.filter('review_' + TALK));
  });
  it('transcriptSyncTarget claims only the transcript review entry', () => {
    const tgt = transcriptSyncTarget(TALK, 'uk');
    assert.strictEqual(tgt.slug, 'transcript-uk');
    assert.ok(tgt.filter('review_' + TALK));
    assert.ok(!tgt.filter('srt_edits_' + TALK + '_video1_uk'));
    assert.ok(!tgt.filter('preview_' + TALK + '_video1'));
  });
});

describe('collectSyncEntries', () => {
  it('collects review, review_srt and preview entries for the talk only', () => {
    const storage = memStorage({
      ['review_' + TALK]: JSON.stringify({ marks: { 3: 'note' }, edits: { 7: 'текст' } }),
      ['review_srt_' + TALK + '_video1_en_uk']: JSON.stringify({ marks: {}, edits: { 1: 'a' } }),
      ['preview_' + TALK + '_video1']: JSON.stringify({ mode: 'edit', markers: [], edits: { uk: { 4: 'x' } } }),
      'review_2000-07-02_Other-Talk': JSON.stringify({ marks: { 1: 'other' }, edits: {} }),
      ['sy_review_mode_' + TALK]: '{"mode":"srt"}',
      ['sy.preview_pos.' + TALK + '.video1']: '17',
    });
    const entries = collectSyncEntries(TALK, storage);
    assert.deepStrictEqual(Object.keys(entries).sort(), [
      'preview_' + TALK + '_video1',
      'review_' + TALK,
      'review_srt_' + TALK + '_video1_en_uk',
    ]);
    assert.strictEqual(entries['review_' + TALK].edits[7], 'текст');
  });
  it('drops empty entries and unparseable values', () => {
    const storage = memStorage({
      ['review_' + TALK]: JSON.stringify({ marks: {}, edits: {} }),
      ['preview_' + TALK + '_v']: JSON.stringify({ mode: 'edit', markers: [], edits: { uk: {} } }),
      ['review_srt_' + TALK + '_v_en_uk']: 'not json',
    });
    assert.deepStrictEqual(collectSyncEntries(TALK, storage), {});
  });
});

describe('applySyncEntries', () => {
  it('writes entries, removes stale sync-space keys, reports real changes', () => {
    const storage = memStorage({
      ['review_' + TALK]: JSON.stringify({ marks: {}, edits: { 1: 'old' } }),
      ['review_srt_' + TALK + '_v_en_uk']: JSON.stringify({ marks: {}, edits: { 2: 'gone' } }),
      ['sy_review_mode_' + TALK]: '{"mode":"srt"}',
    });
    const entries = {
      ['review_' + TALK]: { marks: {}, edits: { 1: 'new' } },
      ['preview_' + TALK + '_v']: { mode: 'edit', markers: [], edits: { uk: { 3: 'x' } } },
    };
    const changed = applySyncEntries(TALK, entries, storage).sort();
    assert.deepStrictEqual(changed, [
      'preview_' + TALK + '_v',
      'review_' + TALK,
      'review_srt_' + TALK + '_v_en_uk',
    ]);
    assert.strictEqual(JSON.parse(storage.getItem('review_' + TALK)).edits[1], 'new');
    assert.strictEqual(storage.getItem('review_srt_' + TALK + '_v_en_uk'), null);
    // untouched: non-sync-space key survives
    assert.strictEqual(storage.getItem('sy_review_mode_' + TALK), '{"mode":"srt"}');
  });
  it('reports no changes when the storage already matches', () => {
    const entry = { marks: { 1: 'm' }, edits: {} };
    const storage = memStorage({ ['review_' + TALK]: JSON.stringify(entry) });
    const changed = applySyncEntries(TALK, { ['review_' + TALK]: entry }, storage);
    assert.deepStrictEqual(changed, []);
  });
  it('a key filter scopes both collection and stale-deletion to one target', () => {
    const CK = 'srt_edits_' + TALK + '_video1_uk';
    const storage = memStorage({
      [CK]: JSON.stringify({ 4: 'sub' }),
      ['review_' + TALK]: JSON.stringify({ marks: {}, edits: { 1: 'transcript' } }),
    });
    const tgt = srtSyncTarget(TALK, 'video1', 'uk');
    // collection sees only the target's key
    assert.deepStrictEqual(Object.keys(collectSyncEntries(TALK, storage, tgt.filter)), [CK]);
    // applying an EMPTY target doc removes the target's key but must NOT touch
    // the transcript key that belongs to a different target
    const changed = applySyncEntries(TALK, {}, storage, tgt.filter);
    assert.deepStrictEqual(changed, [CK]);
    assert.strictEqual(storage.getItem(CK), null);
    assert.ok(storage.getItem('review_' + TALK), 'other-target key survives');
  });
});

describe('mergeSyncDocs (three-way, per item)', () => {
  const K = 'review_' + TALK;
  function doc(edits, marks) { return { [K]: { marks: marks || {}, edits: edits } }; }

  it('adopts a remote-only addition', () => {
    const r = mergeSyncDocs(doc({}), doc({}), doc({ 5: 'remote' }));
    assert.strictEqual(r.entries[K].edits[5], 'remote');
    assert.strictEqual(r.changedVsLocal, true);
    assert.strictEqual(r.changedVsRemote, false);
  });
  it('keeps a local-only addition', () => {
    const r = mergeSyncDocs(doc({}), doc({ 5: 'local' }), doc({}));
    assert.strictEqual(r.entries[K].edits[5], 'local');
    assert.strictEqual(r.changedVsLocal, false);
    assert.strictEqual(r.changedVsRemote, true);
  });
  it('a local delete wins over an unchanged remote copy', () => {
    const base = doc({ 5: 'v' });
    const r = mergeSyncDocs(base, doc({}), doc({ 5: 'v' }));
    assert.strictEqual(r.entries[K], undefined); // entry emptied out entirely
    assert.strictEqual(r.changedVsRemote, true);
  });
  it('a remote delete is adopted when local did not touch the item', () => {
    const base = doc({ 5: 'v', 6: 'w' });
    const r = mergeSyncDocs(base, doc({ 5: 'v', 6: 'w' }), doc({ 6: 'w' }));
    assert.deepStrictEqual(r.entries[K].edits, { 6: 'w' });
    assert.strictEqual(r.changedVsLocal, true);
  });
  it('both changed differently: local wins and the loser is flagged for re-push', () => {
    const base = doc({ 5: 'v' });
    const r = mergeSyncDocs(base, doc({ 5: 'mine' }), doc({ 5: 'theirs' }));
    assert.strictEqual(r.entries[K].edits[5], 'mine');
    assert.strictEqual(r.changedVsRemote, true);
    assert.strictEqual(r.changedVsLocal, false);
  });
  it('independent items from both sides merge item-by-item', () => {
    const base = doc({ 1: 'a' });
    const r = mergeSyncDocs(base, doc({ 1: 'a', 2: 'local' }), doc({ 1: 'a', 3: 'remote' }));
    assert.deepStrictEqual(r.entries[K].edits, { 1: 'a', 2: 'local', 3: 'remote' });
    assert.strictEqual(r.changedVsLocal, true);
    assert.strictEqual(r.changedVsRemote, true);
  });
  it('empty local + non-empty remote adopts remote with nothing to push', () => {
    const r = mergeSyncDocs({}, {}, doc({ 5: 'remote' }, { 2: 'note' }));
    assert.deepStrictEqual(r.entries[K].edits, { 5: 'remote' });
    assert.deepStrictEqual(r.entries[K].marks, { 2: 'note' });
    assert.strictEqual(r.changedVsLocal, true);
    assert.strictEqual(r.changedVsRemote, false);
  });
  it('merges preview language-scoped edits and markers by identity', () => {
    const PK = 'preview_' + TALK + '_v';
    const m1 = { time: 10.5, tc: '00:00:10', text: 'sub a', comment: '' };
    const m1edited = { time: 10.5, tc: '00:00:10', text: 'sub a', comment: 'local note' };
    const m2 = { time: 99, tc: '00:01:39', text: 'sub b', comment: 'remote note' };
    const base = { [PK]: { mode: 'marker', markers: [m1], edits: { uk: { 1: 'x' } } } };
    const local = { [PK]: { mode: 'marker', markers: [m1edited], edits: { uk: { 1: 'x' } } } };
    const remote = { [PK]: { mode: 'marker', markers: [m1, m2], edits: { uk: { 1: 'x', 9: 'remote' } } } };
    const r = mergeSyncDocs(base, local, remote);
    const merged = r.entries[PK];
    assert.strictEqual(merged.markers.length, 2);
    assert.strictEqual(merged.markers.find((m) => m.time === 10.5).comment, 'local note');
    assert.strictEqual(merged.markers.find((m) => m.time === 99).comment, 'remote note');
    assert.deepStrictEqual(merged.edits.uk, { 1: 'x', 9: 'remote' });
    // markers stay sorted by time
    assert.ok(merged.markers[0].time <= merged.markers[1].time);
  });
});

describe('flatten/unflatten shape stability', () => {
  it('round-trips entries to the exact JSON the app itself stores', () => {
    // Byte-identical shapes matter: doFlush's "unchanged" fast path and
    // applySyncEntries' change detection compare JSON strings.
    const PK = 'preview_' + TALK + '_v';
    const RK = 'review_' + TALK;
    const m = { time: 5, tc: '00:00:05', text: 'sub', comment: 'c' };
    const preview = { mode: 'edit', markers: [m], edits: { uk: { 1: 'x' } } };
    const review = { marks: { 2: 'note' }, edits: { 1: 'y' } };
    const rt = unflattenDoc(flattenDoc({ [PK]: preview, [RK]: review }));
    assert.strictEqual(JSON.stringify(rt[PK]), JSON.stringify(preview));
    assert.strictEqual(JSON.stringify(rt[RK]), JSON.stringify(review));
    assert.ok(!('marks' in rt[PK]), 'preview entries carry no marks field');
    assert.ok(!('markers' in rt[RK]), 'review entries carry no markers field');
  });
});

describe('canonical srt_edits entries (shared preview/review block store)', () => {
  const CK = 'srt_edits_' + TALK + '_video1_uk';

  it('collectSyncEntries picks up canonical keys and drops empty maps', () => {
    const storage = memStorage({
      [CK]: JSON.stringify({ 4: 'правка' }),
      ['srt_edits_' + TALK + '_video1_en']: JSON.stringify({}),
      'srt_edits_2000-07-02_Other-Talk_v_uk': JSON.stringify({ 1: 'other' }),
    });
    const entries = collectSyncEntries(TALK, storage);
    assert.deepStrictEqual(Object.keys(entries), [CK]);
    assert.deepStrictEqual(entries[CK], { 4: 'правка' });
  });

  it('applySyncEntries removes stale canonical keys absent from the doc', () => {
    const storage = memStorage({ [CK]: JSON.stringify({ 4: 'gone' }) });
    const changed = applySyncEntries(TALK, {}, storage);
    assert.deepStrictEqual(changed, [CK]);
    assert.strictEqual(storage.getItem(CK), null);
  });

  it('round-trips to the exact JSON saveSrtEdits stores', () => {
    const entry = { 2: 'а', 11: 'б' };
    const rt = unflattenDoc(flattenDoc({ [CK]: entry }));
    assert.strictEqual(JSON.stringify(rt[CK]), JSON.stringify(entry));
    assert.ok(!('marks' in rt[CK]) && !('edits' in rt[CK]),
      'canonical entries stay a plain block map');
  });

  it('merges canonical entries per block', () => {
    const base = { [CK]: { 1: 'a' } };
    const local = { [CK]: { 1: 'a', 2: 'local' } };
    const remote = { [CK]: { 1: 'a', 3: 'remote' } };
    const r = mergeSyncDocs(base, local, remote);
    assert.deepStrictEqual(r.entries[CK], { 1: 'a', 2: 'local', 3: 'remote' });
    assert.strictEqual(r.changedVsLocal, true);
    assert.strictEqual(r.changedVsRemote, true);
  });

  it('an emptied canonical entry disappears from the merged doc', () => {
    const base = { [CK]: { 1: 'v' } };
    const r = mergeSyncDocs(base, {}, base);
    assert.strictEqual(r.entries[CK], undefined);
    assert.strictEqual(r.changedVsRemote, true);
  });
});

describe('makeSyncDoc', () => {
  it('wraps entries with version/revision/client/talkId', () => {
    const d = makeSyncDoc(TALK, { a: 1 }, 4, 'k3b9x2', '2026-07-13T22:00:00Z');
    assert.deepStrictEqual(d, {
      version: 1, revision: 4, updatedAt: '2026-07-13T22:00:00Z',
      client: 'k3b9x2', talkId: TALK, entries: { a: 1 },
    });
  });
});

// ---------------------------------------------------------------------------
// Sync engine
// ---------------------------------------------------------------------------
const { createSyncEngine } = require('../site/js/edit_sync');

const RKEY = 'review_' + TALK;
const BRANCH_NAME = 'sync/tester/' + TALK;

// Manual timer harness: engine timers only fire when the test says so.
function timerHarness() {
  let seq = 0;
  const timers = new Map();
  return {
    set(fn, ms) { seq += 1; timers.set(seq, { fn, ms }); return seq; },
    clear(id) { timers.delete(id); },
    fire(maxMs) {
      const due = [...timers].filter(([, t]) => t.ms <= maxMs);
      due.forEach(([id]) => timers.delete(id));
      due.forEach(([, t]) => t.fn());
    },
    delays() { return [...timers.values()].map((t) => t.ms); },
  };
}

// Drain resolved promise chains (gh stubs resolve immediately).
async function settle() { for (let i = 0; i < 50; i++) await Promise.resolve(); }

// gh double: every call recorded as [name, ...detail]; behavior overridable.
function ghStub(over) {
  over = over || {};
  const calls = [];
  function record(name, detail) { calls.push([name].concat(detail || [])); }
  let putCount = 0;
  let pullCount = 0;
  // Simulate a branch deleted out from under the engine (external PR close +
  // branch delete, or a teardown on another device): GitHub answers PUT/GET on
  // a missing branch with 404 "Branch <name> not found". createRef re-creates it.
  let branchGone = !!over.branchGone;
  const gh = {
    calls,
    puts: [],
    // Stateful like the real Contents API: a PUT to the state path makes the
    // file visible to later GETs, a DELETE removes it. An explicit
    // over.remote (value or function) takes precedence.
    _stateFile: null,
    getFileContent: async (api, token, path, ref) => {
      record('getFileContent', [path, ref]);
      if (branchGone) return null;                 // 404 on a missing branch -> null
      if ('remote' in over) {
        const r = typeof over.remote === 'function' ? over.remote() : over.remote;
        return r || null;
      }
      return gh._stateFile;
    },
    getBranchHeadSha: async (api, token, branch) => { record('getBranchHeadSha', [branch]); return 'head1'; },
    createRef: async (api, token, name, sha) => {
      record('createRef', [name, sha]);
      if (over.refExists) { const e = new Error('Reference already exists'); e.status = 422; throw e; }
      if (!over.branchStaysGone) branchGone = false;  // the branch exists again
      return {};
    },
    putFile: async (api, token, opts) => {
      if (branchGone) { const e = new Error('Branch ' + opts.branch + ' not found'); e.status = 404; throw e; }
      putCount += 1;
      record('putFile', [opts.path, opts.sha || null, !!opts.keepalive]);
      if (opts.path.indexOf('.review-sync/') === 0) {
        gh.puts.push(JSON.parse(opts.content));
      }
      if (over.putFails && putCount <= over.putFails.length) {
        const spec = over.putFails[putCount - 1];
        if (spec) { const e = new Error(spec.message || 'fail'); e.status = spec.status; throw e; }
      }
      const sha = 'sha_after_put' + putCount;
      if (opts.path.indexOf('.review-sync/') === 0) {
        gh._stateFile = { content: opts.content, sha };
      }
      return { content: { sha } };
    },
    createPull: async (api, token, opts) => {
      pullCount += 1;
      record('createPull', [opts.head, opts.base, !!opts.draft]);
      if (over.draftUnsupported && opts.draft) {
        const e = new Error('Draft pull requests are not supported in this repository.');
        e.status = 422;
        throw e;
      }
      if (over.pullFails && pullCount <= over.pullFails.length) {
        const spec = over.pullFails[pullCount - 1];
        if (spec) { const e = new Error(spec.message || 'fail'); e.status = spec.status; throw e; }
      }
      return { number: 77, html_url: 'https://github.com/x/pull/77', node_id: 'PR_n77', draft: !!opts.draft };
    },
    findOpenPrByHead: async (api, token, owner, branch) => {
      record('findOpenPrByHead', [owner, branch]);
      return over.existingPr || null;
    },
    getFileSha: async (api, token, path, ref) => {
      record('getFileSha', [path, ref]);
      return 'fileblob1';
    },
    deleteFile: async (api, token, opts) => {
      record('deleteFile', [opts.path, opts.branch, opts.sha]);
      if (opts.path.indexOf('.review-sync/') === 0) gh._stateFile = null;
      return {};
    },
    markPullReady: async (token, nodeId) => {
      record('markPullReady', [nodeId]);
      if (over.readyFails) throw new Error('graphql down');
      return {};
    },
    convertPullToDraft: async (token, nodeId) => {
      record('convertPullToDraft', [nodeId]);
      return {};
    },
    closePull: async (api, token, prNumber) => {
      record('closePull', [prNumber]);
      // Hook to simulate a re-edit (or anything) landing mid-teardown.
      if (over.onClosePull) over.onClosePull();
      if (over.closePullFails) { const e = new Error('close failed'); e.status = over.closePullFails; throw e; }
      return { number: prNumber, state: 'closed' };
    },
    // Mirrors the real helper: already-gone (404/422) resolves; other errors
    // throw. Deleting the branch also removes the state file that lived on it.
    deleteRef: async (api, token, branchName) => {
      record('deleteRef', [branchName]);
      const s = over.deleteRefStatus;
      if (s && s !== 404 && s !== 422) { const e = new Error('delete failed'); e.status = s; throw e; }
      gh._stateFile = null;
      return null;
    },
  };
  return gh;
}

function makeEngine(over, storageInit, engineOver) {
  const timers = timerHarness();
  const gh = ghStub(over);
  const statuses = [];
  const applied = [];
  const storage = memStorage(storageInit || {});
  const engine = createSyncEngine(Object.assign({
    api: 'https://api.github.com/repos/sy-tools/sy-subtitles',
    owner: 'sy-tools',
    repo: 'sy-tools/sy-subtitles',
    token: 'gho_x',
    login: 'tester',
    talkId: TALK,
    base: 'main',
    branch: BRANCH_NAME,
    storage,
    gh,
    now: () => 1770000000000,
    setTimeoutFn: timers.set.bind(timers),
    clearTimeoutFn: timers.clear.bind(timers),
    isOffline: (e) => /fetch failed/.test((e && e.message) || ''),
    onStatus: (s) => statuses.push(s),
    onRemoteApplied: (keys) => applied.push(keys),
    clientId: 'client1',
  }, engineOver || {}));
  return { engine, timers, gh, statuses, applied, storage };
}

function localEdit(storage, idx, text) {
  const cur = JSON.parse(storage.getItem(RKEY) || '{"marks":{},"edits":{}}');
  cur.edits[idx] = text;
  storage.setItem(RKEY, JSON.stringify(cur));
}

function remoteDoc(edits, revision, sha) {
  return {
    content: JSON.stringify(makeSyncDoc(TALK,
      { [RKEY]: { marks: {}, edits: edits } }, revision || 1, 'other', '2026-07-13T21:00:00Z')),
    sha: sha || 'sha_remote1',
  };
}

describe('engine: debounce + coalesce', () => {
  it('one push 15s after the last edit; re-edits re-arm the timer', async () => {
    const { engine, timers, gh, storage } = makeEngine();
    localEdit(storage, 1, 'а');
    engine.notifyEdit();
    localEdit(storage, 1, 'аб');
    engine.notifyEdit();
    timers.fire(14999);
    await settle();
    assert.strictEqual(gh.puts.length, 0);
    timers.fire(15000);
    await settle();
    assert.strictEqual(gh.puts.length, 1);
    assert.strictEqual(gh.puts[0].entries[RKEY].edits[1], 'аб');
  });
  it('blur (flushSoon) pushes after the 1.5s coalesce window', async () => {
    const { engine, timers, gh, storage } = makeEngine();
    localEdit(storage, 2, 'x');
    engine.notifyEdit();
    engine.flushSoon();
    timers.fire(1500);
    await settle();
    assert.strictEqual(gh.puts.length, 1);
  });
  it('does nothing when no edit happened (not dirty)', async () => {
    const { engine, timers, gh } = makeEngine();
    engine.flushSoon();
    timers.fire(20000);
    await settle();
    await engine.flush();
    assert.strictEqual(gh.calls.length, 0);
  });
});

describe('engine: bootstrap', () => {
  it('first push creates branch, state file (no sha) and a draft PR', async () => {
    const { engine, gh, storage } = makeEngine();
    localEdit(storage, 1, 'перший');
    engine.notifyEdit();
    await engine.flush();
    const names = gh.calls.map((c) => c[0]);
    assert.deepStrictEqual(names, [
      'getFileContent', 'findOpenPrByHead', 'getBranchHeadSha', 'createRef', 'putFile', 'createPull',
    ]);
    assert.deepStrictEqual(gh.calls[3], ['createRef', BRANCH_NAME, 'head1']);
    assert.strictEqual(gh.calls[4][2], null); // no sha: brand-new file
    assert.deepStrictEqual(gh.calls[5], ['createPull', BRANCH_NAME, 'main', true]);
    const info = engine.getInfo();
    assert.strictEqual(info.prNumber, 77);
    assert.strictEqual(info.prUrl, 'https://github.com/x/pull/77');
    assert.strictEqual(info.status, 'synced');
    // base meta persisted for the next session
    const base = JSON.parse(storage.getItem(syncBaseKey(TALK)));
    assert.strictEqual(base.prNumber, 77);
    assert.strictEqual(base.sha, 'sha_after_put1');
  });
  it('adopts pre-existing local edits on attach and creates the PR (no fresh edit needed)', async () => {
    const { engine, gh, storage } = makeEngine();
    // Edits already sit in localStorage from a previous session; the user just
    // navigates back onto the page and never types — so no notifyEdit() fires.
    localEdit(storage, 1, 'from a previous session');
    await engine.attach();
    assert.strictEqual(
      engine.getInfo().dirty,
      true,
      'attach must mark un-synced local edits dirty so the first sync triggers',
    );
    await engine.flush();
    const names = gh.calls.map((c) => c[0]);
    assert.ok(
      names.includes('createPull'),
      'a draft PR must be created for edits that predate the engine',
    );
    assert.strictEqual(engine.getInfo().prNumber, 77);
  });
  it('tolerates an already-existing branch ref (422)', async () => {
    const { engine, gh, storage } = makeEngine({ refExists: true });
    localEdit(storage, 1, 'x');
    engine.notifyEdit();
    await engine.flush();
    assert.strictEqual(gh.puts.length, 1);
    assert.strictEqual(engine.getInfo().status, 'synced');
  });
  it('falls back to a non-draft PR when drafts are unsupported (422)', async () => {
    const { engine, gh, storage } = makeEngine({ draftUnsupported: true });
    localEdit(storage, 1, 'x');
    engine.notifyEdit();
    await engine.flush();
    const pulls = gh.calls.filter((c) => c[0] === 'createPull');
    assert.deepStrictEqual(pulls.map((c) => c[3]), [true, false]);
    assert.strictEqual(engine.getInfo().prNumber, 77);
  });
  it('adopts an existing draft PR on the branch instead of creating a second one', async () => {
    const { engine, gh, storage } = makeEngine({
      existingPr: { number: 12, html_url: 'https://github.com/x/pull/12', node_id: 'PR_n12', draft: true },
    });
    localEdit(storage, 1, 'x');
    engine.notifyEdit();
    await engine.flush();
    assert.strictEqual(gh.calls.filter((c) => c[0] === 'createPull').length, 0);
    assert.strictEqual(engine.getInfo().prNumber, 12);
    assert.strictEqual(engine.getInfo().status, 'synced');
    assert.strictEqual(gh.puts.length, 1);
  });
  it('an edit onto a branch with a submitted (ready) PR converts it back to draft', async () => {
    // Post-finalize continuation, possibly from another device: the
    // deterministic branch carries an open NON-draft PR. A new edit silently
    // re-drafts it and the sync resumes — fully reversible lifecycle.
    const { engine, gh, storage } = makeEngine({
      existingPr: { number: 12, html_url: 'https://github.com/x/pull/12', node_id: 'PR_n12', draft: false },
    });
    localEdit(storage, 1, 'x');
    engine.notifyEdit();
    await engine.flush();
    assert.strictEqual(gh.calls.filter((c) => c[0] === 'convertPullToDraft').length, 1);
    assert.strictEqual(gh.puts.length, 1);
    const info = engine.getInfo();
    assert.strictEqual(info.prNumber, 12);
    assert.strictEqual(info.prDraft, true);
    assert.strictEqual(info.status, 'synced');
  });
});

describe('engine: teardown on full revert', () => {
  it('reverting the last edit closes the PR, deletes the branch and hides the chip', async () => {
    const { engine, gh, storage } = makeEngine();
    localEdit(storage, 1, 'правка');
    engine.notifyEdit();
    await engine.flush();
    assert.strictEqual(engine.getInfo().prNumber, 77);   // PR created

    storage.removeItem(RKEY);                             // revert everything
    engine.notifyEdit();
    await engine.flush();

    assert.deepStrictEqual(gh.calls.find((c) => c[0] === 'closePull'), ['closePull', 77]);
    assert.deepStrictEqual(gh.calls.find((c) => c[0] === 'deleteRef'), ['deleteRef', BRANCH_NAME]);
    const info = engine.getInfo();
    assert.strictEqual(info.status, 'idle');             // chip hides
    assert.strictEqual(info.prNumber, null);             // in-memory base reset
    const base = JSON.parse(storage.getItem(syncBaseKey(TALK)));
    assert.strictEqual(base.prNumber, null);             // persisted base wiped
    assert.strictEqual(base.sha, null);
  });

  it('a fresh edit after teardown re-creates the branch and PR from scratch', async () => {
    const { engine, gh, storage } = makeEngine();
    localEdit(storage, 1, 'a'); engine.notifyEdit(); await engine.flush();
    storage.removeItem(RKEY); engine.notifyEdit(); await engine.flush();  // teardown
    assert.strictEqual(gh.calls.filter((c) => c[0] === 'closePull').length, 1); // PR really closed
    localEdit(storage, 2, 'b'); engine.notifyEdit(); await engine.flush(); // re-edit
    assert.strictEqual(engine.getInfo().prNumber, 77);
    assert.strictEqual(engine.getInfo().status, 'synced');
    assert.strictEqual(gh.calls.filter((c) => c[0] === 'createRef').length, 2); // branch recreated
  });

  it('teardown is best-effort: an already-gone branch (404) still completes', async () => {
    const { engine, storage } = makeEngine({ deleteRefStatus: 404 });
    localEdit(storage, 1, 'a'); engine.notifyEdit(); await engine.flush();
    storage.removeItem(RKEY); engine.notifyEdit(); await engine.flush();
    const info = engine.getInfo();
    assert.strictEqual(info.status, 'idle');             // not an error
    assert.strictEqual(info.prNumber, null);
  });

  it('closes a finalized (ready) PR too — no edits means no PR', async () => {
    const { engine, gh, storage } = makeEngine();
    localEdit(storage, 1, 'a'); engine.notifyEdit(); await engine.flush();
    await engine.finalize();                             // PR -> ready for review
    assert.strictEqual(engine.getInfo().prDraft, false);
    storage.removeItem(RKEY); engine.notifyEdit(); await engine.flush();
    assert.deepStrictEqual(gh.calls.find((c) => c[0] === 'closePull'), ['closePull', 77]);
    assert.strictEqual(engine.getInfo().status, 'idle');
  });

  it('empty edits with nothing ever synced stays idle (no teardown network)', async () => {
    const { engine, gh } = makeEngine();                 // never synced, no PR
    engine.notifyEdit();                                 // dirty but collect() empty
    await engine.flush();
    assert.strictEqual(gh.calls.filter((c) => c[0] === 'closePull').length, 0);
    assert.strictEqual(gh.calls.filter((c) => c[0] === 'deleteRef').length, 0);
    assert.strictEqual(engine.getInfo().status, 'idle');
  });

  it('keeps the PR when the remote branch still carries a concurrent edit', async () => {
    // Two devices, same talk/target: this device reverts to zero, but the other
    // synced an edit we never pulled. Teardown must pull+merge and, finding the
    // merge non-empty, push instead of destroying the branch (which would lose
    // the other device's edit) — the CAS guarantee of the old empty-push path.
    const { engine, gh, storage } = makeEngine();
    localEdit(storage, 1, 'mine');
    engine.notifyEdit();
    await engine.flush();                                 // PR 77; remote = {1:'mine'}
    const remote = JSON.parse(gh._stateFile.content);
    remote.entries[RKEY].edits[5] = 'from phone';         // concurrent device's edit
    gh._stateFile = { content: JSON.stringify(remote), sha: 'sha_concurrent' };

    storage.removeItem(RKEY);                             // revert my only edit
    engine.notifyEdit();
    await engine.flush();

    assert.strictEqual(gh.calls.filter((c) => c[0] === 'closePull').length, 0, 'must NOT close the PR');
    assert.strictEqual(gh.calls.filter((c) => c[0] === 'deleteRef').length, 0, 'must NOT delete the branch');
    assert.strictEqual(JSON.parse(storage.getItem(RKEY)).edits[5], 'from phone', 'concurrent edit merged in');
    assert.notStrictEqual(engine.getInfo().status, 'idle');
  });

  it('a re-edit that lands mid-teardown is not dropped and the chip never lies idle', async () => {
    // undo -> redo: the revert triggers teardown; a new edit arrives while
    // closePull/deleteRef are on the wire. It must survive with the chip honest
    // (not idle) and re-create the PR from the pristine base on the next flush.
    const holder = {};
    const { engine, gh, storage } = makeEngine({
      onClosePull: () => { localEdit(storage, 9, 'redo'); holder.engine.notifyEdit(); },
    });
    holder.engine = engine;
    localEdit(storage, 1, 'first');
    engine.notifyEdit();
    await engine.flush();                                 // PR 77

    storage.removeItem(RKEY);
    engine.notifyEdit();
    await engine.flush();                                 // teardown; onClosePull injects the redo

    const mid = engine.getInfo();
    assert.notStrictEqual(mid.status, 'idle', 'chip must not read idle while an edit is pending');
    assert.strictEqual(mid.prNumber, null);              // base was reset
    assert.strictEqual(JSON.parse(storage.getItem(RKEY)).edits[9], 'redo', 'the redo survived locally');

    await engine.flush();                                 // the pending edit re-creates from scratch
    const after = engine.getInfo();
    assert.strictEqual(after.prNumber, 77);
    assert.strictEqual(after.status, 'synced');
    assert.strictEqual(gh.calls.filter((c) => c[0] === 'createRef').length, 2); // branch recreated
  });
});

describe('engine: self-heal on an externally deleted branch', () => {
  // Seeds a "synced" base pointing at a PR whose branch was deleted out of band
  // (PR closed + branch deleted on github.com, or a teardown on another device).
  function seededSynced() {
    return {
      [syncBaseKey(TALK)]: JSON.stringify({
        doc: {}, sha: 'oldsha', revision: 1,
        prNumber: 77, prUrl: 'https://github.com/x/pull/77', nodeId: 'PR_n77',
        prDraft: true, fileShas: {}, branch: BRANCH_NAME,
      }),
    };
  }

  it('re-creates the branch + a fresh PR when a push hits "Branch not found"', async () => {
    const { engine, gh, storage } = makeEngine({ branchGone: true }, seededSynced());
    localEdit(storage, 1, 'again');
    engine.notifyEdit();
    await engine.flush();

    const info = engine.getInfo();
    assert.strictEqual(info.status, 'synced', 'heals to synced, not error');
    assert.strictEqual(info.prNumber, 77, 'a fresh PR was created');
    assert.ok(gh.calls.some((c) => c[0] === 'createRef'), 'branch was re-created');
    assert.ok(gh.calls.some((c) => c[0] === 'createPull'), 'a new PR was opened');
    assert.strictEqual(gh.puts.at(-1).entries[RKEY].edits[1], 'again', 'the edit reached the branch');
    const base = JSON.parse(storage.getItem(syncBaseKey(TALK)));
    assert.strictEqual(base.sha !== null && base.sha !== 'oldsha', true, 'base advanced to the new state');
  });

  it('surfaces an error (no infinite loop) if the branch stays gone after re-create', async () => {
    const { engine, gh, storage } = makeEngine({ branchGone: true, branchStaysGone: true }, seededSynced());
    localEdit(storage, 1, 'x');
    engine.notifyEdit();
    await engine.flush();
    assert.strictEqual(engine.getInfo().status, 'error', 'one retry then surfaces the error');
    // Exactly one heal attempt: createRef is tried once, never in a loop.
    assert.strictEqual(gh.calls.filter((c) => c[0] === 'createRef').length, 1);
  });
});

describe('engine: real-file commits', () => {
  it('pushes the rebuilt real file alongside the state file', async () => {
    const files = [{ path: 'talks/' + TALK + '/transcript_uk.txt', content: 'ПОВНИЙ ФАЙЛ' }];
    const { engine, gh, storage } = makeEngine({}, null, { buildFiles: () => files });
    localEdit(storage, 1, 'x');
    engine.notifyEdit();
    await engine.flush();
    const filePuts = gh.calls.filter((c) => c[0] === 'putFile' && c[1] === files[0].path);
    assert.strictEqual(filePuts.length, 1);
    // the blob sha for the real file was looked up on the sync branch
    assert.deepStrictEqual(gh.calls.find((c) => c[0] === 'getFileSha'),
      ['getFileSha', files[0].path, BRANCH_NAME]);
    assert.strictEqual(engine.getInfo().status, 'synced');
  });
  it('caches the real file sha across pushes', async () => {
    const files = [{ path: 'talks/' + TALK + '/transcript_uk.txt', content: 'V1' }];
    const { engine, gh, storage } = makeEngine({}, null, { buildFiles: () => files });
    localEdit(storage, 1, 'x');
    engine.notifyEdit();
    await engine.flush();
    localEdit(storage, 1, 'y');
    files[0].content = 'V2';
    engine.notifyEdit();
    await engine.flush();
    assert.strictEqual(gh.calls.filter((c) => c[0] === 'getFileSha').length, 1);
    assert.strictEqual(gh.calls.filter((c) => c[0] === 'putFile' && c[1] === files[0].path).length, 2);
  });
});

describe('engine: finalize + re-draft lifecycle', () => {
  async function bootstrapped(over, engineOver) {
    const made = makeEngine(over, null, engineOver);
    localEdit(made.storage, 1, 'x');
    made.engine.notifyEdit();
    await made.engine.flush();
    return made;
  }
  it('finalize deletes the state file, flips ready and reports the PR', async () => {
    const { engine, gh } = await bootstrapped();
    const pr = await engine.finalize();
    assert.deepStrictEqual(pr, { number: 77, html_url: 'https://github.com/x/pull/77' });
    const del = gh.calls.find((c) => c[0] === 'deleteFile');
    assert.ok(del && del[1] === syncFilePath(TALK) && del[2] === BRANCH_NAME);
    assert.deepStrictEqual(gh.calls.find((c) => c[0] === 'markPullReady'), ['markPullReady', 'PR_n77']);
    const info = engine.getInfo();
    assert.strictEqual(info.status, 'ready');
    assert.strictEqual(info.prDraft, false);
  });
  it('finalize flushes pending edits first', async () => {
    const { engine, gh, storage } = await bootstrapped();
    localEdit(storage, 2, 'останнє');
    engine.notifyEdit();
    await engine.finalize();
    assert.strictEqual(gh.puts.length, 2);
    assert.ok(JSON.stringify(gh.puts[1]).includes('останнє'));
    const seq = gh.calls.map((c) => c[0]);
    assert.ok(seq.indexOf('deleteFile') > seq.lastIndexOf('putFile'), 'delete follows the last push');
  });
  it('announces syncing before the work, so the chip fills the wait', async () => {
    // Finalize is 3-4 sequential calls fired from a dropdown item that closes
    // itself. Without this the chip kept its old tone the whole time and the
    // click looked like it did nothing.
    const { engine, statuses } = await bootstrapped();
    statuses.length = 0;
    const p = engine.finalize();
    assert.strictEqual(statuses[0], 'syncing', 'emitted before the first await');
    await p;
    assert.strictEqual(statuses[statuses.length - 1], 'ready');
  });
  it('restores the previous status when finalize fails, never a stuck spinner', async () => {
    const { engine, statuses } = await bootstrapped({ readyFails: true });
    assert.strictEqual(engine.getInfo().status, 'synced');
    statuses.length = 0;
    await assert.rejects(engine.finalize(), /graphql down/);
    assert.strictEqual(engine.getInfo().status, 'synced', 'not left on syncing');
    assert.strictEqual(statuses[statuses.length - 1], 'synced');
  });
  it('a pull landing mid-finalize neither repaints the chip nor eats the restore', async () => {
    // focus / visibilitychange fire pull(), and tabbing away to GitHub during
    // finalize is the likeliest thing a user does here. Unguarded, pull writes
    // 'synced' over the progress tone, and the failure restore then sees a
    // status it does not recognise and says nothing — leaving the chip claiming
    // "synced" for a PR that was never finalized.
    const { engine, statuses } = await bootstrapped({ readyFails: true });
    const p = engine.finalize();
    statuses.length = 0;
    await engine.pull(true);
    assert.deepStrictEqual(statuses, [], 'the pull repainted nothing');
    assert.strictEqual(engine.getInfo().status, 'syncing');
    await assert.rejects(p, /graphql down/);
    assert.strictEqual(engine.getInfo().status, 'synced');
  });
  it('restores pending, not synced, when an edit landed while finalize ran', async () => {
    const { engine, storage } = await bootstrapped({ readyFails: true });
    const p = engine.finalize();
    localEdit(storage, 2, 'нове');
    engine.notifyEdit();
    await assert.rejects(p, /graphql down/);
    assert.strictEqual(engine.getInfo().status, 'pending', 'an unflushed edit is not "synced"');
  });
  it('keeps the progress tone across its own pre-flush', async () => {
    // finalize()'s comment claims it owns the chip while it runs. Its own
    // flush writes 'synced' — a green "done" flashing three requests before
    // the work is actually done.
    const { engine, statuses, storage } = await bootstrapped();
    localEdit(storage, 2, 'нове');
    engine.notifyEdit();
    statuses.length = 0;
    await engine.finalize();
    assert.ok(!statuses.slice(0, -1).includes('synced'),
      `no 'synced' before the end, got ${JSON.stringify(statuses)}`);
    assert.strictEqual(statuses[statuses.length - 1], 'ready');
  });

  it('restores a state that is true NOW, not the one it snapshotted', async () => {
    // The pre-flush pushes everything and moves the status on; restoring the
    // status from before it means the chip says "pending" for a talk with
    // nothing pending, and no debounce will ever clear it (dirty is false).
    const { engine, storage } = await bootstrapped({ readyFails: true });
    localEdit(storage, 2, 'нове');
    engine.notifyEdit();
    assert.strictEqual(engine.getInfo().status, 'pending');
    await assert.rejects(engine.finalize(), /graphql down/);
    const inf = engine.getInfo();
    assert.strictEqual(inf.dirty, false, 'the pre-flush pushed it');
    assert.strictEqual(inf.status, 'synced', 'so "pending" would be a lie');
  });

  it('never restores a transient syncing — the chip would spin forever', async () => {
    const { engine, gh, storage } = await bootstrapped({ readyFails: true });
    localEdit(storage, 2, 'нове');
    engine.notifyEdit();
    const inFlight = engine.flush();          // status -> 'syncing'
    assert.strictEqual(engine.getInfo().status, 'syncing');
    const p = engine.finalize();
    await inFlight;
    await assert.rejects(p, /graphql down/);
    assert.notStrictEqual(engine.getInfo().status, 'syncing');
    assert.ok(gh.calls.length > 0);
  });

  it('leaves an error the flush surfaced instead of painting over it', async () => {
    const { engine, storage } = await bootstrapped({
      // null = let the bootstrap push through; the finalize pre-flush is the
      // second put, and that is the one that fails.
      putFails: [null, { status: 500, message: 'Server error' }],
      readyFails: true,
    });
    localEdit(storage, 2, 'нове');
    engine.notifyEdit();
    await assert.rejects(engine.finalize(), /graphql down/);
    const inf = engine.getInfo();
    assert.strictEqual(inf.status, 'error', 'the push really did fail');
    assert.ok(inf.error && inf.error.message, 'and still says why');
  });

  it('stays quiet after destroy when the finalize chain SUCCEEDS', async () => {
    // The failure tail guards on `disposed`; the success tail eight lines
    // above did not, so a talk left mid-finalize painted the next talk's chip.
    const { engine, statuses } = await bootstrapped();
    const p = engine.finalize();
    await engine.destroy();
    statuses.length = 0;
    await p;
    assert.deepStrictEqual(statuses, []);
  });

  it('refuses a second finalize while one is already running', async () => {
    const { engine } = await bootstrapped();
    const first = engine.finalize();
    await assert.rejects(engine.finalize(), /already finalizing/);
    await first;
  });

  it('stays quiet after destroy when the finalize chain then fails', async () => {
    // Same contract every other tail in this engine honours: once destroyed,
    // no more status emissions — the chip belongs to whatever view is up now.
    const { engine, statuses } = await bootstrapped({ readyFails: true });
    const p = engine.finalize();
    await engine.destroy();
    statuses.length = 0;
    await assert.rejects(p, /graphql down/);
    assert.deepStrictEqual(statuses, []);
  });
  it('the first edit after finalize re-drafts the PR and recreates the state', async () => {
    const { engine, gh, storage } = await bootstrapped();
    await engine.finalize();
    localEdit(storage, 2, 'нове');
    engine.notifyEdit();
    await engine.flush();
    assert.strictEqual(gh.calls.filter((c) => c[0] === 'convertPullToDraft').length, 1);
    assert.strictEqual(gh.puts.length, 2); // state file re-created
    const info = engine.getInfo();
    assert.strictEqual(info.prDraft, true);
    assert.strictEqual(info.status, 'synced');
  });
});

describe('engine: destroy vs in-flight flush', () => {
  it('destroy() resolves after the in-flight flush and suppresses its tail', async () => {
    let releasePut;
    const putGate = new Promise((res) => { releasePut = res; });
    const { engine, gh, storage } = makeEngine();
    const origPut = gh.putFile;
    gh.putFile = async (...a) => { await putGate; return origPut(...a); };
    localEdit(storage, 1, 'x');
    engine.notifyEdit();
    const flushP = engine.flush();
    await settle(); // flush is now parked on the PUT
    let destroyed = false;
    const destroyP = engine.destroy().then(() => { destroyed = true; });
    await settle();
    assert.strictEqual(destroyed, false, 'destroy must wait for the in-flight flush');
    releasePut();
    await flushP;
    await destroyP;
    assert.strictEqual(destroyed, true);
    // the tail (PR creation) was suppressed by the dispose
    assert.strictEqual(gh.calls.filter((c) => c[0] === 'createPull').length, 0);
  });
});

describe('engine: no-op protection', () => {
  it('never bootstraps a branch/PR when there is nothing to sync', async () => {
    // e.g. a mode toggle marks the state dirty without any real edit —
    // not even a lookup GET is spent on it (attach() covers adoption).
    const { engine, gh } = makeEngine();
    engine.notifyEdit();
    await engine.flush();
    assert.deepStrictEqual(gh.calls, []);
    assert.strictEqual(engine.getInfo().status, 'idle');
  });
  it('skips the PUT when the doc is unchanged since the last push', async () => {
    const { engine, gh, storage } = makeEngine();
    localEdit(storage, 1, 'x');
    engine.notifyEdit();
    await engine.flush();
    assert.strictEqual(gh.puts.length, 1);
    engine.notifyEdit(); // dirty again, but storage did not change
    await engine.flush();
    assert.strictEqual(gh.puts.length, 1);
    assert.strictEqual(engine.getInfo().status, 'synced');
    assert.strictEqual(engine.getInfo().dirty, false);
  });
  it('flush({force}) retries the PR creation after it failed once', async () => {
    const { engine, gh, storage } = makeEngine({ pullFails: [{ status: 500, message: 'boom' }] });
    localEdit(storage, 1, 'x');
    engine.notifyEdit();
    await engine.flush();
    assert.strictEqual(engine.getInfo().status, 'error');
    assert.strictEqual(engine.getInfo().prNumber, null);
    await engine.flush({ force: true });
    assert.strictEqual(gh.puts.length, 1); // state already pushed — no re-PUT
    assert.strictEqual(engine.getInfo().prNumber, 77);
    assert.strictEqual(engine.getInfo().status, 'synced');
  });
});

describe('engine: CAS conflict', () => {
  it('409 -> pull fresh remote, merge, retry with the fresh sha', async () => {
    let after409 = false;
    const { engine, gh, storage, applied } = makeEngine({
      remote: () => (after409 ? remoteDoc({ 9: 'віддалений' }, 3, 'sha_fresh') : null),
      putFails: [{ status: 409, message: 'is at ... but expected' }],
    });
    localEdit(storage, 1, 'локальний');
    engine.notifyEdit();
    const origPut = gh.putFile;
    // flip the remote into existence once the first PUT has conflicted
    gh.putFile = async (...a) => { const p = origPut(...a); after409 = true; return p; };
    await engine.flush();
    assert.strictEqual(gh.puts.length, 2);
    const finalDoc = gh.puts[1];
    assert.strictEqual(finalDoc.entries[RKEY].edits[1], 'локальний');
    assert.strictEqual(finalDoc.entries[RKEY].edits[9], 'віддалений');
    // remote-won items were applied into local storage too
    assert.strictEqual(JSON.parse(storage.getItem(RKEY)).edits[9], 'віддалений');
    assert.strictEqual(applied.length, 1);
    assert.strictEqual(engine.getInfo().status, 'synced');
  });
  it('persistent 409s end in an error status after 3 attempts', async () => {
    const { engine, gh, storage } = makeEngine({
      remote: () => remoteDoc({ 9: 'r' }, 3, 'sha_fresh'),
      putFails: [{ status: 409 }, { status: 409 }, { status: 409 }],
    });
    localEdit(storage, 1, 'x');
    engine.notifyEdit();
    await engine.flush();
    assert.strictEqual(engine.getInfo().status, 'error');
    assert.strictEqual(gh.puts.length, 3);
  });
});

describe('engine: pull', () => {
  it('adopts remote edits on a clean client without pushing', async () => {
    const { engine, gh, storage, applied, timers } = makeEngine({ remote: remoteDoc({ 5: 'з телефона' }, 2) });
    await engine.pull(true);
    assert.strictEqual(JSON.parse(storage.getItem(RKEY)).edits[5], 'з телефона');
    assert.deepStrictEqual(applied, [[RKEY]]);
    timers.fire(60000);
    await settle();
    assert.strictEqual(gh.puts.length, 0);
    assert.strictEqual(engine.getInfo().status, 'synced');
  });
  it('merges into dirty local state and schedules a re-push', async () => {
    const { engine, gh, storage, timers } = makeEngine({ remote: remoteDoc({ 5: 'з телефона' }, 2) });
    localEdit(storage, 1, 'тут');
    engine.notifyEdit();
    await engine.pull(true);
    timers.fire(15000);
    await settle();
    assert.strictEqual(gh.puts.length, 1);
    assert.deepStrictEqual(gh.puts[0].entries[RKEY].edits, { 1: 'тут', 5: 'з телефона' });
  });
  it('is throttled: a second non-forced pull within 60s is skipped', async () => {
    const { engine, gh } = makeEngine({ remote: remoteDoc({ 5: 'r' }, 2) });
    await engine.pull();
    await engine.pull();
    const gets = gh.calls.filter((c) => c[0] === 'getFileContent');
    assert.strictEqual(gets.length, 1);
  });
});

describe('engine: offline + auth failures', () => {
  it('network failure parks the sync as pending and retries cleanly', async () => {
    const { engine, gh, storage } = makeEngine({ putFails: [{ status: undefined, message: 'fetch failed' }] });
    localEdit(storage, 1, 'x');
    engine.notifyEdit();
    await engine.flush();
    assert.strictEqual(engine.getInfo().status, 'pending');
    engine.notifyEdit();
    await engine.flush();
    assert.strictEqual(engine.getInfo().status, 'synced');
    assert.strictEqual(gh.puts.length, 2);
  });
  it('401 surfaces as an auth error', async () => {
    const { engine, storage } = makeEngine({ putFails: [{ status: 401, message: 'Bad credentials' }] });
    localEdit(storage, 1, 'x');
    engine.notifyEdit();
    await engine.flush();
    const info = engine.getInfo();
    assert.strictEqual(info.status, 'error');
    assert.strictEqual(info.error.kind, 'auth');
  });
});

describe('engine: attach', () => {
  it('re-attaches to an existing remote + PR found by head', async () => {
    const { engine, storage, applied } = makeEngine({
      remote: remoteDoc({ 4: 'збережене' }, 6),
      existingPr: { number: 12, html_url: 'https://github.com/x/pull/12', node_id: 'PR_n12', draft: true },
    });
    await engine.attach();
    assert.strictEqual(JSON.parse(storage.getItem(RKEY)).edits[4], 'збережене');
    assert.strictEqual(applied.length, 1);
    const info = engine.getInfo();
    assert.strictEqual(info.prNumber, 12);
    assert.strictEqual(info.prUrl, 'https://github.com/x/pull/12');
  });
  it('uses the cached PR from the base meta without querying /pulls', async () => {
    const baseMeta = {
      doc: {}, sha: 'sha_old', revision: 2,
      prNumber: 12, prUrl: 'https://github.com/x/pull/12', nodeId: 'PR_n12', branch: BRANCH_NAME,
    };
    const { engine, gh } = makeEngine(
      { remote: remoteDoc({ 4: 'v' }, 2, 'sha_old') },
      { [syncBaseKey(TALK)]: JSON.stringify(baseMeta) });
    await engine.attach();
    assert.strictEqual(gh.calls.filter((c) => c[0] === 'findOpenPrByHead').length, 0);
    assert.strictEqual(engine.getInfo().prUrl, 'https://github.com/x/pull/12');
  });
  it('stays idle (chip hidden) when there is no remote and no local edits', async () => {
    const { engine, gh } = makeEngine();
    await engine.attach();
    assert.strictEqual(engine.getInfo().status, 'idle');
    assert.strictEqual(gh.puts.length, 0);
  });
});

describe('engine: target-scoped coexistence', () => {
  // Two engines for the same talk but different targets (a video SRT and the
  // transcript) must each sync only their own keys, to their own state path,
  // without deleting the other target's local edits.
  it('two targets sync independently and never clobber each other', async () => {
    const CK = 'srt_edits_' + TALK + '_video1_uk';
    const storage = memStorage({
      [CK]: JSON.stringify({ 4: 'sub-edit' }),
      ['review_' + TALK]: JSON.stringify({ marks: {}, edits: { 1: 'transcript-edit' } }),
    });
    const srt = srtSyncTarget(TALK, 'video1', 'uk');
    const tr = transcriptSyncTarget(TALK, 'uk');
    const shared = {
      api: 'https://api.github.com/repos/sy-tools/sy-subtitles', owner: 'sy-tools',
      token: 'gho_x', login: 'tester', talkId: TALK, base: 'main', storage,
      now: () => 1770000000000, clientId: 'client1',
      isOffline: () => false,
    };
    const ghA = ghStub();
    const ghB = ghStub();
    const tA = timerHarness(); const tB = timerHarness();
    const engA = createSyncEngine(Object.assign({}, shared, {
      gh: ghA, target: srt.slug, entryFilter: srt.filter,
      branch: 'sync/tester/' + TALK + '--' + srt.slug,
      setTimeoutFn: tA.set.bind(tA), clearTimeoutFn: tA.clear.bind(tA),
    }));
    const engB = createSyncEngine(Object.assign({}, shared, {
      gh: ghB, target: tr.slug, entryFilter: tr.filter,
      branch: 'sync/tester/' + TALK + '--' + tr.slug,
      setTimeoutFn: tB.set.bind(tB), clearTimeoutFn: tB.clear.bind(tB),
    }));

    engA.notifyEdit(); await engA.flush(); await settle();
    engB.notifyEdit(); await engB.flush(); await settle();

    // Each engine wrote to its OWN state path.
    assert.ok(ghA.calls.some((c) => c[0] === 'putFile' && c[1] === '.review-sync/' + TALK + '/video1-uk.json'));
    assert.ok(ghB.calls.some((c) => c[0] === 'putFile' && c[1] === '.review-sync/' + TALK + '/transcript-uk.json'));
    // Each doc carries ONLY its own target's entry.
    assert.deepStrictEqual(Object.keys(ghA.puts[0].entries), [CK]);
    assert.deepStrictEqual(Object.keys(ghB.puts[0].entries), ['review_' + TALK]);
    // Neither engine deleted the other's local edit.
    assert.ok(storage.getItem(CK));
    assert.ok(storage.getItem('review_' + TALK));
    // Base metas are stored under distinct target-scoped keys.
    assert.ok(storage.getItem(syncBaseKey(TALK, srt.slug)));
    assert.ok(storage.getItem(syncBaseKey(TALK, tr.slug)));
    assert.strictEqual(storage.getItem(syncBaseKey(TALK)), null);
  });
});

// --- File-content hygiene ------------------------------------------------------
//
// Collaborators still hold edits containing NBSP in localStorage from before the
// input fields were fixed; this is the last gate before the bytes reach GitHub.
// Invisible characters ONLY -- `content` is a whole rebuilt file, so the
// field-level rule would collapse its newlines and destroy the SRT.
const { sanitizeInvisible } = require('../site/js/text_sanitize');

describe('engine: rebuilt file hygiene', () => {
  const SRT_PATH = 'talks/' + TALK + '/video1/final/uk.srt';

  // gh.putFile is resolved on the stub at call time, so wrapping it after
  // construction captures exactly what the engine sends.
  function capturePuts(engineOver) {
    const h = makeEngine(undefined, undefined, engineOver);
    const seen = [];
    const origPut = h.gh.putFile;
    h.gh.putFile = async (api, token, opts) => { seen.push(opts); return origPut(api, token, opts); };
    return Object.assign({ seen }, h);
  }

  async function pushOnce(h) {
    localEdit(h.storage, 1, 'а');
    h.engine.notifyEdit();
    h.timers.fire(15000);
    await settle();
  }

  it('strips invisible characters from rebuilt files before putFile', async () => {
    const dirty = '1\n00:00:01,000 --> 00:00:02,000\nПривіт\u00a0світ\u200b\n\n';
    const h = capturePuts({
      buildFiles: () => [{ path: SRT_PATH, content: dirty }],
      sanitize: sanitizeInvisible,
    });
    await pushOnce(h);

    const srt = h.seen.filter((o) => o.path === SRT_PATH);
    assert.strictEqual(srt.length, 1, 'the rebuilt SRT was not pushed');
    assert.ok(!srt[0].content.includes('\u00a0'), 'NBSP reached putFile');
    assert.ok(!srt[0].content.includes('\u200b'), 'ZWSP reached putFile');
    assert.ok(srt[0].content.includes('Привіт світ'), 'NBSP was deleted instead of folded to a space');
    assert.ok(
      srt[0].content.includes('00:00:01,000 --> 00:00:02,000'),
      'SRT line structure was destroyed -- the field-level rule was applied by mistake',
    );
  });

  it('passes content through unchanged when no sanitizer is wired', async () => {
    // edit_sync.js must stay loadable in a context that never pulls the twin in.
    const content = '1\n00:00:01,000 --> 00:00:02,000\nplain\n\n';
    const h = capturePuts({ buildFiles: () => [{ path: SRT_PATH, content: content }] });
    await pushOnce(h);

    const srt = h.seen.filter((o) => o.path === SRT_PATH);
    assert.strictEqual(srt.length, 1);
    assert.strictEqual(srt[0].content, content);
  });
});


// --- index.html wiring -----------------------------------------------------
//
// The engine-side hygiene tests above inject `sanitize` themselves, so the
// one line in index.html that actually wires sanitizeInvisible into
// ensureEditSync could be deleted with every test green. Pin the wiring the
// way test_spa_cache.js pins the stylesheet links: by reading the source.
describe('index.html wiring', () => {
  const fs = require('node:fs');
  const path = require('node:path');
  const html = fs.readFileSync(path.join(__dirname, '..', 'site', 'index.html'), 'utf8');

  it('passes sanitizeInvisible into the sync engine', () => {
    assert.match(html, /sanitize:\s*sanitizeInvisible/);
  });

  it('loads text_sanitize.js before the inline app code that calls it', () => {
    const tag = html.indexOf('src="js/text_sanitize.js"');
    assert.notStrictEqual(tag, -1, 'text_sanitize.js script tag missing');
  });
});
