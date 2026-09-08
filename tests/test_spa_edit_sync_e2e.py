"""E2E for the SPA's edit auto-sync feature (site/js/edit_sync.js wired into
site/index.html).

For a signed-in user on a review/preview view, edits stored in localStorage
auto-sync to a file-scoped state file (.review-sync/<talkId>/<target>.json) on
a deterministic branch (sync/<login>/<talkId>--<target>) behind a draft PR,
where the target names the edited file (transcript-<lang> or <video>-<lang>).
This suite drives the real browser flow with all GitHub endpoints mocked via
page.route:

  1. first edit bootstraps the branch, state file, draft PR AND commits the
     real edited file (v2 pushes the transcript alongside the state file),
  2. cross-device pull adopts remote edits without pushing,
  3. a CAS 409 triggers a fetch + three-way merge + retry,
  4. the signed-in preview hides Copy-all + the issue button, and the removed
     one-button PR control (#btn-preview-pr) is absent (signed out keeps the
     affordances in marker mode),
  5. finalize (from the chip dropdown) deletes the state file and marks the
     draft PR ready via GraphQL — no re-commit, no new branch/PR,
  6. a NEW edit after finalize re-drafts the PR (GraphQL) and re-pushes state,
  7. the sync chip's dropdown opens the PR url,
  8. a preview subtitle edit syncs to the VIDEO-scoped target (its own branch/
     state/PR + final/uk.srt), distinct from the transcript target — v3's
     file-scoped PRs.

The harness mirrors tests/test_spa_auth_actions_e2e.py: a local http.server
serves site/ with window.__SY_* injected in <head>, the signed-in session is
seeded via sy_gh_token / sy_gh_user, and window.open is stubbed. Generic
GitHub routes are registered first; specific routes after (later routes win).
"""

import base64
import http.server
import json
import threading
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

SITE = Path(__file__).parent.parent / "site"
SPA_URL = "/index.html"
MOCK_PLAYER_JS = (Path(__file__).parent / "fixtures" / "mock_vimeo_player.js").read_text()

# Session identity: the sync branch is derived from this login + the talk id +
# the file-scoped target. The review view here opens in transcript-default
# mode, so its target is transcript-<rightLang> (rightLang defaults to uk).
LOGIN = "tester"
TALK_ID = "2001-01-01_Test-Talk"
VIDEO_SLUG = "Test-Video"
SYNC_TARGET = "transcript-uk"
SYNC_BRANCH = f"sync/{LOGIN}/{TALK_ID}--{SYNC_TARGET}"
STATE_PATH = f".review-sync/{TALK_ID}/{SYNC_TARGET}.json"
REVIEW_KEY = f"review_{TALK_ID}"
SYNC_BASE_KEY = f"sy_sync_base_{TALK_ID}__{SYNC_TARGET}"

PR_NUMBER = 88
PR_URL = "https://github.com/sy-tools/sy-subtitles/pull/88"
PR_NODE_ID = "PR_n88"

SAMPLE_META = """title: 'Test Talk: Subtitle Preview'
date: '2001-01-01'
location: Test Location
videos:
- slug: Test-Video
  title: Test Video
  video_ref: r1DBtMTl9VW1NC
"""

SAMPLE_UK_SRT = """1
00:00:01,000 --> 00:00:05,000
Перший субтитр

2
00:00:06,000 --> 00:00:10,000
Другий субтитр
"""

SAMPLE_EN = "Talk Language: English\n\nFirst paragraph.\n\nSecond paragraph.\n"
SAMPLE_UK = "Мова промови: англійська\n\nПерший абзац.\n\nДругий абзац.\n"
# rightParas[0] == "Перший абзац." after the header line is stripped.
PARA0 = "Перший абзац."

MOCK_TREE = {
    "sha": "test123",
    "tree": [
        {"path": f"talks/{TALK_ID}/{VIDEO_SLUG}/final/uk.srt", "type": "blob"},
        {"path": f"talks/{TALK_ID}/{VIDEO_SLUG}/source/en.srt", "type": "blob"},
        {"path": f"talks/{TALK_ID}/meta.yaml", "type": "blob"},
        {"path": f"talks/{TALK_ID}/review_report.md", "type": "blob"},
        {"path": f"talks/{TALK_ID}/transcript_en.txt", "type": "blob"},
        {"path": f"talks/{TALK_ID}/transcript_uk.txt", "type": "blob"},
    ],
}

REVIEW_STATUS_UNASSIGNED = {
    "version": 1,
    "updated_at": "2026-07-12T00:00:00Z",
    "talks": {
        TALK_ID: {
            "status": "pending",
            "reviewer": None,
            "issue_number": 42,
            "updated_at": "2026-07-12T00:00:00Z",
        },
    },
}

# Chip / dropdown labels (English | Ukrainian) — both UI languages accepted.
SYNCED_LABEL_RE = "Synced|Синхронізовано"
READY_LABEL_RE = "In review|На ревʼю"
FINALIZE_LABEL_RE = "Finalize|Фіналізувати"
OPEN_PR_LABEL_RE = "View on GitHub|Переглянути на GitHub"


