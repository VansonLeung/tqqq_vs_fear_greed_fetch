"""Load full source snapshots, cache validated responses, and align market sessions."""

from datetime import datetime, timezone

import pandas as pd
import pandas_market_calendars as mcal

from ..models import DataError, utc_iso
from ..providers import cnn_history, tqqq
from ..providers.history_http import fetch_json
from .cache import HistoryCache


def load_histories(config, now, fetcher=None):
    start = (pd.Timestamp(now).tz_localize(None) - pd.DateOffset(years=6)).date()
    end = now.date()
    frames, sources, issues = {}, {}, []
    adapters = {"tqqq": (tqqq, tqqq.history_url(start, end)),
                "cnn": (cnn_history, cnn_history.history_url(start))}
    with HistoryCache(config.database) as cache:
        for name, (adapter, url) in adapters.items():
            old = cache.get(name)
            cached, revised = False, 0
            try:
                payload = (fetcher or fetch_json)(config, url, adapter.SOURCE_URL)
                frame = adapter.parse_history(payload)
                if old:
                    prior = adapter.parse_history(old["payload"])
                    column = "close" if name == "tqqq" else "fg"
                    common = frame.index.intersection(prior.index)
                    revised = int((frame.loc[common, column] != prior.loc[common, column]).sum())
                fetched_at = utc_iso(datetime.now(timezone.utc))
                cache.save(name, fetched_at, url, payload)
            except DataError as exc:
                issues.append({"source": name, **exc.issue()})
                if not old:
                    continue
                frame = adapter.parse_history(old["payload"])
                fetched_at, url, cached = old["fetched_at"], old["url"], True
            frames[name] = frame
            sources[name] = {"name": "Nasdaq TQQQ" if name == "tqqq" else "CNN F&G",
                             "url": url, "fetched_at": fetched_at, "is_cached": cached,
                             "revised_rows": revised,
                             "timestamp_semantics": "US market session date" if name == "tqqq" else "UTC date label; publication time unknown"}
    if len(frames) != 2:
        raise DataError("history_unavailable", "; ".join(i["message"] for i in issues))
    return frames, sources, issues


def align_sessions(frames, sources, now, observation=None):
    """Exclude unfinished sessions; never move a UTC historical date back one day."""
    start = min(frame.index.min() for frame in frames.values())
    schedule = mcal.get_calendar("NYSE").schedule(start_date=start.date(), end_date=now.date())
    schedule = schedule[schedule["market_close"] <= now]
    if schedule.empty:
        raise DataError("no_sessions", "No completed market sessions in chart history")
    sessions = pd.DatetimeIndex(schedule.index).tz_localize(None)
    result = pd.DataFrame(index=sessions)
    issues = []
    for name, frame in frames.items():
        column = "close" if name == "tqqq" else "fg"
        frame = frame.loc[frame.index <= sessions[-1]]
        valid = frame.index.intersection(sessions)
        if valid.empty:
            raise DataError("empty_history", f"No completed sessions for {name}")
        result[column] = frame[column].reindex(sessions)
        last = valid[-1]
        sources[name].update(latest_session=str(last.date()),
                             source_timestamp=str(last.date()),
                             freshness="current" if last == sessions[-1] else "stale")
        missing = int(result.loc[valid[0]:last, column].isna().sum())
        if missing:
            issues.append({"code": "history_gaps", "source": name, "message": f"{name}: {missing} missing interior market sessions"})
        if sources[name]["freshness"] == "stale":
            issues.append({"code": "stale_history", "source": name, "message": f"{name} ends {last.date()}; expected {sessions[-1].date()}"})
    if observation:
        session = pd.Timestamp(observation["market_date"])
        if session in result.index:
            result.loc[session, "fg"] = observation["score"]
            # Only replace the latest historical point's timestamp metadata when
            # this live observation is at least as recent as the chart tail.
            if session >= pd.Timestamp(sources["cnn"]["latest_session"]):
                sources["cnn"].update(latest_session=str(session.date()),
                                      source_timestamp=observation["observed_at"],
                                      freshness="current" if session == sessions[-1] else "stale")
    result.index.name = "session"
    return result, sources, issues
