// Service Worker for SPA caching
// Browser detects changes by comparing sw.js byte-for-byte.
// CACHE_VERSION: bump when cache format changes or to force purge.
var CACHE_VERSION = 19;
var CACHE_NAME = 'sy-subtitles-c' + CACHE_VERSION;

// Routing predicates (isImmutable / isApiOrRaw / isNavigation / pickStrategy) are
// single-sourced in js/sw_routing.js so the Node suite can unit-test every branch
// (tests/test_sw_routing.js). importScripts evaluates it in this worker's global
// scope, exposing the functions here; the module's CommonJS export is a no-op in
// the worker (no `module`). Path is relative to this script, so sw.js and js/ stay
// siblings on GitHub Pages (/sy-subtitles/) and locally alike.
//
// The ?v= cache-buster matters because updateViaCache defaults to 'imports':
// imported scripts may be served from the HTTP cache during an SW update, unlike
// the top-level sw.js. Tying the query to CACHE_VERSION means a version bump
// re-fetches fresh routing logic — so routing changes must bump CACHE_VERSION.
importScripts('js/sw_routing.js?v=' + CACHE_VERSION);

// App shell, precached on install. Without this the FIRST visit cannot work
// offline: the worker only caches what it intercepts, and on the first load the
// page + all its <script src> ran before the worker was controlling — so an
// offline reload right after the first visit would request an uncached
// index.html and get a blank page. Precaching makes offline boot work from
// visit #1. The js and css lists are kept in lockstep with index.html's
// <script src="js/…"> and <link href="css/…"> tags by tests/test_sw_precache.js.
// './' and 'index.html' are both precached so either navigation form (the bare
// directory root or /index.html?query) resolves.
var SHELL_ASSETS = [
  './',
  'index.html',
  'icon.png',
  'css/tokens.css',
  'css/components.css',
  'js/preferences.js',
  'js/typo_hints.js',
  'js/preview_srt_parser.js',
  'js/preview_state.js',
  'js/edit_store.js',
  'js/load_token.js',
  'js/index_url_state.js',
  'js/manifest_fetch.js',
  'js/offline_fallback.js',
  'js/talk_slug.js',
  'js/text_sanitize.js',
  'js/vimeo_codec.js',
  'js/end_freeze.js',
  'js/add_talk_data.js',
  'js/shell_version.js',
  'js/boot_loader.js',
  'js/talk_actions.js',
  'js/review_issue.js',
  'js/passphrase_gate.js',
  'js/github_auth.js',
  'js/github_api.js',
  'js/edit_sync.js',
  'js/marker_sync.js',
  'js/sync_status_view.js',
  'js/my_work.js',
  'js/burn_video.js',
  'js/burn_artifact.js',
  'js/export_menu.js'
];

// Scripts that load inside the typo-hints Worker rather than through a <script>
// tag, so the shell lockstep above cannot see them. Left uncached, switching the
// hints on while offline starts a worker whose script 404s: it dies quietly, and
// every later scan is posted into a corpse. The dictionary they read is
// deliberately absent — 9 MB has no business in an install-time precache, and
// the hints are a feature the user opts into, not part of booting.
var WORKER_ASSETS = ['js/typo_worker.js', 'js/vendor/typo.js'];

// Cross-origin libs the shell needs to boot (js-yaml parses every meta.yaml).
// Best-effort: a CDN hiccup must not fail the whole install, so each is added
// individually and swallows its own error.
var SHELL_CDN = ['https://cdn.jsdelivr.net/npm/js-yaml@4/dist/js-yaml.min.js'];

self.addEventListener('install', function(e) {
  // Activate the new worker regardless of whether the precache below succeeds.
  // Precaching is a best-effort enhancement, not a prerequisite: gating
  // skipWaiting on it would let a single failed asset (a 404, a storage-quota
  // error, or a Cache-API-restricted private window) leave the user stuck on the
  // old controller with the new routing/version never shipping.
  self.skipWaiting();
  e.waitUntil(
    caches.open(CACHE_NAME).then(function(c) {
      return c.addAll(SHELL_ASSETS.concat(WORKER_ASSETS)).then(function() {
        return Promise.all(SHELL_CDN.map(function(u) {
          // Best-effort: a CDN hiccup must not fail the install — but log it, so a
          // silently-missing js-yaml (which parses every meta.yaml) is diagnosable.
          return c.add(u).catch(function(err) {
            console.warn('[SW] CDN precache skipped:', u, err);
          });
        }));
      });
    }).catch(function(err) {
      // Shell precache failed (an asset 404'd, or the Cache API is unavailable).
      // Swallow so install still succeeds and the worker activates with live
      // network routing — only offline boot is degraded, not the whole worker —
      // and log which/why instead of surfacing a bare "SW install failed".
      console.error('[SW] shell precache failed — offline boot degraded:', err);
    })
  );
});

self.addEventListener('activate', function(e) {
  // Delete all caches except current version
  e.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(
        keys.filter(function(k) { return k !== CACHE_NAME; })
            .map(function(k) { return caches.delete(k); })
      );
    })
  );
  // Take control of all clients immediately
  self.clients.claim();
});

// Strategy: network-first with cache fallback
function networkFirst(request) {
  return fetch(request).then(function(response) {
    if (response.ok) {
      var clone = response.clone();
      caches.open(CACHE_NAME).then(function(c) { c.put(request, clone); });
    }
    return response;
  }).catch(function() {
    // ignoreSearch so an offline fallback matches the precached copy even when the
    // request carries a query the cache key lacks — applies to every network-first
    // miss, most visibly a navigation like /index.html?sw=1 or /?branch=x.
    return caches.match(request, { ignoreSearch: true }).then(function(hit) {
      if (hit) return hit;
      // A navigation that still missed (any path/query) boots the SPA from the
      // precached shell rather than failing with a blank page. Under the app's
      // hash routing the document URL is always '/' or '/index.html' (both
      // precached → a direct hit above), so this deep fallback is reached only by
      // a non-hash deep link; it is intentionally not E2E-covered for that reason.
      if (request.mode === 'navigate') {
        return caches.match('./', { ignoreSearch: true }).then(function(root) {
          return root || caches.match('index.html', { ignoreSearch: true });
        });
      }
      // Non-navigation offline miss: fail explicitly. Response.error() yields the
      // same network error the page's fetch().catch() already handles, but states
      // the intent rather than letting respondWith synthesize it from undefined.
      return Response.error();
    });
  });
}

// Strategy: cache-first with network fallback
function cacheFirst(request) {
  return caches.match(request).then(function(cached) {
    if (cached) return cached;
    return fetch(request).then(function(response) {
      if (response.ok) {
        var clone = response.clone();
        caches.open(CACHE_NAME).then(function(c) { c.put(request, clone); });
      }
      return response;
    });
  });
}

self.addEventListener('fetch', function(e) {
  var strategy = pickStrategy(e.request.url);
  if (strategy === 'cache-first') {
    // CDN libs, icon, and sha-pinned ?v= content (SRT/transcripts): cache-first
    e.respondWith(cacheFirst(e.request));
  } else if (strategy === 'network-only') {
    // GitHub REST API (the Trees manifest, the branch list): passthrough, never
    // cached. Offline this rejects, so the app falls back to its localStorage
    // manifest and shows the offline badge.
    e.respondWith(fetch(e.request));
  } else {
    // HTML shell + meta.yaml + everything else: network-first
    e.respondWith(networkFirst(e.request));
  }
});
