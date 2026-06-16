from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from morning_brief.config import get_settings
from morning_brief.job import run_brief_job


OUTPUT_DIR = Path("outputs")


st.set_page_config(
    page_title="Markets Console",
    page_icon="",
    layout="wide",
    initial_sidebar_state="collapsed",
)


TERMINAL_CSS = """
<style>
:root {
  --bg: #090b0f;
  --panel: #111821;
  --panel-2: #151f2b;
  --line: #273342;
  --text: #e7edf3;
  --muted: #8ea0b4;
  --green: #2dd4a4;
  --red: #ff647c;
  --amber: #f7c948;
  --cyan: #5bd7ff;
}
.stApp {
  background: var(--bg);
  color: var(--text);
}
header[data-testid="stHeader"] {
  background: transparent;
}
section[data-testid="stSidebar"] {
  background: #0d1218;
}
.block-container {
  padding-top: 1rem;
  padding-bottom: 4rem;
  max-width: 1180px;
}
h1, h2, h3 {
  letter-spacing: 0;
}
.console-title {
  border-bottom: 1px solid var(--line);
  padding-bottom: .65rem;
  margin-bottom: .75rem;
}
.console-kicker {
  color: var(--cyan);
  font-size: .78rem;
  text-transform: uppercase;
  letter-spacing: .08em;
  font-weight: 700;
}
.console-title h1 {
  font-size: 1.9rem;
  margin: .2rem 0 .15rem;
}
.console-sub {
  color: var(--muted);
  font-size: .92rem;
}
.metric-tile {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: .8rem .85rem;
  min-height: 84px;
}
.metric-label {
  color: var(--muted);
  font-size: .72rem;
  text-transform: uppercase;
  letter-spacing: .06em;
}
.metric-value {
  color: var(--text);
  font-size: 1.25rem;
  font-weight: 700;
  line-height: 1.25;
  margin-top: .25rem;
}
.metric-note {
  color: var(--muted);
  font-size: .78rem;
  margin-top: .25rem;
}
.alert-strip {
  border-left: 3px solid var(--amber);
  background: #171511;
  color: #f5e6b8;
  padding: .75rem .85rem;
  border-radius: 4px;
  margin: .5rem 0 1rem;
}
div[data-testid="stDataFrame"] {
  border: 1px solid var(--line);
  border-radius: 6px;
}
.stTabs [data-baseweb="tab-list"] {
  gap: .35rem;
  border-bottom: 1px solid var(--line);
}
.stTabs [data-baseweb="tab"] {
  background: var(--panel);
  border: 1px solid var(--line);
  border-bottom: none;
  border-radius: 6px 6px 0 0;
  padding: .55rem .75rem;
}
.stTabs [aria-selected="true"] {
  color: var(--cyan);
}
button[kind="primary"] {
  border-radius: 6px;
}
.small-note {
  color: var(--muted);
  font-size: .82rem;
}
@media (max-width: 720px) {
  .block-container {
    padding-left: .75rem;
    padding-right: .75rem;
  }
  .console-title h1 {
    font-size: 1.45rem;
  }
}
</style>
"""


def _artifact_sort_key(path: Path) -> tuple[float, str]:
    return (path.stat().st_mtime, path.name)


def latest_json_path(brief_type: str) -> Path | None:
    paths = [
        path
        for path in OUTPUT_DIR.glob(f"{brief_type}_brief_*.json")
        if "_sample" not in path.name
        and "_fallback" not in path.name
        and not path.name.endswith(".audio.json")
    ]
    return max(paths, key=_artifact_sort_key) if paths else None


def matching_path(json_path: Path, suffix: str) -> Path:
    return json_path.with_suffix(suffix)


@st.cache_data(ttl=20)
def load_brief(path_text: str) -> dict[str, Any]:
    path = Path(path_text)
    return json.loads(path.read_text(encoding="utf-8"))


def section_text(markdown: str, heading: str) -> str:
    pattern = rf"(^##\s+.*{re.escape(heading)}.*$)"
    match = re.search(pattern, markdown, flags=re.MULTILINE | re.IGNORECASE)
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^##\s+", markdown[start:], flags=re.MULTILINE)
    end = start + next_match.start() if next_match else len(markdown)
    return markdown[start:end].strip()


