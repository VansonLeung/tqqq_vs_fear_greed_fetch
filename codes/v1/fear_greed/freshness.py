"""Conservative freshness based on NYSE session closes, not a CNN publication SLA."""

from datetime import datetime, timedelta

import pandas_market_calendars as mcal

from .models import parse_time


def assess_freshness(observation: dict | None, now: datetime) -> tuple[str, list[dict]]:
    if observation is None:
        return "unavailable", []
    try:
        calendar = mcal.get_calendar("NYSE")
        schedule = calendar.schedule(
            start_date=(now - timedelta(days=35)).date(), end_date=now.date()
        )
        completed = schedule[schedule["market_close"] <= now]
        if completed.empty:
            raise ValueError("No completed session in calendar window")
        expected_date = completed.index[-1].date().isoformat()
        expected_close = completed.iloc[-1]["market_close"].to_pydatetime()
    except Exception:
        return "unknown", [{"code": "calendar_unavailable", "message": "Cannot determine latest completed NYSE session"}]
    if observation["market_date"] < expected_date or parse_time(observation["observed_at"]) < expected_close:
        return "stale", [{
            "code": "stale_observation",
            "message": f"Expected an observation at or after the {expected_date} NYSE close",
        }]
    return "current", []
