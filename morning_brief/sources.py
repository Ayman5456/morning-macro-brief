from __future__ import annotations

import csv
import html
import json
import math
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .models import BriefOptions


USER_AGENT = "morning-macro-brief/0.2"

GLOBAL_MARKETS = {
    "US - S&P 500": "^GSPC",
    "US - Nasdaq Composite": "^IXIC",
    "US - Russell 2000": "^RUT",
    "Volatility - VIX": "^VIX",
    "Europe - STOXX 50": "^STOXX50E",
    "Europe - DAX": "^GDAXI",
    "Europe - FTSE 100": "^FTSE",
    "China/HK - Hang Seng": "^HSI",
    "China - CSI 300": "000300.SS",
    "India - Nifty 50": "^NSEI",
    "Singapore - STI": "^STI",
    "Japan - Nikkei 225": "^N225",
    "South Korea - KOSPI": "^KS11",
    "DXY": "DX-Y.NYB",
    "EUR/USD": "EURUSD=X",
    "USD/JPY": "JPY=X",
    "USD/CNH": "CNH=X",
    "USD/INR": "INR=X",
    "USD/SGD": "SGD=X",
    "USD/KRW": "KRW=X",
    "Gold ETF": "GLDM",
    "Oil ETF": "USO",
    "Copper ETF": "CPER",
    "US High Yield ETF": "HYG",
    "US Investment Grade ETF": "LQD",
}

FRED_SERIES = {
    "UST 2Y": "DGS2",
    "UST 10Y": "DGS10",
    "UST 30Y": "DGS30",
    "10Y-2Y curve": "T10Y2Y",
    "10Y breakeven inflation": "T10YIE",
    "Effective fed funds": "DFF",
    "SOFR": "SOFR",
    "US CPI": "CPIAUCSL",
    "US payroll employment": "PAYEMS",
    "US unemployment rate": "UNRATE",
    "US initial claims": "ICSA",
}

RSS_FEEDS = {
    "CNBC markets": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "CNBC economy": "https://www.cnbc.com/id/20910258/device/rss/rss.html",
    "BBC business": "https://feeds.bbci.co.uk/news/business/rss.xml",
    "MarketWatch": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "Nikkei Asia": "https://asia.nikkei.com/rss/feed/nar",
}

DIVERSIFICATION_WATCHLIST = {
    "MSFT - Microsoft": "MSFT",
    "AMZN - Amazon": "AMZN",
    "META - Meta Platforms": "META",
    "BRK-B - Berkshire Hathaway": "BRK-B",
    "JPM - JPMorgan Chase": "JPM",
    "V - Visa": "V",
    "LLY - Eli Lilly": "LLY",
    "UNH - UnitedHealth": "UNH",
    "COST - Costco": "COST",
    "CAT - Caterpillar": "CAT",
    "ETN - Eaton": "ETN",
    "XOM - Exxon Mobil": "XOM",
    "NEE - NextEra Energy": "NEE",
    "TM - Toyota Motor ADR": "TM",
    "ASML - ASML ADR": "ASML",
    "TSM - Taiwan Semiconductor ADR": "TSM",
}


