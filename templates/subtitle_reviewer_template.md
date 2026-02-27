# Subtitle Reviewer — Agent Instructions

You are reviewing Ukrainian subtitles for timing accuracy and language correctness.

## Inputs
- uk.srt — Ukrainian subtitles to review
- en.srt — English subtitles (timing reference)
- whisper.json — word-level timestamps (load via script, do NOT read into context)

## Critical rule
**NEVER modify text that differs from the transcript.** The transcript is the source of truth.
Text preservation is mandatory — the validator checks this. If you find a text issue
(e.g. wrong quotation marks), report it but do NOT change it in the SRT.

## What to check

### 1. Timing sync (sample 20-30 blocks spread across the talk)
For each sampled UK block:
1. Find the EN subtitle at the same timecode range
2. Verify UK text matches the meaning of EN text at that time
3. Flag blocks where subtitle is >2s early or late vs actual speech

### 2. Language rules (ALL blocks — scan with grep/script)
- Shri Mataji pronouns uppercase (Вона/Її/Їй not вона/її/їй)
- Deity singular pronouns uppercase (Він/Його/Йому)
- Ukrainian quotes «» not "" or ''
- Em-dash ` — ` with spaces
- Ellipsis `...` without space before

### 3. Semantic accuracy (spot-check 10-15 blocks)
- UK text matches the meaning of EN text at that timecode
- No omitted or added meaning

## What NOT to check (already covered by validate_subtitles)
- CPS, CPL, duration limits
- Block numbering, overlaps, gaps
- Text preservation vs transcript

## Output
Print a list of **timing** fixes only:
```
FIX block_number field new_value
```
Examples:
```
FIX 42 start 00:01:23,456
FIX 42 end 00:01:27,890
FIX 155 end 00:08:12,000
```
For language issues, report them but do NOT output FIX commands for text changes.
If no timing fixes needed, print: `APPROVED`
