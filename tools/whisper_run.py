"""Whisper speech detection wrapper.

Runs OpenAI Whisper on a video/audio file and saves segment JSON.

Usage:
    python -m tools.whisper_run --video PATH --output PATH [--model medium] [--language en]
"""

import argparse
import json


def run_whisper(video_path, output_path, model='medium', language='en'):
    """Run Whisper and save segments to JSON.

    Uses the openai-whisper Python API.
    """
    import whisper

    print(f"Loading Whisper model: {model}")
    model_obj = whisper.load_model(model)

    print(f"Transcribing: {video_path}")
    result = model_obj.transcribe(
        video_path,
        language=language,
        verbose=False,
        word_timestamps=True,
    )

    segments = []
    for seg in result['segments']:
        seg_data = {
            'id': seg['id'],
            'start': seg['start'],
            'end': seg['end'],
            'text': seg['text'].strip(),
        }
        if 'words' in seg:
            seg_data['words'] = [
                {'start': w['start'], 'end': w['end'], 'word': w['word'].strip()}
                for w in seg['words']
            ]
        segments.append(seg_data)

    output = {
        'language': result.get('language', language),
        'segments': segments,
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(segments)} segments to {output_path}")
    return output


def main():
    parser = argparse.ArgumentParser(description='Run Whisper speech detection')
    parser.add_argument('--video', required=True, help='Input video/audio file')
    parser.add_argument('--output', required=True, help='Output JSON file')
    parser.add_argument('--model', default='medium', help='Whisper model (tiny/base/small/medium/large)')
    parser.add_argument('--language', default='en', help='Language code')
    args = parser.parse_args()

    run_whisper(args.video, args.output, args.model, args.language)


if __name__ == '__main__':
    main()
