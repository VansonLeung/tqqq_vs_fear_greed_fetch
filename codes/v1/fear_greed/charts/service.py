"""Optional chart extension: source/rendering failures preserve the CNN report."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from ..config import REPORT_TIMEZONE
from ..models import DataError, utc_iso
from .artifacts import save_json
from .history import align_sessions, load_histories
from .indicators import add_indicators


def selected_kinds(mode, now):
    if mode == "auto":
        return ["daily", "weekly"] if now.astimezone(ZoneInfo(REPORT_TIMEZONE)).weekday() == 5 else ["daily"]
    if mode == "both":
        return ["daily", "weekly"]
    if mode not in ("daily", "weekly"):
        raise ValueError("Unknown chart mode")
    return [mode]


def attach_charts(report, config, output_dir, mode="auto", *, now=None, fetcher=None):
    now = now or datetime.now(timezone.utc)
    output_dir = Path(output_dir).expanduser().resolve()
    report["artifacts"], report["chart_issues"] = [], []
    try:
        frames, sources, issues = load_histories(config, now, fetcher)
        observation = report["observation"] if report["fetch_status"] == "success" and report["freshness"] == "current" else None
        data, sources, alignment_issues = align_sessions(frames, sources, now, observation)
        data = add_indicators(data)
        report["chart_issues"].extend(issues + alignment_issues)
        last_session = data.dropna(subset=["close", "fg"], how="all").index[-1]
        fingerprint_window = data.loc[last_session - pd.DateOffset(years=5):]
        identity = hashlib.sha256(fingerprint_window.to_csv().encode()).hexdigest()
        stamp = utc_iso(datetime.now(timezone.utc))
        from .render import render_chart
        for kind in selected_kinds(mode, now):
            manifest_path = output_dir / f"latest-{kind}.json"
            previous_identity = None
            if manifest_path.exists():
                try:
                    previous_identity = json.loads(manifest_path.read_text()).get("data_hash")
                except (ValueError, OSError):
                    pass
            try:
                filename = f"tqqq-fg-{kind}-{now.astimezone(ZoneInfo(REPORT_TIMEZONE)):%Y-%m-%d}.png"
                artifact = render_chart(data, sources, output_dir / filename, kind, stamp, previous_identity == identity)
                artifact.update(data_hash=identity, no_new_data=previous_identity == identity)
                save_json(artifact, manifest_path)
                report["artifacts"].append(artifact)
            except Exception as exc:
                report["chart_issues"].append({"code": "chart_render_failed", "kind": kind,
                                                "message": f"{type(exc).__name__}: {exc}"})
    except Exception as exc:
        report["chart_issues"].append({"code": exc.code if isinstance(exc, DataError) else "chart_preparation_failed",
                                      "message": str(exc)})
    return report
