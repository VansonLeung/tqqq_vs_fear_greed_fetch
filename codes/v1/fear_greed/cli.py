"""One-shot command for an external scheduler or existing Telegram process."""

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

from .config import Config
from .formatters.text import format_report
from .service import prepare_report
from .storage import read_events


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Config().database)
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--events-after", type=int, help="Replay persisted events after this sequence, without fetching")
    parser.add_argument("--charts", choices=("auto", "daily", "weekly", "both"), help="Generate PNG charts; auto adds weekly on Saturday Hong Kong time")
    parser.add_argument("--output-dir", type=Path, default=Path(".runtime/charts"))
    args = parser.parse_args(argv)
    if args.events_after is not None and args.charts:
        parser.error("--events-after cannot be combined with --charts")
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    try:
        config = Config(database=args.database, timeout_seconds=args.timeout, attempts=args.attempts)
        if args.events_after is not None:
            print(json.dumps({"schema_version": "1", "events": read_events(config.database, args.events_after)}))
            return 0
        report = prepare_report(config)
        if args.charts:
            from .charts.service import attach_charts
            report = attach_charts(report, config, args.output_dir, args.charts)
        print(format_report(report) if args.format == "text" else json.dumps(report, allow_nan=False))
        return 0 if not report["quality_issues"] and not report.get("chart_issues") and report["freshness"] == "current" else 1
    except (OSError, sqlite3.Error, ValueError) as exc:
        print(json.dumps({"schema_version": "1", "error": {"code": "preparation_failed", "message": str(exc)}}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
