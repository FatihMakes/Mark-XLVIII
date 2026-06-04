"""
core/tradingview.py — Live market analysis tool for the Eva and Tom roles.

Gives a role agent (or Jarvis directly) live price + technical read for a symbol via
TradingView's public analysis (the ``tradingview_ta`` library): close, the BUY/SELL/
NEUTRAL recommendation, and the key indicators (RSI, MACD, EMAs). Eva uses it for the
gold/numbers desk; Tom uses it to see the live price and signal BEFORE describing an
order (it does not place orders — Tom's confirmation gate still governs any trade).

Scoping (Tier 2): this is registered as the ``tradingview`` tool and added to the eva/tom
allowlists. The registry/role machinery is unchanged — it is just another tool.

The pure parts (symbol resolution, interval normalisation, formatting) are unit-tested
with an injected fake handler, so no network or the ``tradingview_ta`` package is needed
to test the logic. The default handler factory builds a real ``TA_Handler``.
"""

from __future__ import annotations

from typing import Callable


# keyword -> (symbol, exchange, screener). Verified live against tradingview_ta.
# Gold/silver sit on OANDA under the 'cfd' screener (NOT 'forex').
SYMBOL_MAP: dict[str, tuple[str, str, str]] = {
    "gold": ("XAUUSD", "OANDA", "cfd"),
    "xau": ("XAUUSD", "OANDA", "cfd"),
    "xauusd": ("XAUUSD", "OANDA", "cfd"),
    "silver": ("XAGUSD", "OANDA", "cfd"),
    "xag": ("XAGUSD", "OANDA", "cfd"),
    "btc": ("BTCUSD", "BINANCE", "crypto"),
    "bitcoin": ("BTCUSD", "BINANCE", "crypto"),
    "eth": ("ETHUSD", "BINANCE", "crypto"),
    "ethereum": ("ETHUSD", "BINANCE", "crypto"),
    "eurusd": ("EURUSD", "OANDA", "forex"),
    "eur": ("EURUSD", "OANDA", "forex"),
    "gbpusd": ("GBPUSD", "OANDA", "forex"),
    "usdjpy": ("USDJPY", "OANDA", "forex"),
}

# user input -> canonical interval label
_INTERVAL_ALIASES = {
    "1": "1m", "1m": "1m", "1min": "1m",
    "5": "5m", "5m": "5m", "5min": "5m",
    "15": "15m", "15m": "15m", "15min": "15m",
    "30": "30m", "30m": "30m", "30min": "30m",
    "60": "1h", "1h": "1h", "60m": "1h", "hour": "1h", "1hour": "1h",
    "120": "2h", "2h": "2h",
    "240": "4h", "4h": "4h",
    "1d": "1d", "d": "1d", "day": "1d", "daily": "1d",
    "1w": "1w", "w": "1w", "week": "1w", "weekly": "1w",
    "1mo": "1M", "1month": "1M", "month": "1M",
}

DEFAULT_INTERVAL = "15m"


def normalize_interval(value: str | None) -> str:
    """Normalise a user interval ('15', '15min', '1 hour') to a canonical label."""
    if not value:
        return DEFAULT_INTERVAL
    key = str(value).strip().lower().replace(" ", "")
    return _INTERVAL_ALIASES.get(key, DEFAULT_INTERVAL)


def resolve_symbol(
    query: str,
    *,
    exchange: str = "",
    screener: str = "",
) -> tuple[str, str, str] | None:
    """Resolve a free-text query to (symbol, exchange, screener).

    Order: known keyword map → explicit symbol+exchange+screener overrides → None.
    """
    if not query:
        return None
    low = query.strip().lower()
    # direct keyword hit, or any mapped keyword appearing in the phrase
    if low in SYMBOL_MAP:
        return SYMBOL_MAP[low]
    for kw, triple in SYMBOL_MAP.items():
        if kw in low:
            return triple
    # explicit override: caller gave us enough to query directly
    if exchange and screener:
        return (query.strip().upper(), exchange.upper(), screener.lower())
    return None


def _f(indicators: dict, key: str, ndigits: int = 2):
    v = indicators.get(key)
    try:
        return round(float(v), ndigits)
    except (TypeError, ValueError):
        return None


