# Testing Guide

How the test suite is organised and how to run the parts you need. The
project is **test-first** (see `CLAUDE.md` → Development) — every behaviour
change starts with a failing test.

## Layout

| Suite | Runner | Files | What it covers |
|-------|--------|-------|----------------|
| Python | `pytest` | `tests/test_*.py` | `tools/*` — pipeline logic, validation, sync, build |
| JavaScript | `node --test` | `tests/test_*.js` | `site/js/*` — SPA parsing/state, XSS guards, bookmarklet |

Shared Python fixtures live in `tests/conftest.py`; data fixtures in
`tests/fixtures/` (sample SRT/whisper/transcripts, parsed-HTML vectors,
`pipeline_snapshots/`).

## Running

```bash
# Everything (Python, parallel)
pytest tests/ -n auto

# JavaScript
node --test tests/test_*.js

# A single file / test
pytest tests/test_optimize.py
pytest tests/test_offset_srt.py -k detect
```

### Markers (run subsets)

Markers are registered in `pyproject.toml`. The big lever is `e2e`, which
tags the Playwright/browser tests (~410 of them):

```bash
# Fast lane — skip browser E2E (no chromium needed)
pytest tests/ -n auto -m "not e2e"

# Only the browser E2E
pytest tests/ -n auto -m e2e

# Boot smoke — the ~2s gate that proves the SPA actually boots+renders+styles
pytest -m smoke
```

| Marker | Meaning |
|--------|---------|
| `e2e` | Browser/Playwright tests — slow, need `playwright install chromium`. |
| `smoke` | Fast boot smoke (`tests/test_spa_boot_smoke.py`) — also tagged `e2e`. See below. |
| `integration` | Multi-component / subprocess tests (e.g. dry-run matrix). |
| `golden` | Regression over shipped talk corpora. |
| `slow` | Wall-clock heavy (>1s). |
| `flaky` | Retried via `pytest-rerunfailures` (browser timing under `-n auto`). |

### Boot smoke — "green tests" must mean "the site works"

The unit lanes (`node --test`, `pytest -m "not e2e"`) only grep strings out of
`index.html` / `*.js` / `*.css`; the ~320 render-level e2e tests are skipped by the
fast lane. So a change can leave the SPA a **blank page** (boot throws, or an
unlinked/404 stylesheet) while every test a developer runs still passes — this
actually happened during the CSS-externalization work.

`tests/test_spa_boot_smoke.py` closes that gap: it loads the app the way it runs
(mocked GitHub, empty repo tree — deterministic, offline) and asserts it **boots**
(index view renders), is **styled** (the stylesheet applied), and threw **nothing**
uncaught. It is tagged both `e2e` (so `-m "not e2e"` stays chromium-free) and
`smoke` (so `pytest -m smoke` is a ~2s gate). **Run `pytest -m smoke` for any
change under `site/` — and actually open the page** (`?repo=owner/name` off
GitHub Pages, e.g. `localhost:8000/?repo=sy-tools/sy-subtitles`); a green unit
suite alone does not prove the app renders. Open it with
`python -m tools.serve_auth_local`, never a bare `http.server`: only the former
injects the auth hooks, and only port 8000 can complete a sign-in (see
CLAUDE.md "Local Setup").

### Golden corpus

```bash
# Curated set (CI default)
pytest tests/test_golden_talks.py
# Full corpus (has known-broken xfails — see KNOWN_BROKEN_VALIDATION)
GOLDEN_TALKS_SCOPE=all pytest tests/test_golden_talks.py
```

### Property-based tests (Hypothesis)

`tests/test_property_invariants.py` proves invariants that must hold for *any*
input (no overlaps, text preservation, monotonic timing, idempotent
`optimize()`, …). These catch the failure modes that only surface at playback.

### Coverage

```bash
pytest tests/ -n auto --cov=tools --cov-report=term-missing
```

CI runs the same flags **report-only** (no enforced floor yet); the trend
shows in the `test` job log. JS coverage is not wired up yet (Node's
`--experimental-test-coverage` is the intended path).

## Determinism

`tests/test_sync_player_integration.py` hits the **real** Vimeo SDK. It runs
by default (including in CI — Vimeo is stable, and the class retries twice to
absorb a transient blip). Opt out in offline/restricted environments with:

```bash
SY_E2E_REAL_VIMEO=0 pytest tests/test_sync_player_integration.py
```

Every other test runs against mocked fixtures (GitHub API, meta.yaml, SRTs)
and makes no outbound calls.

## Dry-run snapshots

`tests/test_dryrun_matrix.py` replays the full pipeline against canned LLM
responses in `tests/fixtures/pipeline_snapshots/`, then `tools.verify_snapshot`
checks the output (text preservation, block-count tolerance, CPS, validation).

### Re-timing after a segmentation change

`work/timecodes.txt` is the builder agent's answer for **one specific cut** of
the transcript into blocks. Change how that cut is made — a new sentence
boundary in `tools/text_segmentation.py`, a newly declared remark in
`glossary/subtitle_omit.yaml` — and the ids stop lining up: `build_map
assemble` drops every block without a timecode and the replay fails text
preservation. Carry the recorded timings over to the new cut:

```bash
python -m tools.retime_snapshot \
  --snapshot tests/fixtures/pipeline_snapshots/TALK/VIDEO \
  --whisper  talks/TALK/VIDEO/source/whisper.json
```

Unchanged blocks keep their recorded span; a block that became several splits
its span at the widest **real whisper pauses** inside it (never at a character
ratio — a span with no usable pause is split evenly and reported as a
`WARNING`); a block whose text is no longer shipped is dropped. `--check`
reports the drift and exits non-zero without writing.

After re-timing, refresh `expected/final_uk.srt` and `manifest.baseline` by
replaying the matrix — they are reference artefacts, not inputs.

> ⚠️ **Known gap:** the *original* generator `tools/bootstrap_snapshot.py` was
> removed in `c72e1b53` ("drop uk.map … legacy cleanup"). `retime_snapshot`
> covers segmentation changes; creating a snapshot for a **new** talk from
> scratch still has no tool.