@pytest.fixture(scope="module")
def server():
    injected = (
        (SITE / "index.html")
        .read_text()
        .replace(
            "<head>",
            "<head><script>window.__SY_REPO='sy-tools/sy-subtitles';"
            "window.__SY_GH_CLIENT_ID='Iv1.test';"
            "window.__SY_GH_EXCHANGE_URL='https://oauth-exchange.test/exchange';</script>",
            1,
        )
        .encode("utf-8")
    )
    directory = str(SITE)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=directory, **k)

        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path.split("?", 1)[0] in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(injected)))
                self.end_headers()
                self.wfile.write(injected)
                return
            super().do_GET()

    httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()


# --- doc / body helpers ----------------------------------------------------


def sync_doc(entries, revision=1):
    """A remote sync document as edit_sync.js models it."""
    return {
        "version": 1,
        "revision": revision,
        "updatedAt": "2026-07-13T00:00:00Z",
        "client": "remoteclient",
        "talkId": TALK_ID,
        "entries": entries,
    }


def sync_doc_b64(entries, revision=1):
    """base64 of the JSON document, as the Contents API `content` field."""
    return base64.b64encode(json.dumps(sync_doc(entries, revision)).encode("utf-8")).decode("ascii")


def review_entry(edits, marks=None):
    return {"marks": marks or {}, "edits": edits}


def decode_put_doc(call):
    """Parse the sync document out of a recorded PUT to the state file."""
    return json.loads(base64.b64decode(call["body"]["content"]).decode("utf-8"))


# --- routing ---------------------------------------------------------------


def _record(calls, status, payload):
    def handle(route):
        req = route.request
        calls.append(
            {
                "method": req.method,
                "url": req.url,
                "body": json.loads(req.post_data) if req.post_data else None,
            }
        )
        route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))

    return handle


