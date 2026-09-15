import math
import json
from pathlib import Path

import pytest

from fear_greed.formatters.text import display_number
from fear_greed.models import DataError
from fear_greed.rules import classify
from fear_greed.validation import parse_observation
from conftest import instant, payload


@pytest.mark.parametrize("score,category", [
    (0, "extreme_fear"), (24.9999, "extreme_fear"), (25, "extreme_fear"),
    (25.0001, "fear"), (25.5, "fear"), (44.9999, "fear"), (45, "neutral"),
    (45.0001, "neutral"), (55, "neutral"), (55.0001, "greed"),
    (74.9999, "greed"), (75, "extreme_greed"), (100, "extreme_greed"),
])
def test_verified_cnn_boundaries(score, category):
    assert classify(score) == category
    result = parse_observation(payload(score, rating=None), instant())
    assert result.category == category
    assert result.score == score
    assert result.classification_source == "cnn_raw_score_fallback"


def test_synthetic_summary_precision_and_provenance(cnn_fixture):
    result = parse_observation(cnn_fixture, instant())
    assert result.score == 31.0571
    assert result.category == "fear"
    assert result.original_category == "fear"
    assert result.market_date == "2026-09-14"
    assert result.classification_source == "cnn"


def test_captured_live_cnn_summary():
    data = json.loads((Path(__file__).parent / "fixtures/cnn_summary.live.json").read_text())
    result = parse_observation(data, instant("2026-09-15T04:30:00Z"))
    assert result.score == 30.9428571428571
    assert result.category == "fear"
    assert result.original_category == "fear"
    assert result.market_date == "2026-09-14"
    assert result.observed_at == "2026-09-15T00:00:00.000000Z"


def test_captured_api_boundary_ratings_use_raw_scores():
    data = json.loads((Path(__file__).parent / "fixtures/cnn_historical_boundaries.live.json").read_text())
    assert data["raw_classification_mismatch_count"] == 0
    assert data["data"]
    for point in data["data"]:
        assert classify(point["y"]) == point["rating"].replace(" ", "_")


@pytest.mark.parametrize("score", [True, None, "31", math.nan, math.inf, -1, 101, 10**1000])
def test_invalid_scores(score):
    data = payload()
    data["fear_and_greed"]["score"] = score
    with pytest.raises(DataError, match="finite number"):
        parse_observation(data, instant())


@pytest.mark.parametrize("timestamp", [None, 1789416300000, "2026-09-14", "2026-09-14T20:05:00", "bad"])
def test_invalid_timestamp(timestamp):
    with pytest.raises(DataError, match="timestamp"):
        parse_observation(payload(timestamp=timestamp), instant())


def test_future_timestamp():
    with pytest.raises(DataError) as caught:
        parse_observation(payload(timestamp="2026-09-15T00:00:01Z"), instant())
    assert caught.value.code == "future_observation"


@pytest.mark.parametrize("rating", ["unknown", 12, "", "extreme greed"])
def test_invalid_or_conflicting_rating(rating):
    with pytest.raises(DataError):
        parse_observation(payload(31, rating=rating), instant())


def test_category_normalization():
    assert parse_observation(payload(20, rating=" EXTREME_FEAR "), instant()).category == "extreme_fear"


def test_market_date_uses_new_york_and_preserves_explicit_date():
    result = parse_observation(payload(timestamp="2026-09-15T00:00:00Z"), instant())
    assert result.market_date == "2026-09-14"
    result = parse_observation(payload(market_date="2026-09-11"), instant())
    assert result.market_date == "2026-09-11"
    assert result.market_date_source == "cnn"
    with pytest.raises(DataError):
        parse_observation(payload(market_date="2026-09-15"), instant())


@pytest.mark.parametrize("data", [[], {}, {"fear_and_greed": []}])
def test_schema_changes(data):
    with pytest.raises(DataError):
        parse_observation(data, instant())


def test_display_rounding_does_not_classify_the_display_value():
    score = 25.01
    assert display_number(score) == "25.0"
    assert classify(score) == "fear"
    assert display_number(1.25) == "1.3"
    assert display_number(-0.001, signed=True) == "+0.0"
