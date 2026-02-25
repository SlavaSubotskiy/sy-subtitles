# SY Subtitles — Claude Code Instructions

## Project

Ukrainian subtitle translation for Sahaja Yoga lectures from amruta.org.
Source language: English. Target language: Ukrainian.

## Workflow

1. Open a talk directory under `talks/{date}_{slug}/`
2. Read `source/en.srt` — the English original
3. Reference `glossary/` for Sahaja Yoga terminology
4. Edit `work/uk_corrected.srt` — the Ukrainian translation
5. Push changes — GitHub Actions will optimize and validate automatically

## Language Rules

### Deity Pronoun Capitalization
- **Shri Mataji**: ALWAYS uppercase pronouns (Я/Мені/Мій/Моя/Вона/Її/Їй)
- **Individual Incarnations** (Krishna, Buddha, Moses, etc.) singular: uppercase (Він/Його/Йому)
- **Incarnations plural** mid-sentence: lowercase (вони/їм/їх)
- **Regular people**: always lowercase (except sentence start)

### Ukrainian Orthography
- Reflexive verbs: `-ся` not `-сь` (e.g., `дотримуєтеся` not `дотримуєтесь`)
- Quotation marks: `<<>>` (Ukrainian "yalynky" style)
- Em-dash: ` -- ` with spaces for interjections
- Ellipsis: `...` (three dots, no space before)

### SRT Format
- Single-line mode (no manual line breaks in subtitle text)
- UTF-8 encoding with BOM is acceptable
- Block numbering must be sequential starting from 1

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
python -m tools.optimize_srt --srt PATH --json PATH --output PATH
python -m tools.text_export --srt PATH --meta PATH --output PATH
python -m tools.scrape_listing --output glossary/corpus/index.yaml --cookie "..."
python -m tools.fetch_transcripts --index glossary/corpus/index.yaml --cookie "..."
```