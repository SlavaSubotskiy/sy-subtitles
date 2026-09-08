"""E2E coverage for the service worker (site/sw.js).

The SPA skips SW registration on localhost (index.html guards on hostname),
so the Playwright suite never exercised the worker. These tests register
sw.js directly and drive the real install / activate / fetch-handler chain in
Chromium, covering the caching strategy (cache-first for immutable assets,
network-first for navigation — the branch where isApiOrRaw/isNavigation live)
and the activate-time purge of stale version caches.

Reuses the server/page fixtures from test_preview_spa.
"""

from __future__ import annotations

import pytest

from tests.test_preview_spa import (  # noqa: F401  — re-exported fixtures
    mock_player_js,
    page,
    server,
    spa_path,
)

# SW install/activate/claim and the fetch chain are timing-sensitive under
# `pytest -n auto` on a 2-core CI runner. The assertions are deterministic;
# only the scheduling is not — so retry rather than widen the timeout forever.
pytestmark = [pytest.mark.e2e, pytest.mark.flaky(reruns=2, reruns_delay=2)]

CACHE = "sy-subtitles-c19"  # CACHE_NAME in sw.js (CACHE_VERSION = 19)
SW_WAIT_MS = 15000


def _register_sw(page, server):  # noqa: F811
    """Register sw.js and wait until it controls the page (clients.claim())."""
    page.goto(f"{server}/index.html")
    page.evaluate("() => navigator.serviceWorker.register('sw.js')")
    page.wait_for_function("() => !!navigator.serviceWorker.controller", timeout=SW_WAIT_MS)


