// Boot loader timing policy for the index's centred loading mark.
//
// The mark itself is CSS (.app-loader in css/components.css); this decides WHEN
// it may appear and for how long it must stay. Both extremes look broken: paint
// it the instant a load starts and a warm-cache render flashes it for a single
// frame; drop it the instant the data lands and a load that only just crossed
// the delay does the same. So a show is delayed, and a mark that did appear
// outlives its arrival.
//
// Single source for the browser (script tag) and the Node tests
// (tests/test_boot_loader.js); `now` and `schedule` are injected so the tests
// drive a fake clock instead of sleeping.

// Long enough that a manifest served from cache never paints the mark, short
// enough that a real network load feels answered immediately.
var LOADER_SHOW_DELAY_MS = 140;

// Once the mark is on screen it stays at least this long, so a load finishing
// just after the delay does not blink it out mid-breath.
var LOADER_MIN_VISIBLE_MS = 620;

function createBootLoader(deps) {
  var showDelay = deps.showDelay == null ? LOADER_SHOW_DELAY_MS : deps.showDelay;
  var minVisible = deps.minVisible == null ? LOADER_MIN_VISIBLE_MS : deps.minVisible;
  var cancelShow = null;   // set while a show is armed but has not fired
  var shownAt = null;      // set once the mark is actually on screen
  var done = false;        // latch, so a repeated finish() cannot hide twice

  function start() {
    cancelShow = deps.schedule(function () {
      cancelShow = null;
      shownAt = deps.now();
      deps.show();
    }, showDelay);
  }

  // `outcome` is whatever the caller needs to render — nothing on success, the
  // error on failure. It travels THROUGH the loader because the caller cannot
  // paint it at will: the mark may still be serving out its minimum. settle()
  // is therefore always called exactly once, and is the single place where the
  // screen goes from loading to loaded (or to an error).
  function finish(outcome) {
    if (done) return;
    done = true;
    if (cancelShow) {   // the load beat the delay — the mark never painted
      cancelShow();
      cancelShow = null;
    }
    var left = shownAt == null ? 0 : minVisible - (deps.now() - shownAt);
    if (left <= 0) deps.settle(outcome);
    else deps.schedule(function () { deps.settle(outcome); }, left);
  }

  return { start: start, finish: finish };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    createBootLoader: createBootLoader,
    LOADER_SHOW_DELAY_MS: LOADER_SHOW_DELAY_MS,
    LOADER_MIN_VISIBLE_MS: LOADER_MIN_VISIBLE_MS,
  };
}
