import json
from pathlib import Path

from PIL import Image
import pandas as pd
import pytest

from fear_greed.charts.service import attach_charts, selected_kinds
from fear_greed.charts.indicators import add_indicators
from fear_greed.charts.render import render_chart
from fear_greed.models import DataError
from conftest import instant
from test_chart_indicators import frame


def test_weekly_selection_uses_hong_kong_day():
    assert selected_kinds("auto", instant("2026-09-18T23:59:00Z")) == ["daily", "weekly"]
    assert selected_kinds("auto", instant("2026-09-19T17:00:00Z")) == ["daily"]
    assert selected_kinds("both", instant()) == ["daily", "weekly"]


def sources():
    return {name: {"latest_session": "2025-12-30", "freshness": "current", "is_cached": False,
                   "source_timestamp": "2025-12-30"} for name in ("tqqq", "cnn")}


@pytest.mark.parametrize("kind", ["daily", "weekly"])
def test_png_output_is_atomic_and_readable(tmp_path, kind):
    data = add_indicators(frame())
    destination = tmp_path / "chart.png"
    artifact = render_chart(data, sources(), destination, kind, "2026-01-01T00:00:00Z")
    assert artifact["path"] == str(destination.resolve())
    with Image.open(destination) as image:
        assert image.size == (1800, 1200)
        assert image.format == "PNG"
    assert not list(tmp_path.glob(".chart-*"))
    summary = artifact["forward_performance"]
    assert summary["horizon_sessions"] == 20
    assert sum(row["sample_count"] for row in summary["results"]) == len(data) - 20


def test_chart_failure_preserves_base_report(config, tmp_path):
    report = {"observation": None, "fetch_status": "failure", "freshness": "unavailable", "quality_issues": []}
    original = dict(report)
    def fail(*args):
        raise DataError("no_source", "source unavailable")
    result = attach_charts(report, config, tmp_path, fetcher=fail, now=instant())
    assert all(result[key] == value for key, value in original.items())
    assert result["artifacts"] == []
    assert result["chart_issues"]


def test_rerun_reuses_data_identity_and_render_failure_omits_artifact(config, tmp_path, monkeypatch):
    raw = frame()
    frames = {"tqqq": raw[["close"]], "cnn": raw[["fg"]]}
    metadata = sources()
    monkeypatch.setattr("fear_greed.charts.service.load_histories", lambda *args: (frames, metadata, []))
    monkeypatch.setattr("fear_greed.charts.service.align_sessions", lambda *args: (raw, metadata, []))
    report = {"observation": None, "fetch_status": "failure", "freshness": "unavailable"}
    first = attach_charts(dict(report), config, tmp_path, "daily", now=instant())
    second = attach_charts(dict(report), config, tmp_path, "daily", now=instant())
    assert first["artifacts"][0]["data_hash"] == second["artifacts"][0]["data_hash"]
    assert second["artifacts"][0]["no_new_data"]
    def broken(*args):
        raise OSError("disk full")
    monkeypatch.setattr("fear_greed.charts.render.render_chart", broken)
    failed = attach_charts(dict(report), config, tmp_path, "both", now=instant())
    assert not failed["artifacts"]
    assert len(failed["chart_issues"]) == 2
