// Service Worker for SPA caching
// Version is passed via registration URL query: sw.js?v=10
// This ensures SW and index.html share the same version.
var VERSION = new URL(self.location).searchParams.get('v') || '0';
var CACHE_NAME = 'sy-subtitles-v' + VERSION;

// Assets that are truly immutable (versioned CDN URLs, static images)
var IMMUTABLE_PATTERNS = [
  'cdn.jsdelivr.net',
  'player.vimeo.com/api',
  '/icon.png'
];

self.addEventListener('install', function(e) {
  // Skip waiting — activate immediately so new version takes effect
  self.skipWaiting();
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

function isImmutable(url) {
  return IMMUTABLE_PATTERNS.some(function(p) { return url.includes(p); });
}

function isApiOrRaw(url) {
  return url.includes('api.github.com') || url.includes('raw.githubusercontent.com');
}

function isNavigation(url) {
  // index.html or root path — always network-first
  return url.endsWith('/') || url.endsWith('/index.html') || url.includes('sy-subtitles/#');
}

// Strategy: network-first with cache fallback
function networkFirst(request) {
  return fetch(request).then(function(response) {
    if (response.ok) {
      var clone = response.clone();
      caches.open(CACHE_NAME).then(function(c) { c.put(request, clone); });
    }
    return response;
  }).catch(function() {
    return caches.match(request);
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
  var url = e.request.url;

  if (isNavigation(url) || isApiOrRaw(url)) {
    // HTML page + API + raw content: always try network first
    e.respondWith(networkFirst(e.request));
  } else if (isImmutable(url)) {
    // CDN libs, icon: cache-first (immutable, versioned)
    e.respondWith(cacheFirst(e.request));
  } else {
    // Everything else (Vimeo player, etc): network-first
    e.respondWith(networkFirst(e.request));
  }
});
