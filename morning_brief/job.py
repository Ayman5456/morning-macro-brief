from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from .agent import generate_brief
from .cleanup import cleanup_audio_artifacts
from .config import get_settings
from .models import BriefJobResult, BriefOptions
from .render import fallback_output
from .sources import collect_context, sample_context
from .tts import synthesize_long_audio


def run_brief_job(
    mode: Literal["text", "audio", "both", "json"] = "text",
    target_date: str | None = None,
    timezone: str | None = None,
    region: str = "global",
    target_audio_minutes: int = 15,
    brief_type: str = "morning",
    model: str | None = None,
    voice: str | None = None,
    audio_format: str | None = None,
    keep_audio_files: int | None = None,
    delete_audio_segments: bool | None = None,
    cleanup_audio: bool = True,
    output_dir: Path | None = None,
    sample_data: bool = False,
    no_agent: bool = False,
) -> BriefJobResult:
    settings = get_settings()
    options = BriefOptions(
        target_date=target_date,
        timezone=timezone or settings.timezone,
        region=region,
        target_audio_minutes=target_audio_minutes,
        brief_type=brief_type,  # type: ignore[arg-type]
    )
    out_dir = output_dir or settings.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    context = None
    if no_agent:
        context = sample_context(options, settings.portfolio_path) if sample_data else collect_context(options, settings.portfolio_path)
        output = fallback_output(context)
    else:
        output = generate_brief(options, model or settings.model)

    slug_date = output.market_date.replace("/", "-").replace(" ", "-")
    suffix = "_sample" if sample_data else "_fallback" if no_agent else ""
    brief_prefix = f"{output.brief_type}_brief"
    markdown_path = out_dir / f"{brief_prefix}_{slug_date}{suffix}.md"
    json_path = out_dir / f"{brief_prefix}_{slug_date}{suffix}.json"
    selected_audio_format = (audio_format or settings.audio_format).lower()
    audio_path = out_dir / f"{brief_prefix}_{slug_date}{suffix}.{selected_audio_format}"

    markdown_path.write_text(output.markdown, encoding="utf-8")
    json_path.write_text(json.dumps(output.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")

    final_audio_path = None
    segments: list[Path] = []
    if mode in {"audio", "both"}:
        final_audio_path, segments = synthesize_long_audio(
            output.audio_script,
            audio_path,
            settings.tts_model,
            voice or settings.tts_voice,
            selected_audio_format,
            delete_segments=delete_audio_segments
            if delete_audio_segments is not None
            else settings.delete_audio_segments,
        )
        if cleanup_audio:
            preserve = {final_audio_path, *segments}
            cleanup_audio_artifacts(
                out_dir,
                keep_audio_files if keep_audio_files is not None else settings.keep_audio_files,
                preserve=preserve,
            )

    return BriefJobResult(
        output=output,
        markdown_path=str(markdown_path),
        json_path=str(json_path),
        audio_path=str(final_audio_path) if final_audio_path else None,
        audio_segment_paths=[str(path) for path in segments],
        context=context,
    )
