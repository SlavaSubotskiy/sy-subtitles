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
   transcript_en.txt        │  │ (.yml)   │   │ (Claude Opus)     │ │
   en.srt                   │  └─────────┘   └───────────────────┘ │
                            │                        │              │
                            │                        ▼              │
                            │  ┌──────────────────────────────────┐ │
                            │  │ build (prepare → chunks → assemble)│
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
│       ├── meta.yaml               # Talk metadata (title, date, videos[])
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
├── glossary/                       # Translation knowledge base
│   ├── terms_lookup.yaml           # 374 EN→UK terms
│   ├── terms_context.yaml          # Disambiguation context
│   ├── chakra_map.yaml             # Chakra/deity mappings
│   └── chakra_system.yaml          # Full subtle system reference
├── tools/                          # Python tooling
│   ├── download.py                 # Fetch from amruta.org
│   ├── build_map.py                # Subtitle mapping orchestrator
│   ├── build_srt.py                # SRT generator from mapping
│   ├── validate_subtitles.py       # SRT validation
│   ├── optimize_srt.py             # Timing optimizer (splits/merges)
│   ├── sync_transcript_to_srt.py   # Text-only sync for PR edits
│   ├── offset_srt.py               # Multi-video offset detection
│   ├── text_export.py              # SRT → plain text
│   ├── srt_utils.py                # Shared SRT parsing/writing
│   ├── config.py                   # Threshold constants
│   ├── builder_data.py             # Whisper data query interface
│   └── align_uk.py                 # Ukrainian text alignment
├── site/                           # GitHub Pages SPA
│   ├── index.html                  # Preview + Review app
│   └── icon.png                    # Mahayantra favicon
├── review-status.json              # Review tracking (synced from Issues)
├── templates/                      # Prompt templates
│   └── language_review_template.md
└── .github/workflows/
    ├── subtitle-pipeline.yml       # Main pipeline (whisper→translate→build)
    ├── sync-subtitles.yml          # PR-based transcript sync
    ├── sync-review-status.yml      # Issues → review-status.json
    ├── whisper.yml                 # Reusable whisper workflow
    └── ci.yml                      # Lint + tests + E2E
```

## Workflows

### subtitle-pipeline.yml (main)
Triggered manually via `workflow_dispatch`. Full pipeline:
1. **Discover** — finds videos and determines what needs processing
2. **Whisper** — calls `whisper.yml` for word-level speech timestamps
3. **Translate + Review** — Claude Opus translates EN→UK, then 2+1 review
4. **Build** — `build_map.py prepare` → parallel LLM chunks → `build_map.py assemble` → `build_srt.py`
5. **Validate** — text preservation, CPS, timing checks
6. **Commit** — pushes results + creates review tracking Issue

### sync-subtitles.yml
Triggered on PRs that modify `transcript_uk.txt`. Does text-only swap in SRT blocks (no re-timing), then validates.

### sync-review-status.yml
Triggered on Issue label/assign changes. Syncs GitHub Issues → `review-status.json`.
Auto-updates labels: assign → `review:in-progress`, close → `review:approved`.

### whisper.yml
Reusable workflow. Downloads video, runs Whisper for word-level timestamps.

### ci.yml
Runs on every push: ruff lint, Python tests, JS tests, Playwright E2E.

## Subtitle Builder (V2)

Three-phase architecture:
1. **Prepare** (Python, deterministic) — splits Ukrainian text into subtitle-sized blocks, finds paragraph boundaries, creates LLM prompt chunks
2. **Matrix chunks** (LLM, parallel) — each chunk receives UK blocks + EN transcript context + whisper timestamps. LLM returns ONLY timecodes, never modifies text
3. **Assemble** (Python, deterministic) — collects chunk results, builds mapping table, generates SRT via `build_srt.py`

Key principle: **LLM determines timing, Python guarantees text integrity.**

## SPA (GitHub Pages)

Single-file app at `site/index.html`:
- **Index** — talk list with search/filter, review status badges (from `review-status.json`)
- **Preview** — Vimeo player + subtitle overlay + markers
- **Review** — side-by-side EN/UK transcript editor

Data sources (zero backend):
- GitHub Trees API → talk discovery (1 API call, cached with ETag)
- `raw.githubusercontent.com` → meta.yaml, SRT, transcripts
- `review-status.json` → review badges (static file, no API cost)
- `localStorage` → markers, edits, cache

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