def first_markdown_table(text: str) -> pd.DataFrame:
    lines = [line.strip() for line in text.splitlines() if line.strip().startswith("|")]
    if len(lines) < 3:
        return pd.DataFrame()
    headers = [cell.strip() for cell in lines[0].strip("|").split("|")]
    rows = []
    for line in lines[2:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == len(headers):
            rows.append(cells)
    return pd.DataFrame(rows, columns=headers)


def numeric_change_series(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    change_col = next((col for col in df.columns if "change %" in col.lower()), None)
    label_col = df.columns[0]
    if not change_col:
        return pd.DataFrame()
    out = df[[label_col, change_col]].copy()
    out[change_col] = (
        out[change_col]
        .astype(str)
        .str.replace("%", "", regex=False)
        .str.replace("+", "", regex=False)
        .replace("", pd.NA)
    )
    out[change_col] = pd.to_numeric(out[change_col], errors="coerce")
    return out.dropna()


def audio_manifest_for(json_path: Path) -> tuple[Path | None, list[Path]]:
    manifest = json_path.with_suffix(".audio.json")
    if not manifest.exists():
        return None, []
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    segments = []
    for raw_name in payload.get("segments", []):
        path = Path(raw_name)
        segments.append(path if path.is_absolute() else manifest.parent / path)
    return manifest, [path for path in segments if path.exists()]


def render_metric(label: str, value: str, note: str = "") -> None:
    st.markdown(
        f"""
        <div class="metric-tile">
          <div class="metric-label">{label}</div>
          <div class="metric-value">{value}</div>
          <div class="metric-note">{note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_value(brief: dict[str, Any], json_path: Path) -> tuple[str, str]:
    generated = brief.get("generated_at", "")
    try:
        dt = datetime.fromisoformat(generated)
        generated_label = dt.strftime("%d %b, %H:%M")
    except Exception:
        generated_label = generated[:16] or "unknown"
    return generated_label, datetime.fromtimestamp(json_path.stat().st_mtime).strftime("%H:%M")


def render_audio(manifest: Path | None, segments: list[Path]) -> None:
    if not manifest or not segments:
        st.markdown('<div class="alert-strip">No compressed audio found for this brief yet. Generate audio from the controls panel.</div>', unsafe_allow_html=True)
        return

    st.caption(f"Playlist manifest: `{manifest.name}`")
    for index, path in enumerate(segments, start=1):
        with st.expander(f"Part {index:02d} · {path.name}", expanded=index == 1):
            st.audio(path.read_bytes(), format="audio/aac")
            st.download_button(
                "Download part",
                data=path.read_bytes(),
                file_name=path.name,
                mime="audio/aac",
                key=f"download-{path.name}",
            )


def render_generate_controls(brief_type: str) -> None:
    st.subheader("Generate")
    st.caption("Manual controls. These can call the OpenAI API and may take a few minutes.")
    target_date = st.date_input("Brief date", value=datetime.now().date())
    audio_format = st.selectbox("Audio format", ["aac", "mp3", "wav"], index=0)
    keep_audio = st.number_input("Final audio files to keep", min_value=1, max_value=10, value=1)
    mode = st.radio("Run mode", ["text", "both"], horizontal=True, index=0)

    if st.button(f"Run {brief_type} brief", type="primary", use_container_width=True):
        with st.status("Generating brief...", expanded=True) as status:
            st.write("Running engine. This may take a while for full text and audio.")
            result = run_brief_job(
                mode=mode,  # type: ignore[arg-type]
                brief_type=brief_type,
                target_date=target_date.isoformat(),
                audio_format=audio_format,
                keep_audio_files=int(keep_audio),
            )
            st.write(f"Markdown: {result.markdown_path}")
            if result.audio_path:
                st.write(f"Audio manifest: {result.audio_path}")
            status.update(label="Generation complete", state="complete")
        st.cache_data.clear()
        st.rerun()


def render_empty_state(brief_type: str) -> None:
    st.markdown(
        f"""
        <div class="alert-strip">
          No {brief_type} brief artifact found yet. Use the Generate panel to create one.
        </div>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.markdown(TERMINAL_CSS, unsafe_allow_html=True)
    settings = get_settings()

    st.markdown(
        """
        <div class="console-title">
          <div class="console-kicker">MRT Markets Console</div>
          <h1>Global Macro Briefing Terminal</h1>
          <div class="console-sub">Morning and evening market intelligence for Singapore commute windows.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left, right = st.columns([1, 1])
    with left:
        brief_type = st.radio("Brief", ["morning", "evening"], horizontal=True, label_visibility="collapsed")
    with right:
        st.caption(f"Timezone: `{settings.timezone}` · Audio retention: latest `{settings.keep_audio_files}`")

    json_path = latest_json_path(brief_type)
    if not json_path:
        render_empty_state(brief_type)
        with st.sidebar:
            render_generate_controls(brief_type)
        return

    brief = load_brief(str(json_path))
    markdown = brief.get("markdown", "")
    generated_label, file_time = status_value(brief, json_path)
    manifest, audio_segments = audio_manifest_for(json_path)

    market_df = first_markdown_table(section_text(markdown, "Global market snapshot"))
    portfolio_df = first_markdown_table(section_text(markdown, "Portfolio"))
    calendar_df = first_markdown_table(section_text(markdown, "Calendar"))
    risk_flags = brief.get("risk_flags", [])
    word_count = len(re.findall(r"\b\w+\b", brief.get("audio_script", "")))

    metric_cols = st.columns(4)
    with metric_cols[0]:
        render_metric("Mode", brief_type.upper(), "commute profile")
    with metric_cols[1]:
        render_metric("Generated", generated_label, f"file {file_time}")
    with metric_cols[2]:
        render_metric("Audio", f"{len(audio_segments)} parts", "AAC playlist" if audio_segments else "not generated")
    with metric_cols[3]:
        render_metric("Script", f"{word_count:,} words", f"{len(risk_flags)} caveats")

    if risk_flags:
        st.markdown(
            f'<div class="alert-strip">{risk_flags[0]}</div>',
            unsafe_allow_html=True,
        )

    today, macro, portfolio, ideas, audio, transcript, controls = st.tabs(
        ["Today", "Global Macro", "Portfolio", "Diversify", "Audio", "Transcript", "Controls"]
    )

    with today:
        st.subheader(brief.get("title", "Latest Brief"))
        opening = section_text(markdown, "Opening dashboard")
        st.markdown(opening or markdown[:1800])
        st.divider()
        if not market_df.empty:
            st.dataframe(market_df.head(16), use_container_width=True, hide_index=True)

    with macro:
        st.subheader("Global Market Board")
        if market_df.empty:
            st.info("No market table found in the latest brief.")
        else:
            st.dataframe(market_df, use_container_width=True, hide_index=True)
            changes = numeric_change_series(market_df)
            if not changes.empty:
                label_col, change_col = changes.columns[0], changes.columns[1]
                st.bar_chart(changes.set_index(label_col)[change_col], height=320)

        calendar_section = section_text(markdown, "Calendar")
        calendar_table = first_markdown_table(calendar_section)
        st.subheader("Calendar")
        if not calendar_table.empty:
            st.dataframe(calendar_table.head(40), use_container_width=True, hide_index=True)
        else:
            st.caption("No calendar table parsed from the latest brief.")

    with portfolio:
        st.subheader("Portfolio Impact")
        if portfolio_df.empty:
            st.info("No portfolio table found in the latest brief.")
        else:
            st.dataframe(portfolio_df, use_container_width=True, hide_index=True)
            changes = numeric_change_series(portfolio_df)
            if not changes.empty:
                label_col, change_col = changes.columns[0], changes.columns[1]
                st.bar_chart(changes.set_index(label_col)[change_col], height=360)

    with ideas:
        st.subheader("Macro-Driven Diversification Map")
        diversification_section = section_text(markdown, "Diversification")
        if diversification_section:
            st.markdown(diversification_section)
        else:
            st.info("No macro-driven diversification section found in the latest brief.")

    with audio:
        st.subheader("Audio Playlist")
        render_audio(manifest, audio_segments)

    with transcript:
        st.subheader("Full Transcript")
        st.markdown(markdown)
        st.download_button(
            "Download Markdown",
            data=markdown.encode("utf-8"),
            file_name=json_path.with_suffix(".md").name,
            mime="text/markdown",
            use_container_width=True,
        )

    with controls:
        render_generate_controls(brief_type)

    with st.sidebar:
        st.subheader("Artifacts")
        st.caption(f"JSON: `{json_path.name}`")
        md_path = json_path.with_suffix(".md")
        if md_path.exists():
            st.caption(f"Markdown: `{md_path.name}`")
        if manifest:
            st.caption(f"Audio: `{manifest.name}`")


if __name__ == "__main__":
    main()
