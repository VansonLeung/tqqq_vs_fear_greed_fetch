"""Plain text output that needs no Telegram-specific escaping."""

from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from ..config import REPORT_TIMEZONE
from ..models import parse_time


def display_number(value: float, signed: bool = False) -> str:
    rounded = Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    if rounded == 0:
        rounded = abs(rounded)
    return format(rounded, "+.1f" if signed else ".1f")


def format_report(report: dict) -> str:
    lines = [f"CNN Fear & Greed — {report['report_date']} (Hong Kong)"]
    observation = report["observation"]
    if observation:
        label = observation["category"].replace("_", " ").title()
        lines.append(f"{display_number(observation['score'])}/100 — {label}")
        local = parse_time(observation["observed_at"]).astimezone(ZoneInfo(REPORT_TIMEZONE))
        lines.append(f"Observation: {local:%Y-%m-%d %H:%M:%S %Z}; market date: {observation['market_date']}")
        if report["change_points"] is not None:
            lines.append(f"Change since previous observation: {display_number(report['change_points'], True)} points")
        if report["extreme_status"]:
            lines.append(f"Warning: {label}")
        if report["entry_event"] and not report["is_cached"] and report["freshness"] == "current":
            lines.append(f"Entry recorded at {report['entry_event']['observed_at']}")
        if not report["is_new_observation"]:
            lines.append("No new accepted observation on this run.")
    else:
        lines.append("Index unavailable.")
    lines.append(f"Freshness: {report['freshness']}; fetch: {report['fetch_status']}")
    if report["is_cached"]:
        lines.append("Using stored data.")
    if report["fetched_at"]:
        lines.append(f"Last successful retrieval: {report['fetched_at']}")
    lines.extend(issue["message"] for issue in report["quality_issues"])
    lines.append(report["source"]["url"])
    lines.extend(f"Chart: {artifact['path']}" for artifact in report.get("artifacts", []))
    lines.extend(issue["message"] for issue in report.get("chart_issues", []))
    return "\n".join(lines)