def _wire(pg, calls, review_status, sync_opts):
    """Register read mocks first, then write mocks (later-registered win).

    sync_opts controls the .review-sync/<talkId>.json contents endpoint:
      get_mode:          "404" (no state yet) or "doc" (return doc_entries)
      doc_entries:       entries returned for get_mode=="doc"
      doc_sha:           sha returned with the doc (default "shaR1")
      put_conflict_once: first PUT -> 409, then a GET returns conflict_entries
      conflict_entries:  the remote doc served after the 409 (CAS merge input)
      conflict_sha:      sha for the conflict doc (default "shaRemote")
    """
    state = {"conflicted": False}

    # 1) generic API + raw + vimeo (read side)
    pg.route(
        "**/api.github.com/**",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            headers={"ETag": '"e2e"'},
            body=json.dumps(MOCK_TREE),
        ),
    )
    pg.route("**/raw.githubusercontent.com/**", lambda r: r.fulfill(status=404, body="not found"))
    pg.route(
        "**/raw.githubusercontent.com/**/meta.yaml",
        lambda r: r.fulfill(status=200, content_type="text/plain", body=SAMPLE_META),
    )
    pg.route(
        "**/raw.githubusercontent.com/**/uk.srt",
        lambda r: r.fulfill(status=200, content_type="text/plain", body=SAMPLE_UK_SRT),
    )
    pg.route(
        "**/raw.githubusercontent.com/**/transcript_en.txt",
        lambda r: r.fulfill(status=200, content_type="text/plain", body=SAMPLE_EN),
    )
    pg.route(
        "**/raw.githubusercontent.com/**/transcript_uk.txt",
        lambda r: r.fulfill(status=200, content_type="text/plain", body=SAMPLE_UK),
    )
    pg.route(
        "**/raw.githubusercontent.com/**/review-status.json",
        lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(review_status)),
    )
    pg.route(
        "**/player.vimeo.com/api/player.js",
        lambda r: r.fulfill(status=200, content_type="application/javascript", body=MOCK_PLAYER_JS),
    )
    pg.route(
        "**/player.vimeo.com/video/**",
        lambda r: r.fulfill(status=200, content_type="text/html", body="<html></html>"),
    )

    # Repo root: the write-access probe (#753) GETs this on boot. The signed-in
    # test user HAS write access, so report push=true — else ghWriteUser() is null
    # and the sync engines never attach.
    pg.route(
        "**/api.github.com/repos/sy-tools/sy-subtitles",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"permissions": {"push": True, "pull": True}}),
        ),
    )

    # 2) write endpoints — registered last so they shadow the generic API mock.
    pg.route("**/api.github.com/repos/**/git/ref/heads/main", _record(calls, 200, {"object": {"sha": "base1"}}))
    pg.route("**/api.github.com/repos/**/git/refs", _record(calls, 201, {}))

    def delete_ref(route):
        # DELETE /git/refs/heads/<branch> — teardown drops the sync branch.
        req = route.request
        calls.append({"method": req.method, "url": req.url, "body": None})
        route.fulfill(status=204, body="")

    pg.route("**/api.github.com/repos/**/git/refs/heads/**", delete_ref)

    def pulls(route):
        req = route.request
        if req.method == "GET":
            # findOpenPrByHead — cosmetic re-attach lookup; report none.
            route.fulfill(status=200, content_type="application/json", body=json.dumps([]))
            return
        calls.append(
            {"method": req.method, "url": req.url, "body": json.loads(req.post_data) if req.post_data else None}
        )
        route.fulfill(
            status=201,
            content_type="application/json",
            body=json.dumps({"number": PR_NUMBER, "html_url": PR_URL, "node_id": PR_NODE_ID, "draft": True}),
        )

    pg.route("**/api.github.com/repos/**/pulls**", pulls)

    def graphql(route):
        # Draft <-> ready are the only GraphQL mutations; dispatch by the query
        # text so a finalize (markPullRequestReadyForReview) and an
        # edit-after-finalize (convertPullRequestToDraft) each get a matching
        # reply. Always record for the assertions.
        req = route.request
        body = json.loads(req.post_data) if req.post_data else None
        calls.append({"method": req.method, "url": req.url, "body": body})
        query = (body or {}).get("query", "")
        if "convertPullRequestToDraft" in query:
            data = {"convertPullRequestToDraft": {"pullRequest": {"isDraft": True}}}
        else:
            data = {"markPullRequestReadyForReview": {"pullRequest": {"isDraft": False}}}
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"data": data}))

    pg.route("**/api.github.com/graphql", graphql)

    # Issue endpoints for marker-sync (create / list / get / patch) + labels.
    issue_state = {"issue": None, "next": 900}

    def labels(route):
        route.fulfill(status=201, content_type="application/json", body=json.dumps({}))

    pg.route("**/api.github.com/repos/**/labels", labels)

    def issues(route):
        req = route.request
        method = req.method
        url = req.url
        if method == "GET" and "/issues?" in url:  # list by label
            rows = [issue_state["issue"]] if issue_state["issue"] else []
            route.fulfill(status=200, content_type="application/json", body=json.dumps(rows))
            return
        if method == "GET":  # single issue
            route.fulfill(status=200, content_type="application/json", body=json.dumps(issue_state["issue"] or {}))
            return
        body = json.loads(req.post_data) if req.post_data else {}
        calls.append({"method": method, "url": url, "body": body})
        if method == "POST":
            n = issue_state["next"]
            issue_state["next"] += 1
            issue_state["issue"] = {
                "number": n,
                "title": body.get("title"),
                "state": "open",
                "node_id": f"I_{n}",
                "html_url": f"https://github.com/x/issues/{n}",
                "body": body.get("body", ""),
            }
            route.fulfill(status=201, content_type="application/json", body=json.dumps(issue_state["issue"]))
            return
        if issue_state["issue"]:  # PATCH
            if "body" in body:
                issue_state["issue"]["body"] = body["body"]
            if "state" in body:
                issue_state["issue"]["state"] = body["state"]
        route.fulfill(status=200, content_type="application/json", body=json.dumps(issue_state["issue"] or {}))

    pg.route("**/api.github.com/repos/**/issues**", issues)

    def talks_contents(route):
        req = route.request
        if req.method == "GET":
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"sha": "blob1"}))
            return
        calls.append(
            {"method": req.method, "url": req.url, "body": json.loads(req.post_data) if req.post_data else None}
        )
        route.fulfill(status=201, content_type="application/json", body=json.dumps({"content": {"sha": "blobP"}}))

    pg.route("**/api.github.com/repos/**/contents/talks/**", talks_contents)

    def review_sync_contents(route):
        req = route.request
        method = req.method
        if method == "GET":
            serve_doc = state["conflicted"] or sync_opts.get("get_mode") == "doc"
            if serve_doc:
                if state["conflicted"]:
                    entries = sync_opts.get("conflict_entries", {})
                    sha = sync_opts.get("conflict_sha", "shaRemote")
                else:
                    entries = sync_opts.get("doc_entries", {})
                    sha = sync_opts.get("doc_sha", "shaR1")
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"content": sync_doc_b64(entries), "sha": sha}),
                )
            else:
                route.fulfill(status=404, content_type="application/json", body=json.dumps({"message": "Not Found"}))
            return
        # PUT / DELETE — record the write.
        calls.append({"method": method, "url": req.url, "body": json.loads(req.post_data) if req.post_data else None})
        if method == "PUT":
            if sync_opts.get("put_conflict_once") and not state["conflicted"]:
                state["conflicted"] = True
                route.fulfill(status=409, content_type="application/json", body=json.dumps({"message": "conflict"}))
                return
            route.fulfill(status=201, content_type="application/json", body=json.dumps({"content": {"sha": "shaP1"}}))
            return
        # DELETE
        route.fulfill(status=200, content_type="application/json", body=json.dumps({}))

    pg.route("**/api.github.com/repos/**/contents/.review-sync/**", review_sync_contents)


def _page(browser, calls, review_status, sync_opts=None, signed_in=True):
    ctx = browser.new_context()
    pg = ctx.new_page()
    _wire(pg, calls, review_status, sync_opts or {})
    pg.add_init_script(
        "localStorage.removeItem('sy_tree_cache__main');localStorage.removeItem('sy_review_status__main');"
    )
    if signed_in:
        pg.add_init_script(
            "localStorage.setItem('sy_gh_token', 'gho_e2e');"
            "localStorage.setItem('sy_gh_user',"
            f" JSON.stringify({{login: '{LOGIN}', avatar_url: 'icon.png'}}));"
        )
    pg.add_init_script(
        "window.__spa_auto_info_confirm = true;"
        "window.__opened = []; window.open = function(u){ window.__opened.push(u); };"
    )
    return ctx, pg


# --- helpers on the running page ------------------------------------------


def _open_review(pg, server):
    pg.goto(f"{server}{SPA_URL}#/review/{TALK_ID}")
    pg.wait_for_function("document.querySelectorAll('.cell.uk .cell-text').length > 0", timeout=10000)


