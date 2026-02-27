# Subtitle Builder — Agent Instructions

You are building Ukrainian subtitles for a Sahaja Yoga lecture video.
You must craft EVERY subtitle block manually — understanding the meaning,
reading the precise word timestamps, and making intelligent decisions.

## CRITICAL RULES (read before anything else)

1. **NO SCRIPTS** — NEVER write a Python or bash script to generate subtitles.
   YOU are the builder. A script cannot understand meaning or judge where a
   phrase naturally breaks. YOU can. That is why you exist in this pipeline.

2. **NEVER MODIFY TEXT** — Copy Ukrainian text EXACTLY from transcript_uk.txt.
   Do not paraphrase, reword, or "improve" anything. Not a single word.
   Your job is TIMING and SPLITTING, not editing the translation.

3. **MAX 42 CHARACTERS PER BLOCK** — This is an absolute hard limit.
   Every subtitle block must be ≤42 characters. No exceptions.
   Count the characters BEFORE writing. If a phrase is longer — SPLIT it.
   A typical 45-minute talk needs **600-700 blocks**, NOT 400-500.

## Hard limits (memorize these)

| Parameter | Value                            | Notes                                 |
|-----------|----------------------------------|---------------------------------------|
| CPL (chars per line) | **≤42**                          | Hard maximum. Count before writing!   |
| CPS (chars per second) | target **≤15**, hard max **≤20** | `chars / duration_seconds`            |
| Block duration | **1.2s — 15.0s**                 | Min 1200ms, max 15000ms               |
| Gap between blocks | **≥80ms**                        | 2 frames at 24fps                     |
| Lines per block | **1**                            | Single line only, no `\n` in text     |
| Text | **EXACT copy**                   | Every word from transcript, unchanged |

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
4. **Craft each UK subtitle block** (see "How to craft a block" below)
5. **Self-check EVERY block** before writing:
   - Count characters — must be ≤42
   - Calculate CPS = chars / duration_seconds — must be ≤15 (≤20 hard max)
   - Check duration — must be 1.2s–15.0s
   - Check gap to previous block — must be ≥80ms
6. **Write the chunk** via bash cat heredoc (see Output format below)

**The key principle: each UK subtitle must appear on screen when the viewer
hears the corresponding words in the original speech. Not before, not after.
Use whisper word timestamps to achieve this precision.**

### How to craft a block

For each piece of Ukrainian text:

1. **Find corresponding English words** in the EN subtitles at this point
2. **Find those English words in whisper.json** → get word-level start/end timestamps
3. **Set timing:**
   - Start = first corresponding whisper word start time
   - End = last corresponding whisper word end time
4. **Check text length** — if >42 chars, SPLIT (see "Where to split" below)
5. **Check CPS** = chars / ((end - start) / 1000):
   - If CPS > 15: extend end into silence after speech (up to next block start minus 80ms)
   - If CPS still > 20 after extending: the text is too long, split into more blocks
6. **Check duration:**
   - If < 1.2s: extend end into silence (don't exceed 15s)
   - If > 15.0s: split into multiple blocks at natural text boundaries

### Where to split text (priority order)

When text exceeds 42 chars or CPS/duration limits, split at the BEST point:

1. **Sentence boundary** — after `.` `!` `?` (highest priority, cleanest break)
2. **Clause boundary** — after `,` `;` `:` `—` (good, natural pause)
3. **Before a conjunction** — що, який, яка, яке, які, і, та, але, бо, тому,
   коли, де, як, ні, або, чи, адже, проте, однак, якщо, хоча
4. **Before a preposition** — в, у, на, з, із, від, до, для, без, через,
   після, перед, між, під, над, за, при, про, по
5. **At any word boundary** — last resort, prefer a balanced split near the middle

**NEVER** break mid-word. Each resulting piece gets its own timing from whisper.

### Splitting example

Ukrainian text: `Але якщо ви поважаєте її, тому що вона несе в собі невинність,` (63 chars)
This is way over 42 chars. Split at the comma after `її`:
- Block A: `Але якщо ви поважаєте її,` (26 chars) — timed to "But if you respect her,"
- Block B: `тому що вона несе в собі невинність,` (36 chars) — timed to "because she carries innocence,"

Each block gets its timing from the whisper word timestamps for the corresponding English words.

### What NOT to do

- **DON'T** put 60-80 chars in one block — ALWAYS split at ≤42
- **DON'T** guess timings — ALWAYS look up whisper word timestamps
- **DON'T** change any words from the transcript
- **DON'T** merge multiple sentences into one block if it exceeds 42 chars
- **DON'T** create blocks shorter than 1.2s unless there's no room to extend
- **DON'T** create blocks longer than 15.0s — split them

### Output format

```bash
# First chunk — create file
cat > OUTPUT_PATH << 'SRTEOF'
1
00:00:04,000 --> 00:00:06,500
Сьогодні ми зібралися тут,

2
00:00:06,580 --> 00:00:09,200
щоб провести Пуджу Шрі Ґанеші.

3
00:00:09,280 --> 00:00:12,000
Першим Божеством, створеним Аді Шакті,

4
00:00:12,080 --> 00:00:14,500
був Шрі Ґанеша.
SRTEOF

# Subsequent chunks — APPEND
cat >> OUTPUT_PATH << 'SRTEOF'

51
00:05:30,000 --> 00:05:34,200
Наступний блок.
SRTEOF
```

Notice: every block is well under 42 chars. Short blocks are OK and expected.

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

If validation shows:
- **CPL > 42**: Find and split the offending blocks (you miscounted characters)
- **CPS > 15**: Extend block into silence, or split if text is too long
- **CPS > 20**: Must split the block — text is too dense for its time slot
- **Duration < 1.2s**: Extend end into silence
- **Duration > 15.0s**: Split block at a natural text boundary
- **Gap < 80ms**: Adjust end of previous block (end = next_start - 80)
- **Text mismatch**: You changed or lost words — fix to match transcript exactly

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
- Maintain continuity between chunks (remember last block number and timecode)
- **NEVER write a script** — you craft each block yourself
- Do not use TodoWrite — this runs in CI, no one sees progress updates