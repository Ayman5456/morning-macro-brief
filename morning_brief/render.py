from __future__ import annotations

from datetime import datetime
from typing import Any

from .models import AudioChapter, BriefOutput


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    header = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join("" if cell is None else str(cell) for cell in row) + " |" for row in rows]
    return "\n".join([header, divider, *body])


def collect_citations(context: dict[str, Any]) -> list[str]:
    citations: list[str] = []
    def add(value: Any) -> None:
        if isinstance(value, str) and value.startswith("http") and value not in citations:
            citations.append(value)
    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"source", "link", "feed"}:
                    add(item)
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(context)
    return citations


def collect_errors(context: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for section in [
        "global_markets",
        "us_rates_macro",
        "economic_calendar",
        "global_news",
        "portfolio_market_data",
        "portfolio_news",
        "portfolio_ticker_news",
        "diversification_watchlist_market_data",
        "diversification_watchlist_ticker_news",
    ]:
        errors.extend(context.get(section, {}).get("errors", []))
    return errors


def fallback_output(context: dict[str, Any]) -> BriefOutput:
    metadata = context.get("metadata", {})
    target_date = str(metadata.get("target_date", "unknown date"))
    brief_type = str(metadata.get("brief_type", "morning"))
    generated_at = str(metadata.get("collected_at", datetime.utcnow().isoformat()))
    session_context = context.get("session_context", {})
    market_rows = context.get("global_markets", {}).get("rows", [])
    rate_rows = context.get("us_rates_macro", {}).get("rows", [])
    calendar_rows = context.get("economic_calendar", {}).get("rows", [])
    news_rows = context.get("global_news", {}).get("rows", [])
    portfolio_rows = context.get("portfolio_market_data", {}).get("rows", [])
    portfolio_news = {row.get("ticker"): row for row in context.get("portfolio_news", {}).get("rows", [])}
    ticker_news = {row.get("ticker"): row for row in context.get("portfolio_ticker_news", {}).get("rows", [])}
    diversification_rows = context.get("diversification_watchlist_market_data", {}).get("rows", [])
    diversification_news = {
        row.get("ticker"): row for row in context.get("diversification_watchlist_ticker_news", {}).get("rows", [])
    }

    parts = [
        f"# Global {brief_type.title()} Macro Brief - {target_date}",
        "",
        "## Opening Dashboard",
        "",
        "This deterministic fallback brief displays collected data without agent synthesis.",
        "Use the full agent run for the richer 15-minute interpretation and portfolio outlook.",
        "",
        "## Session Timing",
        "",
        _table(
            ["Field", "Value"],
            [
                ["Brief type", brief_type],
                ["Singapore now", session_context.get("singapore_now")],
                ["New York now", session_context.get("new_york_now")],
                ["US cash open in Singapore", session_context.get("us_cash_open_singapore")],
                ["Session emphasis", session_context.get("session_emphasis")],
            ],
        ),
        "",
        "## Global Market Snapshot",
        "",
        _table(
            ["Market", "Level", "Change", "Change %"],
            [[row.get("name"), row.get("price"), row.get("change"), row.get("change_pct")] for row in market_rows],
        ),
        "",
        "## US Rates And Macro",
        "",
        _table(
            ["Indicator", "Date", "Value", "Change"],
            [[row.get("name"), row.get("date"), row.get("value"), row.get("change")] for row in rate_rows],
        ),
        "",
        "## Global Economic Calendar",
        "",
        _table(
            ["Country", "Event", "Time/Date", "Actual", "Forecast", "Previous"],
            [
                [row.get("country"), row.get("event"), row.get("date"), row.get("actual"), row.get("forecast"), row.get("previous")]
                for row in calendar_rows[:40]
            ],
        ),
        "",
        "## Portfolio Snapshot",
        "",
        "Portfolio holdings are the primary focus. Use the full agent run for thesis, catalyst, risk, and macro/industry read-through by holding.",
        "",
        _table(
            ["Holding", "Symbol", "Level", "Change %", "Broad Matches", "Ticker Headlines"],
            [
                [
                    row.get("name"),
                    row.get("symbol"),
                    row.get("price"),
                    row.get("change_pct"),
                    len(portfolio_news.get(str(row.get("symbol")), {}).get("matched_news", [])),
                    len(ticker_news.get(str(row.get("symbol")), {}).get("headlines", [])),
                ]
                for row in portfolio_rows
            ],
        ),
        "",
        "## Diversification Research Watchlist",
        "",
        "This is a research watchlist only, not a buy list. It is included to help compare portfolio concentration against broader macro and industry exposures.",
        "",
        _table(
            ["Candidate", "Symbol", "Level", "Change %", "Ticker Headlines"],
            [
                [
                    row.get("name"),
                    row.get("symbol"),
                    row.get("price"),
                    row.get("change_pct"),
                    len(diversification_news.get(str(row.get("symbol")), {}).get("headlines", [])),
                ]
                for row in diversification_rows
            ],
        ),
        "",
        "## Headlines",
        "",
    ]
    for row in news_rows[:30]:
        title = row.get("title") or "Untitled"
        link = row.get("link") or row.get("feed") or ""
        source = row.get("source_name") or "source"
        parts.append(f"- [{title}]({link}) - {source}" if link else f"- {title} - {source}")

    errors = collect_errors(context)
    if errors:
        parts.extend(["", "## Data Caveats", ""])
        parts.extend(f"- {error}" for error in errors[:30])

    parts.extend(["", "## Disclaimer", "", "Informational only; not investment advice."])

    audio_script = "\n\n".join(
        [
            f"Global morning macro brief for {target_date}.",
            "The data collector has assembled global markets, US rates, macro calendar items, public headlines, and portfolio snapshots.",
            "Run the full agent path for a 15-minute explanation of what the data means for economies, markets, the portfolio, and diversification candidates.",
            "This is informational only and not investment advice.",
        ]
    )
    return BriefOutput(
        title=f"Global {brief_type.title()} Macro Brief - {target_date}",
        market_date=target_date,
        brief_type=brief_type,  # type: ignore[arg-type]
        generated_at=generated_at,
        markdown="\n".join(parts),
        audio_script=audio_script,
        audio_chapters=[AudioChapter(title="Fallback Brief", summary="Collected data without agent interpretation.")],
        citations=collect_citations(context),
        risk_flags=errors,
    )
