# SY Subtitles – Claude Code Instructions

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
   Optional inputs: `timing_source=auto|whisper|en-srt` (default `auto` —
   en-srt if present, else whisper), `dry_run=true` (replay snapshots via
   `tools.fake_llm`, no commit).
4. Pipeline runs automatically:
   - **Whisper**: speech detection → `whisper.json` (word-level timestamps)
   - **Translate**: Claude agent translates EN → UK → `transcript_uk.txt`
   - **Review**: 2+1 review (Reviewer L + Reviewer S + Critic)
   - **Build**: single-pass Opus 4.7 agent writes `timecodes.txt` (`#N | start | end`
     per block); Python merges with `uk_blocks.json` in memory → `final/uk.srt`
   - **Validate**: structural checks (text, CPL, CPS, overlaps, gaps)
   - **Commit**: pushes all results back to repo

### Other Workflows

See `ARCHITECTURE.md` for full descriptions. In short:
`sync-subtitles.yml` (PR sync), `whisper.yml` (reusable),
`ci.yml` (lint + tests), `deploy-pages.yml`, `glossary-release.yml`,
`sync-review-status.yml`, `new-talk.yml`, `pipeline-matrix-dryrun.yml`,
`golden-talks.yml` (full-corpus pytest, on-demand).

## Local Setup

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt                  # for tests
python -m pytest tests/                              # run Python tests
python -m pytest tests/test_offset_srt.py -k detect  # run a single test
GOLDEN_TALKS_SCOPE=all pytest tests/test_golden_talks.py  # full-corpus golden
```


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

```bash
# Download talk from amruta.org
python -m tools.download --url "https://www.amruta.org/..." [--what all|srt|text]

# Build subtitles (deterministic orchestrator; LLM writes timecodes.txt between prepare and assemble)
python -m tools.build_map prepare        --talk-dir PATH --video-slug SLUG
python -m tools.build_map prepare-timing --talk-dir PATH --video-slug SLUG [--timing-source whisper|en-srt]
python -m tools.build_map assemble       --talk-dir PATH --video-slug SLUG

# Validate SRT subtitles
python -m tools.validate_subtitles --srt PATH --transcript PATH [--whisper-json PATH] --report PATH \
  [--skip-text-check] [--skip-time-check] [--skip-cps-check] [--skip-duration-check]

# Sync transcript edits into existing SRT (for PR workflow)
python -m tools.sync_transcript_to_srt --talk-dir PATH --video-slug SLUG \
  --old-transcript OLD --new-transcript NEW

# Sync SRT text edits back into transcript_uk.txt (reverse direction, for PR workflow)
python -m tools.sync_srt_to_transcript --old-srt OLD --new-srt NEW \
  --transcript transcript_uk.txt

# Two-pass sync driver for sync-subtitles PR workflow (used by Actions)
python -m tools.sync_pr --base SHA --paths "talks/.../transcript_uk.txt ..."

# Resync UK SRT from primary video timeline onto secondary video timeline
python -m tools.resync_srt --primary-uk PATH --primary-en PATH \
  --secondary-en PATH --output PATH

# Validate artifact contracts at pipeline phase boundaries
python -m tools.validate_artifacts [--whisper PATH | --meta PATH |
  --timecodes PATH | --talk-dir PATH]

# Detect and apply timecode offset between videos
python -m tools.offset_srt detect --srt1 PATH --srt2 PATH
python -m tools.offset_srt apply --srt PATH --offset-ms N --output PATH

# Optimize SRT timing
python -m tools.optimize_srt --srt PATH [--json PATH] --output PATH \
  [--skip-duration-split] [--skip-cps-split]

# Export SRT to plain text
python -m tools.text_export --srt PATH --output PATH [--meta PATH] [--double-spacing]

# Align Ukrainian transcript to English whisper timestamps
python -m tools.align_uk --transcript PATH --whisper-json PATH --output PATH \
  [--batch-size N] [--skip-word-align]

# Extract SRT text for language review
python -m tools.extract_review --srt PATH [--output PATH]

# Fetch EN+UK transcripts for glossary corpus
python -m tools.fetch_transcripts [--index PATH] [--slug SLUG] [--delay N] [--cookie COOKIE]

# Scan EN transcript for glossary term candidates
python -m tools.glossary_check --transcript PATH --glossary PATH --report PATH

# Scrape amruta.org UK talk listing into index.yaml
python -m tools.scrape_listing [--output PATH] [--cookie COOKIE] [--url URL]

# Run Whisper speech detection
python -m tools.whisper_run --video PATH --output PATH [--model MODEL] [--language LANG]
```

## Glossary

Sahaja Yoga term dictionaries live in `glossary/`:
- `terms_lookup.yaml` – EN → UK term dictionary
- `terms_context.yaml` – disambiguation context for terms with variants
- `chakra_map.yaml` – chakra/deity/channel mapping
- `chakra_system.yaml` – full subtle system reference

See `glossary/CLAUDE.md` for translator agent instructions (transliteration, capitalization rules).

## Architecture

See `ARCHITECTURE.md` at the project root for the full system architecture overview.

## Review Tracking

`review-status.json` tracks per-talk review state (synced from GitHub issue labels via `sync-review-status.yml`).