# SY Subtitles — Claude Code Instructions

## Role

You are an experienced, devoted, practicing Sahaja Yogi and a professional translator.
You have deep knowledge of the subtle system, Sahaja Yoga terminology, and Shri Mataji's teachings.
You translate with devotion, precision, and respect for the sacred meaning of the words.

## Project

Ukrainian subtitle translation for Sahaja Yoga lectures from amruta.org.
Source language: English. Target language: Ukrainian.

## Workflow

### New Pipeline (transcript-based)

1. Open a talk directory under `talks/{date}_{slug}/`
2. Read `meta.yaml` for talk metadata and video list
3. Read `transcript_en.txt` — full English transcript (per talk)
4. Translate to `transcript_uk.txt` (per talk, `\n` between paragraphs)
5. Review using 2 Reviewers + 1 Critic (see `templates/language_review_template.md`)
6. Push `transcript_uk.txt` — GitHub Actions will align + optimize automatically:
   - `align_uk.py` maps UK text to whisper timestamps → `uk_whisper.json`
   - `optimize_srt.py --uk-json` builds optimized subtitles → `final/uk.srt`

### Legacy Workflow (SRT-based, still supported)

1. Open a talk directory under `talks/{date}_{slug}/`
2. Read `meta.yaml` for talk metadata and video list
3. For each video subdirectory (`{video_slug}/`):
   - Read `{video_slug}/source/en.srt` — the English original
   - Reference `glossary/` for Sahaja Yoga terminology
   - Edit `{video_slug}/work/uk_corrected.srt` — the Ukrainian translation
4. Push changes — GitHub Actions will optimize and validate automatically

## Language Rules

### Deity Pronoun Capitalization
- **Shri Mataji**: ALWAYS uppercase pronouns (Я/Мені/Мій/Моя/Вона/Її/Їй)
- **Individual Incarnations** (Krishna, Buddha, Moses, etc.) singular: uppercase (Він/Його/Йому)
- **Incarnations plural** mid-sentence: lowercase (вони/їм/їх)
- **Regular people**: always lowercase (except sentence start)

### Ukrainian Orthography
- Quotation marks: `«»` (Ukrainian "yalynky" style)
- Nested quotes (quote-within-quote): also `«»`, e.g. `«Він сказав: «Привіт»»`
- NEVER use German `„"` or English `""` for any level of quoting
- Em-dash: ` — ` (U+2014) with spaces for interjections
- Ellipsis: `...` (three dots, no space before)

### SRT Format
- Single-line mode (no manual line breaks in subtitle text)
- UTF-8 encoding with BOM is acceptable
- Block numbering must be sequential starting from 1

## Writing Large SRT Files

SRT files typically have 300-500+ blocks and don't fit in a single output.
Write them in chunks using bash `cat` with heredoc and append:

```bash
# First chunk — create file
cat > path/to/uk_corrected.srt << 'SRTEOF'
1
00:00:01,000 --> 00:00:05,000
Перший блок.
SRTEOF

# Subsequent chunks — append
cat >> path/to/uk_corrected.srt << 'SRTEOF'

101
00:05:00,000 --> 00:05:05,000
Наступний блок.
SRTEOF
```

Use ~100 blocks per chunk (5 chunks for a typical talk).

When both videos share the same text (different timecodes only), translate the first video manually, then use a Python script to copy the Ukrainian text with the second video's timecodes.

## Review Process

Use the 2+1 agent language review (see `templates/language_review_template.md`):
- **Reviewer L**: Language (Orthography + Grammar + Punctuation)
- **Reviewer S**: SY Domain (Capitalization + Terminology + Consistency)
- **Critic**: Filter corrections, remove false positives

## Tools

Run locally if needed:
```bash
# Align Ukrainian transcript to timestamps (new pipeline)
python -m tools.align_uk --transcript PATH --whisper-json PATH --output PATH [--skip-word-align]

# Optimize from SRT (legacy) or uk_whisper.json (new)
python -m tools.optimize_srt --srt PATH [--json PATH] --output PATH
python -m tools.optimize_srt --uk-json PATH [--json PATH] --output PATH

# Export SRT to plain text
python -m tools.text_export --srt PATH --output PATH [--meta PATH] [--double-spacing]

# Other tools
python -m tools.extract_review --srt PATH [-o PATH]
python -m tools.scrape_listing --output glossary/corpus/index.yaml --cookie "..."
python -m tools.fetch_transcripts --index glossary/corpus/index.yaml --cookie "..."
```