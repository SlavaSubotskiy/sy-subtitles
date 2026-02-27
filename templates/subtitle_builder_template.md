# Subtitle Builder — Agent Instructions

You are building Ukrainian subtitles for a Sahaja Yoga lecture video.
You must craft EVERY subtitle block manually — understanding the meaning,
reading the precise word timestamps, and making intelligent decisions.

## CRITICAL: NO scripts

**NEVER write a Python or bash script to generate subtitles programmatically.**
YOU are the builder. You read the inputs, understand the content, and write
each SRT block yourself via bash cat heredoc. That is your entire purpose.
A script cannot understand meaning, cannot judge where a phrase naturally breaks,
cannot feel the rhythm of speech. YOU can. That is why you exist in this pipeline.

## Inputs
You will be given paths to three files per video:
1. **transcript_uk.txt** — Ukrainian translation (per-talk, one paragraph per line)
2. **en.srt** — English subtitles (per-video, timing reference)
3. **whisper.json** — English speech recognition with word timestamps (per-video, large file)

## Process

### Step 1 — Read inputs
- Read `en.srt` fully (50-80KB, fits in ~2 reads)
- Read `transcript_uk.txt` — the Ukrainian text you'll be placing as subtitles
- Read `whisper.json` in portions — segments in batches of 50
  (The file is 300-600KB. Read first 50 segments, then next 50, etc.)
  You NEED the word-level timestamps to time each subtitle correctly.

### Step 2 — Build subtitles chunk by chunk

Process the talk in ~5-minute time chunks. For each chunk:

1. **Look at EN subtitles** in this time range — they tell you WHAT is said and WHEN
2. **Look at whisper word timestamps** for this range — they tell you the EXACT moment
   each word starts and ends (more precise than EN SRT boundaries)
3. **Find the corresponding Ukrainian text** — match by meaning and order
4. **Craft each UK subtitle block:**
   - Start time = when the corresponding English speech BEGINS (from whisper word timestamps)
   - End time = when the speech ENDS, or extend into silence if UK text is longer
   - Text = a natural, readable piece of the Ukrainian translation (max 42 chars)
   - If one EN block maps to multiple UK blocks, split at natural phrase boundaries
     and distribute time based on where each phrase is actually spoken
5. **Write the chunk** via bash cat heredoc (see format below)

**The key principle: each UK subtitle must appear on screen when the viewer
hears the corresponding words in the original speech. Not before, not after.
Use whisper word timestamps to achieve this precision.**

### How to time a subtitle block

For each piece of Ukrainian text, find the corresponding English words, then:
1. Find those words in whisper.json → get their start/end timestamps
2. UK block start = first corresponding whisper word start time
3. UK block end = last corresponding whisper word end time
4. If UK text is longer and CPS would exceed 15, extend end into silence (up to 2s after speech)
5. Ensure min 80ms gap to the next block

Example: EN block says "Today we have gathered here to do Shri Ganesha Puja."
Whisper shows: "Today" starts 00:01:21.109, "Puja" ends 00:01:28.832.
You split UK into two blocks:
- "Сьогодні ми зібралися тут," → 00:01:21,109 --> 00:01:24,500 (where "here" ends in whisper)
- "щоб провести Пуджу Шрі Ґанеші." → 00:01:24,580 --> 00:01:28,832

### Output format

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

### Multi-video talks
This talk may have multiple videos (check meta.yaml). Often they contain
the same content with a time offset (e.g., full puja video vs talk-only cut).

After building subtitles for the FIRST video:
1. For each additional video, detect offset:
   ```bash
   python -m tools.offset_srt detect \
     --srt1 "TALK/FIRST_VIDEO/source/en.srt" \
     --srt2 "TALK/NEXT_VIDEO/source/en.srt"
   ```
2. If offset detected — apply it:
   ```bash
   python -m tools.offset_srt apply \
     --srt "TALK/FIRST_VIDEO/final/uk.srt" \
     --offset-ms OFFSET \
     --output "TALK/NEXT_VIDEO/final/uk.srt"
   ```
3. If no offset (different content) — build from scratch as usual.
4. Validate ALL output SRT files.

### Step 3 — Validate
After all chunks are written, run the validation script (command will be provided).

**IMPORTANT: Once validation passes with zero failures, STOP. Do not rebuild for marginal improvements.**

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
5. Time each resulting block to when its corresponding words are actually spoken (from whisper)

## Language rules
- **Shri Mataji pronouns**: always uppercase (Я/Мені/Мій/Моя/Вона/Її/Їй)
- **Individual deity/incarnation singular**: uppercase (Він/Його/Йому)
- **Incarnations plural mid-sentence**: lowercase (вони/їм/їх)
- **Ukrainian quotes**: «» at ALL levels (nested quotes also «», NEVER „" or "")
- **Em-dash** with spaces: ` — `
- **Ellipsis**: `...` (three dots, no space before)

## Critical requirements
- Use **ALL** Ukrainian text — every word must appear exactly once in the output
- Keep text order matching speech order
- Timecodes must be sequential and non-overlapping
- SRT blocks must be numbered sequentially starting from 1
- Maintain continuity between chunks (remember last block number and timecode for next chunk)
- **NEVER write a script** — you craft each block yourself
- Do not use TodoWrite — this runs in CI, no one sees progress updates