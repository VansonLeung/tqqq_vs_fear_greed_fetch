import json
from pathlib import Path

import pytest

from fear_greed import Config
from fear_greed.models import parse_time
from fear_greed.rules import classify


@pytest.fixture
def config(tmp_path):
    return Config(database=tmp_path / "state.sqlite3", backoff_seconds=0)


@pytest.fixture
def cnn_fixture():
    return json.loads((Path(__file__).parent / "fixtures/cnn_summary.synthetic.json").read_text())


def payload(score=50, timestamp="2026-09-14T20:05:00Z", **extra):
    return {"fear_and_greed": {
        "score": score, "rating": classify(score).replace("_", " "),
        "timestamp": timestamp, **extra,
    }}


def instant(value="2026-09-15T00:00:00Z"):
    return parse_time(value)
