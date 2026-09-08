# Architecture

## Pipeline Flow

```
  amruta.org
      │
      ▼
  ┌─────────┐    git push    ┌──────────────────────────────────────┐
  │ download │ ──────────────►│        subtitle-pipeline.yml         │
  │ (local)  │               │                                      │
  └─────────┘               │  ┌─────────┐   ┌───────────────────┐ │
   meta.yaml                │  │ whisper  │──►│ translate+review  │ │
   transcript_en.txt        │  │ (.yml)   │   │ (Claude)          │ │
   en.srt                   │  └─────────┘   └───────────────────┘ │
                            │                        │              │
                            │                        ▼              │
                            │  ┌──────────────────────────────────┐ │
                            │  │ build (prepare → LLM → assemble)  │ │
                            │  │  Python splits ──► LLM timecodes  │ │
                            │  │  Python assembles ──► uk.srt      │ │
                            │  └──────────────────────────────────┘ │
                            │                        │              │
                            │                        ▼              │
                            │  ┌──────────┐   ┌──────────┐        │
                            │  │ validate  │   │  commit   │───►git │
                            │  └──────────┘   └──────────┘        │
                            └──────────────────────────────────────┘
                                             │
                            ┌────────────────┘
                            ▼
                     ┌─────────────┐
                     │ SPA (Pages) │  reads from raw.githubusercontent.com
                     │ site/       │  review-status.json for badges
                     └─────────────┘
```

## Repository Structure

```
sy-subtitles/
├── talks/                          # Talk data (one dir per talk)
│   └── {date}_{slug}/
│       ├── meta.yaml               # Talk metadata (title, date, videos[]; links as obfuscated video_ref;
│                                  #   each video's `sync:` role — see "Video sync roles" below)
│       ├── transcript_en.txt       # English transcript
│       ├── transcript_uk.txt       # Ukrainian translation (pipeline output)
│       ├── review_report.md        # AI review report
│       └── {video_slug}/
│           ├── source/
│           │   ├── en.srt          # English subtitles (from Vimeo)
│           │   └── whisper.json    # Word-level timestamps
│           ├── work/               # Build intermediates (gitignored + timecodes.txt)
│           │   ├── uk_blocks.json  # Split Ukrainian text blocks
│           │   ├── timing.json     # Compact whisper words / EN SRT blocks
│           │   └── timecodes.txt   # LLM output: #N | start | end per block
│           └── final/
│               ├── uk.srt          # Final Ukrainian subtitles
│               └── report.txt      # Validation report
├── assets/                         # Vendored binary assets
│   └── fonts/                      # PT Serif TTF + license — libass reads it via fontsdir,
│                                   #   so a burned line breaks exactly where the SPA's does
├── glossary/                       # Translation knowledge base
│   ├── terms_lookup.yaml           # 374 EN→UK terms
│   ├── terms_context.yaml          # Disambiguation context
│   ├── chakra_map.yaml             # Chakra/deity mappings
│   └── chakra_system.yaml          # Full subtle system reference
├── tools/                          # Python tooling (see tools/ for full listing)
│   ├── download.py                 # Fetch from amruta.org (local only)
│   ├── whisper_run.py              # Whisper speech detection wrapper
│   ├── burn_subtitles.py           # SRT → ASS → ffmpeg+libass burned-in video
│   ├── render_gate.py              # Blocks a burn gate step until the encode passes N%
│   ├── build_map.py / build_srt.py # Subtitle builder (prepare → LLM → assemble)
│   ├── builder_data.py             # Whisper / EN-SRT timing query interface
│   ├── validate_subtitles.py       # SRT validation (text, CPS, overlaps, gaps)
│   ├── validate_artifacts.py       # Phase-boundary contract enforcement
│   ├── optimize_srt.py             # Timing optimizer (splits/merges)
│   ├── sync_pr.py                  # Two-pass sync driver for sync-subtitles.yml
│   ├── sync_transcript_to_srt.py   # Forward sync (transcript → SRT)
│   ├── sync_srt_to_transcript.py   # Reverse sync (SRT edits → transcript)
│   ├── resync_srt.py               # Cross-video UK SRT resync
│   ├── offset_srt.py               # Multi-video offset detection
│   ├── align_uk.py                 # Ukrainian text alignment to whisper
│   ├── text_export.py              # SRT → plain text
│   ├── extract_review.py           # Extract SRT text for language review
│   ├── glossary_check.py           # Glossary candidate scanner
│   ├── fetch_transcripts.py        # amruta.org transcript corpus fetcher
│   ├── scrape_listing.py           # amruta.org UK index scraper
│   ├── schemas.py                  # Artifact schema validators
│   ├── workflow_validation*.py     # Workflow input guards
│   ├── fake_llm.py                 # Dry-run snapshot replay
│   ├── verify_snapshot.py          # Dry-run output verifier
│   ├── srt_utils.py                # Shared SRT parsing/writing
│   ├── text_segmentation.py        # Shared text segmentation helpers
│   ├── sync_common.py              # Shared sync helpers
│   └── config.py                   # Threshold constants
├── site/                           # GitHub Pages SPA
│   ├── index.html                  # Preview + Review app shell
│   ├── js/                         # Plain-JS modules (single source, shared with node --test)
│   ├── css/                        # Design tokens + components (tokens.css, components.css)
│   ├── styleguide.html             # Live design-system catalog
│   ├── sw.js                       # Service worker (offline shell precache)
│   └── icon.png                    # Mahayantra favicon
├── review-status.json              # Review tracking (synced from Issues)
├── templates/                      # Prompt templates
│   └── language_review_template.md
└── .github/workflows/
    ├── subtitle-pipeline.yml       # Main pipeline (whisper→translate→review→build)
    ├── sync-subtitles.yml          # PR-based transcript ↔ SRT sync
    ├── sync-review-status.yml      # Issues → review-status.json
    ├── whisper.yml                 # Reusable whisper workflow
    ├── ci.yml                      # Lint + tests + E2E
    ├── deploy-pages.yml            # Deploy site/ to GitHub Pages
    ├── glossary-release.yml        # Glossary releases
    ├── golden-talks.yml            # Full-corpus golden tests (manual)
    ├── new-talk.yml                # PR-triggered setup for new talks
    ├── pipeline-matrix-dryrun.yml  # Matrix dry-run validation
    └── burn-subtitles.yml          # Render uk.srt into the video (SPA-dispatched)
```

