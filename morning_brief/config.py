from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]


def load_env_file(path: Path | None = None) -> None:
    env_path = path or WORKSPACE_ROOT / ".env.local"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Settings:
    model: str
    tts_model: str
    tts_voice: str
    timezone: str
    output_dir: Path
    portfolio_path: Path
    audio_format: str
    keep_audio_files: int
    delete_audio_segments: bool


def get_settings() -> Settings:
    load_env_file()
    keep_audio_files = int(os.getenv("BRIEF_KEEP_AUDIO_FILES", "1"))
    delete_audio_segments = os.getenv("BRIEF_DELETE_AUDIO_SEGMENTS", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    return Settings(
        model=os.getenv("BRIEF_MODEL", "gpt-5.5"),
        tts_model=os.getenv("BRIEF_TTS_MODEL", "gpt-4o-mini-tts"),
        tts_voice=os.getenv("BRIEF_TTS_VOICE", "marin"),
        timezone=os.getenv("BRIEF_TIMEZONE", "Asia/Singapore"),
        output_dir=Path(os.getenv("BRIEF_OUTPUT_DIR", str(WORKSPACE_ROOT / "outputs"))),
        portfolio_path=Path(os.getenv("BRIEF_PORTFOLIO_PATH", str(WORKSPACE_ROOT / "data" / "portfolio.json"))),
        audio_format=os.getenv("BRIEF_AUDIO_FORMAT", "aac").lower(),
        keep_audio_files=max(0, keep_audio_files),
        delete_audio_segments=delete_audio_segments,
    )


def require_openai_key() -> None:
    load_env_file()
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is missing. Save it in .env.local or export it.")
