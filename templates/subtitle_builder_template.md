# Subtitle Builder — Agent Instructions

You are building Ukrainian subtitles for a Sahaja Yoga lecture video.
You must craft EVERY subtitle block manually — understanding the meaning,
reading the precise word timestamps, and making intelligent decisions.

## CRITICAL RULES

1. **NO SCRIPTS** — NEVER write Python/bash scripts to generate or fix SRT content.
   YOU craft each block yourself via bash `cat` heredoc.
   You MAY use `python3 -c` ONLY to **read and print** data (whisper segments, SRT stats).
   You MUST NOT use `python3 -c` to **write or modify** any SRT file.

2. **NO PIPELINE TOOLS** — NEVER run `tools/align_uk.py` or `tools/optimize_srt.py`.
   These are CI pipeline tools, not for the builder agent. You ARE the builder.

3. **NEVER MODIFY TEXT** — Copy Ukrainian text EXACTLY from transcript_uk.txt.
   Not a single word changed. Your job is TIMING and SPLITTING only.

4. **MAX 84 CHARACTERS PER BLOCK** — absolute hard limit, no exceptions.

## Hard limits

| Parameter | Value | Quick reference |
|-----------|-------|-----------------|
| CPL | **≤84** | Single line. Count before writing! |
| CPS | target **≤15**, hard max **≤20** | 40ch→2.7s, 60ch→4.0s, 84ch→5.6s min |
| Duration | **1.2s — 15.0s** | Short sentence on slow speech can stay long |
| Gap | **≥80ms** | Between every pair of blocks |
| Lines | **1** | Single line, no `\n` in text |

## Inputs

1. **transcript_uk.txt** — Ukrainian translation (one paragraph per line, sentences separated by `.` `!` `?`)
2. **en.srt** — English subtitles (timing reference)
3. **whisper.json** — word-level timestamps (large file, read in portions)

### whisper.json format

```json
{
  "segments": [
    {
      "id": 0, "start": 4.0, "end": 10.5,
      "text": "Today we have gathered here",
      "words": [
        {"word": "Today", "start": 4.0, "end": 4.3},
        {"word": "we", "start": 4.35, "end": 4.5},
        {"word": "have", "start": 4.55, "end": 4.7},
        {"word": "gathered", "start": 4.75, "end": 5.2},
        {"word": "here", "start": 5.25, "end": 5.6}
      ]
    }
  ]
}
```

Timestamps are in **seconds** (float). Convert to SRT format: `4.0` → `00:00:04,000`.

## Process

### Step 1 — Read inputs
- Read `en.srt` fully (50-80KB, fits in ~2 reads)
- Read `transcript_uk.txt` — the text you'll be placing as subtitles
- Read `whisper.json` in portions using `python3 -c` to print segment summaries:
  print each segment's id, start, end, word count, and text (first 80 chars)

### Step 2 — Split Ukrainian text into sentences

Before building, mentally split transcript_uk.txt into **sentences** (split at `.` `!` `?`).
Each sentence is your atomic work unit. You will process them one by one, in order.

A sentence is typically 20-150 characters. If a sentence is ≤84 chars, it becomes
one subtitle block. If >84 chars, you split it further (see splitting rules).

### Step 3 — Build subtitles sentence by sentence

Work through the talk in **~5-minute time chunks** for output, but your mental
unit is always **one Ukrainian sentence at a time**.

#### Algorithm for each sentence:

1. **Find the corresponding English text** — read en.srt blocks that carry
   the same meaning as this Ukrainian sentence
2. **Look up whisper word timestamps** for those English words:
   - Find the segment(s) containing these English words
   - Read the `words[]` array to get per-word `start` and `end` times
3. **Set timing from whisper words:**
   - Block **start** = `start` of the first corresponding English word
   - Block **end** = `end` of the last corresponding English word
4. **Check length:**
   - If ≤84 chars → one block with the timing from step 3
   - If >84 chars → **split** into pieces (see splitting rules), each piece
     gets timing from the whisper words that correspond to its English portion
5. **Check CPS** (chars ÷ duration):
   - If CPS >15 → extend `end` into silence (up to next block start − 80ms)
   - If CPS still >15 → shift neighboring blocks (see time shifting below)
   - If CPS >20 → must split the block further
