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

templates/                      Agent templates (language review)
glossary/                       SY terminology dictionary (EN → UK, see glossary/README.md)
```

## Adding a New Talk

### 1. Download source materials (local)

```bash
# Single talk (date/slug auto-extracted from URL):
python -m tools.download \
  --url "https://www.amruta.org/1993/09/19/ganesha-puja-cabella-1993/"

# English + Ukrainian transcripts in one go (folder/meta come from the EN page):
python -m tools.download \
  --url "https://www.amruta.org/1984/08/11/raksha-bandhan-and-maryadas-hounslow-1984/" \
  --langs en,uk

# Batch mode:
python -m tools.download --manifest queue.yaml
```

The downloader automatically:
- Names the folder `{date}_{slugify(page_title)}` — the same convention as the
  SPA add-talk flow (single-source slugify in `tools/talk_slug.py`)
- Finds all Vimeo videos on the page
- Creates named subdirectories per video (e.g., `Talk/`, `Bhajan/`)
- Downloads SRTs per video from Vimeo
- Saves `transcript_<lang>.txt` (one per `--langs`, default the URL's language)
  and `meta.yaml`

amruta.org auth (the WordPress session cookie) is documented in
[`docs/amruta-auth.md`](docs/amruta-auth.md).

### 2. Push and run pipeline

```bash
git add talks/{date}_{slug}/
git commit -m "Add {talk title}"
git push

# Trigger the full pipeline (whisper + translate + review + build):
gh workflow run subtitle-pipeline.yml -f talk_id={date}_{slug}
```

The pipeline runs all steps automatically and commits results back to the repo.

### 3. Validation

Validation runs inside the pipeline itself (the **Validate** step checks
text preservation, overlaps, gaps, CPS limits and structural issues before
anything is committed) and again in `sync-subtitles.yml` for PR edits.
There is no separate push-triggered Validate workflow; to re-check an SRT
by hand run `python -m tools.validate_subtitles`.

## PR-based Edits

To fix Ukrainian text after the pipeline ships subtitles, edit
`transcript_uk.txt` (or `final/uk.srt`) on a branch and open a PR.
`sync-subtitles.yml` runs the reverse-then-forward sync and validates
automatically (text-only swaps — edits that change block structure
need a full pipeline rebuild; approximate re-timing is banned).

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
| Min duration | ≥1.2s | ≥1.2s |
| Max duration | ≤7s (optimizer CLI) | ≤21s |
| Min gap | ≥80ms (2 frames @24fps) | ≥80ms |

## License

MIT
<!-- gate skip-path probe -->
