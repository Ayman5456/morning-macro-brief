from __future__ import annotations

import argparse
from pathlib import Path

from .job import run_brief_job


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a global morning macro and portfolio brief.")
    parser.add_argument("--mode", choices=["text", "audio", "both", "json"], default="text")
    parser.add_argument("--date", dest="target_date", help="Business date, YYYY-MM-DD.")
    parser.add_argument("--timezone", help="Timezone for the brief.")
    parser.add_argument("--region", default="global")
    parser.add_argument("--brief-type", choices=["morning", "evening"], default="morning")
    parser.add_argument("--target-audio-minutes", type=int, default=15)
    parser.add_argument("--model", help="OpenAI model for the brief agent.")
    parser.add_argument("--voice", help="TTS voice.")
    parser.add_argument("--audio-format", choices=["aac", "mp3", "opus", "flac", "wav", "pcm"], help="Audio output format.")
    parser.add_argument("--keep-audio", type=int, help="Number of final audio artifacts to keep after generation.")
    parser.add_argument("--delete-audio-segments", action="store_true", help="Delete generated part files after final artifact creation.")
    parser.add_argument("--no-cleanup-audio", action="store_true", help="Do not delete older audio artifacts after generation.")
    parser.add_argument("--cleanup-audio", action="store_true", help="Only clean old audio artifacts, then exit.")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--sample-data", action="store_true")
    parser.add_argument("--no-agent", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.cleanup_audio:
        from .cleanup import cleanup_audio_artifacts
        from .config import get_settings

        settings = get_settings()
        out_dir = args.output_dir or settings.output_dir
        keep = args.keep_audio if args.keep_audio is not None else settings.keep_audio_files
        deleted = cleanup_audio_artifacts(out_dir, keep_final_files=keep)
        for path in deleted:
            print(f"Deleted: {path}")
        print(f"Deleted {len(deleted)} audio artifact(s).")
        return

    result = run_brief_job(
        mode=args.mode,
        target_date=args.target_date,
        timezone=args.timezone,
        region=args.region,
        target_audio_minutes=args.target_audio_minutes,
        brief_type=args.brief_type,
        model=args.model,
        voice=args.voice,
        audio_format=args.audio_format,
        keep_audio_files=args.keep_audio,
        delete_audio_segments=args.delete_audio_segments,
        cleanup_audio=not args.no_cleanup_audio,
        output_dir=args.output_dir,
        sample_data=args.sample_data,
        no_agent=args.no_agent,
    )
    print(f"Markdown: {result.markdown_path}")
    print(f"JSON: {result.json_path}")
    if result.audio_path:
        print(f"Audio: {result.audio_path}")
        for segment in result.audio_segment_paths:
            print(f"Audio segment: {segment}")


if __name__ == "__main__":
    main()