def _wait_chip_synced(pg, timeout=10000):
    pg.wait_for_function(
        "() => {"
        "  const chip = document.getElementById('sync-chip');"
        "  const txt = document.getElementById('sync-chip-text');"
        f"  return chip && chip.style.display !== 'none' && txt && /{SYNCED_LABEL_RE}/.test(txt.textContent);"
        "}",
        timeout=timeout,
    )


def _edit_first_review_cell(pg, appended):
    cell = pg.locator(".cell.uk .cell-text").first
    cell.click()
    cell.press("End")
    cell.type(appended)
    cell.press("Tab")  # blur -> engine.flushSoon() (1.5s coalesce)


def _open_chip_dropdown(pg):
    """Click the chip button and wait until its dropdown is open and populated.

    The chip button ALWAYS toggles the dropdown in v2; items are plain <div>s
    appended when it opens.
    """
    pg.click("#sync-chip-btn")
    pg.wait_for_function(
        "() => { const dd = document.getElementById('sync-chip-dropdown');"
        " return dd && dd.classList.contains('open') && dd.children.length > 0; }",
        timeout=5000,
    )


def _click_dropdown_item(pg, label_re):
    """Open the dropdown and click the item whose text matches label_re."""
    import re

    _open_chip_dropdown(pg)
    pg.locator("#sync-chip-dropdown div", has_text=re.compile(label_re)).first.click()


def _review_sync_puts(calls):
    return [c for c in calls if c["method"] == "PUT" and "/contents/.review-sync/" in c["url"].split("?")[0]]


def _methods_urls(calls):
    return [(c["method"], c["url"].split("/repos/")[-1].split("?")[0]) for c in calls]


# ---------------------------------------------------------------------------
# 1. First edit bootstraps branch + state file + draft PR.
# ---------------------------------------------------------------------------


def test_first_edit_bootstraps_branch_state_and_draft_pr(server, browser):
    calls = []
    ctx, pg = _page(browser, calls, REVIEW_STATUS_UNASSIGNED, {"get_mode": "404"})
    _open_review(pg, server)

    _edit_first_review_cell(pg, " SYNCED123")
    _wait_chip_synced(pg)

    seq = _methods_urls(calls)
    assert ("POST", "sy-tools/sy-subtitles/git/refs") in seq
    assert ("POST", "sy-tools/sy-subtitles/pulls") in seq

    refs = next(c for c in calls if c["url"].endswith("/git/refs"))
    assert refs["body"]["ref"] == "refs/heads/" + SYNC_BRANCH

    puts = _review_sync_puts(calls)
    assert len(puts) == 1
    put = puts[0]
    assert put["url"].split("?")[0].endswith("/contents/" + STATE_PATH)
    assert put["body"]["branch"] == SYNC_BRANCH
    doc = decode_put_doc(put)
    assert REVIEW_KEY in doc["entries"]
    edits = doc["entries"][REVIEW_KEY]["edits"]
    assert any("SYNCED123" in str(v) for v in edits.values())

    # v2 also commits the real edited file to the sync branch so the draft PR
    # diff is human-readable (a PUT to transcript_uk.txt, not just the state).
    real_put = next(
        c
        for c in calls
        if c["method"] == "PUT" and f"/contents/talks/{TALK_ID}/transcript_uk.txt" in c["url"].split("?")[0]
    )
    assert real_put["body"]["branch"] == SYNC_BRANCH
    committed = base64.b64decode(real_put["body"]["content"]).decode("utf-8")
    assert "SYNCED123" in committed

    pull = next(c for c in calls if c["method"] == "POST" and c["url"].endswith("/pulls"))
    assert pull["body"]["draft"] is True
    assert pull["body"]["head"] == SYNC_BRANCH
    assert pull["body"]["base"] == "main"

    assert pg.locator("#sync-chip").is_visible()
    import re

    assert re.search(SYNCED_LABEL_RE, pg.locator("#sync-chip-text").text_content())
    ctx.close()


# ---------------------------------------------------------------------------
# 2. Cross-device pull adopts remote edits without pushing.
# ---------------------------------------------------------------------------


def test_cross_device_pull_adopts_remote_edits_without_push(server, browser):
    calls = []
    remote_entries = {REVIEW_KEY: review_entry({"0": "REMOTE TEXT"})}
    ctx, pg = _page(
        browser,
        calls,
        REVIEW_STATUS_UNASSIGNED,
        {"get_mode": "doc", "doc_entries": remote_entries, "doc_sha": "shaR1"},
    )
    _open_review(pg, server)

    # The remote edit lands in the first cell without any local edit.
    pg.wait_for_function(
        "() => { const c = document.querySelector('.cell.uk .cell-text');"
        " return c && c.innerText.includes('REMOTE TEXT'); }",
        timeout=10000,
    )

    # Settle: no debounce is armed (no local edit), so nothing may push.
    pg.wait_for_timeout(2500)
    assert not _review_sync_puts(calls), "clean local state must not push"
    assert not [c for c in calls if c["method"] == "POST" and c["url"].endswith("/pulls")]
    assert not [c for c in calls if c["url"].endswith("/git/refs")]
    ctx.close()


# ---------------------------------------------------------------------------
# 3. CAS 409 -> fetch, three-way merge, retry.
# ---------------------------------------------------------------------------


