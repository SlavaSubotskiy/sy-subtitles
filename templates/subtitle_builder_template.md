# Subtitle Builder — Agent Instructions

You are building Ukrainian subtitles for a Sahaja Yoga lecture video.
You must craft EVERY subtitle block manually — understanding the meaning,
reading the precise word timestamps, and making intelligent decisions.

## CRITICAL RULES

1. **NO SCRIPTS** — NEVER write a Python or bash script to generate subtitles.
   YOU craft each block yourself via bash cat heredoc.

2. **NEVER MODIFY TEXT** — Copy Ukrainian text EXACTLY from transcript_uk.txt.
   Not a single word changed. Your job is TIMING and SPLITTING only.

3. **MAX 84 CHARACTERS PER BLOCK** — absolute hard limit, no exceptions.
   A typical 45-minute talk needs **500-700 blocks**.

## Hard limits

| Parameter | Value | Quick reference |
|-----------|-------|-----------------|
| CPL | **≤84** | Single line. Count before writing! |
| CPS | target **≤15**, hard max **≤20** | 40ch→2.7s, 60ch→4.0s, 84ch→5.6s min |
| Duration | **1.2s — 15.0s** | Short sentence on slow speech can stay long |
| Gap | **≥80ms** | Between every pair of blocks |
| Lines | **1** | Single line, no `\n` in text |

## Inputs

1. **transcript_uk.txt** — Ukrainian translation (one paragraph per line)
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
- Read `whisper.json` in portions — **50 segments at a time**
  (300-600KB total — read first 50, then next 50, etc.)

### Step 2 — Build subtitles chunk by chunk

Process the talk in **~5-minute time chunks** (~50 EN SRT blocks per chunk).

#### Algorithm for each chunk:

1. **Take EN subtitles** in this time range (e.g. blocks 1-50, timecodes 00:00-05:00)
2. **Take whisper word timestamps** for the same time range
3. **Take the corresponding Ukrainian text** — go through transcript_uk.txt
   in order, matching each EN block's meaning to the next unplaced UK text
4. **For each piece of UK text, craft a subtitle block:**

   a. Find the EN words that correspond to this UK phrase
   b. Look up those EN words in whisper.json → get `start` and `end` timestamps
   c. Set block **start** = whisper start of first corresponding EN word
   d. Set block **end** = whisper end of last corresponding EN word
   e. If text is >84 chars → **split** (see splitting rules below)
   f. If CPS >15 → extend end into silence (up to next block start minus 80ms)
   g. If CPS still >15 after extending → **shift neighboring blocks** (see below)
   h. If duration <1.2s → extend end into silence

5. **Verify the chunk** mentally: all blocks ≤84 chars? CPS reasonable? Gaps ≥80ms?
6. **Write the chunk** via bash cat heredoc

#### Time shifting for fast speech

When speech is very fast, a subtitle block may have high CPS even after extending
into silence. In this case, you MAY shift the timing of the current block and its
neighbors to ensure comfortable reading:

- **Shift a block earlier** — start it before the speech begins (up to 1-2s early),
  borrowing display time from silence before the speech
- **Shift a block later** — let it stay on screen after the speech ends,
  extending into the next silence gap
- **Compress neighboring blocks** — if a neighbor has very low CPS (lots of spare
  time), shorten its display to give more time to the dense block next to it

The goal: **CPS ≤15 everywhere**. It is acceptable for a subtitle to appear
slightly before or after its exact speech moment if this ensures the viewer
can comfortably read it. Readability takes priority over millisecond precision.

#### Sentence integrity principle

**Prefer blocks that start and end on sentence boundaries.**
If only 1-2 words remain until the end of a sentence, include them in the
current block (if ≤84 chars). Do NOT carry orphan endings into the next block.

Good: `І ось що Я хочу вам сказати.` (29ch — full sentence fits)
Bad:  `І ось що Я хочу вам` + `сказати.` (orphan word)

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

**Example:** `Але якщо ви поважаєте її, тому що вона несе в собі невинність,` (63ch)
Split at comma after `її`:
- `Але якщо ви поважаєте її,` (26ch) → timed to whisper for "But if you respect her,"
- `тому що вона несе в собі невинність,` (36ch) → timed to "because she carries innocence,"

### Output format

```bash
# First chunk — create file
cat > OUTPUT_PATH << 'SRTEOF'
1
00:01:21,109 --> 00:01:24,500
Сьогодні ми зібралися тут,

2
00:01:24,580 --> 00:01:28,832
щоб провести Пуджу Шрі Ґанеші.

3
00:01:28,912 --> 00:01:34,200
Першим Божеством, створеним Аді Шакті, був Шрі Ґанеша.
SRTEOF

# Subsequent chunks — APPEND
cat >> OUTPUT_PATH << 'SRTEOF'

51
00:05:30,000 --> 00:05:34,200
Наступний блок.
SRTEOF
```

Block 3 keeps the full sentence together (55 chars, within 84 limit).

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

### Step 3 — Validate

Run the validation script (command will be provided).

**Once validation passes with zero failures, STOP.**

If validation fails:
- **CPL > 84** → split the offending blocks
- **CPS > 15** → extend end into silence, or split
- **CPS > 20** → must split
- **Duration < 1.2s** → extend end
- **Gap < 80ms** → adjust previous block end (= next_start - 80)
- **Text mismatch** → you changed or lost words, fix to match transcript

## Critical requirements

- Use **ALL** Ukrainian text — every word exactly once
- Keep text order matching speech order
- Timecodes sequential and non-overlapping
- Blocks numbered sequentially from 1
- Maintain continuity between chunks (last block number + timecode)
- Do not use TodoWrite — this runs in CI