# sy-subtitles

Sahaja Yoga lecture subtitle translation and optimization toolkit.

Translates English subtitles from [amruta.org](https://www.amruta.org/) lectures into Ukrainian, with automated quality optimization via GitHub Actions.

## How It Works

```
1. [GitHub Actions]  Download SRT + text from amruta.org
2. [GitHub Actions]  Run Whisper speech detection on video
3. [Local]           Translate with Claude Code (EN→UK)
4. [GitHub Actions]  Optimize subtitles (timing, CPS, structure)
5. [GitHub Actions]  Validate SRT quality
```

All automation runs in **GitHub Actions**. Only translation is done locally.

## Repository Structure

```
talks/                          Per-talk directories
  {date}_{slug}/
    source/                     Original materials (EN SRT, whisper JSON, metadata)
    work/                       Translation in progress (UK corrected SRT)
    final/                      Optimized output (UK SRT, plain text, report)
    CLAUDE.md                   Per-talk Claude Code instructions

tools/                          Python modules (used by Actions)
  download.py                   amruta.org downloader
  whisper_run.py                Whisper speech detection wrapper
  optimize_srt.py               SRT timing optimizer
  text_export.py                SRT → plain text exporter
  srt_utils.py                  SRT parsing utilities
  config.py                     Optimization configuration

templates/                      Templates for new talks
glossary/                       SY terminology dictionary (TODO)
```

## Adding a New Talk

### 1. Download source materials

Go to **Actions → Download Materials** and run with:
- `amruta_url`: Full URL of the talk page on amruta.org
- `talk_date`: Date in YYYY-MM-DD format
- `talk_slug`: Short identifier (e.g., `guru-puja`)

This downloads SRT files, transcript text, and creates the talk directory.

### 2. Run Whisper (optional)

Go to **Actions → Whisper Speech Detection** and run with:
- `talk_id`: Directory name (e.g., `1983-07-24_guru-puja`)

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

## Secrets

Configure these in **Settings → Secrets and variables → Actions**:

| Secret | Description |
|--------|-------------|
| `AMRUTA_SESSION_COOKIE` | WordPress session cookie for amruta.org |

## License

MIT
