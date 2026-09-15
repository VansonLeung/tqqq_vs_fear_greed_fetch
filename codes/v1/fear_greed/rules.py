"""CNN raw-score categories, verified against API ratings and page predicates."""

import hashlib
import math

EXTREMES = {"extreme_fear", "extreme_greed"}


def classify(score: float) -> str:
    # The web gauge rounds first, but live API ratings use the raw score.
    # Alert classification follows the API; never classify a display value.
    if isinstance(score, bool) or not 0 <= score <= 100 or not math.isfinite(score):
        raise ValueError("Score must be finite and within [0, 100]")
    if score <= 25:
        return "extreme_fear"
    if score < 45:
        return "fear"
    if score <= 55:
        return "neutral"
    if score < 75:
        return "greed"
    return "extreme_greed"


def entry_event(previous: dict | None, current: dict) -> dict | None:
    if previous is None or current["category"] not in EXTREMES:
        return None
    if previous["category"] == current["category"]:
        return None
    identity = f"cnn|{current['observed_at']}|{current['category']}"
    return {
        "event_id": hashlib.sha256(identity.encode()).hexdigest(),
        "category": current["category"],
        "observed_at": current["observed_at"],
        "previous_observed_at": previous["observed_at"],
    }