def test_cas_conflict_merges_and_retries(server, browser):
    calls = []
    # The concurrent writer touched a DIFFERENT index (1); our local edit is 0.
    conflict_entries = {REVIEW_KEY: review_entry({"1": "REMOTE_CAS"})}
    ctx, pg = _page(
        browser,
        calls,
        REVIEW_STATUS_UNASSIGNED,
        {
            "get_mode": "404",
            "put_conflict_once": True,
            "conflict_entries": conflict_entries,
            "conflict_sha": "shaRemote",
        },
    )
    _open_review(pg, server)

    _edit_first_review_cell(pg, " LOCAL_CAS")
    _wait_chip_synced(pg)

    puts = _review_sync_puts(calls)
    assert len(puts) == 2, "409 must be followed by a retry PUT"
    merged = decode_put_doc(puts[1])["entries"][REVIEW_KEY]["edits"]
    assert any("LOCAL_CAS" in str(v) for v in merged.values()), "local edit preserved"
    assert merged.get("1") == "REMOTE_CAS", "remote edit merged in"

    import re

    assert re.search(SYNCED_LABEL_RE, pg.locator("#sync-chip-text").text_content())
    ctx.close()


# ---------------------------------------------------------------------------
# 4. Signed in hides Copy-all; signed out shows it in marker mode.
# ---------------------------------------------------------------------------


def _open_preview_marker(pg, server):
    pg.goto(f"{server}{SPA_URL}#/preview/{TALK_ID}/{VIDEO_SLUG}")
    pg.wait_for_selector("#mock-player", state="visible", timeout=10000)


def test_signed_in_hides_copy_all_signed_out_shows(server, browser):
    ctx1, pg1 = _page(browser, [], REVIEW_STATUS_UNASSIGNED, {"get_mode": "404"}, signed_in=True)
    _open_preview_marker(pg1, server)
    pg1.evaluate("SPA.setPreviewMode('marker')")  # default is edit since #748
    # Signed in, the auto-sync chip replaces the manual affordances: Copy-all
    # and the issue button are hidden (data-gh-hide), and the removed one-button
    # PR control is not in the DOM at all.
    assert not pg1.locator("#btn-copy-all").is_visible()
    assert not pg1.locator("#btn-preview-issue").is_visible()
    assert pg1.locator("#btn-preview-pr").count() == 0
    ctx1.close()

    ctx2, pg2 = _page(browser, [], REVIEW_STATUS_UNASSIGNED, {"get_mode": "404"}, signed_in=False)
    _open_preview_marker(pg2, server)
    pg2.evaluate("SPA.setPreviewMode('marker')")  # opt into marker mode explicitly
    # In marker mode the signed-out Copy-all affordance shows.
    assert pg2.locator("#btn-copy-all").is_visible()
    # #btn-preview-pr never existed — absent regardless of auth state.
    assert pg2.locator("#btn-preview-pr").count() == 0
    ctx2.close()


# ---------------------------------------------------------------------------
# 5. Finalize (from the chip dropdown): delete state file, mark PR ready via
#    GraphQL. No re-commit, no new branch/PR.
# ---------------------------------------------------------------------------


def test_finalize_deletes_state_and_marks_ready(server, browser):
    calls = []
    local_edit = review_entry({"0": "LOCAL EDIT TEXT"})
    entries = {REVIEW_KEY: local_edit}
    ctx, pg = _page(
        browser,
        calls,
        REVIEW_STATUS_UNASSIGNED,
        {"get_mode": "doc", "doc_entries": entries, "doc_sha": "shaR1"},
    )
    # Seed an attached DRAFT sync PR + a matching local edit + matching remote
    # doc, all of which survive the reload. Nothing is dirty on open, so
    # finalize takes the no-flush path (no re-commit).
    base_meta = {
        "doc": entries,
        "sha": "shaR1",
        "revision": 1,
        "prNumber": PR_NUMBER,
        "prUrl": PR_URL,
        "nodeId": PR_NODE_ID,
        "prDraft": True,
        "fileShas": {},
        "branch": SYNC_BRANCH,
    }
    pg.add_init_script(
        f"localStorage.setItem({json.dumps(SYNC_BASE_KEY)}, {json.dumps(json.dumps(base_meta))});"
        f"localStorage.setItem({json.dumps(REVIEW_KEY)}, {json.dumps(json.dumps(local_edit))});"
    )
    _open_review(pg, server)

    # The attached PR surfaces as a synced chip; finalize lives in its dropdown.
    _wait_chip_synced(pg)
    _click_dropdown_item(pg, FINALIZE_LABEL_RE)
    # finalize resolves -> success dialog (auto-confirmed) -> window.open(prUrl).
    pg.wait_for_function("window.__opened.length > 0", timeout=10000)
    assert pg.evaluate("window.__opened[0]") == PR_URL

    # State file removed on the sync branch.
    delete = next(
        c for c in calls if c["method"] == "DELETE" and c["url"].split("?")[0].endswith("/contents/" + STATE_PATH)
    )
    assert delete["body"]["branch"] == SYNC_BRANCH

    # Draft flipped to ready via GraphQL, keyed on the PR node id.
    graphql = next(c for c in calls if c["method"] == "POST" and c["url"].endswith("/graphql"))
    assert "markPullRequestReadyForReview" in graphql["body"]["query"]
    assert graphql["body"]["variables"]["id"] == PR_NODE_ID

    # No re-commit of the real file, no second branch, no second PR.
    assert not [
        c
        for c in calls
        if c["method"] == "PUT" and f"/contents/talks/{TALK_ID}/transcript_uk.txt" in c["url"].split("?")[0]
    ]
    assert not [c for c in calls if c["method"] == "POST" and c["url"].endswith("/git/refs")]
    assert not [c for c in calls if c["method"] == "POST" and c["url"].endswith("/pulls")]

    # Chip now shows the ready ("In review") state.
    import re

    pg.wait_for_function(
        "() => { const txt = document.getElementById('sync-chip-text');"
        f"  return txt && /{READY_LABEL_RE}/.test(txt.textContent); }}",
        timeout=10000,
    )
    assert re.search(READY_LABEL_RE, pg.locator("#sync-chip-text").text_content())
    ctx.close()


