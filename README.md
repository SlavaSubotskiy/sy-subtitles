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
1. [Local]           Download SRT + text from amruta.org (multi-video)
2. [GitHub Actions]  Run Whisper speech detection (auto-discovers pending videos)
3. [Local]           Translate with Claude Code (EN→UK)
4. [GitHub Actions]  Optimize subtitles (timing, CPS, structure)
5. [GitHub Actions]  Validate SRT quality
```

Download is done locally (amruta.org is behind Cloudflare). Everything else runs in **GitHub Actions**.

## Repository Structure

```
talks/                          Per-talk directories
  {date}_{slug}/
    meta.yaml                   Talk metadata (title, date, videos list)
    CLAUDE.md                   Per-talk Claude Code instructions
    {video_slug}/               Named video subdirectory (e.g., Talk, Bhajan)
      source/                   Original materials (EN SRT, whisper JSON)
      work/                     Translation in progress (UK corrected SRT)
      final/                    Optimized output (UK SRT, plain text, report)

tools/                          Python modules (used by Actions + locally)
  download.py                   amruta.org downloader (local only, multi-video + batch)
  scrape_listing.py             Scrape talk listing from amruta.org
  fetch_transcripts.py          Fetch EN+UK transcripts for glossary corpus
  whisper_run.py                Whisper speech detection wrapper
  optimize_srt.py               SRT timing optimizer
  text_export.py                SRT → plain text exporter
  srt_utils.py                  SRT parsing utilities
  config.py                     Optimization configuration

templates/                      Templates for new talks
glossary/                       SY terminology dictionary (362 terms)
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
- Writes `meta.yaml` with the videos list

### 2. Run Whisper (auto-discovery)

Go to **Actions → Whisper Speech Detection** and run:
- **Empty `talk_id`**: auto-discovers ALL videos missing `whisper.json`
- **Specific `talk_id`**: processes only that talk's pending videos

Whisper runs in parallel (max 3 concurrent) and commits all results in a single push.

### 3. Translate locally

```bash
git pull
# Edit talks/{id}/{video_slug}/work/uk_corrected.srt using Claude Code
git add talks/{id}/{video_slug}/work/uk_corrected.srt
git commit -m "Translate {talk_name}"
git push
```

### 4. Automatic optimization

Pushing `uk_corrected.srt` triggers the **Optimize** workflow automatically:
- Detects ALL changed `uk_corrected.srt` files
- Runs the SRT optimizer per video (uses Whisper data if available)
- Generates `final/uk.srt`, `final/report.txt`
- Commits results back to the repo

### 5. Automatic validation

Pushing to `final/*.srt` triggers the **Validate** workflow:
- Checks for overlaps, gaps, CPS limits, structural issues
- Posts results as check annotations

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
| Lines per block | 1 (single-line mode) | 1 |
| Min duration | ≥1.2s | ≥1.0s |
| Max duration | ≤7s | ≤8s |
| Min gap | ≥80ms (2 frames @24fps) | ≥80ms |

## License

MIT