def build_session_context(options: BriefOptions, now: datetime) -> dict[str, Any]:
    singapore = ZoneInfo("Asia/Singapore")
    new_york = ZoneInfo("America/New_York")
    local_now = now.astimezone(ZoneInfo(options.timezone))
    sg_now = now.astimezone(singapore)
    ny_now = now.astimezone(new_york)
    target = date.fromisoformat(options.target_date) if options.target_date else sg_now.date()
    us_open_ny = datetime(target.year, target.month, target.day, 9, 30, tzinfo=new_york)
    us_open_sg = us_open_ny.astimezone(singapore)
    minutes_to_us_open = int((us_open_sg - sg_now).total_seconds() // 60)
    if options.brief_type == "evening":
        emphasis = (
            "Evening Singapore commute brief: focus on US pre-market, futures proxies, "
            "US macro releases, earnings/events, and what matters before the US cash open."
        )
    else:
        emphasis = (
            "Morning Singapore commute brief: focus on overnight US close, Asia open, "
            "Europe context, macro/rates developments, and portfolio read-through for the day ahead."
        )
    return {
        "brief_type": options.brief_type,
        "local_timezone": options.timezone,
        "local_now": local_now.isoformat(),
        "singapore_now": sg_now.isoformat(),
        "new_york_now": ny_now.isoformat(),
        "target_date_sgt": target.isoformat(),
        "us_cash_open_new_york": us_open_ny.isoformat(),
        "us_cash_open_singapore": us_open_sg.isoformat(),
        "minutes_to_us_cash_open_from_collection": minutes_to_us_open,
        "session_emphasis": emphasis,
        "timing_note": (
            "US cash market open is 9:30 AM New York time. In Singapore this is usually "
            "9:30 PM during US daylight saving time and 10:30 PM during US standard time."
        ),
    }


def _request_text(url: str, timeout: float = 10.0) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _request_json(url: str, timeout: float = 10.0) -> Any:
    return json.loads(_request_text(url, timeout=timeout))


def _request_text_with_retry(url: str, timeouts: tuple[float, ...] = (5.0, 9.0)) -> str:
    last_error: Exception | None = None
    for timeout in timeouts:
        try:
            return _request_text(url, timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    assert last_error is not None
    raise last_error


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def _round(value: float | None, digits: int = 3) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _fetch_yahoo_symbol(label: str, symbol: str) -> tuple[dict[str, Any] | None, str | None]:
    encoded = urllib.parse.quote(symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range=5d&interval=1d"
    try:
        payload = _request_json(url, timeout=8)
        result = payload["chart"]["result"][0]
        meta = result.get("meta", {})
        quote = (result.get("indicators", {}).get("quote") or [{}])[0]
        closes = [_safe_float(value) for value in quote.get("close", [])]
        closes = [value for value in closes if value is not None]
        price = _safe_float(meta.get("regularMarketPrice")) or (closes[-1] if closes else None)
        previous = _safe_float(meta.get("previousClose")) or (closes[-2] if len(closes) >= 2 else None)
        change = None if price is None or previous is None else price - previous
        change_pct = None if previous in (None, 0) or change is None else change / previous * 100
        return (
            {
                "name": label,
                "symbol": symbol,
                "price": _round(price, 4),
                "change": _round(change, 4),
                "change_pct": _round(change_pct, 2),
                "currency": meta.get("currency"),
                "exchange": meta.get("exchangeName") or meta.get("fullExchangeName"),
                "source": url,
            },
            None,
        )
    except Exception as exc:  # noqa: BLE001
        return None, f"{label}: {exc}"


def fetch_yahoo_symbols(symbols: dict[str, str], source_name: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(_fetch_yahoo_symbol, label, symbol) for label, symbol in symbols.items()]
        for future in as_completed(futures):
            row, error = future.result()
            if row:
                rows.append(row)
            if error:
                errors.append(error)
    order = list(symbols)
    rows.sort(key=lambda row: order.index(row["name"]) if row["name"] in order else 999)
    return {"source_name": source_name, "rows": rows, "errors": errors}


def fetch_global_markets() -> dict[str, Any]:
    return fetch_yahoo_symbols(GLOBAL_MARKETS, "Yahoo Finance global market proxies")


def _fetch_fred(label: str, series_id: str) -> tuple[dict[str, Any] | None, str | None]:
    start = (date.today() - timedelta(days=500)).isoformat()
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}"
    try:
        text = _request_text_with_retry(url)
        reader = csv.DictReader(StringIO(text))
        valid = [row for row in reader if row.get("observation_date") and row.get(series_id) not in (None, ".", "")]
        if not valid:
            raise ValueError("no valid observations")
        latest = valid[-1]
        prev = valid[-2] if len(valid) >= 2 else None
        value = _safe_float(latest.get(series_id))
        prev_value = _safe_float(prev.get(series_id)) if prev else None
        change = None if value is None or prev_value is None else value - prev_value
        return (
            {
                "name": label,
                "series_id": series_id,
                "date": latest["observation_date"],
                "value": _round(value, 4),
                "change": _round(change, 4),
                "source": url,
            },
            None,
        )
    except Exception as exc:  # noqa: BLE001
        return None, f"{label}: {exc}"


def fetch_us_rates_macro() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_fetch_fred, label, series_id) for label, series_id in FRED_SERIES.items()]
        for future in as_completed(futures):
            row, error = future.result()
            if row:
                rows.append(row)
            if error:
                errors.append(error)
    order = list(FRED_SERIES)
    rows.sort(key=lambda row: order.index(row["name"]) if row["name"] in order else 999)
    return {"source_name": "FRED public CSV", "rows": rows, "errors": errors}