# ---------------------------------------------------------------------------
# 6. Edit after finalize re-drafts the PR (GraphQL) and re-pushes state.
# ---------------------------------------------------------------------------


def test_edit_after_finalize_redrafts(server, browser):
    calls = []
    # Seed an attached READY (non-draft) PR with no cached state (sha null) and
    # a clean local store; the remote state file is 404 (finalize removed it).
    ctx, pg = _page(browser, calls, REVIEW_STATUS_UNASSIGNED, {"get_mode": "404"})
    base_meta = {
        "doc": {},
        "sha": None,
        "revision": 1,
        "prNumber": PR_NUMBER,
        "prUrl": PR_URL,
        "nodeId": PR_NODE_ID,
        "prDraft": False,
        "fileShas": {},
        "branch": SYNC_BRANCH,
    }
    pg.add_init_script(f"localStorage.setItem({json.dumps(SYNC_BASE_KEY)}, {json.dumps(json.dumps(base_meta))});")
    _open_review(pg, server)

    # Attach surfaces the ready PR as the 'ready' chip state.
    pg.wait_for_function(
        "() => { const chip = document.getElementById('sync-chip');"
        "  const txt = document.getElementById('sync-chip-text');"
        f"  return chip && chip.style.display !== 'none' && txt && /{READY_LABEL_RE}/.test(txt.textContent); }}",
        timeout=10000,
    )

    # A fresh edit must silently re-draft the PR and re-create the state file.
    _edit_first_review_cell(pg, " AFTER_FINAL")
    _wait_chip_synced(pg)

    graphql = next(c for c in calls if c["method"] == "POST" and c["url"].endswith("/graphql"))
    assert "convertPullRequestToDraft" in graphql["body"]["query"]
    assert graphql["body"]["variables"]["id"] == PR_NODE_ID

    puts = _review_sync_puts(calls)
    assert puts, "the re-drafted PR must get a fresh state-file PUT"
    assert decode_put_doc(puts[-1])["entries"][REVIEW_KEY]["edits"]

    # No new branch/PR — the finalized PR is reused.
    assert not [c for c in calls if c["method"] == "POST" and c["url"].endswith("/git/refs")]
    assert not [c for c in calls if c["method"] == "POST" and c["url"].endswith("/pulls")]
    ctx.close()


# ---------------------------------------------------------------------------
# 7. The sync chip's dropdown opens the PR url.
# ---------------------------------------------------------------------------


def test_sync_chip_dropdown_opens_pr(server, browser):
    calls = []
    ctx, pg = _page(browser, calls, REVIEW_STATUS_UNASSIGNED, {"get_mode": "404"})
    _open_review(pg, server)

    _edit_first_review_cell(pg, " SYNCED123")
    _wait_chip_synced(pg)

    _click_dropdown_item(pg, OPEN_PR_LABEL_RE)
    pg.wait_for_function("window.__opened.length > 0", timeout=5000)
    assert pg.evaluate("window.__opened[0]") == PR_URL
    ctx.close()


# ---------------------------------------------------------------------------
# 8. A PREVIEW subtitle edit syncs to the VIDEO-scoped target (its own branch,
#    state file and PR), distinct from the transcript target — proving v3's
#    file-scoped PRs. The edit lands in the canonical block store and the
#    committed real file is final/uk.srt.
# ---------------------------------------------------------------------------


def _transcript_puts(calls):
    return [
        c
        for c in calls
        if c["method"] == "PUT" and f"/contents/talks/{TALK_ID}/transcript_uk.txt" in c["url"].split("?")[0]
    ]


def test_reverting_the_last_edit_tears_down_the_pr(server, browser):
    """ "No edits = no PR": reverting the last edit closes the sync PR, deletes
    its branch and hides the chip — instead of committing an empty file."""
    calls = []
    ctx, pg = _page(browser, calls, REVIEW_STATUS_UNASSIGNED, {"get_mode": "404"})
    _open_review(pg, server)

    _edit_first_review_cell(pg, " SYNCED123")
    _wait_chip_synced(pg)
    assert _transcript_puts(calls), "the edit must have committed the transcript"

    # Revert the only edit via the real handler (no forced flush): it must sync
    # on the fast 1.5s cadence (syncRevertSoon -> flushSoon) and, being empty,
    # tear the PR down.
    pg.evaluate("SPA.revertEdit(0)")

    def _closed_pull():
        return [
            c
            for c in calls
            if c["method"] == "PATCH" and "/pulls/" in c["url"] and (c["body"] or {}).get("state") == "closed"
        ]

    def _deleted_branch():
        return [c for c in calls if c["method"] == "DELETE" and f"/git/refs/heads/{SYNC_BRANCH}" in c["url"]]

    for _ in range(60):
        if _closed_pull() and _deleted_branch():
            break
        pg.wait_for_timeout(100)

    assert _closed_pull(), "revert-all must close the sync PR"
    assert _deleted_branch(), "revert-all must delete the sync branch"
    assert _closed_pull()[-1]["url"].split("?")[0].endswith(f"/pulls/{PR_NUMBER}")
    pg.wait_for_selector("#sync-chip", state="hidden", timeout=5000)
    ctx.close()


