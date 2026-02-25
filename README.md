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
1. [Local]           Download SRT + text from amruta.org
2. [GitHub Actions]  Run Whisper speech detection on video
3. [Local]           Translate with Claude Code (EN→UK)
4. [GitHub Actions]  Optimize subtitles (timing, CPS, structure)
5. [GitHub Actions]  Validate SRT quality
```

Download is done locally (amruta.org is behind Cloudflare). Everything else runs in **GitHub Actions**.

## Repository Structure

```
talks/                          Per-talk directories
  {date}_{slug}/
    source/                     Original materials (EN SRT, whisper JSON, metadata)
    work/                       Translation in progress (UK corrected SRT)
    final/                      Optimized output (UK SRT, plain text, report)
    CLAUDE.md                   Per-talk Claude Code instructions

tools/                          Python modules (used by Actions + locally)
  download.py                   amruta.org downloader (local only)
  scrape_listing.py             Scrape talk listing from amruta.org
  fetch_transcripts.py          Fetch EN+UK transcripts for glossary corpus
  whisper_run.py                Whisper speech detection wrapper
  optimize_srt.py               SRT timing optimizer
  text_export.py                SRT → plain text exporter
  srt_utils.py                  SRT parsing utilities
  config.py                     Optimization configuration

templates/                      Templates for new talks
glossary/                       SY terminology dictionary (363 terms)
  corpus/                       Cached transcripts from amruta.org (gitignored)
```

## Adding a New Talk

### 1. Download source materials (local)

```bash
python -m tools.download \
  --url "https://www.amruta.org/..." \
  --talk-dir talks/{date}_{slug}/source \
  --what srt,text \
  --cookie "wordpress_logged_in_...=..."
```

Create `source/meta.yaml` with talk metadata and commit.

### 2. Run Whisper (optional)

Go to **Actions → Whisper Speech Detection** and run with:
- `talk_id`: Directory name (e.g., `1983-07-24_guru-puja`)
- `vimeo_url`: Vimeo player URL (or leave empty to read from meta.yaml)

This downloads the video temporarily, runs Whisper, saves `whisper.json`, then discards the video.

### 3. Translate locally

```bash
git pull
# Edit talks/{id}/work/uk_corrected.srt using Claude Code
git add talks/{id}/work/uk_corrected.srt
git commit -m "Translate {talk_name}"
git push
```

### 4. Automatic optimization

Pushing `uk_corrected.srt` triggers the **Optimize** workflow automatically:
- Runs the SRT optimizer with Whisper timing data
- Generates `final/uk.srt`, `final/uk.txt`, `final/report.txt`
- Commits results back to the repo

### 5. Automatic validation

Pushing to `final/*.srt` triggers the **Validate** workflow:
- Checks for overlaps, gaps, CPS limits, structural issues
- Posts results as check annotations

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