### Video sync roles

A talk's videos are different recordings of the same event, so a subtitle
edit in one has to reach the others. How each video participates is declared
per video in `meta.yaml` under `sync:`, and read only through
`tools/video_roles.py` (`python -m tools.video_roles --talk-dir PATH [--role primary]`):

| Role | Meaning |
|---|---|
| `primary` | Authoritative subtitle text. Exactly one per talk. |
| `derived` | Mirrors the primary's text positionally; keeps its own timing. |
| `independent` | Its own slice of the transcript (a separate talk on the same day); synced against the transcript, never against the primary. |
| `ignored` | Never read, never written — a yogi's introduction, a presents ceremony, a camera angle with no subtitles. |

A multi-video talk MUST declare once more than one of its videos carries a
`uk.srt`; there is no default, because a default in a resolver is seen by
nobody and fires in CI. Below that threshold the resolver still answers: the
one subtitled (or lone) video is `primary` and every other video is
`ignored`. Mind the consequence — a second video that simply has not been
built yet resolves to `ignored`, so it is never built and never synced.
Declare the roles as soon as a talk gains a second video. Rules of thumb: the full
recording is `primary` and the `Talk` cut is `derived`; a video without
`source/en.srt` cannot be `primary`, since resyncing needs an EN bridge on
both sides.

## Workflows

### subtitle-pipeline.yml (main)
Triggered manually via `workflow_dispatch`. Full pipeline:
1. **Discover** — finds videos and determines what needs processing
2. **Whisper** — calls `whisper.yml` for word-level speech timestamps
3. **Translate + Review** — a Claude agent translates EN→UK, then 2+1 review
4. **Build** — `build_map.py prepare` → single-pass LLM timecodes (`build-timecodes` job) → `build_map.py assemble` → `build_srt.py`
5. **Validate** — text preservation, CPS, timing checks
6. **Commit** — rebuilds `site/dict/words_uk.txt` from the corpus it just
   extended (`tools/build_wordlist.py`), then pushes results + creates a
   review tracking Issue

