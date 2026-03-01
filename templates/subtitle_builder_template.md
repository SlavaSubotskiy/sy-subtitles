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
2. **EN_SRT** — English subtitles (path provided in prompt)
3. **WHISPER_JSON** — word-level timestamps (path provided in prompt)

### Querying EN blocks with whisper timestamps

Use the `builder_data` tool to query EN blocks with whisper word timestamps.
All timestamps are already in SRT format (`HH:MM:SS,mmm`) — copy directly.

```bash
# Overview — block count, time range
python -m tools.builder_data info --en-srt EN_SRT --whisper-json WHISPER_JSON

# Query blocks in range (use before each chunk)
python -m tools.builder_data query --en-srt EN_SRT --whisper-json WHISPER_JSON --from 1 --to 50

# Search by English text
python -m tools.builder_data search --en-srt EN_SRT --whisper-json WHISPER_JSON --text "Shri Ganesha"
```

Output format:
```
=== #1 ===
Text: Today we have gathered here to do the Puja of Shri Ganesha.
Timing: 00:01:20,100 → 00:01:27,800
Words: Today 00:01:20,100→00:01:20,400 | we 00:01:20,450→00:01:20,600 | ... | Ganesha. 00:01:23,250→00:01:23,800
```

- **Timing** line = recommended display range (start of speech → extended into silence for readability)
- **Words** line = per-word `start→end` times (use END time when setting block boundaries)

## Process

### Step 1 — Read inputs and get overview
- Read `transcript_uk.txt` — the text you'll be placing as subtitles
- Run `builder_data info` to get block count, time range, and talk boundary:
  ```bash
  python -m tools.builder_data info --en-srt EN_SRT --whisper-json WHISPER_JSON
  ```
- Note the EN SRT end time — your UK SRT must NOT extend beyond it

**CRITICAL — Talk boundary:**
The whisper.json may cover a much longer recording than the actual talk (e.g., a 2-hour
puja ceremony where the talk is only 46 minutes). The `builder_data` tool automatically
limits to EN SRT block range — but your UK SRT must NOT extend beyond the last EN block.

### Step 2 — Split Ukrainian text into sentences

Before building, mentally split transcript_uk.txt into **sentences** (split at `.` `!` `?`).
Each sentence is your atomic work unit. You will process them one by one, in order.

A sentence is typically 20-150 characters. If a sentence is ≤84 chars, it becomes
one subtitle block. If >84 chars, you split it further (see splitting rules).

### Step 3 — Build subtitles sentence by sentence

Work through the talk in **~5-minute time chunks** for output, but your mental
unit is always **one Ukrainian sentence at a time**.

#### Before each chunk — query builder_data

Before building each ~50-block chunk, query the relevant EN blocks:
```bash
python -m tools.builder_data query --en-srt EN_SRT --whisper-json WHISPER_JSON --from N --to M
```
This gives you EN text + whisper-based timing for each block, already in SRT format.

If you need to find which EN blocks correspond to a Ukrainian phrase, use:
```bash
python -m tools.builder_data search --en-srt EN_SRT --whisper-json WHISPER_JSON --text "some english phrase"
```

#### Algorithm for each sentence:

1. **Find the corresponding EN blocks** — from the `builder_data query` output,
   identify which EN blocks carry the same meaning as this Ukrainian sentence
2. **Use the Timing line directly** from builder_data output:
   - Block **start** = start time from the first corresponding EN block's `Timing`
   - Block **end** = end time from the last corresponding EN block's `Timing`
   - The Timing line already includes silence padding — use it as-is
   - **NEVER use word START time as block end** — always use the word's END time (after →)
   - For splitting: use the **Words** line `start→end` to set each piece's boundaries
3. **Check length:**
   - If ≤84 chars → one block with the timing from step 2
   - If >84 chars → **split** into pieces (see splitting rules), each piece
     gets timing from the Words `end` time of its last corresponding English word
4. **Check CPS** (chars ÷ duration):
   - If CPS >15 → extend `end` further into silence (up to next block start − 80ms)
   - If CPS still >15 → shift neighboring blocks (see time shifting below)
   - If CPS >20 → must split the block further
5. **Check duration:**
   - If <1.2s → extend `end` into silence
6. **Write the block(s)** to output via bash `cat` heredoc

After processing ~50 EN SRT blocks worth of sentences, write that chunk.
Then continue with the next chunk.

**IMPORTANT — chunk boundary rule:** Before writing the first block of a new chunk,
verify that its `start` time is ≥ previous block's `end` + 80ms. If whisper gives
an earlier timestamp, adjust the new block's `start` = previous `end` + 80ms.
Overlaps between chunks are a common mistake — always check!

#### Concrete example

Ukrainian sentence: `Сьогодні ми зібралися тут, щоб провести Пуджу Шрі Ґанеші.`

builder_data output for the corresponding EN block:
```
=== #1 ===
Text: Today we have gathered here to do the Puja of Shri Ganesha.
Timing: 00:01:20,100 → 00:01:27,800
Words: Today 00:01:20,100→00:01:20,400 | ... | Ganesha. 00:01:23,250→00:01:23,800
```

→ Use the **Timing** line directly: start `00:01:20,100`, end `00:01:27,800`
→ The end includes silence padding (speech ends at 00:01:23,800, next speech at 00:01:27,880)
→ Text: 57 chars, duration: 7.7s → CPS = 7.4 → Excellent readability

Result:
```
1
00:01:20,100 --> 00:01:27,800
Сьогодні ми зібралися тут, щоб провести Пуджу Шрі Ґанеші.
```

If the sentence were 90 chars, you'd split at a comma and use the **Words** line
to find each piece's end time (the time AFTER → for the last word of each piece).

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

Each piece gets its own timing: start = word START (before →), end = word END (after →).

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