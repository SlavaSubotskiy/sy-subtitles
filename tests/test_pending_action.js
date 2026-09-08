const { describe, it } = require('node:test');
const assert = require('node:assert');
const { createActionLock, pendingStepKey } = require('../site/js/pending_action');

// A deferred promise, so a test can hold an action "in flight" and click again.
function deferred() {
  let resolve, reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

describe('createActionLock', () => {
  it('runs the action and returns its promise', async () => {
    const lock = createActionLock();
    const p = lock.run('add-talk', () => Promise.resolve('pr-7'));
    assert.strictEqual(await p, 'pr-7');
  });

  it('ignores a second call while the first is in flight', async () => {
    // The defect this guards: on the add-talk page the GitHub chain takes
    // seconds, and a second click used to create a SECOND branch and PR.
    const lock = createActionLock();
    const d = deferred();
    let started = 0;
    const fn = () => { started++; return d.promise; };

    const first = lock.run('add-talk', fn);
    const second = lock.run('add-talk', fn);

    assert.ok(first, 'the first call starts the action');
    assert.strictEqual(second, null, 'the second call starts nothing');
    assert.strictEqual(started, 1);

    d.resolve('ok');
    await first;
  });

  it('reports the busy key while in flight and releases on success', async () => {
    const lock = createActionLock();
    const d = deferred();
    const p = lock.run('finalize', () => d.promise);
    assert.strictEqual(lock.isBusy('finalize'), true);
    d.resolve(null);
    await p;
    assert.strictEqual(lock.isBusy('finalize'), false);
  });

  it('releases the key when the action rejects, so a retry is possible', async () => {
    const lock = createActionLock();
    const d = deferred();
    const p = lock.run('finalize', () => d.promise);
    d.reject(new Error('HTTP 500'));
    await assert.rejects(p, /HTTP 500/);
    assert.strictEqual(lock.isBusy('finalize'), false);
    assert.ok(lock.run('finalize', () => Promise.resolve(1)), 'the key is claimable again');
  });

  it('releases the key when the action throws synchronously', () => {
    const lock = createActionLock();
    assert.throws(() => lock.run('k', () => { throw new Error('boom'); }), /boom/);
    assert.strictEqual(lock.isBusy('k'), false);
  });

  it('keeps keys independent', () => {
    const lock = createActionLock();
    const d = deferred();
    lock.run('a', () => d.promise);
    assert.strictEqual(lock.isBusy('a'), true);
    assert.strictEqual(lock.isBusy('b'), false);
    assert.ok(lock.run('b', () => deferred().promise), 'a different key is free');
  });

  it('releases immediately when the action returns no promise', () => {
    const lock = createActionLock();
    lock.run('k', () => 42);
    assert.strictEqual(lock.isBusy('k'), false);
  });

  it("run's falsy return is ambiguous — isBusy is what says whether it started", () => {
    // Both of these answer null, for opposite reasons. A caller that has to
    // undo something on the "did not start" branch MUST ask isBusy first, or
    // it will undo nothing for an action that did start (and, painting a
    // button, leave it busy forever).
    const lock = createActionLock();
    assert.strictEqual(lock.run('k', () => null), null, 'started, returned null');
    const d = deferred();
    lock.run('busy', () => d.promise);
    assert.strictEqual(lock.run('busy', () => d.promise), null, 'did not start');
    assert.strictEqual(lock.isBusy('busy'), true);
    assert.strictEqual(lock.isBusy('k'), false);
  });

  it('does not treat an inherited property name as a busy key', () => {
    // A bare {} registry would report 'constructor'/'toString' as busy and
    // silently swallow the click.
    const lock = createActionLock();
    assert.strictEqual(lock.isBusy('constructor'), false);
    assert.ok(lock.run('constructor', () => Promise.resolve(1)));
  });
});

describe('pendingStepKey', () => {
  it('maps each step of the one-click PR chain to its own label', () => {
    assert.strictEqual(pendingStepKey('branch'), 'pending.branch');
    assert.strictEqual(pendingStepKey('commit'), 'pending.commit');
    assert.strictEqual(pendingStepKey('pr'), 'pending.pr');
  });

  it('maps the single-request action', () => {
    assert.strictEqual(pendingStepKey('issue'), 'pending.issue');
  });

  it('has no key nothing can reach', () => {
    // Finalize is fired from a dropdown item with no button to label — the
    // chip carries that wait — so a 'finalize' step would be a dead string.
    assert.strictEqual(pendingStepKey('finalize'), 'pending.working');
  });

  it('falls back to the generic label for an unknown or missing step', () => {
    // A typo in a step name must still leave a legible button, never a blank one.
    assert.strictEqual(pendingStepKey('typo'), 'pending.working');
    assert.strictEqual(pendingStepKey(''), 'pending.working');
    assert.strictEqual(pendingStepKey(undefined), 'pending.working');
    assert.strictEqual(pendingStepKey(null), 'pending.working');
  });

  it('never returns an inherited property instead of a key', () => {
    // A plain-object map answers 'toString' with the inherited function, and
    // the button would then be labelled with a stringified function.
    for (const name of ['toString', 'constructor', 'valueOf', '__proto__']) {
      assert.strictEqual(pendingStepKey(name), 'pending.working', name);
    }
  });
});

// ---------------------------------------------------------------------------
// createBusyRunner: the paint/restore half of the feature. These are the cases
// that decide whether a button ever comes back from its busy state.
// ---------------------------------------------------------------------------
const { createBusyRunner } = require('../site/js/pending_action');

const LABELS = {
  'add.submit': 'Create PR',
  'pending.working': 'Working…',
  'pending.branch': 'Creating the branch…',
  'pending.commit': 'Committing the file…',
  'pending.pr': 'Opening the PR…',
};

function fakeButton(attrs) {
  const a = Object.assign({ 'data-i18n': 'add.submit' }, attrs || {});
  const classes = new Set();
  return {
    textContent: 'Create PR',
    // A real button has this, and a real one going true steals focus. Modelled
    // so the "we never disable it" test can actually fail.
    disabled: false,
    classList: {
      add: (c) => classes.add(c),
      remove: (c) => classes.delete(c),
      contains: (c) => classes.has(c),
    },
    getAttribute: (k) => (k in a ? a[k] : null),
    setAttribute: (k, v) => { a[k] = String(v); },
    removeAttribute: (k) => { delete a[k]; },
  };
}

function runner(over) {
  const said = [];
  const deps = Object.assign({
    lock: createActionLock(),
    t: (k) => LABELS[k] || k,
    announce: (text) => said.push(text),
  }, over || {});
  return { run: createBusyRunner(deps), said, lock: deps.lock };
}

const look = (btn) => ({
  text: btn.textContent,
  i18n: btn.getAttribute('data-i18n'),
  busy: btn.classList.contains('btn--busy'),
  ariaBusy: btn.getAttribute('aria-busy'),
  ariaDisabled: btn.getAttribute('aria-disabled'),
});

describe('createBusyRunner', () => {
  it('dresses the button and relabels it per step', () => {
    const { run } = runner();
    const btn = fakeButton();
    run(btn, 'k', (step) => { step('branch'); return deferred().promise; });
    assert.deepStrictEqual(look(btn), {
      text: 'Creating the branch…', i18n: 'pending.branch',
      busy: true, ariaBusy: 'true', ariaDisabled: 'true',
    });
  });

  it('marks aria-disabled rather than disabling — a disabled button drops focus', () => {
    // The user activated this button with Enter; setting .disabled would throw
    // focus to <body> and take the accessible name with it. The lock is what
    // actually refuses the second click, so nothing is lost by staying focusable.
    const { run } = runner();
    const btn = fakeButton();
    run(btn, 'k', () => deferred().promise);
    assert.strictEqual(btn.disabled, false, 'the native property is untouched');
    assert.strictEqual(btn.getAttribute('disabled'), null,
      'and neither is the attribute — restore() would never take it off again');
    assert.strictEqual(btn.getAttribute('aria-disabled'), 'true');
  });

  it('clears the live region when the action ends', async () => {
    // role="status" text lingers for the rest of the session otherwise, and
    // some screen readers re-announce a status node on re-render.
    const { run, said } = runner();
    await run(fakeButton(), 'k', (step) => { step('pr'); return Promise.resolve(); });
    await Promise.resolve();
    assert.strictEqual(said[said.length - 1], '', `left: ${JSON.stringify(said)}`);
  });

  it('ignores a step called after the action settled', async () => {
    // A late step would repaint busy with no restore left to run — a button
    // stuck forever. The module is a reusable primitive; hold its own invariant.
    const { run } = runner();
    const btn = fakeButton();
    let late;
    await run(btn, 'k', (step) => { late = step; return Promise.resolve(); });
    await Promise.resolve();
    late('branch');
    assert.strictEqual(look(btn).busy, false);
    assert.strictEqual(look(btn).text, 'Create PR');
    assert.strictEqual(look(btn).ariaDisabled, null);
  });

  it('narrates every step into the live region', async () => {
    // aria-busy on a button announces nothing; without this the step labels
    // are invisible to a screen reader.
    const { run, said } = runner();
    await run(fakeButton(), 'k', (step) => {
      step('branch'); step('commit'); step('pr');
      return Promise.resolve();
    });
    assert.deepStrictEqual(said,
      ['Working…', 'Creating the branch…', 'Committing the file…', 'Opening the PR…', '']);
  });

  it('returns the button to rest on success', async () => {
    const { run } = runner();
    const btn = fakeButton();
    await run(btn, 'k', (step) => { step('pr'); return Promise.resolve(1); });
    await Promise.resolve();
    assert.deepStrictEqual(look(btn), {
      text: 'Create PR', i18n: 'add.submit',
      busy: false, ariaBusy: null, ariaDisabled: null,
    });
  });

  it('returns the button to rest when the action rejects', async () => {
    const { run, lock } = runner();
    const btn = fakeButton();
    await run(btn, 'k', () => Promise.reject(new Error('HTTP 500'))).catch(() => {});
    await Promise.resolve();
    assert.strictEqual(look(btn).busy, false);
    assert.strictEqual(look(btn).text, 'Create PR');
    assert.strictEqual(lock.isBusy('k'), false);
  });

  it('returns the button to rest when the action throws synchronously', () => {
    const { run } = runner();
    const btn = fakeButton();
    assert.throws(() => run(btn, 'k', () => { throw new Error('boom'); }), /boom/);
    assert.strictEqual(look(btn).busy, false);
    assert.strictEqual(look(btn).text, 'Create PR');
  });

  it('returns the button to rest when the action returns no promise', () => {
    // run() answers null for this AND for "already busy"; confusing the two
    // would leave the button busy with nothing left to un-busy it.
    const { run } = runner();
    [undefined, null, 0].forEach(function (value, i) {
      const btn = fakeButton();
      run(btn, 'k' + i, () => value);
      assert.strictEqual(look(btn).busy, false, String(value));
      assert.strictEqual(look(btn).text, 'Create PR', String(value));
    });
  });

  it('a second call while busy starts nothing and disturbs nothing', () => {
    const { run } = runner();
    const btn = fakeButton();
    let started = 0;
    run(btn, 'k', () => { started++; return deferred().promise; });
    const painted = look(btn);
    assert.strictEqual(run(btn, 'k', () => { started++; return Promise.resolve(); }), null);
    assert.strictEqual(started, 1);
    assert.deepStrictEqual(look(btn), painted, 'still wearing the first action state');
  });

  it('hands back a pre-existing aria-disabled instead of clearing it', async () => {
    const { run } = runner();
    const btn = fakeButton({ 'aria-disabled': 'true' });
    await run(btn, 'k', () => Promise.resolve());
    await Promise.resolve();
    assert.strictEqual(btn.getAttribute('aria-disabled'), 'true');
  });

  it('restores raw text for a button carrying no data-i18n', async () => {
    const { run } = runner();
    const btn = fakeButton();
    btn.removeAttribute('data-i18n');
    btn.textContent = 'Ad hoc';
    await run(btn, 'k', () => Promise.resolve());
    await Promise.resolve();
    assert.strictEqual(btn.textContent, 'Ad hoc');
    assert.strictEqual(btn.getAttribute('data-i18n'), null);
  });

  it('still locks and narrates when there is no button to dress', () => {
    const { run, said, lock } = runner();
    assert.ok(run(null, 'k', (step) => { step('issue'); return deferred().promise; }));
    assert.strictEqual(lock.isBusy('k'), true);
    assert.ok(said.indexOf('pending.issue') !== -1);
  });
});
