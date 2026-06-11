from __future__ import annotations

from pathlib import Path


AUDIO_EXTENSIONS = {".aac", ".mp3", ".opus", ".flac", ".wav", ".pcm", ".audio.json"}


def _audio_sort_key(path: Path) -> tuple[float, str]:
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        mtime = 0.0
    return (mtime, path.name)


def list_audio_artifacts(output_dir: Path) -> list[Path]:
    if not output_dir.exists():
        return []
    artifacts = []
    for pattern in ["morning_brief_*", "evening_brief_*"]:
        for path in output_dir.glob(pattern):
            if path.is_file() and any(str(path).endswith(ext) for ext in AUDIO_EXTENSIONS):
                artifacts.append(path)
    return sorted(artifacts, key=_audio_sort_key, reverse=True)


def cleanup_audio_artifacts(
    output_dir: Path,
    keep_final_files: int,
    preserve: set[Path] | None = None,
) -> list[Path]:
    preserve_resolved = {path.resolve() for path in preserve or set()}
    artifacts = list_audio_artifacts(output_dir)
    preserved_final_count = sum(
        1
        for path in preserve or set()
        if path.is_file()
        and any(str(path).endswith(ext) for ext in AUDIO_EXTENSIONS)
        and "_part" not in path.stem
    )
    final_files = [
        path
        for path in artifacts
        if "_part" not in path.stem and path.resolve() not in preserve_resolved
    ]
    segment_files = [
        path
        for path in artifacts
        if "_part" in path.stem and path.resolve() not in preserve_resolved
    ]

    deletions: list[Path] = []
    if keep_final_files >= 0:
        older_keep_slots = max(0, keep_final_files - preserved_final_count)
        deletions.extend(final_files[older_keep_slots:])
    deletions.extend(segment_files)

    deleted: list[Path] = []
    for path in deletions:
        try:
            path.unlink()
            deleted.append(path)
        except FileNotFoundError:
            continue
    return deleted