### sync-subtitles.yml
Triggered on PRs that modify `transcript_uk.txt` **or** `*/final/uk.srt`.
Runs the sync driver (`tools/sync_pr.py`): SRT edits are first synced
back into the transcript (reverse), a block boundary moved on a derived
video is carried straight to the primary (re-cuts cannot travel through a
transcript), then the transcript is synced out to every video's SRT
(forward) — text-only swaps, no re-timing — and validates.

### sync-review-status.yml
Triggered on Issue label/assign changes. Syncs GitHub Issues → `review-status.json`.
Auto-updates labels: assign → `review:in-progress`, close → `review:approved`.

### whisper.yml
Reusable workflow. Downloads video, runs Whisper for word-level timestamps.
Also `workflow_dispatch` callable with a `force` flag.

### ci.yml
Runs on every push: ruff lint, Python tests, JS tests, Playwright E2E.
Default golden-talks scope is the curated fixture; full-corpus run lives in
`golden-talks.yml`.

### deploy-pages.yml
Deploys `site/` to GitHub Pages on changes under `site/`.

### glossary-release.yml
Tags and packages glossary releases.

### golden-talks.yml
Manual `workflow_dispatch` — runs `tests/test_golden_talks.py` with
`GOLDEN_TALKS_SCOPE=all` against every shipped `uk.srt`.

### new-talk.yml
Triggered when a PR adds a new talk directory; bootstraps metadata.

### pipeline-matrix-dryrun.yml
Replays the subtitle pipeline using `tools.fake_llm` snapshots — exercises
the build/sync stack without burning Claude calls.

### burn-subtitles.yml
`workflow_dispatch` from the preview SPA: downloads the video, burns
`final/uk.srt` into the picture with ffmpeg+libass reproducing the fullscreen
subtitle look, and uploads the MP4 as a 7-day artifact. Sizing arrives as
ratios measured in the browser (see `tools/burn_subtitles.py`). `run-name` is
the talk's human title, so a run is found by eye in the Actions list; the
caller's `request_id` rides along at the end because `workflow_dispatch`
returns no run id, and that is how the SPA finds its own run.

**Two refs, on purpose.** The workflow file and `tools/` come from the ref the
dispatch names — always the deployed SPA's own version. The subtitles come from
the `source_ref` input, checked out separately into `content/`, because a
reviewer's edit-sync branch is cut from `main` once and never fast-forwarded:
dispatching against it would run whatever renderer `main` happened to carry on
the day they first edited.

The job runs ffmpeg **once**, detached, writing an `-progress` file, and then
declares twenty cheap named steps (`Render 5%` … `Render 95%`, `Finish render`)
that each block in `tools/render_gate.py` until the encode passes that
threshold. That shape exists because a *step completing* is the only live,
CORS-clean progress channel a browser has into a running job — the log blob
404s mid-run and annotations appear only at finalisation — and the SPA already
polls the job's step list. So the bar is made of facts: each completed step
name credits a fixed slice of it (`BURN_STEP_WEIGHTS` in
`site/js/burn_video.js`, pinned against these step names by
`tests/test_burn_workflow_steps.py`). The grid is 5% because the corpus's
longest talk encodes in about 50 minutes, where 10% gates would leave the bar
motionless for over five minutes at a time.

## Subtitle Builder (V2)

Three-phase architecture:
1. **Prepare** (Python, deterministic) — splits Ukrainian text into subtitle-sized blocks and prepares timing data (`build_map.py prepare` / `prepare-timing`)
2. **Build timecodes** (LLM, single pass) — one Claude builder agent (model selectable via the `model` input) receives the UK blocks + EN transcript + timing source (whisper words or en.srt) and writes `timecodes.txt` (`#N | start | end` per block). The LLM returns ONLY timecodes, never modifies text
3. **Assemble** (Python, deterministic) — merges `timecodes.txt` with `uk_blocks.json` in memory and generates SRT via `build_srt.py`

