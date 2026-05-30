from app.collectors.mexc_collector import MexcCollector


def test_mexc_parse_ticker_payload():
    collector = MexcCollector(symbols=["XAUT_USDT"])
    tick = collector._parse_ticker(
        {
            "symbol": "XAUT_USDT",
            "lastPrice": 4519.3,
            "bid1": 4519.2,
            "ask1": 4519.3,
            "volume24": 98406552,
            "holdVol": 34212284,
            "timestamp": 1780134420770,
        },
        "XAUT_USDT",
    )

    assert tick is not None
    assert tick.exchange == "mexc"
    assert tick.symbol == "XAUT_USDT"
    assert tick.market_type == "perp"
    assert tick.bid == 4519.2
    assert tick.ask == 4519.3
    assert tick.mid == 4519.25
    assert tick.last_price == 4519.3
    assert tick.volume_24h == 98406552
    assert tick.open_interest == 34212284


def test_mexc_parse_ticker_rejects_empty_book():
    collector = MexcCollector(symbols=["XAUT_USDT"])

    assert collector._parse_ticker({"symbol": "XAUT_USDT", "bid1": 0, "ask1": 4519.3}, "XAUT_USDT") is None
    assert collector._parse_ticker({"symbol": "XAUT_USDT", "bid1": 4519.2, "ask1": 0}, "XAUT_USDT") is None
