# Subtitle Reviewer — Agent Instructions

You are reviewing Ukrainian subtitles for timing accuracy and readability.

## Inputs
- uk.srt — Ukrainian subtitles to review
- en.srt — English subtitles (timing reference)
- whisper.json — word-level timestamps (read in portions)

## Review Process

### Check timing sync (ALL blocks)
Read the full uk.srt and en.srt. For each UK block:
1. Find the EN subtitle at the same timecode range
2. Verify UK text matches the meaning of EN text at that time
3. Use whisper.json word timestamps to verify subtitle appears when speech happens
4. Flag blocks where subtitle is >2s early or late vs actual speech

### Check readability (ALL blocks)
For every block check:
- CPS > 18 — suggest extending into silence or splitting
- CPL > 42 — suggest shorter text break
- Duration < 1.2s — suggest merging with neighbor
- Text that breaks mid-phrase awkwardly
- Orphan words (1-2 word blocks that should merge with previous)

### Check language rules (ALL blocks)
- Shri Mataji pronouns uppercase (Вона/Її/Їй not вона/її/їй)
- Deity singular pronouns uppercase (Він/Його/Йому)
- Ukrainian quotes «» not ""
- Em-dash ` — ` with spaces
- Ellipsis `...` without space before

## Output
Print a list of fixes in format:
```
FIX block_number field new_value
```
Examples:
```
FIX 42 start 00:01:23,456
FIX 42 end 00:01:27,890
FIX 42 text Виправлений текст блоку.
FIX 155 end 00:08:12,000
```
If no fixes needed, print: `APPROVED`
