"""
TradingView tool tests (stdlib unittest — fake handler, no network, no tradingview_ta).

Run:
    python -m unittest tests.core.test_tradingview -v

Covers the pure logic and the failure-isolated tool boundary:
  - symbol resolution (gold -> OANDA/cfd, explicit overrides, unknown -> None)
  - interval normalisation
  - analysis formatting
  - get_analysis with an injected fake handler (success + raising handler -> error data)
"""

import unittest

from core import tradingview as TV


class FakeAnalysis:
    def __init__(self, summary, indicators):
        self.summary = summary
        self.indicators = indicators


class FakeHandler:
    def __init__(self, analysis):
        self._a = analysis

    def get_analysis(self):
        return self._a


GOLD_SUMMARY = {"RECOMMENDATION": "SELL", "BUY": 5, "SELL": 12, "NEUTRAL": 9}
GOLD_IND = {"close": 4446.14, "RSI": 50.2945, "MACD.macd": 1.803,
            "MACD.signal": 0.479, "EMA50": 4448.27, "EMA200": 4471.65}


class TestSymbolResolution(unittest.TestCase):
    def test_known_keywords(self):
        self.assertEqual(TV.resolve_symbol("gold"), ("XAUUSD", "OANDA", "cfd"))
        self.assertEqual(TV.resolve_symbol("what is the gold price"),
                         ("XAUUSD", "OANDA", "cfd"))
        self.assertEqual(TV.resolve_symbol("BTC"), ("BTCUSD", "BINANCE", "crypto"))

    def test_gold_uses_cfd_not_forex(self):
        # Regression: forex screener fails for gold; it must resolve to cfd.
        self.assertEqual(TV.resolve_symbol("gold")[2], "cfd")

    def test_explicit_override(self):
        self.assertEqual(
            TV.resolve_symbol("AAPL", exchange="NASDAQ", screener="america"),
            ("AAPL", "NASDAQ", "america"),
        )

    def test_unknown_returns_none(self):
        self.assertIsNone(TV.resolve_symbol("zzzqqq"))
        self.assertIsNone(TV.resolve_symbol(""))


class TestIntervalNormalisation(unittest.TestCase):
    def test_aliases(self):
        self.assertEqual(TV.normalize_interval("15"), "15m")
        self.assertEqual(TV.normalize_interval("15min"), "15m")
        self.assertEqual(TV.normalize_interval("1 hour"), "1h")
        self.assertEqual(TV.normalize_interval("daily"), "1d")
        self.assertEqual(TV.normalize_interval(None), "15m")
        self.assertEqual(TV.normalize_interval("garbage"), "15m")


class TestFormatting(unittest.TestCase):
    def test_format_includes_price_signal_indicators(self):
        text = TV.format_analysis("XAUUSD", "15m", GOLD_SUMMARY, GOLD_IND)
        self.assertIn("XAUUSD (15m): 4446.14", text)
        self.assertIn("Signal: SELL (5 buy / 12 sell / 9 neutral)", text)
        self.assertIn("RSI 50.3", text)
        self.assertIn("MACD 1.803 vs signal 0.479", text)
        self.assertIn("EMA200 4471.65", text)

    def test_format_tolerates_missing_indicators(self):
        text = TV.format_analysis("XAUUSD", "15m", {"RECOMMENDATION": "NEUTRAL"}, {})
        self.assertIn("XAUUSD (15m)", text)
        self.assertIn("NEUTRAL", text)


class TestGetAnalysis(unittest.TestCase):
    def _factory(self, summary, ind):
        return lambda sym, exch, scr, interval: FakeHandler(FakeAnalysis(summary, ind))

    def test_success(self):
        res = TV.get_analysis("gold", "15m",
                              handler_factory=self._factory(GOLD_SUMMARY, GOLD_IND))
        self.assertTrue(res["ok"])
        self.assertEqual(res["symbol"], "XAUUSD")
        self.assertEqual(res["recommendation"], "SELL")
        self.assertIn("4446.14", res["text"])

    def test_passes_resolved_params_to_factory(self):
        seen = {}

        def factory(sym, exch, scr, interval):
            seen.update(symbol=sym, exchange=exch, screener=scr, interval=interval)
            return FakeHandler(FakeAnalysis(GOLD_SUMMARY, GOLD_IND))

        TV.get_analysis("gold", "1h", handler_factory=factory)
        self.assertEqual(seen, {"symbol": "XAUUSD", "exchange": "OANDA",
                                "screener": "cfd", "interval": "1h"})

    def test_unknown_symbol_returns_error_data(self):
        res = TV.get_analysis("zzzqqq")
        self.assertFalse(res["ok"])
        self.assertIn("couldn't map", res["text"])

    def test_raising_handler_becomes_error_data(self):
        def boom(*a):
            raise RuntimeError("network down")

        res = TV.get_analysis("gold", handler_factory=boom)
        self.assertFalse(res["ok"])
        self.assertIn("failed", res["text"])

    def test_tool_entry_point(self):
        # tradingview_tool uses the real factory; force an unknown symbol so it
        # returns deterministically without a network call.
        out = TV.tradingview_tool({"symbol": "zzzqqq"})
        self.assertIn("couldn't map", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