class TestServiceWorker:
    def test_registers_activates_and_controls_page(self, server, page):  # noqa: F811
        _register_sw(page, server)
        script_url = page.evaluate("() => navigator.serviceWorker.controller.scriptURL")
        assert script_url.endswith("/sw.js"), script_url

    def test_immutable_asset_populates_versioned_cache(self, server, page):  # noqa: F811
        _register_sw(page, server)
        page.evaluate("() => fetch('icon.png')")
        page.wait_for_function(
            "async () => { const c = await caches.open('sy-subtitles-c19');"
            " return !!(await c.match(location.origin + '/icon.png')); }",
            timeout=10000,
        )
        assert CACHE in page.evaluate("() => caches.keys()")

    def test_immutable_asset_is_served_cache_first(self, server, page):  # noqa: F811
        _register_sw(page, server)
        # Seed a sentinel under the icon.png key; cache-first must return it
        # without going to the network.
        page.evaluate(
            "async () => { const c = await caches.open('sy-subtitles-c19');"
            " await c.put(location.origin + '/icon.png',"
            " new Response('SENTINEL', {headers: {'content-type': 'text/plain'}})); }"
        )
        body = page.evaluate("async () => (await (await fetch('icon.png')).text())")
        assert body == "SENTINEL", f"icon.png was not served cache-first: {body[:80]!r}"

    def test_navigation_is_network_first_over_stale_cache(self, server, page):  # noqa: F811
        _register_sw(page, server)
        # Seed a stale sentinel for index.html; network-first must prefer the
        # live response when the network is reachable.
        page.evaluate(
            "async () => { const c = await caches.open('sy-subtitles-c19');"
            " await c.put(location.origin + '/index.html',"
            " new Response('STALE', {headers: {'content-type': 'text/html'}})); }"
        )
        body = page.evaluate("async () => (await (await fetch('index.html')).text())")
        assert "STALE" not in body, "index.html was served from stale cache (should be network-first)"
        assert "<" in body, f"expected the real index.html, got: {body[:80]!r}"

    def test_activate_purges_stale_version_caches(self, server, page):  # noqa: F811
        page.goto(f"{server}/index.html")
        # Seed an OLD version cache before the worker activates.
        page.evaluate(
            "async () => { const c = await caches.open('sy-subtitles-c2');"
            " await c.put(location.origin + '/old', new Response('x')); }"
        )
        page.evaluate("() => navigator.serviceWorker.register('sw.js')")
        page.wait_for_function("() => !!navigator.serviceWorker.controller", timeout=SW_WAIT_MS)
        # The activate handler deletes every cache whose name != CACHE_NAME.
        page.wait_for_function(
            "async () => !(await caches.keys()).includes('sy-subtitles-c2')",
            timeout=10000,
        )
        assert "sy-subtitles-c2" not in page.evaluate("() => caches.keys()")

    def test_activate_keeps_current_version_cache(self, server, page):  # noqa: F811
        # The purge must delete OTHER versions, never the current one. Seed c3
        # with a sentinel before activation; it (and its entry) must survive.
        page.goto(f"{server}/index.html")
        page.evaluate(
            "async () => { const c = await caches.open('sy-subtitles-c19');"
            " await c.put(location.origin + '/keep', new Response('KEEP')); }"
        )
        page.evaluate("() => navigator.serviceWorker.register('sw.js')")
        page.wait_for_function("() => !!navigator.serviceWorker.controller", timeout=SW_WAIT_MS)
        assert CACHE in page.evaluate("() => caches.keys()")
        survived = page.evaluate(
            "async () => { const c = await caches.open('sy-subtitles-c19');"
            " const r = await c.match(location.origin + '/keep'); return r ? await r.text() : null; }"
        )
        assert survived == "KEEP", "activate wrongly purged the current-version cache"

    def test_claims_a_preexisting_uncontrolled_client(self, server, page):  # noqa: F811
        # The page loads with no controller (registration happens after load);
        # clients.claim() must take control of this already-open client without
        # a reload — that is what lets the SW serve the current session offline.
        page.goto(f"{server}/index.html")
        assert page.evaluate("() => navigator.serviceWorker.controller") is None
        page.evaluate("() => navigator.serviceWorker.register('sw.js')")
        page.wait_for_function("() => !!navigator.serviceWorker.controller", timeout=SW_WAIT_MS)
        assert page.evaluate("() => !!navigator.serviceWorker.controller") is True

    def test_install_precaches_app_shell(self, server, page):  # noqa: F811
        # The install handler precaches the shell, so it is present WITHOUT any
        # navigation beyond the first load — this is what lets the very first
        # offline reload boot (the page + js loaded before the worker controlled,
        # so they would not otherwise be cached).
        _register_sw(page, server)
        page.wait_for_function(
            "async () => { const c = await caches.open('sy-subtitles-c19');"
            " const us = (await c.keys()).map(r => r.url);"
            " return us.some(u => u.split('?')[0].endsWith('/index.html'))"
            " && us.filter(u => u.includes('/js/')).length >= 11"
            " && us.some(u => u.endsWith('/icon.png')); }",
            timeout=10000,
        )
        shell = page.evaluate(
            "async () => { const c = await caches.open('sy-subtitles-c19');"
            " const us = (await c.keys()).map(r => r.url);"
            " return { index: us.some(u => u.split('?')[0].endsWith('/index.html')),"
            " js: us.filter(u => u.includes('/js/')).length,"
            " icon: us.some(u => u.endsWith('/icon.png')),"
            " root: us.some(u => u.split('?')[0].endsWith('/')) }; }"
        )
        assert shell["index"], "index.html not precached on install"
        assert shell["js"] >= 11, f"expected all shell js precached, got {shell['js']}"
        assert shell["icon"], "icon.png not precached on install"
        assert shell["root"], "directory root ('./') not precached on install"


