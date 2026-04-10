"""Whisper speech detection wrapper.

Runs faster-whisper on a video/audio file and saves segment JSON.
Uses Silero VAD to filter non-speech regions (prevents hallucination
on music/silence). Anti-hallucination parameters enabled by default.

Usage:
    python -m tools.whisper_run --video PATH --output PATH [--model medium] [--language en]
"""

import argparse
import json


def run_whisper(video_path, output_path, model="medium", language="en"):
    """Run faster-whisper with VAD and save segments to JSON."""
    from faster_whisper import WhisperModel

    print(f"Loading faster-whisper model: {model}")
    model_obj = WhisperModel(model, device="cpu", compute_type="int8")

    print(f"Transcribing: {video_path}")
    raw_segments, info = model_obj.transcribe(
        video_path,
        language=language,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={
            "threshold": 0.5,
            "min_silence_duration_ms": 500,
            "speech_pad_ms": 400,
            "min_speech_duration_ms": 250,
        },
        condition_on_previous_text=False,
        no_speech_threshold=0.6,
        log_prob_threshold=-1.0,
        compression_ratio_threshold=2.4,
        hallucination_silence_threshold=2.0,
        repetition_penalty=1.2,
    )

    segments = []
    for seg in raw_segments:
        text = seg.text.strip()
        # Skip hallucinated segments (dots only, empty)
        if not text or all(c in ".… " for c in text):
            continue
        seg_data = {
            "id": len(segments),
            "start": seg.start,
            "end": seg.end,
            "text": text,
        }
        if seg.words:
            seg_data["words"] = [
                {"start": w.start, "end": w.end, "word": w.word.strip()} for w in seg.words if w.word.strip()
            ]
        segments.append(seg_data)

    output = {
        "language": info.language,
        "segments": segments,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total_words = sum(len(s.get("words", [])) for s in segments)
    print(f"Saved {len(segments)} segments ({total_words} words) to {output_path}")
    return output


def main():
    parser = argparse.ArgumentParser(description="Run Whisper speech detection")
    parser.add_argument("--video", required=True, help="Input video/audio file")
    parser.add_argument("--output", required=True, help="Output JSON file")
    parser.add_argument("--model", default="medium", help="Whisper model (tiny/base/small/medium/large)")
    parser.add_argument("--language", default="en", help="Language code")
    args = parser.parse_args()

    run_whisper(args.video, args.output, args.model, args.language)


if __name__ == "__main__":
    main()
