from __future__ import annotations

from pathlib import Path

from morning_brief.cleanup import cleanup_audio_artifacts
from morning_brief.config import WORKSPACE_ROOT
from morning_brief.models import BriefOptions
from morning_brief.render import fallback_output
from morning_brief.sources import sample_context
from morning_brief.tts import split_script


def test_sample_fallback_has_global_and_portfolio_sections() -> None:
    context = sample_context(
        BriefOptions(target_date="2026-06-11", target_audio_minutes=15, brief_type="evening"),
        WORKSPACE_ROOT / "data" / "portfolio.json",
    )
    output = fallback_output(context)
    assert "Global Market Snapshot" in output.markdown
    assert "Portfolio Snapshot" in output.markdown
    assert "Japan" in output.markdown
    assert "NBIS" in output.markdown
    assert "US cash open" in output.markdown
    assert output.brief_type == "evening"


def test_split_script_chunks_long_text() -> None:
    text = "\n\n".join(["word " * 200 for _ in range(8)])
    chunks = split_script(text, max_chars=1200)
    assert len(chunks) > 1
    assert all(len(chunk) <= 1200 for chunk in chunks)


def test_cleanup_audio_keeps_preserved_latest(tmp_path: Path) -> None:
    old_final = tmp_path / "morning_brief_2026-06-10.audio.json"
    new_final = tmp_path / "evening_brief_2026-06-11.audio.json"
    old_segment = tmp_path / "morning_brief_2026-06-10_part01.aac"
    for path in [old_final, new_final, old_segment]:
        path.write_text("x", encoding="utf-8")

    deleted = cleanup_audio_artifacts(tmp_path, keep_final_files=1, preserve={new_final})

    assert new_final.exists()
    assert not old_final.exists()
    assert not old_segment.exists()
    assert set(deleted) == {old_final, old_segment}
