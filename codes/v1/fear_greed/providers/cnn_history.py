"""Keep CNN's UTC historical dates, excluding its appended live-summary point."""

import math

import pandas as pd

from ..config import ENDPOINT, SOURCE_URL
from ..models import DataError, parse_time
from ..rules import classify

EARLIEST = "2021-09-01"


def history_url(start) -> str:
    return ENDPOINT + "/" + max(str(start), EARLIEST)


def parse_history(payload: dict) -> pd.DataFrame:
    try:
        rows = payload["fear_and_greed_historical"]["data"]
        if not rows:
            raise ValueError("Empty CNN history")
        records = {}
        for position, row in enumerate(rows):
            score, timestamp = row["y"], row["x"]
            if (isinstance(score, bool) or not isinstance(score, (int, float))
                    or not 0 <= score <= 100 or not math.isfinite(score)):
                raise ValueError("Invalid score")
            if (isinstance(timestamp, bool) or not isinstance(timestamp, (int, float))
                    or not math.isfinite(timestamp)):
                raise ValueError("Invalid date label")
            date_label = pd.to_datetime(timestamp, unit="ms", utc=True)
            category = classify(score)
            rating = row.get("rating")
            if rating is not None and (not isinstance(rating, str)
                                      or "_".join(rating.lower().split()) != category):
                raise ValueError("Historical rating conflicts with raw score")
            if date_label != date_label.normalize():
                # CNN appends the current summary using its publication time.
                # It is not another historical session: do not round it into a
                # date or overwrite a dated score. align_sessions handles the
                # separately validated live observation's market date.
                summary = payload.get("fear_and_greed")
                if (position != len(rows) - 1 or not records
                        or not isinstance(summary, dict)
                        or isinstance(summary.get("score"), bool)
                        or summary.get("score") != score
                        or pd.Timestamp(parse_time(summary.get("timestamp"))) != date_label
                        or date_label.tz_localize(None) <= max(records)):
                    raise ValueError("Unexpected non-midnight CNN history point; expected a matching live-summary tail")
                continue
            session = date_label.tz_localize(None)
            record = {"fg": float(score), "category": category}
            if session in records and records[session] != record:
                raise ValueError("Conflicting duplicate historical date")
            records[session] = record  # Identical tail duplicates are common.
        return pd.DataFrame.from_dict(records, orient="index").sort_index()
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise DataError("cnn_history_schema", f"Invalid CNN history: {exc}") from exc
