from __future__ import annotations

import json
from pathlib import Path

from agents import Agent, Runner, function_tool

from .config import get_settings, require_openai_key
from .models import BriefOptions, BriefOutput
from .sources import collect_context


PROMPT_PATH = Path(__file__).resolve().parents[1] / "docs" / "prompt.md"


@function_tool
def collect_global_brief_context(
    target_date: str | None = None,
    timezone: str = "Asia/Singapore",
    region: str = "global",
    target_audio_minutes: int = 15,
    brief_type: str = "morning",
) -> str:
    """Collect global macro, markets, news, calendar, and portfolio context for the brief."""
    settings = get_settings()
    options = BriefOptions(
        target_date=target_date,
        timezone=timezone,
        region=region,
        target_audio_minutes=target_audio_minutes,
        brief_type=brief_type,  # type: ignore[arg-type]
    )
    context = collect_context(options, settings.portfolio_path)
    return json.dumps(context, ensure_ascii=False, indent=2)


def build_agent(model: str) -> Agent:
    return Agent(
        name="Global Morning Macro Portfolio Brief Agent",
        model=model,
        instructions=PROMPT_PATH.read_text(encoding="utf-8"),
        tools=[collect_global_brief_context],
        output_type=BriefOutput,
    )


def generate_brief(options: BriefOptions, model: str) -> BriefOutput:
    require_openai_key()
    prompt = (
        f"Generate today's global {options.brief_type} macro, market, economy, and portfolio brief. "
        "Call collect_global_brief_context first. "
        "Produce the required structured output. "
        "The audio script must be 2200 to 2700 words for a roughly 15-minute listen. "
        "Make the user's portfolio the center of gravity: spend roughly 40% to 50% of the brief on portfolio impact, "
        "holding-specific catalysts, industry read-through, and outlook implications. "
        "Include a macro-driven diversification map using the supplied country, sector, industry, and exposure-proxy data; "
        "judge what kinds of equities by country and industry deserve research, and do not frame proxy tickers as buy recommendations. "
        "If brief_type is evening, prioritize the upcoming US cash open, pre-market setup, "
        "earnings/events due before or after market, futures proxies where supplied, and what to watch from Singapore time. "
        "If brief_type is morning, prioritize overnight US close, Asia open, Europe context, and the day-ahead macro setup. "
        f"Options: {options.model_dump_json()}"
    )
    result = Runner.run_sync(build_agent(model), prompt)
    output = result.final_output
    if isinstance(output, BriefOutput):
        return output
    if isinstance(output, dict):
        return BriefOutput.model_validate(output)
    raise TypeError(f"Unexpected agent output type: {type(output)!r}")
