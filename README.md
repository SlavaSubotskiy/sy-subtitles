# sy-subtitles

> This project is humbly dedicated to Shri Mataji Nirmala Devi.
> May the auspicious grace of Shri Ganesha remove all obstacles,
> and may the devoted energy of Shri Hanumana carry Her words
> to the hearts of Ukrainian-speaking seekers,
> bringing joy to our Holy Mother.

Sahaja Yoga lecture subtitle translation and optimization toolkit.

Translates English subtitles from [amruta.org](https://www.amruta.org/) lectures into Ukrainian, with automated quality optimization via GitHub Actions.

## How It Works

```
1. [Local]           Download source materials from amruta.org
2. [GitHub Actions]  Whisper speech detection (word-level timestamps)
3. [GitHub Actions]  Translate EN→UK (Claude agent + glossary)
4. [GitHub Actions]  Review translation (2+1: Language + SY Domain + Critic)
5. [GitHub Actions]  Build subtitles (Claude agent: semantic alignment → mapping → SRT)
6. [GitHub Actions]  Validate SRT quality (text, CPL, CPS, overlaps, gaps)
```

Download is done locally (amruta.org is behind Cloudflare). Everything else runs in **GitHub Actions** via `subtitle-pipeline.yml`.

## Repository Structure

```
talks/                          Per-talk directories
  {date}_{slug}/
    meta.yaml                   Talk metadata (title, date, videos list)
    transcript_en.txt           English transcript (full talk)
    transcript_uk.txt           Ukrainian translation (full talk)
    review_report.md            Translation review report
    {video_slug}/               Named video subdirectory (e.g., Talk, Bhajan)
      source/                   Original materials (EN SRT, whisper JSON)
      work/                     Build intermediates (timecodes.txt — LLM output)
      final/                    Output (uk.srt, report.txt, build_report.txt)

tools/                          Python modules (see ARCHITECTURE.md for full list)
  download.py                   amruta.org downloader (local only, multi-video + batch)
  build_map.py / build_srt.py   Subtitle builder (prepare → LLM timecodes → assemble)
  validate_subtitles.py         SRT validation (text, CPL, CPS, overlaps, gaps)
  optimize_srt.py               SRT timing optimizer (run from main pipeline)
  sync_*.py                     Transcript ↔ SRT sync (PR workflow)

templates/                      Agent templates (builder, review)
glossary/                       SY terminology dictionary (EN → UK, see glossary/README.md)
```

## Adding a New Talk

### 1. Download source materials (local)

```bash
# Single talk (date/slug auto-extracted from URL):
python -m tools.download \
  --url "https://www.amruta.org/1993/09/19/ganesha-puja-cabella-1993/"

# Batch mode:
python -m tools.download --manifest queue.yaml
```

The downloader automatically:
- Extracts date and slug from the URL
- Finds all Vimeo videos on the page
- Creates named subdirectories per video (e.g., `Talk/`, `Bhajan/`)
- Downloads SRTs per video from Vimeo
- Saves `transcript_en.txt` and `meta.yaml`

### 2. Push and run pipeline

```bash
git add talks/{date}_{slug}/
git commit -m "Add {talk title}"
git push

# Trigger the full pipeline (whisper + translate + review + build):
gh workflow run subtitle-pipeline.yml -f talk_id={date}_{slug}
```

The pipeline runs all steps automatically and commits results back to the repo.

### 3. Automatic validation

Pushing to `final/*.srt` triggers the **Validate** workflow:
- Checks for overlaps, gaps, CPS limits, structural issues
- Posts results as check annotations

## PR-based Edits

To fix Ukrainian text after the pipeline ships subtitles, edit
`transcript_uk.txt` (or `final/uk.srt`) on a branch and open a PR.
`sync-subtitles.yml` runs the reverse-then-forward sync, optimizes,
and validates automatically.

## Batch Download

Create a `queue.yaml` file (gitignored):

```yaml
talks:
  - url: https://www.amruta.org/1993/09/19/ganesha-puja-cabella-1993/
  - url: https://www.amruta.org/1985/06/16/some-talk/
    slug: short-slug  # optional override
```

Run: `python -m tools.download --manifest queue.yaml`

## Optimization Parameters

| Parameter | Target | Hard Limit |
|-----------|--------|------------|
| CPS (chars/sec) | ≤15 | ≤20 |
| CPL (chars/line) | – | ≤84 |
| Lines per block | 1 (single-line mode) | 1 |
| Min duration | ≥1.2s | ≥1.0s |
| Max duration | ≤15s | ≤21s |
| Min gap | ≥80ms (2 frames @24fps) | ≥80ms |

## License

MIT