def fetch_economic_calendar(target: date) -> dict[str, Any]:
    url = f"https://api.nasdaq.com/api/calendar/economicevents?date={target.isoformat()}"
    countries = {
        "United States",
        "Euro Zone",
        "Germany",
        "France",
        "Italy",
        "United Kingdom",
        "China",
        "Hong Kong",
        "India",
        "Singapore",
        "Japan",
        "South Korea",
        "Canada",
    }
    try:
        payload = _request_json(url, timeout=10)
        data = payload.get("data") or {}
        rows = []
        for item in data.get("rows") or []:
            country = item.get("country")
            if country not in countries:
                continue
            rows.append(
                {
                    "country": country,
                    "event": html.unescape(item.get("eventName") or ""),
                    "date": f"{target.isoformat()} {item.get('gmt') or ''} GMT".strip(),
                    "actual": html.unescape(item.get("actual") or "").replace("\xa0", " ").strip(),
                    "forecast": html.unescape(item.get("consensus") or "").replace("\xa0", " ").strip(),
                    "previous": html.unescape(item.get("previous") or "").replace("\xa0", " ").strip(),
                    "description": html.unescape(item.get("description") or "")[:500],
                    "source": url,
                }
            )
        errors = [] if rows else ["Economic calendar returned no rows for selected global countries/date."]
        return {"source_name": "Nasdaq public economic calendar", "as_of": data.get("asOf"), "rows": rows[:80], "errors": errors}
    except Exception as exc:  # noqa: BLE001
        return {"source_name": "Nasdaq public economic calendar", "rows": [], "errors": [str(exc)], "source": url}


def _child_text(element: ET.Element, name: str) -> str | None:
    for child in list(element):
        if child.tag.split("}")[-1].lower() == name.lower() and child.text:
            return child.text.strip()
    return None


