import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from fear_greed.charts.history import align_sessions, load_histories
from fear_greed.models import DataError
from fear_greed.providers import cnn_history, tqqq
from conftest import instant


def fixture(name):
    return json.loads((Path(__file__).parent / "fixtures" / name).read_text())


def test_nasdaq_prices_are_not_adjusted_a_second_time():
    frame = tqqq.parse_history(fixture("nasdaq_history.excerpt.json"))
    assert frame.loc["2025-11-19", "close"] == 50.025
    assert frame.loc["2025-11-20", "close"] == 46.45
    assert frame.loc["2022-12-28", "close"] == 8.08
    assert frame.index.is_monotonic_increasing


@pytest.mark.parametrize("change", ["truncated", "duplicate", "negative", "wrong_symbol"])
def test_invalid_tqqq_history(change):
    payload = fixture("nasdaq_history.excerpt.json")
    data = payload["data"]
    if change == "truncated":
        data["totalRecords"] += 1
    elif change == "duplicate":
        data["tradesTable"]["rows"][1] = data["tradesTable"]["rows"][0]
    elif change == "negative":
        data["tradesTable"]["rows"][0]["close"] = "-1"
    else:
        data["symbol"] = "QQQ"
    with pytest.raises(DataError):
        tqqq.parse_history(payload)


def test_cnn_dates_are_utc_labels_and_identical_tail_is_deduplicated():
    frame = cnn_history.parse_history(fixture("cnn_history.excerpt.json"))
    assert pd.Timestamp("2021-09-01") in frame.index
    assert pd.Timestamp("2021-08-31") not in frame.index
    assert not frame.index.has_duplicates
    assert frame.loc["2026-09-14", "fg"] == pytest.approx(30.9428571428571)


def test_cnn_live_tail_is_excluded_without_changing_historical_dates_or_scores():
    payload = fixture("cnn_history.live_tail.json")
    dated = copy.deepcopy(payload)
    dated["fear_and_greed_historical"]["data"].pop()
    expected = cnn_history.parse_history(dated)
    pd.testing.assert_frame_equal(cnn_history.parse_history(payload), expected)

    # A live update may differ from the same UTC day's dated historical score.
    payload["fear_and_greed_historical"]["data"][-1]["y"] = 35
    payload["fear_and_greed"]["score"] = 35
    pd.testing.assert_frame_equal(cnn_history.parse_history(payload), expected)


@pytest.mark.parametrize("change", ["missing_summary", "timestamp", "naive_timestamp",
                                    "score", "interior", "older", "no_history"])
def test_cnn_non_midnight_exception_requires_a_matching_live_tail(change):
    payload = fixture("cnn_history.live_tail.json")
    rows = payload["fear_and_greed_historical"]["data"]
    if change == "missing_summary":
        del payload["fear_and_greed"]
    elif change == "timestamp":
        rows[-1]["x"] += 1000
    elif change == "naive_timestamp":
        payload["fear_and_greed"]["timestamp"] = "2026-09-15T07:37:31"
    elif change == "score":
        rows[-1]["y"] = 35
    elif change == "interior":
        rows[-1], rows[-2] = rows[-2], rows[-1]
    elif change == "older":
        rows[-1]["x"] = pd.Timestamp("2021-09-01T01:00:00Z").timestamp() * 1000
        payload["fear_and_greed"]["timestamp"] = "2021-09-01T01:00:00Z"
    else:
        payload["fear_and_greed_historical"]["data"] = rows[-1:]
    with pytest.raises(DataError):
        cnn_history.parse_history(payload)


@pytest.mark.parametrize("change", ["intraday", "conflict", "rating", "invalid"])
def test_reject_changed_cnn_historical_semantics(change):
    payload = fixture("cnn_history.excerpt.json")
    row = payload["fear_and_greed_historical"]["data"][-1]
    if change == "intraday":
        row["x"] += 3600000
    elif change == "conflict":
        row["y"] = 40
    elif change == "rating":
        row["rating"] = "extreme greed"
    else:
        row["y"] = float("nan")
    with pytest.raises(DataError):
        cnn_history.parse_history(payload)


def test_alignment_excludes_future_session_and_keeps_gaps():
    frames = {
        "tqqq": pd.DataFrame({"close": [10, 11, 12]}, index=pd.to_datetime(["2026-09-10", "2026-09-11", "2026-09-14"])),
        "cnn": pd.DataFrame({"fg": [30, 40, 45]}, index=pd.to_datetime(["2026-09-10", "2026-09-14", "2026-09-15"])),
    }
    data, sources, issues = align_sessions(frames, {"tqqq": {}, "cnn": {}}, instant())
    assert data.index[-1] == pd.Timestamp("2026-09-14")
    assert data.loc["2026-09-14", "fg"] == 40
    assert pd.isna(data.loc["2026-09-11", "fg"])
    assert sources["cnn"]["latest_session"] == "2026-09-14"
    assert any(i["code"] == "history_gaps" for i in issues)


@pytest.mark.parametrize("cnn_fixture", ["cnn_history.excerpt.json", "cnn_history.live_tail.json"])
def test_cache_fallback_preserves_dates_and_replaces_full_adjusted_history(config, cnn_fixture):
    nasdaq, cnn = fixture("nasdaq_history.excerpt.json"), fixture(cnn_fixture)
    def fetch(config, url, referer):
        return nasdaq if "nasdaq" in url else cnn
    first, sources, _ = load_histories(config, instant(), fetch)
    initial_fetch_time = sources["tqqq"]["fetched_at"]
    def rejected(*args):
        raise DataError("http", "source unavailable")
    cached, cache_sources, issues = load_histories(config, instant(), rejected)
    pd.testing.assert_frame_equal(cached["tqqq"], first["tqqq"])
    pd.testing.assert_frame_equal(cached["cnn"], first["cnn"])
    assert cache_sources["tqqq"]["is_cached"]
    assert cache_sources["tqqq"]["fetched_at"] == initial_fetch_time
    assert len(issues) == 2
    for row in nasdaq["data"]["tradesTable"]["rows"]:
        row["close"] = str(float(row["close"]) / 2)
    updated, metadata, _ = load_histories(config, instant(), fetch)
    assert metadata["tqqq"]["revised_rows"] == len(first["tqqq"])
    pd.testing.assert_series_equal(updated["tqqq"].close, first["tqqq"].close / 2)


def test_no_cache_source_failure_is_explicit(config):
    def rejected(*args):
        raise DataError("http", "source unavailable")
    with pytest.raises(DataError, match="source unavailable"):
        load_histories(config, instant(), rejected)
