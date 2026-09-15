import numpy as np
import pandas as pd
import pytest

from fear_greed.charts.indicators import add_indicators, drawdown, extreme_transitions, forward_performance, trend_label


def frame(size=260):
    return pd.DataFrame({"close": np.arange(1, size + 1, dtype=float), "fg": np.full(size, 50.)},
                        index=pd.bdate_range("2025-01-01", periods=size))


def test_moving_average_warmup_and_session_changes():
    data = frame()
    data["fg"] = np.linspace(20, 80, len(data))
    result = add_indicators(data)
    assert pd.isna(result.iloc[198].sma200)
    assert result.iloc[199].sma200 == 100.5
    assert result.iloc[200].sma200 == 101.5
    assert result.iloc[20].return20 == 20
    assert result.iloc[5].fg_change5 == pytest.approx(data.fg.iloc[5] - data.fg.iloc[0])
    assert result.iloc[4].fg_sma5 == pytest.approx(data.fg.iloc[:5].mean())
    # Slicing a display window retains averages calculated before that window.
    assert result.iloc[230:].iloc[0].sma200 == pytest.approx(data.close.iloc[31:231].mean())


def test_gaps_break_averages_changes_and_event_inference():
    data = frame()
    data.iloc[235, data.columns.get_loc("fg")] = np.nan
    data.iloc[230, data.columns.get_loc("close")] = np.nan
    result = add_indicators(data)
    assert pd.isna(result.iloc[240].fg_change20)
    assert pd.isna(result.iloc[235].return20)
    assert pd.isna(result.iloc[236].fg_sma5)
    assert pd.isna(result.iloc[239].sma20)
    small = frame(6)
    small["fg"] = [20, 30, 80, np.nan, 20, 21]
    events = extreme_transitions(add_indicators(small))
    assert [(direction, zone) for _, direction, zone in events] == [("exit", "extreme_fear"), ("enter", "extreme_greed")]


def test_window_drawdown():
    close = pd.Series([100., 120., 90., 110.])
    assert drawdown(close).tolist() == pytest.approx([0, 0, -.25, -1/12])
    assert drawdown(close.iloc[2:]).tolist() == [0, 0]


def test_forward_performance_excludes_unfinished_outcomes_and_zero_is_not_a_win():
    data = frame(5)
    data["close"] = [100., 110., 100., 110., 50.]
    data["fg"] = [25., 25., 25., 25., 25.]
    result = forward_performance(data, horizon=2)
    fear = result["results"][0]
    assert fear["sample_count"] == 3
    assert fear["mean_return"] == pytest.approx(-.5 / 3)
    assert fear["win_rate"] == 0
    assert result["results"][1]["mean_return"] is None
    assert result["results"][1]["win_rate"] is None


def test_forward_performance_preserves_session_gaps_and_category_boundaries():
    data = frame(8)
    data["fg"] = [25., 25.1, 45., 55., 55.1, 75., 100., 0.]
    summary = forward_performance(data, horizon=1)["results"]
    assert [row["sample_count"] for row in summary] == [1, 1, 2, 1, 2]
    assert all(row["win_rate"] == 1 for row in summary)

    data = frame(7)
    data.loc[data.index[2], "close"] = float("nan")
    # Only starting sessions 3 and 4 have complete 2-session price paths.
    # Missing starting sentiment excludes session 3, without compressing time.
    data.loc[data.index[3], "fg"] = float("nan")
    neutral = forward_performance(data, horizon=2)["results"][2]
    assert neutral["sample_count"] == 1
    assert neutral["mean_return"] == pytest.approx(7 / 5 - 1)
    assert neutral["win_rate"] == 1


@pytest.mark.parametrize("price,sentiment,label", [
    (.1, 5, "Price and sentiment strengthening"), (-.1, -5, "Price and sentiment weakening"),
    (.1, -5, "Price-sentiment divergence"), (-.1, 5, "Sentiment improving; price falling"),
    (0, 5, "TQQQ unchanged"), (.1, 0, "Sentiment unchanged"),
    (float("nan"), 5, "Trend comparison unavailable"),
])
def test_trend_annotations(price, sentiment, label):
    assert trend_label(price, sentiment) == label
