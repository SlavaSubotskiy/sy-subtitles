// Pending-action feedback: the in-flight lock and the busy-label vocabulary.
//
// The signed-in write actions ("Create PR" on the add-talk page, Finalize in
// the sync chip, Create issue) are chains of sequential GitHub calls — seconds
// of wall clock during which the app used to look untouched. Two things were
// wrong with that: the wait was unnarrated, and the trigger stayed live, so a
// second click really did create a second branch and a second PR.
//
// This module owns the two decisions behind the fix, so both are testable
// without a browser: WHETHER an action may start, and WHAT the button says
// while it runs. The DOM writing stays in index.html.
//
// Single source shared by index.html (<script src>) and the node test suite.
(function (root) {
  'use strict';

  // One registry of in-flight action keys. `run` starts the action only when
  // its key is free and releases the key however the action settles — a
  // failure must leave the button clickable again, or the only way back is a
  // reload.
  //
  // Contract: `run` returns whatever `fn()` returned (every caller in the app
  // returns a promise), or null when the key is already busy. That return is
  // therefore AMBIGUOUS for a falsy value — a caller that must undo something
  // on the "did not start" branch has to ask `isBusy` FIRST (withBusyButton
  // does; otherwise a button it painted could never be un-painted).
  function createActionLock() {
    // Object.create(null): a bare {} would answer isBusy('constructor') with
    // the inherited function and swallow that click.
    var inflight = Object.create(null);

    function isBusy(key) { return inflight[key] === true; }

    function run(key, fn) {
      if (isBusy(key)) return null;
      inflight[key] = true;
      var out;
      try {
        out = fn();
      } catch (e) {
        delete inflight[key];
        throw e;
      }
      if (!out || typeof out.then !== 'function') {
        delete inflight[key];
        return out;
      }
      function release() { delete inflight[key]; }
      // A release-only continuation: its rejection handler returns normally,
      // so this branch never becomes an unhandled rejection of its own. The
      // ORIGINAL promise is what the caller gets, so an existing .catch still
      // sees the error.
      out.then(release, release);
      return out;
    }

    return { run: run, isBusy: isBusy };
  }

  // Step name -> i18n key for the busy label. The one-click PR chain reports
  // 'branch' / 'commit' / 'pr' as it goes (see submitFilesPr), the
  // single-request actions report themselves once. An unknown name degrades to
  // the generic label: a typo must leave a legible button, never a blank one.
  // Null-prototype, for the same reason the lock's registry is: a plain object
  // answers 'toString' with the inherited function, and the button would end up
  // labelled with a stringified function.
  var STEP_KEYS = Object.create(null);
  STEP_KEYS.branch = 'pending.branch';
  STEP_KEYS.commit = 'pending.commit';
  STEP_KEYS.pr = 'pending.pr';
  STEP_KEYS.issue = 'pending.issue';

  function pendingStepKey(step) {
    return (step && STEP_KEYS[step]) || 'pending.working';
  }

  // The runner: dress a button for the length of an action, narrate the phase,
  // and put the button back however the action ends. `deps` carries the three
  // things this module cannot reach on its own — the shared lock, the
  // translator, and a writer for the page's aria-live region.
  //
  // Returns withBusyButton(btn, key, fn): fn is handed a `step` function it
  // calls to name the current phase. A null btn is allowed — the lock and the
  // narration still apply, which is what a hidden trigger needs.
  function createBusyRunner(deps) {
    var lock = deps.lock;
    var translate = deps.t || function (k) { return k; };
    var announce = deps.announce || function () {};

    return function withBusyButton(btn, key, fn) {
      // Everything restore() needs, read before the first repaint.
      var restKey = btn ? btn.getAttribute('data-i18n') : null;
      var restText = btn ? btn.textContent : '';
      var restAria = btn ? btn.getAttribute('aria-disabled') : null;
      var settled = false;

      function paint(stepKey) {
        // A step reported after the action ended would repaint the busy state
        // with no restore left to run — a button stuck forever.
        if (settled) return;
        var text = translate(stepKey);
        // aria-busy on a button announces nothing, so the phase has to reach
        // assistive tech through a live region or it is invisible.
        announce(text);
        if (!btn) return;
        btn.classList.add('btn--busy');
        // aria-disabled, NOT the disabled property: disabling the element the
        // user just activated with Enter throws focus to <body> and takes the
        // accessible name with it. The lock is what actually refuses a second
        // click, so the button loses nothing by staying focusable.
        btn.setAttribute('aria-disabled', 'true');
        btn.setAttribute('aria-busy', 'true');
        // The key travels with the text: translatePage() only rewrites
        // [data-i18n] elements, so without this the label would stick in the
        // old language if the UI language is toggled mid-flight.
        btn.setAttribute('data-i18n', stepKey);
        btn.textContent = text;
      }

      function restore() {
        settled = true;
        // Leave nothing in the live region: role="status" text lingers for the
        // rest of the session, and some screen readers re-announce it later.
        announce('');
        if (!btn) return;
        btn.classList.remove('btn--busy');
        btn.removeAttribute('aria-busy');
        // Hand back what was there — a button already marked aria-disabled for
        // its own reasons must not come back enabled.
        if (restAria === null) btn.removeAttribute('aria-disabled');
        else btn.setAttribute('aria-disabled', restAria);
        if (restKey) {
          btn.setAttribute('data-i18n', restKey);
          btn.textContent = translate(restKey);
        } else {
          btn.removeAttribute('data-i18n');
          btn.textContent = restText;
        }
      }

      // isBusy BEFORE run, not the falsy return after it: run() answers null
      // both for "already busy" and for "started, returned nothing", and
      // confusing the two would paint a button that never gets un-painted.
      if (lock.isBusy(key)) return null;
      var started;
      try {
        started = lock.run(key, function () {
          // A generic label first, so an action that reports no step at all
          // still says something; a stepped one overwrites it in the same tick.
          paint(pendingStepKey(null));
          return fn(function (step) { paint(pendingStepKey(step)); });
        });
      } catch (e) {
        // fn threw before returning a promise. The lock has already released
        // its key; the button is ours to hand back before the error travels on.
        restore();
        throw e;
      }
      // A synchronous action is already finished by the time we get here.
      if (!started || typeof started.then !== 'function') { restore(); return started; }
      started.then(restore, restore);
      return started;
    };
  }

  var api = {
    createActionLock: createActionLock,
    pendingStepKey: pendingStepKey,
    createBusyRunner: createBusyRunner,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else Object.keys(api).forEach(function (k) { root[k] = api[k]; });
})(typeof window !== 'undefined' ? window : this);
