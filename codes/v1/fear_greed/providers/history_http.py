"""Bounded JSON transport shared by the historical source adapters."""

import json
import logging
import time
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..models import DataError
from .cnn import MAX_RESPONSE_BYTES, TRANSIENT_STATUS


def fetch_json(config, url: str, referer: str) -> dict:
    request = Request(url, headers={"User-Agent": "FearGreedDaily/0.1",
                                   "Accept": "application/json", "Referer": referer})
    for attempt in range(config.attempts):
        try:
            with urlopen(request, timeout=config.timeout_seconds) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise DataError("history_size", "Historical response exceeded 10 MiB")
            try:
                data = json.loads(raw)
            except (ValueError, UnicodeError) as exc:
                raise DataError("history_json", "Malformed historical JSON") from exc
            if not isinstance(data, dict):
                raise DataError("history_schema", "Historical response is not an object")
            return data
        except HTTPError as exc:
            retry = exc.code in TRANSIENT_STATUS
            error = DataError("history_http", f"Historical source returned HTTP {exc.code}")
            exc.close()
        except (URLError, OSError, HTTPException) as exc:
            retry = True
            error = DataError("history_network", f"Historical request failed ({type(exc).__name__})")
        if not retry or attempt + 1 == config.attempts:
            raise error
        delay = config.backoff_seconds * 2 ** attempt
        logging.getLogger(__name__).warning("History request failed; retrying in %.1fs", delay)
        time.sleep(delay)
    raise AssertionError("Invalid attempt configuration")
