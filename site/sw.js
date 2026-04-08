// Service Worker for offline SPA caching
var CACHE_NAME = 'sy-subtitles-v10';
var STATIC_ASSETS = [
  './',
  './index.html',
  './icon.png',
  'https://cdn.jsdelivr.net/npm/js-yaml@4/dist/js-yaml.min.js'
];

self.addEventListener('install', function(e) {
  e.waitUntil(
    caches.open(CACHE_NAME).then(function(cache) {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', function(e) {
  e.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(
        keys.filter(function(k) { return k !== CACHE_NAME; })
            .map(function(k) { return caches.delete(k); })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', function(e) {
  // Network-first for API/raw (always fresh data), cache-first for static
  var url = e.request.url;
  if (url.includes('api.github.com') || url.includes('raw.githubusercontent.com') || url.endsWith('/') || url.endsWith('/index.html')) {
    // Network first, fall back to cache
    e.respondWith(
      fetch(e.request).then(function(r) {
        if (r.ok) {
          var clone = r.clone();
          caches.open(CACHE_NAME).then(function(c) { c.put(e.request, clone); });
        }
        return r;
      }).catch(function() {
        return caches.match(e.request);
      })
    );
  } else {
    // Cache first for static assets
    e.respondWith(
      caches.match(e.request).then(function(cached) {
        return cached || fetch(e.request).then(function(r) {
          if (r.ok) {
            var clone = r.clone();
            caches.open(CACHE_NAME).then(function(c) { c.put(e.request, clone); });
          }
          return r;
        });
      })
    );
  }
});
