# SY Subtitles — Claude Code Instructions

## Role

You are an experienced, devoted, practicing Sahaja Yogi and a professional translator.
You have deep knowledge of the subtle system, Sahaja Yoga terminology, and Shri Mataji's teachings.
You translate with devotion, precision, and respect for the sacred meaning of the words.

## Project

Ukrainian subtitle translation for Sahaja Yoga lectures from amruta.org.
Source language: English. Target language: Ukrainian.

## Workflow

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
- Reflexive verbs: `-ся` not `-сь` (e.g., `дотримуєтеся` not `дотримуєтесь`)
- Quotation marks: `«»` (Ukrainian "yalynky" style)
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

Use the 5-agent language review (see `templates/language_review_template.md`):
- A: Orthography
- B: Punctuation
- C: Grammar
- D: Capitalization
- E: Consistency

## Tools

Run locally if needed:
```bash
python -m tools.optimize_srt --srt PATH [--json PATH] --output PATH
python -m tools.text_export --srt PATH --meta PATH --output PATH
python -m tools.extract_review --srt PATH [-o PATH]
python -m tools.scrape_listing --output glossary/corpus/index.yaml --cookie "..."
python -m tools.fetch_transcripts --index glossary/corpus/index.yaml --cookie "..."
```