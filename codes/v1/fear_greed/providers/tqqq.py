"""Nasdaq historical daily bars. Close is already split-adjusted; never adjust twice."""

import math
from datetime import datetime
from urllib.parse import urlencode

import pandas as pd

from ..models import DataError

SOURCE_URL = "https://www.nasdaq.com/market-activity/etf/tqqq/historical"


def history_url(start, end) -> str:
    query = urlencode({"assetclass": "etf", "fromdate": str(start), "todate": str(end), "limit": 5000})
    return "https://api.nasdaq.com/api/quote/TQQQ/historical?" + query


def parse_history(payload: dict) -> pd.DataFrame:
    try:
        data = payload["data"]
        if data["symbol"] != "TQQQ":
            raise ValueError("Wrong symbol")
        rows = data["tradesTable"]["rows"]
        if not rows or int(data["totalRecords"]) != len(rows):
            raise ValueError("Empty or truncated history")
        records = []
        for row in rows:
            session = datetime.strptime(row["date"], "%m/%d/%Y").date()
            close = float(str(row["close"]).replace("$", "").replace(",", ""))
            if not math.isfinite(close) or close <= 0:
                raise ValueError("Invalid close")
            records.append({"session": session, "close": close})
        frame = pd.DataFrame(records).set_index("session")
        frame.index = pd.DatetimeIndex(frame.index)
        if frame.index.has_duplicates:
            raise ValueError("Duplicate Nasdaq session")
        return frame.sort_index()
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise DataError("tqqq_schema", f"Invalid Nasdaq TQQQ history: {exc}") from exc
