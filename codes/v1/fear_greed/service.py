"""Fetch once, validate, persist atomically, and prepare the caller's report."""

import json
from datetime import datetime, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from .config import ENDPOINT, REPORT_TIMEZONE, SOURCE_URL, Config
from .freshness import assess_freshness
from .models import DataError, utc_iso
from .providers.cnn import fetch_payload
from .rules import EXTREMES
from .storage import Store
from .validation import parse_observation


def prepare_report(
    config: Config | None = None, *, now: datetime | None = None,
    fetcher: Callable[[Config], dict] | None = None,
) -> dict:
    """Return JSON-safe data. Source failures are reports; storage failures raise.

    ``now`` and ``fetcher`` support deterministic tests/offline replay. Keep replay
    databases separate from production. Network access occurs before the DB lock.
    """
    config = config or Config()
    if now is not None:
        utc_iso(now)  # Reject naive clocks before performing I/O.
    payload, candidate, issues = None, None, []
    fetch_status = "success"
    try:
        payload = (fetcher or fetch_payload)(config)
    except DataError as exc:
        fetch_status = "failure"
        issues.append(exc.issue())
    now = now or datetime.now(timezone.utc)
    generated_at = utc_iso(now)
    if fetch_status == "success":
        try:
            candidate = parse_observation(payload, now).to_dict()
        except DataError as exc:
            fetch_status = "failure"
            issues.append(exc.issue())

    with Store(config.database) as store, store.transaction():
        latest = store.latest()
        stored = json.loads(latest["observation"]) if latest else None
        is_cached, is_new = stored is not None, False
        if candidate and stored:
            if candidate["observed_at"] < stored["observed_at"]:
                issues.append({"code": "out_of_order", "message": "Ignored an observation older than the stored snapshot"})
                candidate = None
            elif candidate["observed_at"] == stored["observed_at"] and candidate != stored:
                issues.append({"code": "observation_revision", "message": "Retained the original same-timestamp observation; revision saved in provenance"})
                candidate = None
        if candidate:
            freshness, freshness_issues = assess_freshness(candidate, now)
            is_new = store.save_observation(candidate, generated_at, freshness == "current")
            observation, fetched_at, is_cached = candidate, generated_at, False
        else:
            observation = stored
            fetched_at = latest["fetched_at"] if latest else None
            freshness, freshness_issues = assess_freshness(observation, now)
        issues.extend(freshness_issues)
        previous = store.previous(observation["observed_at"]) if observation else None
        # Replays expose the persisted ID. A failed/stale run never creates an
        # event. Callers can also recover older events through read_events().
        event = store.event(observation["observed_at"]) if observation else None
        store.save_attempt(generated_at, fetch_status, payload, issues)

    return {
        "schema_version": "1",
        "report_date": now.astimezone(ZoneInfo(REPORT_TIMEZONE)).date().isoformat(),
        "generated_at": generated_at,
        "source": {"name": "CNN Fear & Greed Index", "url": SOURCE_URL, "data_url": ENDPOINT},
        "observation": observation,
        "fetched_at": fetched_at,
        "previous_observation": previous,
        "change_points": observation["score"] - previous["score"] if observation and previous else None,
        "classification_source": observation["classification_source"] if observation else None,
        "freshness": freshness,
        "fetch_status": fetch_status,
        "is_cached": is_cached,
        "is_new_observation": is_new,
        "extreme_status": observation["category"] if observation and observation["category"] in EXTREMES else None,
        "entry_event": event,
        "quality_issues": issues,
    }
