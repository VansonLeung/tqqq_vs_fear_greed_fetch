import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from fear_greed import prepare_report, read_events
from fear_greed.formatters.text import format_report
from fear_greed.models import DataError
from conftest import instant, payload


def run(config, score=50, timestamp="2026-09-14T20:05:00Z", now="2026-09-15T00:00:00Z", **extra):
    return prepare_report(config, now=instant(now), fetcher=lambda _: payload(score, timestamp, **extra))


def fail(config, now="2026-09-15T00:00:00Z"):
    def broken(_):
        raise DataError("http_error", "CNN returned HTTP 418")
    return prepare_report(config, now=instant(now), fetcher=broken)


def test_first_run_has_status_without_entry(config):
    report = run(config, 20)
    assert report["extreme_status"] == "extreme_fear"
    assert report["entry_event"] is None
    assert report["previous_observation"] is None
    assert report["change_points"] is None
    assert report["report_date"] == "2026-09-15"
    assert report["is_new_observation"]
    assert "Warning: Extreme Fear" in format_report(report)


def test_entry_repeats_exit_reentry_and_recovery(config):
    run(config)
    entry = run(config, 20, "2026-09-14T20:10:00Z")
    replay = run(config, 20, "2026-09-14T20:10:00Z")
    assert entry["entry_event"] == replay["entry_event"]
    assert not replay["is_new_observation"]
    assert replay["change_points"] == -30
    continued = run(config, 19, "2026-09-14T20:15:00Z")
    assert continued["extreme_status"] == "extreme_fear"
    assert continued["entry_event"] is None
    run(config, 40, "2026-09-14T20:20:00Z")
    reentry = run(config, 18, "2026-09-14T20:25:00Z")
    greed = run(config, 80, "2026-09-14T20:30:00Z")
    assert reentry["entry_event"]["event_id"] != entry["entry_event"]["event_id"]
    assert greed["entry_event"]["category"] == "extreme_greed"
    events = read_events(config.database)
    assert len(events) == 3
    assert read_events(config.database, events[0]["sequence"]) == events[1:]


def test_first_run_failure_and_cached_failure(config):
    unavailable = fail(config)
    assert unavailable["freshness"] == "unavailable"
    assert unavailable["observation"] is None
    assert unavailable["change_points"] is None
    assert unavailable["classification_source"] is None
    assert not unavailable["is_cached"]
    first = run(config, 31.0571)
    cached = fail(config, "2026-09-16T00:00:00Z")
    assert cached["observation"] == first["observation"]
    assert cached["fetched_at"] == first["fetched_at"]
    assert cached["fetch_status"] == "failure"
    assert cached["freshness"] == "stale"
    assert cached["is_cached"]
    assert cached["entry_event"] is None
    json.dumps(cached, allow_nan=False)


def test_stale_observation_does_not_advance_alert_state(config):
    run(config)
    stale = run(config, 20, "2026-09-15T18:00:00Z", "2026-09-16T00:00:00Z")
    assert stale["fetch_status"] == "success"
    assert stale["freshness"] == "stale"
    assert not stale["is_new_observation"]
    assert stale["entry_event"] is None
    fresh = run(config, 19, "2026-09-15T20:05:00Z", "2026-09-16T00:00:00Z")
    assert fresh["entry_event"] is not None
    assert fresh["previous_observation"]["score"] == 50


def test_revisions_and_old_observations_preserve_snapshot_and_provenance(config):
    baseline = run(config)
    revised = run(config, 20)
    assert revised["observation"] == baseline["observation"]
    assert revised["quality_issues"][0]["code"] == "observation_revision"
    older = run(config, 20, "2026-09-11T20:05:00Z")
    assert older["observation"] == baseline["observation"]
    assert older["quality_issues"][0]["code"] == "out_of_order"
    assert read_events(config.database) == []
    with sqlite3.connect(config.database) as db:
        attempts = db.execute("SELECT payload FROM attempts ORDER BY sequence").fetchall()
    assert len(attempts) == 3
    assert json.loads(attempts[1][0])["fear_and_greed"]["score"] == 20


def test_invalid_payload_does_not_overwrite_last_good(config):
    baseline = run(config)
    invalid = run(config, 20, "2026-09-14T20:10:00Z", rating="greed")
    assert invalid["observation"] == baseline["observation"]
    assert invalid["fetch_status"] == "failure"
    assert invalid["quality_issues"][0]["code"] == "category_conflict"
    assert read_events(config.database) == []


def test_concurrent_preparations_create_one_event(config):
    run(config)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: run(config, 20, "2026-09-14T20:10:00Z"), range(3)))
    assert len(read_events(config.database)) == 1
    assert len({r["entry_event"]["event_id"] for r in results}) == 1
    assert sum(r["is_new_observation"] for r in results) == 1


def test_storage_failure_rolls_back_observation_and_event(config, monkeypatch):
    from fear_greed.storage import Store
    baseline = run(config)
    with monkeypatch.context() as context:
        def fail_write(*args, **kwargs):
            raise sqlite3.OperationalError("simulated disk failure")
        context.setattr(Store, "save_attempt", fail_write)
        with pytest.raises(sqlite3.OperationalError):
            run(config, 20, "2026-09-14T20:10:00Z")
    assert read_events(config.database) == []
    assert fail(config)["observation"] == baseline["observation"]
    assert run(config, 20, "2026-09-14T20:10:00Z")["entry_event"] is not None
