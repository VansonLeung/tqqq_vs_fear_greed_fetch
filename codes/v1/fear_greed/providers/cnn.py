"""Small bounded HTTP client. No alternative provider or browser impersonation."""

import json
import logging
import time
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..config import ENDPOINT, SOURCE_URL, Config
from ..models import DataError

LOGGER = logging.getLogger(__name__)
MAX_RESPONSE_BYTES = 10 * 1024 * 1024
TRANSIENT_STATUS = {408, 429, 500, 502, 503, 504}


def fetch_payload(config: Config) -> dict:
    request = Request(ENDPOINT, headers={
        "User-Agent": "FearGreedDaily/0.1",
        "Accept": "application/json",
        "Referer": SOURCE_URL,
    })
    for attempt in range(config.attempts):
        retryable = False
        try:
            with urlopen(request, timeout=config.timeout_seconds) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise DataError("response_too_large", "CNN response exceeded 10 MiB")
            try:
                payload = json.loads(raw)
            except (ValueError, UnicodeError) as exc:
                raise DataError("invalid_json", "CNN returned malformed JSON") from exc
            if not isinstance(payload, dict):
                raise DataError("invalid_payload", "CNN response must be a JSON object")
            return payload
        except HTTPError as exc:
            error = DataError("http_error", f"CNN returned HTTP {exc.code}")
            retryable = exc.code in TRANSIENT_STATUS
            exc.close()
        except (URLError, TimeoutError, OSError, HTTPException) as exc:
            error = DataError("network_error", f"CNN request failed ({type(exc).__name__})")
            retryable = True
        if not retryable or attempt + 1 == config.attempts:
            raise error
        delay = config.backoff_seconds * (2 ** attempt)
        LOGGER.warning("CNN request failed; retrying in %.1f seconds", delay)
        time.sleep(delay)
    raise AssertionError("Unreachable with validated attempts")
