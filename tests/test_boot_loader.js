// Boot-loader timing policy: when the index's centred loading mark is allowed
// to appear, and for how long it must stay once it has.
//
// The policy exists because both extremes look broken. Showing the mark the
// instant a load starts makes a warm-cache render (tens of milliseconds) flash
// it for one frame; hiding it the instant the data lands does the same to a
// load that only just crossed the delay. Single source: site/js/boot_loader.js
// (loaded by the SPA, require'd here) so the browser and these tests can never
// disagree about the timings.
const { test } = require('node:test');
const assert = require('node:assert');

const { createBootLoader, LOADER_SHOW_DELAY_MS, LOADER_MIN_VISIBLE_MS } = require('../site/js/boot_loader.js');

// Fake clock: `now` and `schedule` are injected, so every test drives time
// explicitly instead of sleeping. schedule() returns its own canceller.
function fakeClock() {
  let t = 0;
  let timers = [];
  return {
    now: function () { return t; },
    schedule: function (cb, ms) {
      const timer = { at: t + ms, cb: cb, cancelled: false };
      timers.push(timer);
      return function () { timer.cancelled = true; };
    },
    advance: function (ms) {
      const target = t + ms;
      // Fire in due order, allowing a callback to schedule further work.
      for (;;) {
        const due = timers
          .filter(function (x) { return !x.cancelled && x.at <= target; })
          .sort(function (a, b) { return a.at - b.at; })[0];
        if (!due) break;
        due.cancelled = true;
        t = due.at;
        due.cb();
      }
      t = target;
    },
    pending: function () {
      return timers.filter(function (x) { return !x.cancelled; }).length;
    },
  };
}

// A loader wired to a fake clock, recording the calls it makes: `calls` is the
// order of events, `settled` the outcomes handed to settle().
function harness(opts) {
  const clock = fakeClock();
  const calls = [];
  const settled = [];
  const loader = createBootLoader(Object.assign({
    now: clock.now,
    schedule: clock.schedule,
    show: function () { calls.push('show'); },
    settle: function (outcome) { calls.push('settle'); settled.push(outcome); },
  }, opts || {}));
  return { clock: clock, calls: calls, settled: settled, loader: loader };
}

test('a load in flight shows nothing until the show delay has passed', () => {
  const h = harness();

  h.loader.start();
  assert.deepStrictEqual(h.calls, [], 'nothing may paint on start()');

  h.clock.advance(LOADER_SHOW_DELAY_MS - 1);
  assert.deepStrictEqual(h.calls, [], 'still nothing one tick before the delay');

  h.clock.advance(1);
  assert.deepStrictEqual(h.calls, ['show'], 'the mark appears once the delay elapses');
});

test('a load that beats the show delay never paints the mark at all', () => {
  const h = harness();

  h.loader.start();
  h.clock.advance(LOADER_SHOW_DELAY_MS - 20);
  h.loader.finish();
  h.clock.advance(10000);

  assert.deepStrictEqual(h.calls, ['settle'], 'straight to the loaded screen, no mark in between');
  assert.strictEqual(h.clock.pending(), 0, 'the pending show must be cancelled, not left armed');
});

test('a mark already on screen is held for the minimum visible time', () => {
  const h = harness();

  h.loader.start();
  h.clock.advance(LOADER_SHOW_DELAY_MS);
  assert.deepStrictEqual(h.calls, ['show']);

  // Data lands 100ms after the mark appeared — far too soon to take it away.
  h.clock.advance(100);
  h.loader.finish();
  assert.deepStrictEqual(h.calls, ['show'], 'must not hide mid-breath');

  h.clock.advance(LOADER_MIN_VISIBLE_MS - 100 - 1);
  assert.deepStrictEqual(h.calls, ['show'], 'still held one tick short of the minimum');

  h.clock.advance(1);
  assert.deepStrictEqual(h.calls, ['show', 'settle'], 'released exactly at the minimum');
});

test('a slow load settles the moment its data lands', () => {
  const h = harness();

  h.loader.start();
  h.clock.advance(LOADER_SHOW_DELAY_MS + LOADER_MIN_VISIBLE_MS + 5000);
  h.loader.finish();

  assert.deepStrictEqual(h.calls, ['show', 'settle'], 'no artificial wait once the minimum is spent');
});

test('finish() is idempotent — a second call never settles twice', () => {
  const h = harness();

  h.loader.start();
  h.clock.advance(LOADER_SHOW_DELAY_MS + LOADER_MIN_VISIBLE_MS);
  h.loader.finish();
  h.loader.finish();
  h.clock.advance(10000);

  assert.deepStrictEqual(h.calls, ['show', 'settle']);
});

test('finish() without a start() settles at once — an outcome is never swallowed', () => {
  const h = harness();

  h.loader.finish('done');
  h.clock.advance(10000);

  assert.deepStrictEqual(h.calls, ['settle'], 'no mark to wait on, so settle immediately');
  assert.deepStrictEqual(h.settled, ['done']);
});

// The outcome has to travel through the loader, not around it: the caller
// cannot paint an error the moment the request rejects, because the mark may
// still be serving out its minimum. So finish() carries the outcome and the
// settle callback applies it — hide the mark AND render what arrived.
test('the outcome reaches settle even when the mark never painted', () => {
  const h = harness();
  const err = { error: 'rate limit' };

  h.loader.start();
  h.clock.advance(LOADER_SHOW_DELAY_MS - 20);
  h.loader.finish(err);

  assert.deepStrictEqual(h.settled, [err], 'a fast failure must still be rendered');
});

test('the outcome reaches settle only after the held mark is released', () => {
  const h = harness();
  const err = { error: 'HTTP 500' };

  h.loader.start();
  h.clock.advance(LOADER_SHOW_DELAY_MS + 50);
  h.loader.finish(err);
  assert.deepStrictEqual(h.settled, [], 'the mark is still serving its minimum');

  h.clock.advance(LOADER_MIN_VISIBLE_MS);
  assert.deepStrictEqual(h.settled, [err]);
});

test('the show delay is short enough to stay responsive, long enough to swallow a cache hit', () => {
  assert.ok(LOADER_SHOW_DELAY_MS >= 80 && LOADER_SHOW_DELAY_MS <= 250,
    'show delay out of the usable band: ' + LOADER_SHOW_DELAY_MS);
  assert.ok(LOADER_MIN_VISIBLE_MS >= LOADER_SHOW_DELAY_MS,
    'a mark shown must outlive the delay that gated it');
});
