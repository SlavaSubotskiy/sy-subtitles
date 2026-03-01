# Subtitle Builder — Agent Instructions

You are building a **mapping table** for Ukrainian subtitles.
Your mapping will be processed by `build_srt.py` which adds padding, enforces gaps, and formats the final SRT.

**Your job: semantic alignment and splitting only.**

## CRITICAL RULES

1. **NO SCRIPTS** — NEVER write Python/bash scripts to generate or fix mapping content.
   YOU craft each line yourself via bash `cat` heredoc.
   You MAY use `python3 -c` ONLY to **read and print** data.

2. **NO PIPELINE TOOLS** — NEVER run `tools/align_uk.py` or `tools/optimize_srt.py`.

3. **NEVER MODIFY TEXT** — Copy Ukrainian text EXACTLY from transcript_uk.txt.
   Not a single word changed. Your job is TIMING and SPLITTING only.

4. **MAX 84 CHARACTERS PER LINE** — absolute hard limit, no exceptions. Count before writing!

## What you control

| Parameter | Limit | Your responsibility |
|-----------|-------|---------------------|
| CPL | **≤ 84** | Split long sentences |
| Text | **exact** | Copy from transcript, every word once |
| Timing | **speech range** | From whisper word timestamps |

## What the script handles (NOT you)

- Padding (extending end into silence for readability)
- Gap enforcement (≥ 80ms between blocks)
- Duration enforcement (≥ 1.2s minimum)
- SRT formatting and numbering

## Inputs

1. **transcript_uk.txt** — Ukrainian translation (one paragraph per line)
2. **EN_SRT** — English subtitles (path provided in prompt)
3. **WHISPER_JSON** — word-level timestamps (path provided in prompt)

### Querying EN blocks with whisper timestamps

```bash
# Overview — block count, time range
python -m tools.builder_data info --en-srt EN_SRT --whisper-json WHISPER_JSON

# Query blocks in range
python -m tools.builder_data query --en-srt EN_SRT --whisper-json WHISPER_JSON --from 1 --to 50

# Search by English text
python -m tools.builder_data search --en-srt EN_SRT --whisper-json WHISPER_JSON --text "Shri Ganesha"
```

Output format:
```
=== #1 ===
Text: Today we have gathered here to do the Puja of Shri Ganesha.
Timing: 00:01:20,100 → 00:01:23,800
Words: Today 00:01:20,100→00:01:20,400 | we 00:01:20,450→00:01:20,600 | ... | Ganesha. 00:01:23,250→00:01:23,800
```

- **Timing** line = pure speech range (first word start → last word end)
- **Words** line = per-word `start→end` (use END time after → for block boundaries)

## Output format — Mapping table

Output a pipe-separated mapping via `cat` heredoc:

```
block# | start_timecode | end_timecode | ukrainian_text
```

Timecodes = **speech boundaries** from whisper. The script adds padding later.

```bash
# First chunk — create file
cat > OUTPUT_PATH << 'MAPEOF'
1 | 00:01:20,100 | 00:01:23,800 | Сьогодні ми зібралися тут, щоб провести Пуджу Шрі Ґанеші.
2 | 00:01:37,500 | 00:01:43,250 | Першим Божеством, створеним Аді Шакті, був Шрі Ґанеша,
3 | 00:01:43,250 | 00:01:52,600 | тому що спочатку необхідно було створити Божество принципів.
MAPEOF

# Subsequent chunks — APPEND
cat >> OUTPUT_PATH << 'MAPEOF'
51 | 00:05:30,000 | 00:05:34,200 | Наступний блок.
MAPEOF
```

## Process

### Step 1 — Read inputs and get overview
- Read `transcript_uk.txt`
- Run `builder_data info` to get block count and time range
- Note the EN SRT end time — your mapping must NOT extend beyond it

### Step 2 — Build mapping sentence by sentence

Work through the talk in **~50-block chunks**.

**Before each chunk**, query the relevant EN blocks:
```bash
python -m tools.builder_data query --en-srt EN_SRT --whisper-json WHISPER_JSON --from N --to M
```

#### For each Ukrainian sentence:

1. **Find corresponding EN blocks** — which EN blocks carry the same meaning
2. **Set timing from whisper:**
   - Block **start** = start time from first corresponding EN block's `Timing` (before →)
   - Block **end** = end time from last corresponding EN block's `Timing` (after →)
   - **NEVER use word START time as block end** — always use the word's END time (after →)
   - For splitting: use **Words** line `end` times to set each piece's boundaries
3. **Check length:**
   - If ≤ 84 chars → one mapping line
   - If > 84 chars → split (see splitting rules below)
4. **Write the mapping line(s)**

#### Concrete example

Ukrainian sentence: `Сьогодні ми зібралися тут, щоб провести Пуджу Шрі Ґанеші.`

builder_data output:
```
=== #1 ===
Text: Today we have gathered here to do the Puja of Shri Ganesha.
Timing: 00:01:20,100 → 00:01:23,800
Words: Today 00:01:20,100→00:01:20,400 | ... | Ganesha. 00:01:23,250→00:01:23,800
```

→ Use Timing line: start `00:01:20,100`, end `00:01:23,800`

Mapping line:
```
1 | 00:01:20,100 | 00:01:23,800 | Сьогодні ми зібралися тут, щоб провести Пуджу Шрі Ґанеші.
```

### Splitting rules (when text > 84 chars)

Split at the BEST point, in priority order:

1. **Sentence boundary** — after `.` `!` `?`
2. **Clause boundary** — after `,` `;` `:` `—`
3. **Before a conjunction** — що, який, яка, яке, які, і, та, але, бо, тому, коли, де, як, ні, або, чи, адже, проте, однак, якщо, хоча
4. **Before a preposition** — в, у, на, з, із, від, до, для, без, через, після, перед, між, під, над, за, при, про, по
5. **Any word boundary** — near the middle, as last resort

Each piece gets its own timing from the Words line end times.

### Multi-video talks

After building the mapping for the FIRST video, handle remaining videos:
1. Detect offset:
   ```bash
   python -m tools.offset_srt detect \
     --srt1 "TALK/FIRST_VIDEO/source/en.srt" \
     --srt2 "TALK/NEXT_VIDEO/source/en.srt"
   ```
2. If offset detected — apply it to the BUILT SRT (not the mapping):
   ```bash
   python -m tools.offset_srt apply \
     --srt "TALK/FIRST_VIDEO/final/uk.srt" \
     --offset-ms OFFSET \
     --output "TALK/NEXT_VIDEO/final/uk.srt"
   ```
3. If no offset (different content) — build a separate mapping from scratch.
4. Validate ALL output SRT files.

### Step 3 — Build SRT from mapping

After writing the complete mapping, run:
```bash
python -m tools.build_srt \
  --mapping "OUTPUT_PATH" \
  --output "SRT_OUTPUT_PATH" \
  --report "REPORT_PATH"
```

This produces the final SRT with padding, gaps, and proper formatting.

### Step 4 — Validate

Run the validation script (command will be provided).

**Once validation passes with zero failures, STOP.**

If validation fails:
- **Text mismatch** → fix mapping text to match transcript exactly
- **CPL > 84** → split the offending block in mapping
- **CPS > 20** → split or adjust timing in mapping
- Then re-run `build_srt` and validate again.

**NEVER write SRT directly. Always go through the mapping → build_srt pipeline.**

## Critical requirements

- Use **ALL** Ukrainian text — every word exactly once
- Keep text order matching speech order
- Blocks numbered sequentially from 1
- Maintain continuity between chunks (last block number)
- Do not use TodoWrite — this runs in CI
