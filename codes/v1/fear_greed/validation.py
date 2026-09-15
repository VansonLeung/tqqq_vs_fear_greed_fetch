"""Parse only the current CNN summary; historical points are not live snapshots."""

import math
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .config import MARKET_TIMEZONE
from .models import DataError, Observation, parse_time, utc_iso
from .rules import classify


def parse_observation(payload: dict, now: datetime) -> Observation:
    summary = payload.get("fear_and_greed") if isinstance(payload, dict) else None
    if not isinstance(summary, dict):
        raise DataError("invalid_payload", "Missing fear_and_greed summary object")
    score = summary.get("score")
    if (isinstance(score, bool) or not isinstance(score, (int, float))
            or not 0 <= score <= 100 or not math.isfinite(score)):
        raise DataError("invalid_score", "CNN score must be a finite number in [0, 100]")
    try:
        timestamp = parse_time(summary.get("timestamp"))
    except (ValueError, TypeError, OverflowError) as exc:
        raise DataError("invalid_timestamp", "CNN timestamp must be timezone-aware ISO 8601") from exc
    if timestamp > now:
        raise DataError("future_observation", "CNN observation is later than preparation time")
    local_date = timestamp.astimezone(ZoneInfo(MARKET_TIMEZONE)).date()
    provided_date = summary.get("market_date")
    try:
        market_date = date.fromisoformat(provided_date) if provided_date is not None else local_date
    except (ValueError, TypeError) as exc:
        raise DataError("invalid_market_date", "Invalid CNN market_date") from exc
    if market_date > local_date:
        raise DataError("invalid_market_date", "CNN market_date is later than its observation")
    original = summary.get("rating")
    expected = classify(score)
    if original is None:
        category, classification_source = expected, "cnn_raw_score_fallback"
    else:
        if not isinstance(original, str):
            raise DataError("invalid_category", "CNN rating must be text")
        category = "_".join(original.lower().replace("_", " ").split())
        if category not in {"extreme_fear", "fear", "neutral", "greed", "extreme_greed"}:
            raise DataError("invalid_category", "Unrecognized CNN rating")
        if category != expected:
            raise DataError("category_conflict", "CNN rating conflicts with its verified raw-score classification")
        classification_source = "cnn"
    return Observation(
        float(score), category, original, utc_iso(timestamp), market_date.isoformat(),
        "cnn" if provided_date is not None else "observation_america_new_york",
        classification_source,
    )
