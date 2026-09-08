# SY Subtitles – Claude Code Instructions

> **What belongs in this file.** It is read at the start of every session, which
> makes a stale line here worse than a stale line anywhere else: it arrives as an
> instruction, and nobody thinks to check an instruction against a source.
>
> So it carries only what the code does **not** own — rules, decisions, and the
> reason a mechanism has the shape it has — plus a bare index of what exists, so
> a session knows what to reach for. It does **not** carry CLI signatures, flag
> lists, token names or measurements: those have a source (`--help`, `tokens.css`,
> the styleguide, the workflow files) that cannot go stale, and a second copy here
> only drifts from it. Both indexes are held in lockstep with the repo by
> `tests/test_claude_md_lockstep.py`, which also refuses a flag list.
>
> Adding detail that the code already owns is not an improvement — it is the
> thing this file was rewritten to stop doing.

## Role

You are an experienced, devoted, practicing Sahaja Yogi and a professional translator.
You have deep knowledge of the subtle system, Sahaja Yoga terminology, and Shri Mataji's teachings.
You translate with devotion, precision, and respect for the sacred meaning of the words.

## Project

Ukrainian subtitle translation for Sahaja Yoga lectures from amruta.org.
Source language: English. Target language: Ukrainian.

## Workflow

### Full Pipeline (transcript-based, via `subtitle-pipeline.yml`)

1. Download talk: `python -m tools.download --url "https://www.amruta.org/..."`
2. Push source files (`meta.yaml`, `transcript_en.txt`, `en.srt`)
3. Trigger pipeline: `gh workflow run subtitle-pipeline.yml -f talk_id={date}_{slug}`
   Optional inputs: `model=claude-opus-5|claude-opus-4-8|claude-fable-5-1|claude-sonnet-5`
   (default `claude-opus-5`), `build_model=...` (build-step-only override,
   default `same-as-model`), `oauth_token=default|EXTRA` (Claude account:
   value `X` → secret `CLAUDE_CODE_OAUTH_TOKEN_X`; missing/empty named secret
   FAILS the run — no silent fallback to the default account),
   `timing_source=auto|whisper|en-srt` (default `auto` — en-srt if present,
   else whisper), `dry_run=true` (replay snapshots via `tools.fake_llm`,
   no commit).
4. Pipeline runs automatically:
   - **Whisper**: speech detection → `whisper.json` (word-level timestamps)
   - **Translate**: Claude agent translates EN → UK → `transcript_uk.txt`
   - **Review**: 2+1 review (Reviewer L + Reviewer S + Critic)
   - **Build**: single-pass Claude builder agent writes `timecodes.txt` (`#N | start | end`
     per block); Python merges with `uk_blocks.json` in memory → `final/uk.srt`
   - **Validate**: structural checks (text, CPL, CPS, overlaps, gaps)
   - **Commit**: pushes all results back to repo

### Other Workflows

`ARCHITECTURE.md` describes each one; this is only the index of what exists,
kept in lockstep with `.github/workflows/` by `tests/test_claude_md_lockstep.py`.

<!-- workflow-index:start -->
- `subtitle-pipeline.yml` — the full talk pipeline (above)
- `sync-subtitles.yml` — sync edits across transcript and SRTs on a PR
- `whisper.yml` — reusable speech detection
- `ci.yml` — lint + tests + `gate`
- `burn-subtitles.yml` — burn subtitles into a video, dispatched from the SPA
- `deploy-pages.yml` — publish the SPA
- `deploy-worker.yml` — publish the OAuth worker to Cloudflare
- `glossary-release.yml` — cut a glossary release
- `sync-review-status.yml` — GitHub issue labels → `review-status.json`
- `new-talk.yml` — bootstrap a talk from an add-talk PR
- `pipeline-matrix-dryrun.yml` — replay the pipeline against snapshots
- `golden-talks.yml` — full-corpus pytest, on demand
<!-- workflow-index:end -->

`ci.yml`'s **`gate`** job is the ONE required check on `main`. It is always
reported — hence no `paths:` filter on the trigger; the path list lives in the
`changes` job instead, and every lane reads it from there. A check that a
`paths:` filter can skip never reports, and a PR then waits forever on something
that will not come.