class TestServiceWorkerOffline:
    """Offline fallback + the network-first/cache-first branches under a real
    dropped connection (driven by CDP set_offline, so the assertions are
    deterministic — only the worker scheduling is retried via the module mark)."""

    def _go_offline(self, page):  # noqa: F811
        page.context.set_offline(True)

    def _go_online(self, page):  # noqa: F811
        page.context.set_offline(False)

    def test_cache_first_miss_goes_to_network_then_serves_offline(self, server, page):  # noqa: F811
        # icon.png is immutable → cache-first. First fetch is a MISS, so it must
        # fall through to the network and populate the cache; a later OFFLINE
        # fetch must then be served from that cache. (The install precache seeds
        # icon.png, so delete it first to exercise the genuine miss path.)
        _register_sw(page, server)
        page.evaluate(
            "async () => { const c = await caches.open('sy-subtitles-c19');"
            " await c.delete(location.origin + '/icon.png'); }"
        )
        miss = page.evaluate(
            "async () => { const c = await caches.open('sy-subtitles-c19');"
            " return !!(await c.match(location.origin + '/icon.png')); }"
        )
        assert miss is False, "precondition: icon.png must not be cached yet"
        page.evaluate("() => fetch('icon.png')")
        page.wait_for_function(
            "async () => { const c = await caches.open('sy-subtitles-c19');"
            " return !!(await c.match(location.origin + '/icon.png')); }",
            timeout=10000,
        )
        self._go_offline(page)
        try:
            ok = page.evaluate("async () => (await fetch('icon.png')).ok")
            assert ok is True, "icon.png not served from cache while offline"
        finally:
            self._go_online(page)

    def test_navigation_offline_falls_back_to_cached_shell(self, server, page):  # noqa: F811
        # The key offline-reload guarantee: index.html is network-first, so once
        # it has been fetched online (and cached) an OFFLINE request serves the
        # cached shell instead of failing. Without this the app cannot load at
        # all offline, and the localStorage degradation never gets a chance.
        _register_sw(page, server)
        page.evaluate("() => fetch('index.html')")
        page.wait_for_function(
            "async () => { const c = await caches.open('sy-subtitles-c19');"
            " return !!(await c.match(location.origin + '/index.html')); }",
            timeout=10000,
        )
        self._go_offline(page)
        try:
            body = page.evaluate("async () => (await (await fetch('index.html')).text())")
            assert "<" in body, f"offline shell not served from cache: {body[:80]!r}"
        finally:
            self._go_online(page)

    def test_network_first_miss_offline_rejects_gracefully(self, server, page):  # noqa: F811
        # A never-cached request while offline: networkFirst's caches.match
        # returns undefined → respondWith(undefined) → the page fetch rejects
        # (a clean network error), and the worker keeps serving other requests.
        _register_sw(page, server)
        # Seed a cached asset so we can prove the SW is still alive afterwards.
        page.evaluate("() => fetch('icon.png')")
        page.wait_for_function(
            "async () => { const c = await caches.open('sy-subtitles-c19');"
            " return !!(await c.match(location.origin + '/icon.png')); }",
            timeout=10000,
        )
        self._go_offline(page)
        try:
            outcome = page.evaluate(
                "async () => { try { await fetch('never-cached-' + 'xyz.js'); return 'resolved'; }"
                " catch (e) { return 'rejected'; } }"
            )
            assert outcome == "rejected", "uncached offline request should reject, not resolve"
            # Worker still healthy: the cached immutable asset is still served.
            still_ok = page.evaluate("async () => (await fetch('icon.png')).ok")
            assert still_ok is True, "worker stopped serving cached assets after an offline miss"
        finally:
            self._go_online(page)

    def test_non_ok_response_is_not_cached(self, server, page):  # noqa: F811
        # networkFirst caches only response.ok — a 404 must never be stored
        # (otherwise a transient miss would be served forever).
        _register_sw(page, server)
        status = page.evaluate("async () => (await fetch('definitely-missing-asset.js')).status")
        assert status == 404, f"expected a 404 from the test server, got {status}"
        cached = page.evaluate(
            "async () => { const c = await caches.open('sy-subtitles-c19');"
            " return !!(await c.match(location.origin + '/definitely-missing-asset.js')); }"
        )
        assert cached is False, "a 404 response was wrongly written to the cache"

    def test_app_asset_is_network_first_with_offline_fallback(self, server, page):  # noqa: F811
        # Same-origin non-immutable assets (js/css) take the "everything else"
        # branch → network-first. Online caches them; offline serves the copy.
        _register_sw(page, server)
        page.evaluate("() => fetch('js/sw_routing.js')")
        page.wait_for_function(
            "async () => { const c = await caches.open('sy-subtitles-c19');"
            " return !!(await c.match(location.origin + '/js/sw_routing.js')); }",
            timeout=10000,
        )
        self._go_offline(page)
        try:
            body = page.evaluate("async () => (await (await fetch('js/sw_routing.js')).text())")
            assert "pickStrategy" in body, "app js not served from cache while offline"
        finally:
            self._go_online(page)

    def test_sha_versioned_content_is_served_cache_first(self, server, page):  # noqa: F811
        # Subtitle/transcript URLs carry a ?v=<blob sha> cache-buster, so they are
        # immutable by URL → cache-first. Proof: seed a sentinel under the key and
        # fetch it WHILE ONLINE — cache-first returns the cached copy without ever
        # hitting the network (a network-first route would try the network first).
        _register_sw(page, server)
        srt_url = "https://raw.githubusercontent.com/o/r/main/talks/x/uk/final/uk.srt?v=ab12cd34"
        page.evaluate(
            "async (u) => { const c = await caches.open('sy-subtitles-c19');"
            " await c.put(u, new Response('CACHED-SRT',"
            " {status: 200, headers: {'content-type': 'text/plain'}})); }",
            srt_url,
        )
        # Online (no set_offline): cache-first must still serve the cached bytes.
        body = page.evaluate("async (u) => (await (await fetch(u)).text())", srt_url)
        assert body == "CACHED-SRT", f"sha-versioned content not served cache-first: {body[:60]!r}"

    def test_raw_is_network_first_with_offline_cache_fallback(self, server, page):  # noqa: F811
        # raw.githubusercontent.com (meta.yaml etc.) is network-first, so an
        # OFFLINE request falls back to whatever the SW previously cached — this is
        # what makes already-viewed content available offline.
        _register_sw(page, server)
        url = "https://raw.githubusercontent.com/o/r/main/talks/x/meta.yaml"
        page.evaluate(
            "async (u) => { const c = await caches.open('sy-subtitles-c19');"
            " await c.put(u, new Response('CACHED-META',"
            " {status: 200, headers: {'content-type': 'text/plain'}})); }",
            url,
        )
        self._go_offline(page)
        try:
            body = page.evaluate("async (u) => (await (await fetch(u)).text())", url)
            assert body == "CACHED-META", f"raw not served from SW cache offline: {body[:60]!r}"
        finally:
            self._go_online(page)

    def test_trees_api_is_network_only_and_not_cached(self, server, page):  # noqa: F811
        # The Trees API is network-only: the SW never caches it, so offline the
        # request genuinely FAILS (rejects). That is deliberate — it lets the app
        # detect offline and fall back to its localStorage manifest + show the
        # offline badge, instead of being fooled by a cached 200 (the shadowing the
        # earlier network-first behaviour caused). Even a pre-seeded cache entry is
        # bypassed: network-only never consults the cache.
        _register_sw(page, server)
        api = "https://api.github.com/git/trees/main?recursive=1"
        page.evaluate(
            "async (u) => { const c = await caches.open('sy-subtitles-c19');"
            " await c.put(u, new Response('SHOULD-NOT-BE-SERVED', {status: 200})); }",
            api,
        )
        self._go_offline(page)
        try:
            outcome = page.evaluate(
                "async (u) => { try { await fetch(u); return 'resolved'; } catch (e) { return 'rejected'; } }",
                api,
            )
            assert outcome == "rejected", "Trees API offline should reject (network-only), not be served from cache"
        finally:
            self._go_online(page)

    def test_first_visit_offline_reload_boots_shell(self, server, page):  # noqa: F811
        # The whole point of the install precache: an offline reload right after
        # the FIRST visit must still boot the SPA. The first page + its <script
        # src> loaded before the worker controlled, so only the precache has the
        # shell; the navigation falls back to it via ignoreSearch / mode==navigate.
        _register_sw(page, server)
        self._go_offline(page)
        try:
            page.reload(wait_until="domcontentloaded", timeout=15000)
            # I18N is defined by index.html's inline script — its presence proves
            # the precached shell (html + js) booted with no network.
            page.wait_for_function("() => typeof I18N !== 'undefined'", timeout=10000)
            assert page.evaluate("() => typeof t === 'function'") is True
            assert page.evaluate("() => typeof showIndex === 'function'") is True
        finally:
            self._go_online(page)