Key principle: **LLM determines timing, Python guarantees text integrity.**

## SPA (GitHub Pages)

App shell at `site/index.html` plus plain-JS modules under `site/js/`
(shared single-source with the Node test suite), the token/component CSS
under `site/css/` (`tokens.css` + `components.css`, catalogued live in
`site/styleguide.html`), and a service worker (`site/sw.js` +
`site/js/sw_routing.js`) that precaches the shell for offline use:
- **Index** — talk list with search/filter, review status badges (from `review-status.json`)
- **Preview** — Vimeo player + subtitle overlay + markers
- **Review** — side-by-side EN/UK transcript editor

Data sources (zero backend):
- GitHub Trees API → talk discovery (1 API call, cached with ETag)
- `raw.githubusercontent.com` → meta.yaml, SRT, transcripts
- `review-status.json` → review badges (static file, no API cost)
- `localStorage` → markers, edits, preferences, cache

### Typo hints

A preference (the gear menu) underlines words that neither a general Ukrainian
dictionary nor this project's own vocabulary knows, live in the subtitle editor.
Neither source alone is usable here: the dictionary flags every transliterated
term (`Ґрантхі`, `абхішека`), and a bare corpus without morphology flags every
inflected form. Their intersection is what makes the hints quiet enough to leave
on. Measured on a real reviewer PR, 11 flags across 403 edited blocks, all 11
genuine, where the dictionary alone gave 55. Across the whole approved corpus —
1.3M word tokens in 268 files — it flags 32 occurrences of 7 words, and every
one is a real defect: `Mати`, `Toм`, `Aле`, `iндивідуально` and the like, whose
first letter is Latin. Nothing else in the corpus is flagged at all.

Both sides ask their own question of the same word. The dictionary is asked
about it AS WRITTEN (it holds `Лакшмі`, not `лакшмі`, and keys its apostrophes
with `'`); the wordlist is asked about the folded form. `tools/build_wordlist.py`
judges the corpus by exactly that rule, so a word is never in neither place:
lowercasing before asking once underlined 610 forms of this material's own
vocabulary — `Ісус`, `Христос`, `Крішна`, `Лакшмі`.

What this cannot do is judge a name by its case. The list is keyed by the folded
form, so a name the corpus writes lowercase somewhere legitimate — `лакшмі` in a
mantra, `деві` in `Сарва деві дева` — is thereafter accepted in lowercase
everywhere. Capitalisation of the sacred vocabulary stays a matter for the
language review (`glossary/CLAUDE.md`), not for these hints.

A word mixing Cyrillic and Latin is flagged without asking either source: it is
wrong however its pieces are judged, and the corpus holds no legitimate word of
that shape. Read as Cyrillic only, `Mати` left the fragment `ати`, which the
builder then shipped as vocabulary — so the most invisible typo in the language
was also the one the hints could never see.

- `site/dict/uk_UA.{aff,dic}` — vendored hunspell dictionary (MPL 1.1, `dict_uk`)
- `site/dict/words_uk.txt` — only what that dictionary MISSES, built from the
  talks and the glossary by `tools/build_wordlist.py`
- `site/js/typo_worker.js` — holds both; parsing the dictionary costs ~4 s and
  ~290 MB, so it runs off the main thread and only while the preference is on
- `site/js/typo_hints.js` — which words to flag (pure; twin of the tokenizer in
  `tools/build_wordlist.py`, pinned by `tests/fixtures/wordlist_normalization_cases.json`)

Painting goes through the CSS Custom Highlight API, so the text is decorated
where it stands — no wrapper element, and therefore no disturbance to the caret,
the undo stack, or the text the edit store saves.

## Review Tracking

```
Pipeline completes → creates Issue (review:pending)
                          │
Reviewer assigns self ────► Action: label → review:in-progress
                          │         JSON updated
Reviewer closes Issue ────► Action: label → review:approved
                                    JSON updated
SPA reads review-status.json → shows badges
```
