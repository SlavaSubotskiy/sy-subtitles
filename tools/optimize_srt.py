"""SRT subtitle optimizer.

Reads a translated SRT + Whisper JSON, optimizes timing/readability,
writes optimized SRT and a report.

Usage:
    python -m tools.optimize_srt --srt PATH --json PATH --output PATH [--report PATH]
"""

import argparse
import copy
import re
import sys

from .config import OptimizeConfig
from .srt_utils import (
    calc_stats,
    format_stats,
    load_whisper_json,
    parse_srt,
    write_srt,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_best_split_point(text, max_cpl):
    """Find the best point to split a line into two balanced lines."""
    if len(text) <= max_cpl:
        return None

    mid = len(text) // 2
    conjunctions = {
        'що', 'який', 'яка', 'яке', 'які', 'і', 'та', 'але', 'бо', 'тому',
        'коли', 'де', 'як', 'ні', 'або', 'чи', 'адже', 'проте', 'однак',
        'якщо', 'хоча',
    }
    prepositions = {
        'в', 'у', 'на', 'з', 'із', 'від', 'до', 'для', 'без', 'через',
        'після', 'перед', 'між', 'під', 'над', 'за', 'при', 'про', 'по',
    }

    words = text.split(' ')
    pos = 0
    candidates = []

    for i, word in enumerate(words[:-1]):
        pos += len(word)
        line1_len = pos
        line2_len = len(text) - pos - 1

        if line1_len > max_cpl or line2_len > max_cpl:
            pos += 1
            continue

        balance = abs(line1_len - line2_len)
        priority = 4
        if word.endswith(('.', '!', '?')):
            priority = 0
        elif word.endswith((',', ';', ':')):
            priority = 1
        elif i + 1 < len(words) and words[i + 1].lower().rstrip('.,;:!?') in conjunctions:
            priority = 2
        elif i + 1 < len(words) and words[i + 1].lower().rstrip('.,;:!?') in prepositions:
            priority = 3

        score = priority * 1000 + balance
        candidates.append((score, pos))
        pos += 1

    if not candidates:
        pos = 0
        for word in words[:-1]:
            pos += len(word)
            if pos >= mid:
                return pos
            pos += 1
        return None

    candidates.sort()
    return candidates[0][1]


def split_long_line(text):
    """Single-line mode: join all lines into one."""
    return text.replace('\n', ' ')


def find_block_split_point(text):
    """Find best point to split a block's text into two blocks."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    if len(sentences) >= 2:
        mid = len(text) // 2
        pos = 0
        best_pos = None
        best_dist = float('inf')
        for s in sentences[:-1]:
            pos += len(s) + 1
            dist = abs(pos - mid)
            if dist < best_dist:
                best_dist = dist
                best_pos = pos
        if best_pos:
            return best_pos

    mid = len(text) // 2
    best_pos = None
    best_dist = float('inf')
    for m in re.finditer(r'[,;:]\s', text):
        pos = m.end()
        dist = abs(pos - mid)
        if dist < best_dist:
            best_dist = dist
            best_pos = pos
    if best_pos:
        return best_pos

    words = text.split(' ')
    pos = 0
    for w in words[:-1]:
        pos += len(w) + 1
        if pos >= mid:
            return pos

    return None


# ---------------------------------------------------------------------------
# Step 2: Compare with Whisper
# ---------------------------------------------------------------------------

def compare_with_whisper(blocks, whisper_segments, report):
    """Compare SRT timings with Whisper speech timings."""
    report.append("=" * 60)
    report.append("  STEP 2: Comparing SRT with Whisper speech timings")
    report.append("=" * 60)

    speech_intervals = [(seg['start'] * 1000, seg['end'] * 1000) for seg in whisper_segments]
    report.append(f"  Whisper segments: {len(whisper_segments)}")
    report.append(f"  SRT blocks: {len(blocks)}")

    early_starts = 0
    late_ends = 0
    for b in blocks:
        for ws, we in speech_intervals:
            if abs(b['start_ms'] - ws) < 3000:
                if b['start_ms'] < ws - 500:
                    early_starts += 1
                break
        for ws, we in speech_intervals:
            if abs(b['end_ms'] - we) < 3000:
                if b['end_ms'] > we + 2000:
                    late_ends += 1
                break

    report.append(f"  SRT blocks starting >500ms before speech: {early_starts}")
    report.append(f"  SRT blocks ending >2s after speech: {late_ends}")

    return speech_intervals


# ---------------------------------------------------------------------------
# Step 3: Structural fixes
# ---------------------------------------------------------------------------

def fix_structural(blocks, config, report):
    """Fix double spaces, leading/trailing spaces, micro-overlaps."""
    report.append("")
    report.append("=" * 60)
    report.append("  STEP 3: Fixing structural issues")
    report.append("=" * 60)

    fixes = {'double_spaces': 0, 'leading_trailing': 0, 'overlaps_fixed': 0}

    for b in blocks:
        new_text = re.sub(r'  +', ' ', b['text'])
        if new_text != b['text']:
            fixes['double_spaces'] += 1
            b['text'] = new_text

        lines = b['text'].split('\n')
        new_lines = [line.strip() for line in lines]
        new_text = '\n'.join(new_lines)
        if new_text != b['text']:
            fixes['leading_trailing'] += 1
            b['text'] = new_text

    for i in range(1, len(blocks)):
        gap = blocks[i]['start_ms'] - blocks[i - 1]['end_ms']
        if gap < 0:
            blocks[i - 1]['end_ms'] = blocks[i]['start_ms'] - config.min_gap_ms
            fixes['overlaps_fixed'] += 1
        elif 0 < gap < config.min_gap_ms:
            blocks[i - 1]['end_ms'] = blocks[i]['start_ms'] - config.min_gap_ms
            fixes['overlaps_fixed'] += 1

    report.append(f"  Fixed double spaces: {fixes['double_spaces']}")
    report.append(f"  Fixed leading/trailing spaces: {fixes['leading_trailing']}")
    report.append(f"  Fixed overlaps/tiny gaps: {fixes['overlaps_fixed']}")

    return blocks


# ---------------------------------------------------------------------------
# Step 4: Optimize readability (multi-phase)
# ---------------------------------------------------------------------------

def fix_overlaps(blocks, config):
    """Ensure min gap between blocks."""
    for i in range(1, len(blocks)):
        gap = blocks[i]['start_ms'] - blocks[i - 1]['end_ms']
        if gap < config.min_gap_ms:
            blocks[i - 1]['end_ms'] = blocks[i]['start_ms'] - config.min_gap_ms
    return blocks


def extend_cps(blocks, config):
    """Extend block durations to achieve target CPS. Returns count of extended blocks."""
    extended = 0
    for i, b in enumerate(blocks):
        chars = len(b['text'].replace('\n', ''))
        duration_s = (b['end_ms'] - b['start_ms']) / 1000.0
        cps = chars / duration_s if duration_s > 0 else 999

        if cps > config.target_cps:
            needed_duration_ms = int((chars / config.target_cps) * 1000)

            if i + 1 < len(blocks):
                max_end = blocks[i + 1]['start_ms'] - config.min_gap_ms
            else:
                max_end = b['end_ms'] + 60000

            if i > 0:
                min_start = blocks[i - 1]['end_ms'] + config.min_gap_ms
            else:
                min_start = 0

            current_duration = b['end_ms'] - b['start_ms']
            if needed_duration_ms > current_duration:
                extra_needed = needed_duration_ms - current_duration

                can_extend_end = max_end - b['end_ms']
                if can_extend_end > 0:
                    extend_end = min(extra_needed, can_extend_end)
                    b['end_ms'] += extend_end
                    extra_needed -= extend_end

                if extra_needed > 0:
                    can_extend_start = b['start_ms'] - min_start
                    if can_extend_start > 0:
                        extend_start = min(extra_needed, can_extend_start)
                        b['start_ms'] -= extend_start

                extended += 1

    return extended


def split_blocks_by_size(blocks, config):
    """Split blocks exceeding max_chars_block."""
    new_blocks = []
    splits = 0
    for b in blocks:
        text_flat = b['text'].replace('\n', ' ')
        chars = len(text_flat)
        if chars > config.max_chars_block:
            split_pos = find_block_split_point(text_flat)
            if split_pos and split_pos > 10 and (chars - split_pos) > 10:
                text1 = text_flat[:split_pos].strip()
                text2 = text_flat[split_pos:].strip()
                ratio = len(text1) / chars
                duration = b['end_ms'] - b['start_ms']
                mid_time = b['start_ms'] + int(duration * ratio)
                new_blocks.append({
                    'idx': b['idx'],
                    'start_ms': b['start_ms'],
                    'end_ms': mid_time - config.min_gap_ms // 2,
                    'text': split_long_line(text1),
                })
                new_blocks.append({
                    'idx': b['idx'],
                    'start_ms': mid_time + config.min_gap_ms // 2,
                    'end_ms': b['end_ms'],
                    'text': split_long_line(text2),
                })
                splits += 1
                continue
        new_blocks.append(b)
    return new_blocks, splits


def split_blocks_by_cps(blocks, config):
    """Split blocks with CPS above hard max."""
    new_blocks = []
    splits = 0
    for b in blocks:
        chars = len(b['text'].replace('\n', ''))
        duration_s = (b['end_ms'] - b['start_ms']) / 1000.0
        cps = chars / duration_s if duration_s > 0 else 999

        if cps > config.hard_max_cps and chars > 15:
            text_flat = b['text'].replace('\n', ' ')
            split_pos = find_block_split_point(text_flat)
            if split_pos and split_pos > 5 and (len(text_flat) - split_pos) > 5:
                text1 = text_flat[:split_pos].strip()
                text2 = text_flat[split_pos:].strip()
                ratio = len(text1) / len(text_flat)
                duration = b['end_ms'] - b['start_ms']
                mid_time = b['start_ms'] + int(duration * ratio)
                new_blocks.append({
                    'idx': b['idx'],
                    'start_ms': b['start_ms'],
                    'end_ms': mid_time - config.min_gap_ms // 2,
                    'text': split_long_line(text1),
                })
                new_blocks.append({
                    'idx': b['idx'],
                    'start_ms': mid_time + config.min_gap_ms // 2,
                    'end_ms': b['end_ms'],
                    'text': split_long_line(text2),
                })
                splits += 1
                continue
        new_blocks.append(b)
    return new_blocks, splits


def merge_short_blocks(blocks, config):
    """Merge very short adjacent blocks if combined they are within limits."""
    merged = 0
    i = 0
    new_blocks = []
    while i < len(blocks):
        b = copy.deepcopy(blocks[i])
        if i + 1 < len(blocks):
            next_b = blocks[i + 1]
            b_chars = len(b['text'].replace('\n', ''))
            next_chars = len(next_b['text'].replace('\n', ''))
            combined_chars = b_chars + next_chars + 1
            gap = next_b['start_ms'] - b['end_ms']
            b_dur = b['end_ms'] - b['start_ms']

            if b_dur < 800 and combined_chars <= config.max_chars_block and gap < 500:
                combined_text = b['text'].replace('\n', ' ') + ' ' + next_b['text'].replace('\n', ' ')
                b['end_ms'] = next_b['end_ms']
                b['text'] = split_long_line(combined_text)
                merged += 1
                i += 2
                new_blocks.append(b)
                continue

        new_blocks.append(b)
        i += 1

    return new_blocks, merged


def cascade_redistribute(blocks, config, report):
    """Steal time from neighbor blocks (up to 8 blocks away) to reduce CPS."""
    SEARCH_RADIUS = 8
    redistributed = 0

    for iteration in range(5):
        iter_redis = 0
        for i, b in enumerate(blocks):
            chars = len(b['text'].replace('\n', ''))
            dur = b['end_ms'] - b['start_ms']
            cps = chars / (dur / 1000.0) if dur > 0 else 999

            if cps <= config.target_cps:
                continue

            needed_dur = int((chars / config.target_cps) * 1000)
            extra_needed = needed_dur - dur
            if extra_needed <= 0:
                continue

            # Search backwards
            for dist in range(1, min(SEARCH_RADIUS + 1, i + 1)):
                if extra_needed <= 0:
                    break
                nb = blocks[i - dist]
                nb_chars = len(nb['text'].replace('\n', ''))
                nb_dur = nb['end_ms'] - nb['start_ms']
                nb_cps = nb_chars / (nb_dur / 1000.0) if nb_dur > 0 else 999

                if nb_cps < config.target_cps:
                    nb_min_dur = int((nb_chars / config.target_cps) * 1000)
                    nb_can_give = max(0, nb_dur - nb_min_dur - config.min_gap_ms)
                    give = min(extra_needed, nb_can_give)
                    if give > 30:
                        nb['end_ms'] -= give
                        for j in range(i - dist + 1, i):
                            blocks[j]['start_ms'] -= give
                            blocks[j]['end_ms'] -= give
                        b['start_ms'] -= give
                        extra_needed -= give
                        iter_redis += 1

            # Search forwards
            for dist in range(1, min(SEARCH_RADIUS + 1, len(blocks) - i)):
                if extra_needed <= 0:
                    break
                nb = blocks[i + dist]
                nb_chars = len(nb['text'].replace('\n', ''))
                nb_dur = nb['end_ms'] - nb['start_ms']
                nb_cps = nb_chars / (nb_dur / 1000.0) if nb_dur > 0 else 999

                if nb_cps < config.target_cps:
                    nb_min_dur = int((nb_chars / config.target_cps) * 1000)
                    nb_can_give = max(0, nb_dur - nb_min_dur - config.min_gap_ms)
                    give = min(extra_needed, nb_can_give)
                    if give > 30:
                        nb['start_ms'] += give
                        for j in range(i + 1, i + dist):
                            blocks[j]['start_ms'] += give
                            blocks[j]['end_ms'] += give
                        b['end_ms'] += give
                        extra_needed -= give
                        iter_redis += 1

        redistributed += iter_redis
        blocks = fix_overlaps(blocks, config)
        if iter_redis == 0:
            break

    if redistributed:
        report.append(f"  Phase 7 - Cascade time redistribution: {redistributed}")

    return blocks


def absorb_large_gaps(blocks, config, report):
    """Shift block chains toward large gaps to give time to high-CPS blocks."""
    GAP_SEARCH_RADIUS = 10
    gap_absorbed = 0

    for iteration in range(3):
        iter_abs = 0
        for i, b in enumerate(blocks):
            chars = len(b['text'].replace('\n', ''))
            dur = b['end_ms'] - b['start_ms']
            cps = chars / (dur / 1000.0) if dur > 0 else 999

            if cps <= config.target_cps:
                continue

            needed_dur = int((chars / config.target_cps) * 1000)
            extra_needed = needed_dur - dur
            if extra_needed <= 0:
                continue

            # Search forwards for large gaps (> 200ms)
            for dist in range(1, min(GAP_SEARCH_RADIUS + 1, len(blocks) - i)):
                if extra_needed <= 0:
                    break
                j = i + dist
                gap = blocks[j]['start_ms'] - blocks[j - 1]['end_ms']
                if gap > 200:
                    can_use = gap - config.min_gap_ms
                    give = min(extra_needed, can_use)
                    if give > 30:
                        for k in range(i + 1, j):
                            blocks[k]['start_ms'] += give
                            blocks[k]['end_ms'] += give
                        b['end_ms'] += give
                        extra_needed -= give
                        iter_abs += 1

            # Search backwards for large gaps
            for dist in range(1, min(GAP_SEARCH_RADIUS + 1, i + 1)):
                if extra_needed <= 0:
                    break
                j = i - dist
                gap = blocks[j + 1]['start_ms'] - blocks[j]['end_ms']
                if gap > 200:
                    can_use = gap - config.min_gap_ms
                    give = min(extra_needed, can_use)
                    if give > 30:
                        for k in range(j + 1, i):
                            blocks[k]['start_ms'] -= give
                            blocks[k]['end_ms'] -= give
                        b['start_ms'] -= give
                        extra_needed -= give
                        iter_abs += 1

        gap_absorbed += iter_abs
        blocks = fix_overlaps(blocks, config)
        if iter_abs == 0:
            break

    if gap_absorbed:
        report.append(f"  Phase 7b - Large gaps absorbed: {gap_absorbed}")

    return blocks


def optimize_readability(blocks, whisper_segments, config, report):
    """Multi-phase readability optimization."""
    report.append("")
    report.append("=" * 60)
    report.append("  STEP 4: Optimizing readability")
    report.append("=" * 60)

    # Phase 1: Join multi-line blocks (single-line mode)
    lines_joined = 0
    if config.single_line:
        for b in blocks:
            if '\n' in b['text']:
                b['text'] = b['text'].replace('\n', ' ')
                lines_joined += 1
    report.append(f"  Phase 1 - Lines joined (single-line mode): {lines_joined}")

    # Phase 2: Split blocks > max_chars_block
    blocks, size_splits = split_blocks_by_size(blocks, config)
    report.append(f"  Phase 2 - Blocks split (> {config.max_chars_block} chars): {size_splits}")

    # Phase 3: First CPS extension pass
    blocks = fix_overlaps(blocks, config)
    ext1 = extend_cps(blocks, config)
    report.append(f"  Phase 3 - CPS extensions (pass 1): {ext1}")

    # Phase 4: Split remaining high-CPS blocks
    blocks, cps_splits = split_blocks_by_cps(blocks, config)
    report.append(f"  Phase 4 - CPS splits (> {config.hard_max_cps}): {cps_splits}")

    # Phase 5: Merge very short blocks
    blocks, merged = merge_short_blocks(blocks, config)
    report.append(f"  Phase 5 - Merged short blocks: {merged}")

    # Phase 6: Multi-pass CPS extension (3 passes)
    blocks = fix_overlaps(blocks, config)
    for pass_num in range(3):
        ext = extend_cps(blocks, config)
        blocks = fix_overlaps(blocks, config)
        if ext == 0:
            break
        report.append(f"  Phase 6 - CPS extensions (pass {pass_num + 2}): {ext}")

    # Phase 7: Cascade redistribution
    blocks = cascade_redistribute(blocks, config, report)

    # Phase 7b: Absorb large gaps
    blocks = absorb_large_gaps(blocks, config, report)

    # Phase 7c: CPS extension after redistribution
    ext7 = extend_cps(blocks, config)
    blocks = fix_overlaps(blocks, config)
    if ext7:
        report.append(f"  Phase 7c - CPS extensions after redistribution: {ext7}")

    # Ensure single-line for blocks created by later phases
    if config.single_line:
        lines_joined2 = 0
        for b in blocks:
            if '\n' in b['text']:
                b['text'] = b['text'].replace('\n', ' ')
                lines_joined2 += 1
        if lines_joined2:
            report.append(f"  Phase 7c - Additional lines joined: {lines_joined2}")

    # Phase 8: Ensure minimum duration
    for b in blocks:
        if b['end_ms'] - b['start_ms'] < config.min_duration_ms:
            b['end_ms'] = b['start_ms'] + config.min_duration_ms

    # Phase 9: Ensure maximum duration
    for b in blocks:
        if b['end_ms'] - b['start_ms'] > config.max_duration_ms + 1000:
            b['end_ms'] = b['start_ms'] + config.max_duration_ms

    # Phase 10: Final overlap fix
    blocks = fix_overlaps(blocks, config)

    # Phase 11: Final CPS extension
    ext_final = extend_cps(blocks, config)
    blocks = fix_overlaps(blocks, config)
    if ext_final:
        report.append(f"  Phase 11 - Final CPS extensions: {ext_final}")

    return blocks


# ---------------------------------------------------------------------------
# Step 5: Chaining
# ---------------------------------------------------------------------------

def apply_chaining(blocks, config, report):
    """Close gaps of 3-11 frames to 2 frames."""
    report.append("")
    report.append("=" * 60)
    report.append("  STEP 5: Applying chaining")
    report.append("=" * 60)

    frame_ms = 1000 / config.fps
    min_chain_gap = int(3 * frame_ms)
    max_chain_gap = int(11 * frame_ms)
    target_gap = config.min_gap_ms

    chained = 0
    for i in range(1, len(blocks)):
        gap = blocks[i]['start_ms'] - blocks[i - 1]['end_ms']
        if min_chain_gap <= gap <= max_chain_gap:
            blocks[i - 1]['end_ms'] = blocks[i]['start_ms'] - target_gap
            chained += 1

    report.append(f"  Gaps chained (3-11 frames -> 2 frames): {chained}")
    return blocks


# ---------------------------------------------------------------------------
# Step 6: Validation report
# ---------------------------------------------------------------------------

def final_validation(original_blocks, optimized_blocks, config, report):
    """Produce before/after validation report."""
    report.append("")
    report.append("=" * 60)
    report.append("  STEP 6: Final validation report")
    report.append("=" * 60)

    orig_stats = calc_stats(original_blocks, config)
    opt_stats = calc_stats(optimized_blocks, config)

    orig_text = ' '.join(b['text'].replace('\n', ' ') for b in original_blocks)
    opt_text = ' '.join(b['text'].replace('\n', ' ') for b in optimized_blocks)
    orig_text_norm = re.sub(r'\s+', ' ', orig_text).strip()
    opt_text_norm = re.sub(r'\s+', ' ', opt_text).strip()

    text_preserved = orig_text_norm == opt_text_norm
    report.append(f"\n  Text preservation: {'OK' if text_preserved else 'CHANGED!'}")
    report.append(f"  Original chars: {len(orig_text_norm)}, Optimized chars: {len(opt_text_norm)}")

    report.append(f"\n  {'PARAMETER':<30} {'BEFORE':>10} {'AFTER':>10} {'CHANGE':>10}")
    report.append(f"  {'-' * 60}")

    def fmt_change(before, after, lower_better=True):
        diff = after - before
        if diff == 0:
            return "  --"
        arrow = "v" if (diff < 0) == lower_better else "^"
        sign = "+" if diff > 0 else ""
        return f" {sign}{diff}{arrow}"

    rows = [
        ("Total blocks", orig_stats['total_blocks'], opt_stats['total_blocks'], False),
        ("Avg CPS", f"{orig_stats['avg_cps']:.1f}", f"{opt_stats['avg_cps']:.1f}", True),
        ("Max CPS", f"{orig_stats['max_cps']:.1f}", f"{opt_stats['max_cps']:.1f}", True),
        ("CPS > target", orig_stats['cps_over_target'], opt_stats['cps_over_target'], True),
        ("CPS > hard max", orig_stats['cps_over_hard'], opt_stats['cps_over_hard'], True),
        ("Max CPL", orig_stats['max_cpl'], opt_stats['max_cpl'], True),
        ("CPL > max", orig_stats['cpl_over_max'], opt_stats['cpl_over_max'], True),
        ("Chars > max block", orig_stats['chars_over_max'], opt_stats['chars_over_max'], True),
        ("Lines > max", orig_stats['lines_over_max'], opt_stats['lines_over_max'], True),
        ("Duration < min", orig_stats['duration_under_min'], opt_stats['duration_under_min'], True),
        ("Overlaps", orig_stats['overlaps'], opt_stats['overlaps'], True),
        ("Gaps < min", orig_stats['gap_under_min'], opt_stats['gap_under_min'], True),
    ]

    for label, before, after, lower_better in rows:
        if isinstance(before, str):
            report.append(f"  {label:<30} {before:>10} {after:>10}")
        else:
            change = fmt_change(before, after, lower_better)
            report.append(f"  {label:<30} {before:>10} {after:>10} {change:>10}")

    # Worst CPS blocks
    report.append(f"\n  Worst CPS blocks (top 10):")
    cps_blocks = []
    for i, b in enumerate(optimized_blocks):
        chars = len(b['text'].replace('\n', ''))
        duration_s = (b['end_ms'] - b['start_ms']) / 1000.0
        cps = chars / duration_s if duration_s > 0 else 999
        cps_blocks.append((cps, i + 1, chars, duration_s, b['text'].replace('\n', ' ')[:50]))

    cps_blocks.sort(reverse=True)
    for cps, idx, chars, dur, text in cps_blocks[:10]:
        report.append(f"    #{idx}: CPS={cps:.1f} ({chars}ch/{dur:.1f}s) \"{text}\"")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def optimize(srt_path, json_path, output_path, report_path=None, config=None):
    """Run the full optimization pipeline.

    Returns the report as a list of lines.
    """
    if config is None:
        config = OptimizeConfig()

    report = []
    report.append("=" * 60)
    report.append("  SUBTITLE OPTIMIZATION SCRIPT")
    report.append("=" * 60)

    blocks = parse_srt(srt_path)
    whisper_segments = load_whisper_json(json_path)
    original_blocks = copy.deepcopy(blocks)

    orig_stats = calc_stats(blocks, config)
    report.append(format_stats(orig_stats, "ORIGINAL SRT STATISTICS"))

    compare_with_whisper(blocks, whisper_segments, report)
    blocks = fix_structural(blocks, config, report)
    blocks = optimize_readability(blocks, whisper_segments, config, report)
    blocks = apply_chaining(blocks, config, report)
    final_validation(original_blocks, blocks, config, report)

    write_srt(blocks, output_path)
    report.append(f"\n  Optimized SRT written to: {output_path}")
    report.append(f"  Total blocks: {len(blocks)}")

    if report_path:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report))
        report.append(f"  Report saved to: {report_path}")

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Optimize SRT subtitles')
    parser.add_argument('--srt', required=True, help='Input SRT file')
    parser.add_argument('--json', required=True, help='Whisper JSON file')
    parser.add_argument('--output', required=True, help='Output optimized SRT file')
    parser.add_argument('--report', help='Output report file')
    parser.add_argument('--target-cps', type=float, default=15.0)
    parser.add_argument('--hard-max-cps', type=float, default=20.0)
    parser.add_argument('--min-duration', type=int, default=1200, help='Min duration in ms')
    parser.add_argument('--max-duration', type=int, default=7000, help='Max duration in ms')
    parser.add_argument('--min-gap', type=int, default=80, help='Min gap in ms')
    parser.add_argument('--fps', type=int, default=24)
    args = parser.parse_args()

    config = OptimizeConfig(
        target_cps=args.target_cps,
        hard_max_cps=args.hard_max_cps,
        min_duration_ms=args.min_duration,
        max_duration_ms=args.max_duration,
        min_gap_ms=args.min_gap,
        fps=args.fps,
    )

    report = optimize(args.srt, args.json, args.output, args.report, config)
    for line in report:
        print(line)


if __name__ == '__main__':
    main()
