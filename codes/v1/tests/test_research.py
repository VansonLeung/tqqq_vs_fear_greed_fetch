import numpy as np
import pandas as pd
import pytest

from fear_greed.charts.indicators import add_indicators
from fear_greed.research.outcomes import study_outcomes


def research_data():
    dates = pd.bdate_range("2021-01-01", periods=1000)
    data = pd.DataFrame({"close": 100 + np.sin(np.arange(1000) / 20) * 10 + np.arange(1000) * .03,
                         "fg": np.where(np.arange(1000) % 8 < 3, 20., 40.)}, index=dates)
    return add_indicators(data)


def test_research_excludes_overlap_and_windows_crossing_split():
    data = research_data()
    split = data.index[600]
    study = study_outcomes(data, str(split.date()))
    for period, horizons in study["results"].items():
        for horizon, groups in horizons.items():
            events = sorted(groups["above"]["samples"] + groups["below"]["samples"], key=lambda x: x["session"])
            for previous, current in zip(events, events[1:]):
                assert current["session"] > previous["end_session"]
            for group in groups.values():
                assert group["sample_count"] <= group["candidate_count"]
                for sample in group["samples"]:
                    assert sample["end_position"] - sample["start_position"] == int(horizon)
                    if period == "development":
                        assert sample["end_session"] < str(split.date())
                    else:
                        assert sample["session"] >= str(split.date())
    assert "Retrospective" in study["execution"]


def test_research_outcomes_use_complete_paths_and_running_peak():
    data = research_data()
    # Choose a known extreme exit, then alter its outcome path after indicators.
    i = 603
    assert data.iloc[i - 1].category == "extreme_fear"
    assert data.iloc[i].category == "fear"
    data.loc[data.index[i:i+6], "close"] = [100, 120, 90, 110, 115, 125]
    data.loc[data.index[i], "sma200"] = 99
    study = study_outcomes(data, str(data.index[i].date()), horizons=(5,))
    sample = study["results"]["evaluation"]["5"]["above"]["samples"][0]
    assert sample["price_return"] == .25
    assert sample["max_drawdown"] == -.25
    data.loc[data.index[i + 2], "close"] = np.nan
    updated = study_outcomes(data, str(data.index[i].date()), horizons=(5,))
    assert all(s["session"] != str(data.index[i].date())
               for s in updated["results"]["evaluation"]["5"]["above"]["samples"])


def test_missing_sentiment_breaks_exit_and_small_groups_are_marked():
    data = research_data()
    data.loc[:, "category"] = "fear"
    data.loc[data.index[603], "category"] = None
    study = study_outcomes(data, str(data.index[600].date()))
    for period in study["results"].values():
        for horizon in period.values():
            for group in ("above", "below"):
                assert horizon[group]["sample_count"] == 0
                assert horizon[group]["median_price_return"] is None
                assert horizon[group]["small_sample"]


def test_research_rejects_split_outside_usable_history():
    with pytest.raises(ValueError, match="Split date"):
        study_outcomes(research_data(), "2030-01-01")
