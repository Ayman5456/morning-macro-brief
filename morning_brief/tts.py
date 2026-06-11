from __future__ import annotations

import json
import wave
from pathlib import Path

from openai import OpenAI

from .config import require_openai_key

SUPPORTED_AUDIO_FORMATS = {"mp3", "aac", "opus", "flac", "wav", "pcm"}


def split_script(text: str, max_chars: int = 3600) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = paragraph
    if current:
        chunks.append(current)
    return chunks or [text[:max_chars]]


def synthesize_audio_segments(
    text: str,
    output_prefix: Path,
    model: str,
    voice: str,
    audio_format: str,
) -> list[Path]:
    if audio_format not in SUPPORTED_AUDIO_FORMATS:
        raise ValueError(f"Unsupported audio format: {audio_format}")
    require_openai_key()
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    client = OpenAI()
    paths: list[Path] = []
    for index, chunk in enumerate(split_script(text), start=1):
        path = output_prefix.parent / f"{output_prefix.name}_part{index:02d}.{audio_format}"
        with client.audio.speech.with_streaming_response.create(
            model=model,
            voice=voice,
            input=chunk,
            instructions=(
                "Read as a polished 15-minute global markets briefing. "
                "Use a calm professional tone, clear pacing, and brief pauses between sections."
            ),
            response_format=audio_format,
        ) as response:
            response.stream_to_file(path)
        paths.append(path)
    return paths


def combine_wav_segments(segment_paths: list[Path], output_path: Path) -> Path:
    if not segment_paths:
        raise ValueError("No audio segments to combine.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audio_format = None
    frames: list[bytes] = []
    for path in segment_paths:
        with wave.open(str(path), "rb") as src:
            current_format = (src.getnchannels(), src.getsampwidth(), src.getframerate(), src.getcomptype(), src.getcompname())
            if audio_format is None:
                audio_format = current_format
            elif current_format != audio_format:
                raise ValueError(f"Audio segment parameters differ for {path}")
            frames.append(src.readframes(src.getnframes()))
    assert audio_format is not None
    with wave.open(str(output_path), "wb") as dst:
        channels, sample_width, frame_rate, comp_type, comp_name = audio_format
        dst.setnchannels(channels)
        dst.setsampwidth(sample_width)
        dst.setframerate(frame_rate)
        dst.setcomptype(comp_type, comp_name)
        for frame_block in frames:
            dst.writeframes(frame_block)
    return output_path


def write_audio_manifest(segment_paths: list[Path], output_path: Path, audio_format: str) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format": audio_format,
        "segments": [path.name for path in segment_paths],
        "segment_paths": [str(path) for path in segment_paths],
        "note": "Play segments in order. Compressed segment files are kept to avoid huge uncompressed WAV artifacts.",
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output_path


def synthesize_long_audio(
    text: str,
    output_path: Path,
    model: str,
    voice: str,
    audio_format: str,
    delete_segments: bool = False,
) -> tuple[Path, list[Path]]:
    prefix = output_path.with_suffix("")
    segments = synthesize_audio_segments(text, prefix, model, voice, audio_format)
    if audio_format == "wav":
        combined = combine_wav_segments(segments, output_path.with_suffix(".wav"))
        if delete_segments:
            for segment in segments:
                segment.unlink(missing_ok=True)
            return combined, []
        return combined, segments

    manifest = write_audio_manifest(segments, output_path.with_suffix(".audio.json"), audio_format)
    if delete_segments:
        # Keep segments for compressed formats by default. If explicitly deleted, the manifest becomes archival metadata only.
        for segment in segments:
            segment.unlink(missing_ok=True)
        return manifest, []
    return manifest, segments
