"""Small serializable domain types."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone


def utc_iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("A timezone-aware datetime is required")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    if not isinstance(value, str) or "T" not in value:
        raise ValueError("Expected an ISO 8601 timestamp with timezone")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamp has no timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class Observation:
    score: float
    category: str
    original_category: str | None
    observed_at: str
    market_date: str
    market_date_source: str
    classification_source: str

    def to_dict(self) -> dict:
        return asdict(self)


class DataError(Exception):
    """An expected source or validation problem, safe to expose in a report."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code

    def issue(self) -> dict:
        return {"code": self.code, "message": str(self)}
