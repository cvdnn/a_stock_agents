from server.agent.tools import _extract_latest_tech_summary


def test_extract_latest_tech_summary_accepts_current_flat_shape() -> None:
    summary = _extract_latest_tech_summary({
        "ma5": 1275.1,
        "ma10": 1284.2,
        "ma20": 1298.23,
        "macd_bar": -2.31,
        "rsi": 41.88,
    })

    assert summary == {
        "ma5": 1275.1,
        "ma10": 1284.2,
        "ma20": 1298.23,
        "macd_hist": -2.31,
        "rsi": 41.88,
        "rsi6": None,
    }


def test_extract_latest_tech_summary_accepts_legacy_nested_shape() -> None:
    summary = _extract_latest_tech_summary({
        "ma": {"ma5": 1275.1, "ma10": 1284.2, "ma20": 1298.23},
        "macd": {"hist": -2.31},
        "rsi": {"rsi6": 41.88},
    })

    assert summary == {
        "ma5": 1275.1,
        "ma10": 1284.2,
        "ma20": 1298.23,
        "macd_hist": -2.31,
        "rsi": 41.88,
        "rsi6": 41.88,
    }
