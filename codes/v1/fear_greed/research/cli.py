"""Generate a reproducible retrospective study, separate from the daily report."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from ..charts.artifacts import save_json
from ..charts.history import align_sessions, load_histories
from ..charts.indicators import add_indicators
from ..config import Config
from ..models import utc_iso
from .outcomes import study_outcomes


def run_study(config, output_dir, split_date="2025-01-01", *, now=None, fetcher=None):
    now = now or datetime.now(timezone.utc)
    frames, sources, issues = load_histories(config, now, fetcher)
    data, sources, alignment_issues = align_sessions(frames, sources, now)
    study = study_outcomes(add_indicators(data), split_date)
    study.update(sources=sources, quality_issues=issues + alignment_issues, generated_at=utc_iso(now))
    from .render import render_study
    output_dir = Path(output_dir).expanduser().resolve()
    stem = f"extreme-fear-exits-{now:%Y-%m-%d}"
    artifacts = []
    for metric in ("price_return", "max_drawdown"):
        path = render_study(study, output_dir / f"{stem}-{metric}.png", metric)
        artifacts.append({"kind": metric, "path": path, "mime_type": "image/png",
                          "generated_at": study["generated_at"], "displayed_period": study["period"], "sources": sources})
    study["artifacts"] = artifacts
    json_path = save_json(study, output_dir / f"{stem}.json")
    return {"study_path": json_path, "artifacts": artifacts, "quality_issues": study["quality_issues"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Config().database)
    parser.add_argument("--output-dir", type=Path, default=Path(".runtime/research"))
    parser.add_argument("--split-date", default="2025-01-01")
    args = parser.parse_args(argv)
    try:
        result = run_study(Config(database=args.database), args.output_dir, args.split_date)
        print(json.dumps(result, allow_nan=False))
        return 1 if result["quality_issues"] else 0
    except Exception as exc:
        print(json.dumps({"error": {"code": "research_failed", "message": str(exc)}}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