def test_preview_edit_syncs_to_video_scoped_target(server, browser):
    calls = []
    ctx, pg = _page(browser, calls, REVIEW_STATUS_UNASSIGNED, {"get_mode": "404"})
    pg.goto(f"{server}{SPA_URL}#/preview/{TALK_ID}/{VIDEO_SLUG}")
    pg.wait_for_selector("#mock-player", state="visible", timeout=10000)
    pg.wait_for_function(
        "() => window.previewState && (window.previewState.subtitles || []).length > 0",
        timeout=10000,
    )

    # Enter edit mode, position inside block 1 (1-5s) and add an edit.
    pg.evaluate("SPA.setPreviewMode('edit')")
    pg.evaluate("window._vimeoPlayer._currentTime = 3; window.previewState.currentTime = 3;")
    pg.evaluate("SPA.addEdit()")
    cell = pg.locator(".edit-item .edited").first
    cell.click()
    cell.press("End")
    cell.type(" PREVIEWSYNC")
    cell.press("Tab")  # blur -> flushSoon

    _wait_chip_synced(pg)

    video_target = f"{VIDEO_SLUG}-uk"
    video_branch = f"sync/{LOGIN}/{TALK_ID}--{video_target}"
    video_state = f".review-sync/{TALK_ID}/{video_target}.json"
    canon_key = f"srt_edits_{TALK_ID}_{VIDEO_SLUG}_uk"

    # The state PUT went to the VIDEO target's own path + branch — NOT the
    # transcript target used by the review tests above.
    put = next(c for c in _review_sync_puts(calls) if c["url"].split("?")[0].endswith("/contents/" + video_state))
    assert put["body"]["branch"] == video_branch
    doc = decode_put_doc(put)
    assert canon_key in doc["entries"], "edit stored in the canonical block map"
    assert any("PREVIEWSYNC" in str(v) for v in doc["entries"][canon_key].values())

    # A branch ref was created for the video target specifically.
    refs = next(c for c in calls if c["url"].endswith("/git/refs"))
    assert refs["body"]["ref"] == "refs/heads/" + video_branch

    # The real committed file is the video's final/uk.srt with the edit applied.
    real = next(
        c
        for c in calls
        if c["method"] == "PUT" and f"/contents/talks/{TALK_ID}/{VIDEO_SLUG}/final/uk.srt" in c["url"].split("?")[0]
    )
    assert real["body"]["branch"] == video_branch
    committed = base64.b64decode(real["body"]["content"]).decode("utf-8")
    assert "PREVIEWSYNC" in committed
    ctx.close()


# ---------------------------------------------------------------------------
# 9. Signed-in preview markers auto-sync to a GitHub issue (create + teardown).
# ---------------------------------------------------------------------------


def test_signed_in_marker_creates_issue_then_closes_when_emptied(server, browser):
    calls = []
    ctx, pg = _page(browser, calls, REVIEW_STATUS_UNASSIGNED, {"get_mode": "404"}, signed_in=True)
    _open_preview_marker(pg, server)
    pg.evaluate("SPA.setPreviewMode('marker')")  # default is edit since #748
    pg.wait_for_function("() => window.markerSync", timeout=10000)

    # Add a marker -> creates the markers issue on the fast cadence.
    pg.evaluate("window.previewState.currentTime = 3; window.previewState.lastText = 'Sub one';")
    pg.evaluate("SPA.addMarker()")

    def _created():
        return [c for c in calls if c["method"] == "POST" and c["url"].split("?")[0].endswith("/issues")]

    for _ in range(60):
        if _created():
            break
        pg.wait_for_timeout(100)
    created = _created()
    assert created, "adding a marker must create the markers issue"
    body = created[-1]["body"]
    assert body["title"] == f"Markers: {TALK_ID} / {VIDEO_SLUG}"
    assert body["labels"] == ["markers"]
    assert "<!-- sy-markers:" in body["body"], "issue body must carry the structured block"
    pg.wait_for_selector("#marker-chip", state="visible", timeout=5000)
    number = pg.evaluate("window.markerSync.getInfo().issueNumber")

    # Remove the only marker -> teardown closes the same issue.
    pg.evaluate("SPA.removeMarker(0)")

    def _closed():
        return [
            c
            for c in calls
            if c["method"] == "PATCH"
            and c["url"].split("?")[0].endswith(f"/issues/{number}")
            and (c["body"] or {}).get("state") == "closed"
        ]

    for _ in range(60):
        if _closed():
            break
        pg.wait_for_timeout(100)
    assert _closed(), "emptying the markers must close the issue"
    pg.wait_for_selector("#marker-chip", state="hidden", timeout=5000)
    ctx.close()