6. **Check duration:**
   - If <1.2s → extend `end` into silence
7. **Write the block(s)** to output via bash `cat` heredoc

After processing ~50 EN SRT blocks worth of sentences, write that chunk.
Then continue with the next chunk.

**IMPORTANT — chunk boundary rule:** Before writing the first block of a new chunk,
verify that its `start` time is ≥ previous block's `end` + 80ms. If whisper gives
an earlier timestamp, adjust the new block's `start` = previous `end` + 80ms.
Overlaps between chunks are a common mistake — always check!

#### Concrete example

Ukrainian sentence: `Сьогодні ми зібралися тут, щоб провести Пуджу Шрі Ґанеші.`
Corresponding EN: "Today we have gathered here to do the Puja of Shri Ganesha."

Whisper words:
- "Today" 80.1-80.4, "we" 80.45-80.6, "have" 80.65-80.8, "gathered" 80.85-81.3,
  "here" 81.35-81.6, "to" 81.65-81.8, "do" 81.85-82.0, "the" 82.05-82.2,
  "Puja" 82.25-82.6, "of" 82.65-82.8, "Shri" 82.85-83.2, "Ganesha" 83.25-83.8

→ Block start: 80.1 (first word "Today"), end: 83.8 (last word "Ganesha")
→ Text: 57 chars, duration: 3.7s → CPS = 15.4 → OK (under hard max 20)

Result:
```
1
00:01:20,100 --> 00:01:23,800
Сьогодні ми зібралися тут, щоб провести Пуджу Шрі Ґанеші.
```

If the sentence were 90 chars, you'd split at a comma and look up which
English words correspond to each half to set per-piece timing.

#### Time shifting for fast speech

When CPS >15 even after extending into silence, you MAY shift timing:

- **Shift earlier** — start before speech begins (up to 1-2s early)
- **Shift later** — keep on screen after speech ends
- **Compress neighbors** — if a neighbor has low CPS, shorten its display

The goal: **CPS ≤15 everywhere**. Readability takes priority over millisecond precision.

#### Splitting rules (when text >84 chars)

Split at the BEST point, in priority order:

1. **Sentence boundary** — after `.` `!` `?`
2. **Clause boundary** — after `,` `;` `:` `—`
3. **Before a conjunction** — що, який, яка, яке, які, і, та, але, бо, тому,
   коли, де, як, ні, або, чи, адже, проте, однак, якщо, хоча
4. **Before a preposition** — в, у, на, з, із, від, до, для, без, через,
   після, перед, між, під, над, за, при, про, по
5. **Any word boundary** — near the middle, as last resort

Each piece gets its own timing from whisper word timestamps.

### Output format

```bash
# First chunk — create file
cat > OUTPUT_PATH << 'SRTEOF'
1
00:01:20,100 --> 00:01:23,800
Сьогодні ми зібралися тут, щоб провести Пуджу Шрі Ґанеші.

2
00:01:37,500 --> 00:01:45,980
Першим Божеством, створеним Аді Шакті, був Шрі Ґанеша,
SRTEOF

# Subsequent chunks — APPEND
cat >> OUTPUT_PATH << 'SRTEOF'

51
00:05:30,000 --> 00:05:34,200
Наступний блок.
SRTEOF
```

### Multi-video talks

After building subtitles for the FIRST video, handle remaining videos:
1. Detect offset:
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
3. If no offset (different content) — build from scratch.
4. Validate ALL output SRT files.

### Step 4 — Validate

Run the validation script (command will be provided).

**Once validation passes with zero failures, STOP.**

If validation fails, fix the specific blocks using `cat >` to rewrite the file:
- **CPL > 84** → split the offending block
- **CPS > 20** → split or extend into silence
- **Duration < 1.2s** → extend end
- **Gap < 80ms** → adjust previous block end (= next_start − 80)
- **Text mismatch** → you changed or lost words, fix to match transcript

**NEVER rewrite the entire SRT using a Python script.** Fix only the broken blocks
by rewriting the full file via heredoc with the corrections applied.

## Critical requirements

- Use **ALL** Ukrainian text — every word exactly once
- Keep text order matching speech order
- Timecodes sequential and non-overlapping
- Blocks numbered sequentially from 1
- Maintain continuity between chunks (last block number + timecode)
- Do not use TodoWrite — this runs in CI