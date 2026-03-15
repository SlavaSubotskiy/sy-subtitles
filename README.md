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
      work/                     Builder mapping (uk.map)
      final/                    Output (uk.srt, report.txt, build_report.txt)

tools/                          Python modules (used by Actions + locally)
  download.py                   amruta.org downloader (local only, multi-video + batch)
  whisper_run.py                Whisper speech detection wrapper
  builder_data.py               Query EN blocks with whisper timestamps
  build_srt.py                  Build SRT from mapping table
  validate_subtitles.py         SRT validation (text, CPL, CPS, overlaps, gaps)
  offset_srt.py                 Detect/apply timecode offset between videos
  optimize_srt.py               SRT timing optimizer (legacy workflow)
  text_export.py                SRT → plain text exporter
  srt_utils.py                  SRT parsing utilities
  config.py                     Optimization configuration

templates/                      Agent templates (builder, review)
glossary/                       SY terminology dictionary (374 terms)
  corpus/                       Cached transcripts from amruta.org (gitignored)
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

## Legacy Workflow (SRT-based)

For manual SRT translation (without the full pipeline):

```bash
# Edit UK subtitles manually
git pull
# Edit talks/{id}/{video_slug}/work/uk_corrected.srt using Claude Code
git push  # triggers optimize + validate workflows
```

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