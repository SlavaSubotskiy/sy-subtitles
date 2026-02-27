# Subtitle Builder — Agent Instructions

You are building Ukrainian subtitles for a Sahaja Yoga lecture video.

## Inputs
You will be given paths to three files per video:
1. **transcript_uk.txt** — Ukrainian translation (per-talk, paragraphs separated by \n\n)
2. **en.srt** — English subtitles (per-video, timing reference)
3. **whisper.json** — English speech recognition with word timestamps (per-video, large file)

## Process

### Step 1 — Read and understand inputs
- Read `en.srt` fully — it shows WHAT is said and WHEN (50-80KB, fits in ~2 reads)
- Read `transcript_uk.txt` — the Ukrainian text you'll be placing as subtitles
- Read `whisper.json` in portions — use it for precise word-level timing within sentences
  (The file is 300-600KB. Read segments in batches: first 50 segments, then next 50, etc.)

### Step 2 — Create subtitles in chunks
Process the talk in ~5-minute time chunks. For each chunk:
1. Identify the English subtitles in this time range
2. Find the corresponding Ukrainian text (match EN→UK by meaning and order)
3. Create Ukrainian SRT blocks timed to when the English equivalent is spoken
4. Use whisper word timestamps for precise timing (where a sentence starts/ends within a segment)
5. Write the chunk to the output SRT file using bash cat with heredoc:

```bash
# First chunk — create file
cat > OUTPUT_PATH << 'SRTEOF'
1
00:00:04,000 --> 00:00:07,880
Сьогодні ми зібралися тут, щоб провести Пуджу Шрі Ґанеші.

2
00:00:07,960 --> 00:00:12,000
Першим Божеством, створеним Аді Шакті, був Шрі Ґанеша.
SRTEOF

# Subsequent chunks — APPEND
cat >> OUTPUT_PATH << 'SRTEOF'

51
00:05:30,000 --> 00:05:34,200
Наступний блок.
SRTEOF
```

### Step 3 — Validate
After all chunks are written, run the validation script (command will be provided).

## Timing rules
- Use EN subtitle start/end times as the primary reference for WHEN speech occurs
- Use whisper word timestamps to refine timing within sentences (precise start/end of phrases)
- When the Ukrainian text is longer than English, extend the subtitle into silence AFTER speech
- Never start a subtitle before the corresponding speech begins
- Keep subtitle on screen at least 1.2s even for short phrases

## Readability rules
- **CPS** (characters per second): target ≤15, hard maximum ≤20
- **CPL** (characters per line): max 42
- **Block duration**: 1.2s — 7.0s
- **Gap between blocks**: min 80ms (2 frames at 24fps)
- **Single line** per subtitle block (no line breaks within text)
- If CPS is too high, extend subtitle display up to 2s beyond speech end into silence
- Break text at: sentence end > comma/dash > conjunction > preposition
- Never break mid-word

## Text splitting strategy
When a Ukrainian sentence is too long for one subtitle block (would exceed CPS or CPL limits):
1. Split at sentence boundaries first (period, exclamation, question mark)
2. Then at clause boundaries (comma, em-dash, semicolon)
3. Then at conjunction boundaries (що, який, і, та, але, бо, коли, де, як, або, якщо)
4. Then at preposition boundaries (в, у, на, з, від, до, для, без, через, після)
5. Each resulting block gets a proportional share of the original time range

## Language rules
- **Shri Mataji pronouns**: always uppercase (Я/Мені/Мій/Моя/Вона/Її/Їй)
- **Individual deity/incarnation singular**: uppercase (Він/Його/Йому)
- **Incarnations plural mid-sentence**: lowercase (вони/їм/їх)
- **Ukrainian quotes**: «»
- **Em-dash** with spaces: ` — `
- **Ellipsis**: `...` (three dots, no space before)

## Critical requirements
- Use **ALL** Ukrainian text — every word must appear exactly once in the output
- Keep text order matching speech order
- Timecodes must be sequential and non-overlapping
- SRT blocks must be numbered sequentially starting from 1
- Maintain continuity between chunks (remember last block number and timecode for next chunk)
- Do not use TodoWrite — this runs in CI, no one sees progress updates
