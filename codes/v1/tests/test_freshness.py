import pytest

from fear_greed.freshness import assess_freshness
from fear_greed.validation import parse_observation
from conftest import instant, payload


@pytest.mark.parametrize("observed,now,expected", [
    ("2026-09-14T20:05:00Z", "2026-09-15T00:00:00Z", "current"),
    ("2026-09-14T19:59:00Z", "2026-09-15T00:00:00Z", "stale"),
    ("2026-09-11T20:05:00Z", "2026-09-14T00:00:00Z", "current"),  # Sunday
    ("2026-09-04T20:05:00Z", "2026-09-08T00:00:00Z", "current"),  # Labor Day
    ("2026-09-04T20:05:00Z", "2026-09-09T00:00:00Z", "stale"),
    ("2026-03-06T21:05:00Z", "2026-03-09T00:00:00Z", "current"),  # DST weekend
    ("2026-03-09T20:05:00Z", "2026-03-10T00:00:00Z", "current"),
    ("2026-11-02T20:30:00Z", "2026-11-03T00:00:00Z", "stale"),  # standard-time close
    ("2026-11-02T21:05:00Z", "2026-11-03T00:00:00Z", "current"),
    ("2026-11-27T18:05:00Z", "2026-11-28T00:00:00Z", "current"),  # early close
    ("2026-09-11T20:05:00Z", "2026-09-14T18:00:00Z", "current"),  # before Monday close
])
def test_session_freshness(observed, now, expected):
    clock = instant(now)
    observation = parse_observation(payload(timestamp=observed), clock).to_dict()
    assert assess_freshness(observation, clock)[0] == expected


def test_calendar_failure_is_unknown(monkeypatch):
    def broken(*args, **kwargs):
        raise ValueError("calendar broken")
    monkeypatch.setattr("fear_greed.freshness.mcal.get_calendar", broken)
    obs = parse_observation(payload(), instant()).to_dict()
    freshness, issues = assess_freshness(obs, instant())
    assert freshness == "unknown"
    assert issues[0]["code"] == "calendar_unavailable"