def fetch_rss_news(limit_per_feed: int = 10) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for source_name, url in RSS_FEEDS.items():
        try:
            root = ET.fromstring(_request_text(url, timeout=8))
            items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
            for item in items[:limit_per_feed]:
                link = _child_text(item, "link")
                if link is None:
                    for child in list(item):
                        if child.tag.split("}")[-1].lower() == "link":
                            link = child.attrib.get("href")
                            break
                rows.append(
                    {
                        "source_name": source_name,
                        "title": _child_text(item, "title"),
                        "link": link,
                        "published": _child_text(item, "pubDate") or _child_text(item, "updated"),
                        "summary": _child_text(item, "description") or _child_text(item, "summary"),
                        "feed": url,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{source_name}: {exc}")
    return {"source_name": "Public RSS feeds", "rows": rows, "errors": errors}


def load_portfolio(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def portfolio_symbol_map(portfolio: dict[str, Any]) -> dict[str, str]:
    return {f"{item['ticker']} - {item['name']}": item["ticker"] for item in portfolio.get("holdings", [])}


def fetch_portfolio_market_data(portfolio: dict[str, Any]) -> dict[str, Any]:
    return fetch_yahoo_symbols(portfolio_symbol_map(portfolio), "Yahoo Finance portfolio holdings")


def fetch_portfolio_news(portfolio: dict[str, Any], rss_rows: list[dict[str, Any]]) -> dict[str, Any]:
    holdings = portfolio.get("holdings", [])
    results = []
    for holding in holdings:
        terms = [holding["ticker"], holding["name"], *(holding.get("aliases") or [])]
        matches = []
        for row in rss_rows:
            haystack = " ".join(str(row.get(key) or "") for key in ["title", "summary", "source_name"]).lower()
            if any(term.lower().replace(".ks", "").replace(".l", "") in haystack for term in terms):
                matches.append(row)
        results.append(
            {
                "ticker": holding["ticker"],
                "name": holding["name"],
                "theme": holding.get("theme"),
                "region": holding.get("region"),
                "matched_news": matches[:5],
                "source_note": "Matched against collected public RSS headlines and summaries.",
            }
        )
    return {"source_name": "Portfolio RSS headline matching", "rows": results, "errors": []}


def _fetch_yahoo_ticker_news(holding: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    ticker = holding["ticker"]
    encoded = urllib.parse.quote(ticker, safe="")
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={encoded}&region=US&lang=en-US"
    row = {
        "ticker": ticker,
        "name": holding["name"],
        "theme": holding.get("theme"),
        "region": holding.get("region"),
        "headlines": [],
        "feed": url,
    }
    try:
        root = ET.fromstring(_request_text(url, timeout=8))
        items = root.findall(".//item")
        for item in items[:8]:
            row["headlines"].append(
                {
                    "title": _child_text(item, "title"),
                    "link": _child_text(item, "link"),
                    "published": _child_text(item, "pubDate"),
                    "summary": _child_text(item, "description"),
                }
            )
        return row, None
    except Exception as exc:  # noqa: BLE001
        return row, f"{ticker}: {exc}"


def fetch_portfolio_ticker_news(portfolio: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_fetch_yahoo_ticker_news, holding) for holding in portfolio.get("holdings", [])]
        for future in as_completed(futures):
            row, error = future.result()
            rows.append(row)
            if error:
                errors.append(error)
    order = [holding["ticker"] for holding in portfolio.get("holdings", [])]
    rows.sort(key=lambda row: order.index(row["ticker"]) if row["ticker"] in order else 999)
    return {"source_name": "Yahoo Finance per-ticker RSS", "rows": rows, "errors": errors}


def _watchlist_holding(label: str, symbol: str) -> dict[str, Any]:
    name = label.split(" - ", 1)[1] if " - " in label else label
    return {"ticker": symbol, "name": name, "theme": "Diversification watchlist", "region": "Global/US-listed"}


def fetch_diversification_market_data() -> dict[str, Any]:
    return fetch_yahoo_symbols(DIVERSIFICATION_WATCHLIST, "Yahoo Finance diversification watchlist")


def fetch_diversification_ticker_news() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    holdings = [_watchlist_holding(label, symbol) for label, symbol in DIVERSIFICATION_WATCHLIST.items()]
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_fetch_yahoo_ticker_news, holding) for holding in holdings]
        for future in as_completed(futures):
            row, error = future.result()
            rows.append(row)
            if error:
                errors.append(error)
    order = list(DIVERSIFICATION_WATCHLIST.values())
    rows.sort(key=lambda row: order.index(row["ticker"]) if row["ticker"] in order else 999)
    return {"source_name": "Yahoo Finance diversification watchlist RSS", "rows": rows, "errors": errors}


def collect_context(options: BriefOptions, portfolio_path: Path) -> dict[str, Any]:
    tz = ZoneInfo(options.timezone)
    now = datetime.now(tz)
    target = date.fromisoformat(options.target_date) if options.target_date else now.date()
    portfolio = load_portfolio(portfolio_path)
    global_news = fetch_rss_news()
    return {
        "metadata": {
            "brief_type": options.brief_type,
            "target_date": target.isoformat(),
            "timezone": options.timezone,
            "region": options.region,
            "target_audio_minutes": options.target_audio_minutes,
            "collected_at": now.isoformat(),
        },
        "session_context": build_session_context(options, now),
        "global_markets": fetch_global_markets(),
        "us_rates_macro": fetch_us_rates_macro(),
        "economic_calendar": fetch_economic_calendar(target),
        "global_news": global_news,
        "portfolio": portfolio,
        "portfolio_market_data": fetch_portfolio_market_data(portfolio),
        "portfolio_news": fetch_portfolio_news(portfolio, global_news.get("rows", [])),
        "portfolio_ticker_news": fetch_portfolio_ticker_news(portfolio),
        "diversification_watchlist_market_data": fetch_diversification_market_data(),
        "diversification_watchlist_ticker_news": fetch_diversification_ticker_news(),
    }


def sample_context(options: BriefOptions, portfolio_path: Path) -> dict[str, Any]:
    tz = ZoneInfo(options.timezone)
    now = datetime.now(tz)
    target = options.target_date or now.date().isoformat()
    portfolio = load_portfolio(portfolio_path)
    return {
        "metadata": {
            "brief_type": options.brief_type,
            "target_date": target,
            "timezone": options.timezone,
            "region": options.region,
            "target_audio_minutes": options.target_audio_minutes,
            "collected_at": now.isoformat(),
            "sample": True,
        },
        "session_context": build_session_context(options, now),
        "global_markets": {
            "source_name": "Sample global market proxies",
            "rows": [
                {"name": "US - S&P 500", "price": 5420, "change_pct": -0.4},
                {"name": "Europe - STOXX 50", "price": 5050, "change_pct": 0.2},
                {"name": "China/HK - Hang Seng", "price": 18400, "change_pct": -1.1},
                {"name": "India - Nifty 50", "price": 23400, "change_pct": 0.5},
                {"name": "Singapore - STI", "price": 3340, "change_pct": 0.1},
                {"name": "Japan - Nikkei 225", "price": 38600, "change_pct": -0.3},
                {"name": "South Korea - KOSPI", "price": 2760, "change_pct": 0.4},
                {"name": "Gold ETF", "price": 49.2, "change_pct": 0.7},
            ],
            "errors": [],
        },
        "us_rates_macro": {
            "source_name": "Sample rates",
            "rows": [
                {"name": "UST 2Y", "date": target, "value": 4.75, "change": 0.03},
                {"name": "UST 10Y", "date": target, "value": 4.31, "change": 0.02},
                {"name": "10Y-2Y curve", "date": target, "value": -0.44, "change": -0.01},
            ],
            "errors": [],
        },
        "economic_calendar": {
            "source_name": "Sample calendar",
            "rows": [
                {"country": "United States", "event": "Initial jobless claims", "date": target, "forecast": "220K", "previous": "218K"},
                {"country": "Japan", "event": "BOJ policy remarks", "date": target, "forecast": "", "previous": ""},
                {"country": "India", "event": "Industrial production", "date": target, "forecast": "4.0%", "previous": "3.8%"},
            ],
            "errors": [],
        },
        "global_news": {
            "source_name": "Sample news",
            "rows": [
                {"source_name": "Sample wire", "title": "Global yields rise as markets reassess inflation path", "link": "https://example.com/rates"},
                {"source_name": "Sample wire", "title": "Semiconductor shares firm on AI infrastructure demand", "link": "https://example.com/semis"},
            ],
            "errors": [],
        },
        "portfolio": portfolio,
        "portfolio_market_data": {
            "source_name": "Sample portfolio market data",
            "rows": [{"name": f"{h['ticker']} - {h['name']}", "symbol": h["ticker"], "price": 100, "change_pct": 0.5} for h in portfolio["holdings"]],
            "errors": [],
        },
        "portfolio_news": {
            "source_name": "Sample portfolio news",
            "rows": [
                {"ticker": h["ticker"], "name": h["name"], "theme": h["theme"], "region": h["region"], "matched_news": []}
                for h in portfolio["holdings"]
            ],
            "errors": [],
        },
        "portfolio_ticker_news": {
            "source_name": "Sample portfolio ticker news",
            "rows": [
                {
                    "ticker": h["ticker"],
                    "name": h["name"],
                    "theme": h["theme"],
                    "region": h["region"],
                    "headlines": [
                        {
                            "title": f"Sample update for {h['ticker']} tied to {h['theme']}",
                            "link": f"https://example.com/{h['ticker'].lower().replace('.', '-')}",
                        }
                    ],
                }
                for h in portfolio["holdings"]
            ],
            "errors": [],
        },
        "diversification_watchlist_market_data": {
            "source_name": "Sample diversification watchlist market data",
            "rows": [
                {"name": "MSFT - Microsoft", "symbol": "MSFT", "price": 455, "change_pct": 0.4},
                {"name": "JPM - JPMorgan Chase", "symbol": "JPM", "price": 205, "change_pct": 0.8},
                {"name": "LLY - Eli Lilly", "symbol": "LLY", "price": 880, "change_pct": -0.2},
                {"name": "CAT - Caterpillar", "symbol": "CAT", "price": 330, "change_pct": 0.6},
                {"name": "XOM - Exxon Mobil", "symbol": "XOM", "price": 115, "change_pct": 0.3},
            ],
            "errors": [],
        },
        "diversification_watchlist_ticker_news": {
            "source_name": "Sample diversification watchlist ticker news",
            "rows": [
                {
                    "ticker": ticker,
                    "name": name,
                    "headlines": [{"title": f"Sample update for {ticker}", "link": f"https://example.com/{ticker.lower()}"}],
                }
                for ticker, name in [
                    ("MSFT", "Microsoft"),
                    ("JPM", "JPMorgan Chase"),
                    ("LLY", "Eli Lilly"),
                    ("CAT", "Caterpillar"),
                    ("XOM", "Exxon Mobil"),
                ]
            ],
            "errors": [],
        },
    }
