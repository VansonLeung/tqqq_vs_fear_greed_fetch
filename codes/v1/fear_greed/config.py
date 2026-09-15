"""Runtime configuration; no credentials or notification settings."""

from dataclasses import dataclass, field
from pathlib import Path

SOURCE_URL = "https://edition.cnn.com/markets/fear-and-greed"
ENDPOINT = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
REPORT_TIMEZONE = "Asia/Hong_Kong"
MARKET_TIMEZONE = "America/New_York"


@dataclass(frozen=True)
class Config:
    database: Path = field(default_factory=lambda: Path.home() / ".local/share/fear-greed/state.sqlite3")
    timeout_seconds: float = 15.0
    attempts: int = 3
    backoff_seconds: float = 1.0

    def __post_init__(self):
        if not 0 < self.timeout_seconds <= 120:
            raise ValueError("timeout_seconds must be between 0 (exclusive) and 120")
        if not 1 <= self.attempts <= 5:
            raise ValueError("attempts must be between 1 and 5")
        if not 0 <= self.backoff_seconds <= 10:
            raise ValueError("backoff_seconds must be between 0 and 10")