def format_analysis(symbol: str, interval: str, summary: dict, indicators: dict) -> str:
    """Build a concise, voice-friendly summary line from a raw analysis."""
    rec = summary.get("RECOMMENDATION", "NEUTRAL")
    buy, sell, neu = summary.get("BUY", 0), summary.get("SELL", 0), summary.get("NEUTRAL", 0)
    close = _f(indicators, "close", 3)
    rsi = _f(indicators, "RSI", 1)
    macd = _f(indicators, "MACD.macd", 3)
    signal = _f(indicators, "MACD.signal", 3)
    ema50 = _f(indicators, "EMA50", 2)
    ema200 = _f(indicators, "EMA200", 2)

    parts = [f"{symbol} ({interval}): {close}." if close is not None else f"{symbol} ({interval})."]
    parts.append(f"Signal: {rec} ({buy} buy / {sell} sell / {neu} neutral).")
    bits = []
    if rsi is not None:
        bits.append(f"RSI {rsi}")
    if macd is not None and signal is not None:
        bits.append(f"MACD {macd} vs signal {signal}")
    if ema50 is not None:
        bits.append(f"EMA50 {ema50}")
    if ema200 is not None:
        bits.append(f"EMA200 {ema200}")
    if bits:
        parts.append(", ".join(bits) + ".")
    return " ".join(parts)


def _default_handler_factory(symbol: str, exchange: str, screener: str, interval_label: str):
    """Build a real TA_Handler (imported lazily so tests need no network/package)."""
    from tradingview_ta import TA_Handler, Interval

    interval_map = {
        "1m": Interval.INTERVAL_1_MINUTE,
        "5m": Interval.INTERVAL_5_MINUTES,
        "15m": Interval.INTERVAL_15_MINUTES,
        "30m": Interval.INTERVAL_30_MINUTES,
        "1h": Interval.INTERVAL_1_HOUR,
        "2h": Interval.INTERVAL_2_HOURS,
        "4h": Interval.INTERVAL_4_HOURS,
        "1d": Interval.INTERVAL_1_DAY,
        "1w": Interval.INTERVAL_1_WEEK,
        "1M": Interval.INTERVAL_1_MONTH,
    }
    return TA_Handler(
        symbol=symbol, exchange=exchange, screener=screener,
        interval=interval_map.get(interval_label, Interval.INTERVAL_15_MINUTES),
    )


def get_analysis(
    query: str,
    interval: str = DEFAULT_INTERVAL,
    *,
    exchange: str = "",
    screener: str = "",
    handler_factory: Callable | None = None,
) -> dict:
    """Fetch a live analysis. Returns {ok, text, ...} — never raises (errors as data)."""
    resolved = resolve_symbol(query, exchange=exchange, screener=screener)
    if not resolved:
        return {
            "ok": False,
            "text": (
                f"I couldn't map '{query}' to a market. Known: "
                f"{', '.join(sorted(set(k for k in SYMBOL_MAP)))}. "
                f"Or pass exchange + screener explicitly."
            ),
        }
    symbol, exch, scr = resolved
    label = normalize_interval(interval)
    factory = handler_factory or _default_handler_factory
    try:
        handler = factory(symbol, exch, scr, label)
        analysis = handler.get_analysis()
        text = format_analysis(symbol, label, analysis.summary, analysis.indicators)
        return {
            "ok": True,
            "text": text,
            "symbol": symbol,
            "exchange": exch,
            "interval": label,
            "recommendation": analysis.summary.get("RECOMMENDATION"),
            "close": analysis.indicators.get("close"),
        }
    except Exception as e:  # boundary: report as data, never crash the agent
        return {"ok": False, "text": f"TradingView lookup for {symbol} failed: {e}"}


def tradingview_tool(parameters: dict, player=None, speak=None) -> str:
    """Action entry point (matches the other actions' signature).

    Params: symbol|query (required), interval (optional), exchange/screener (optional
    overrides). Returns a concise analysis string for the agent/voice.
    """
    params = parameters or {}
    query = params.get("symbol") or params.get("query") or ""
    result = get_analysis(
        query,
        interval=params.get("interval", DEFAULT_INTERVAL),
        exchange=params.get("exchange", ""),
        screener=params.get("screener", ""),
    )
    text = result["text"]
    try:
        if player is not None and hasattr(player, "write_log"):
            player.write_log(f"TV: {text[:80]}")
    except Exception:
        pass
    return text