# ---------------------------------------------------------------------------
# 10. Preview chip hygiene: one chip per mode, and marker actions never touch
#     the edit engine (regressions the user reported live).
# ---------------------------------------------------------------------------


def test_marker_action_does_not_dirty_the_edit_engine(server, browser):
    # Bug 2: savePreviewState no longer nudges editSync, so a marker add must not
    # mark the edit engine dirty (which would flash a spurious edit chip / draft
    # an edit PR with no edits).
    calls = []
    ctx, pg = _page(browser, calls, REVIEW_STATUS_UNASSIGNED, {"get_mode": "404"}, signed_in=True)
    _open_preview_marker(pg, server)
    pg.evaluate("SPA.setPreviewMode('marker')")
    pg.wait_for_function("() => window.markerSync", timeout=10000)
    # editSync attaches for the preview SRT target regardless of mode.
    pg.wait_for_function("() => window.editSync", timeout=10000)

    pg.evaluate("window.previewState.currentTime = 3; window.previewState.lastText = 'Sub one';")
    pg.evaluate("SPA.addMarker()")
    pg.wait_for_timeout(300)

    assert pg.evaluate("() => window.editSync.getInfo().dirty") is False, (
        "a marker action must not dirty the edit engine (Bug 2)"
    )
    assert not pg.locator("#sync-chip").is_visible(), "the edit chip must not appear for a marker action"
    ctx.close()


def test_edit_chip_is_hidden_in_marker_mode(server, browser):
    # Bug 1: the edit sync chip and the marker chip must not stack. In marker mode
    # the edit chip is suppressed even with pending edits; it returns in edit mode.
    calls = []
    ctx, pg = _page(browser, calls, REVIEW_STATUS_UNASSIGNED, {"get_mode": "404"}, signed_in=True)
    pg.goto(f"{server}{SPA_URL}#/preview/{TALK_ID}/{VIDEO_SLUG}")
    pg.wait_for_selector("#mock-player", state="visible", timeout=10000)
    pg.wait_for_function(
        "() => window.previewState && (window.previewState.subtitles || []).length > 0",
        timeout=10000,
    )

    # Make a real edit so the edit engine has a live chip.
    pg.evaluate("SPA.setPreviewMode('edit')")
    pg.evaluate("window._vimeoPlayer._currentTime = 3; window.previewState.currentTime = 3;")
    pg.evaluate("SPA.addEdit()")
    cell = pg.locator(".edit-item .edited").first
    cell.click()
    cell.press("End")
    cell.type(" X")
    cell.press("Tab")  # blur -> flushSoon
    pg.wait_for_selector("#sync-chip", state="visible", timeout=5000)

    # Switch to marker mode -> the edit chip hides (one chip per mode).
    pg.evaluate("SPA.setPreviewMode('marker')")
    pg.wait_for_selector("#sync-chip", state="hidden", timeout=5000)

    # Back to edit mode -> the edit chip returns.
    pg.evaluate("SPA.setPreviewMode('edit')")
    pg.wait_for_selector("#sync-chip", state="visible", timeout=5000)
    ctx.close()


def test_cloud_chip_dom_contract(server, browser):
    # The status chip is one elegant cloud with three tones: blue progress
    # (pending folds in), green ok (ready folds in), red error. The state word
    # stays in the DOM as an sr-only accessible name (present but not shown).
    calls = []
    ctx, pg = _page(browser, calls, REVIEW_STATUS_UNASSIGNED, {"get_mode": "404"}, signed_in=True)
    pg.goto(f"{server}{SPA_URL}#/review/{TALK_ID}")
    pg.wait_for_function("() => typeof paintSyncChip === 'function'", timeout=10000)

    # Drive each status synchronously so an async engine re-render can't race us.
    result = pg.evaluate(
        """() => {
          const icon = document.getElementById('sync-chip-icon');
          const chip = document.getElementById('sync-chip');
          const txt = document.getElementById('sync-chip-text');
          const snap = (status) => {
            paintSyncChip('sync', status);
            return {
              cls: icon.className,
              svg: !!icon.querySelector('svg'),
              display: chip.style.display,
              label: txt.textContent,
              textW: txt.getBoundingClientRect().width,
            };
          };
          return { syncing: snap('syncing'), pending: snap('pending'),
                   synced: snap('synced'), ready: snap('ready'),
                   error: snap('error'), idle: snap('idle') };
        }"""
    )
    # The tone lives on the reusable .sync-cloud component (icon), not the button,
    # so styleguide.html can render the same component. pending folds into the
    # progress tone (no waiting glyph); ready folds into ok.
    for st in ("syncing", "pending"):
        assert "sync-cloud--progress" in result[st]["cls"], st
        assert result[st]["display"] != "none", st
    for st in ("synced", "ready"):
        assert "sync-cloud--ok" in result[st]["cls"], st
    assert "sync-cloud--error" in result["error"]["cls"]
    # A cloud svg is always painted for a visible tone.
    assert result["synced"]["svg"] is True
    # The label is present (accessible name) but visually hidden (sr-only).
    assert result["synced"]["label"]
    assert result["synced"]["textW"] < 2
    # idle hides the whole chip.
    assert result["idle"]["display"] == "none"
    ctx.close()