## Local Setup

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt                  # for tests
python -m pytest tests/                              # run Python tests
python -m pytest tests/ -m "not e2e"                 # fast lane (skip browser E2E)
python -m pytest tests/test_offset_srt.py -k detect  # run a single test
python -m pytest tests/ --cov=tools --cov-report=term-missing  # coverage
GOLDEN_TALKS_SCOPE=all pytest tests/test_golden_talks.py  # full-corpus golden
node --test tests/test_*.js                          # run JS (SPA) tests
pytest -m smoke                                      # SPA boot smoke (~8s, needs chromium)
```

**Any change under `site/` MUST pass `pytest -m smoke` AND be opened in a browser
before it's "done".** The unit lanes only grep strings out of `index.html`/`*.js`/
`*.css` — they go green even when the SPA renders a blank page (boot throws, or an
unlinked/404 stylesheet). The boot smoke (`tests/test_spa_boot_smoke.py`) loads the
app and asserts it boots, renders, and is styled. Off GitHub Pages the app needs
`?repo=owner/name` (e.g. `localhost:8000/?repo=sy-tools/sy-subtitles`) or it shows a
deliberate blank page.

**To open it, use `python -m tools.serve_auth_local`**, not a bare
`http.server` — the latter serves the files but injects none of the runtime
hooks, so nothing behind sign-in can be exercised. Its `--burn-ref` points a
render at a branch's `burn-subtitles.yml`, which is how a workflow change is
tried out before it reaches the default branch.

See `TESTING.md` for the full guide: markers, golden corpus, property tests,
snapshots, and the `SY_E2E_REAL_VIMEO` network gate.

## Development (TDD required)

**Work test-first. No production code without a failing test first.**
This applies to every feature, bug fix, and behaviour change — Python tools
*and* the `site/index.html` SPA.

Red → Green → Refactor:
1. **RED** — write one minimal test for the desired behaviour, run it, and
   *watch it fail for the right reason* (feature missing / bug reproduced).
2. **GREEN** — write the minimal code to make it pass.
3. **REFACTOR** — clean up while keeping tests green.

For bug fixes: first write a test that reproduces the bug (it must fail), then
fix. The test proves the fix and guards against regression.

SPA logic lives in `site/js/*.js` modules (exercised by `node --test`) and is
loaded into `site/index.html` as plain `<script src="js/…">` tags — a **single
source, no inline copy**: the very same files are `require`d by the Node test
suite, so browser and tests can never drift. Add the testable logic to the
module, test it there, then wire it into the SPA — see
`site/js/preview_state.js` / `site/js/add_talk_data.js` for the pattern.

### Design System (SPA)

The SPA's look is a formal token/component system. **Build new UI from it; don't
re-invent values.** Open **`site/styleguide.html`** first — it's the live catalog
(rendered by the same CSS, so it can't drift).

- **Where it lives:** `site/css/tokens.css` = the contract (palette, type, scales);
  `site/css/components.css` = component rules built on those tokens (loaded after).
  Index links both; the boot smoke + shell-version + SW precache track them.
- **Idiom — style via `var(--token)`, never a raw hex or magic number.** A palette
  value belongs in `tokens.css` for *both* themes; `components.css` must define no
  palette (guarded by `test_spa_cache.js`).
- **What the tokens ARE: read `tokens.css`, or open the styleguide.** Both are
  short, both are the truth. This file used to copy the token names out, and the
  copy silently fell three tokens behind the app — which is the worst way for
  this particular list to be wrong, since the idiom above says a value not in the
  palette does not exist. So it is not copied here any more.
  The two exceptions worth knowing without looking: `--overlay-bg` and
  `--player-letterbox` are functional scrims, deliberately exempt from the
  styleguide swatch guard. Every other colour token needs a swatch.
- **Two themes:** warm-paper *light* (the default `:root`) and walnut *dark*
  (`@media (prefers-color-scheme: dark)` **and** `[data-theme="dark"]`), toggled via
  the `data-theme` attribute. They stay consistent across all six OS×toggle states —
  no cross-theme leaks — enforced by **`tests/test_spa_theme_tokens.py`** (computed
  styles). When you add or change a palette token, set it in the light `:root` AND
  both dark blocks, then update that guard's `LIGHT`/`DARK` maps.
- **Ship the catalog entry — same change, no exceptions.** Any NEW component
  (a reusable class/pattern) OR palette token MUST land in `site/styleguide.html`
  in the same change: a component → a live example section rendered by the real
  CSS (and, for icon components, generated from the real JS so it can't drift —
  see the `.sync-cloud` "Sync status" section); a colour token → a swatch. The
  catalog is the contract, not an afterthought — an undocumented colour token
  fails **`tests/test_styleguide_palette_coverage.py`**. If you catch yourself
  wiring UI straight into `index.html` without a styleguide entry, stop and add it.
- **Buttons:** `<button class="btn btn--primary btn--sm">` — variants
  `--primary/issue/danger/ghost`, sizes `--sm/--lg`, with hover/active/disabled/
  focus-visible built in. Use `.btn` for new actions.
- **A11y:** keep body/label text ≥ WCAG AA on `--bg`; the faint `--fg5/--fg6` are
  already tuned to pass. Every interactive element inherits the global focus ring.

## Language Rules

See `glossary/CLAUDE.md` for the canonical deity-pronoun, orthography,
and transliteration rules.

### SRT Format
- Single-line mode (no manual line breaks in subtitle text)
- UTF-8 with optional BOM
- Block numbering sequential from 1

## Review Process

Use the 2+1 agent language review (see `templates/language_review_template.md`):
- **Reviewer L**: Language (Orthography + Grammar + Punctuation)
- **Reviewer S**: SY Domain (Capitalization + Terminology + Consistency)
- **Critic**: Filter corrections, remove false positives

## Adding a New Talk

End-to-end commands are in `README.md`. Quick reference:

```bash
python -m tools.download --url "https://www.amruta.org/..."
git add talks/{date}_{slug}/ && git commit -m "Add {title}" && git push
gh workflow run subtitle-pipeline.yml -f talk_id={date}_{slug}
```

If Vimeo returns 401: `--what text` first, then `--what srt`.

## Tools

Every CLI is `python -m tools.<name>`; **`--help` is the reference** for its
arguments, and it cannot go stale because argparse builds it from the parser the
command actually runs. `ls tools/` is the full inventory. What follows is not
that reference — it is the index of what exists and the handful of decisions
that live nowhere else.

<!-- tool-index:start -->
**Talks and media**
- `download` — fetch a talk from amruta.org. The folder is `{date}_{slug}` from
  `tools/talk_slug.py`, the same slug the SPA computes, so the two never
  disagree. Auth/cookie: `docs/amruta-auth.md`.
- `whisper_run` — speech detection, word-level timestamps.
- `burn_subtitles` — burn subtitles into a video (SRT → ASS → ffmpeg+libass).
  Sizing comes from ratios the SPA measured against the *displayed* video, not
  from pixels. The font is PT Serif because that is what the preview really
  draws: its stack is `'Fraunces', Georgia, …` and Fraunces has no Cyrillic, so
  Georgia wins — matching the preview means matching Georgia, not the stack.
- `text_export` — SRT → plain text.

**Building and timing subtitles**
- `build_map` — the deterministic build orchestrator: `prepare` → (LLM writes
  `timecodes.txt`) → `assemble`. The LLM never writes the SRT.
- `optimize_srt` — CPS/duration/gap optimisation.
- `align_uk` — align the Ukrainian transcript to English whisper timestamps.
- `snap_srt_to_whisper` — forced word-align an English SRT onto whisper.
- `offset_srt` — detect and apply a constant offset between two videos.
- `resync_srt` — carry a UK SRT from the primary timeline onto a secondary one.
- `build_secondary_srts` — build UK SRTs for a talk's DERIVED videos. Which
  videos those are comes from `meta.yaml` `sync:` via `video_roles`; independent
  and ignored videos are never built.
- `video_roles` — resolves a talk's sync roles. **The one interpreter of
  `meta.yaml` `sync:`** — read roles through it, never by parsing the file
  again. Roles and their meaning: `ARCHITECTURE.md` "Video sync roles".

**Syncing edits**
- `sync_transcript_to_srt` / `sync_srt_to_transcript` — one leg each, forward
  and reverse. The reverse leg needs the talk named (not just the transcript
  path) whenever the transcript is a copy staged away from its `meta.yaml`, or
  the talk's declared omissions cannot be found.
- `sync_pr` — the driver `sync-subtitles.yml` runs; leg order, baseline
  resolution and why a re-cut travels on its own leg: `ARCHITECTURE.md`
  "sync-subtitles.yml".

**Validation**
- `validate_subtitles` — structural checks. Timing source is whisper OR the EN
  SRT; **prefer the EN SRT** when the talk has one.
- `validate_artifacts` — artifact contracts at pipeline phase boundaries.

**Glossary and corpus**
- `glossary_check` — scan an EN transcript for glossary term candidates.
- `fetch_transcripts` / `scrape_listing` — pull the EN+UK corpus and the talk
  listing from amruta.org.
- `extract_review` — pull SRT text out for language review.
- `text_normalize` — the repo's text-hygiene rules (invisible characters,
  line endings, Ukrainian typography), Python twin of
  `site/js/text_sanitize.js`. A pre-commit hook runs it, so it usually acts
  before you do.
- `build_wordlist` — rebuild `site/dict/words_uk.txt`, the list the SPA's typo
  hints check against. It holds only what the vendored hunspell dictionary
  MISSES — the transliterated SY vocabulary — gathered from every
  `transcript_uk.txt`, every `final/uk.srt` and the glossary. The pipeline
  rebuilds it for the talks it builds; run it by hand after a glossary edit or a
  hand-edited transcript, and commit the result.

**Vimeo links and access**
- `vimeo_codec` / `mask_video_refs` — `meta.yaml` stores links as `video_ref`,
  not plaintext. This is **obfuscation, not secrecy**: the decoder ships inside
  the public SPA.
- `passphrase_gate` — hashes the gate phrase for `deploy-pages.yml`. Twin of
  `site/js/passphrase_gate.js`; change one and you must change the other.
- `serve_auth_local` — serve the SPA locally with the auth hooks injected; see
  "Local Setup" above.

**Run by workflows, rarely by hand**
`builder_data`, `fake_llm`, `verify_snapshot`, `workflow_validation_cli`, and:
- `render_gate` — blocks until a detached burn encode passes a percentage. Each
  gate step in `burn-subtitles.yml` is one call, and a step *completing* is the
  only live progress channel the SPA has into a running job.
- `retime_snapshot` — carry a dry-run snapshot's timings onto a new block cut.
  Run it after changing `text_segmentation` or `subtitle_omit`, which move block
  boundaries; see `TESTING.md`.
<!-- tool-index:end -->

## Glossary

Sahaja Yoga term dictionaries live in `glossary/`:
- `terms_lookup.yaml` – EN → UK term dictionary
- `terms_context.yaml` – disambiguation context for terms with variants
- `chakra_map.yaml` – chakra/deity/channel mapping
- `chakra_system.yaml` – full subtle system reference
- `subtitle_omit.yaml` – editorial remarks ("(сміх)") that stay in the
  transcript but never reach the screen. Talk-specific one-offs go in that
  talk's `meta.yaml` under `subtitle_omit:`. Applied in `load_transcript`, so
  the builder and `check_text_preservation` see the same text by construction.
  **Changing either list changes the block cut — re-time the dry-run snapshots
  (`tools.retime_snapshot`) and rebuild affected talks.**

See `glossary/CLAUDE.md` for translator agent instructions (transliteration, capitalization rules).

## Architecture

See `ARCHITECTURE.md` at the project root for the full system architecture overview.

## Review Tracking

`review-status.json` tracks per-talk review state (synced from GitHub issue labels via `sync-review-status.yml`).
