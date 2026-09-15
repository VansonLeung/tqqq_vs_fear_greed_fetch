import io
import json
from http.client import IncompleteRead
from urllib.error import HTTPError

import pytest

from fear_greed.cli import main
from fear_greed.models import DataError
from fear_greed.providers.cnn import fetch_payload
from conftest import instant


def test_transient_errors_retry_then_succeed(config, monkeypatch, cnn_fixture):
    calls = []
    def response(*args, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise TimeoutError()
        if len(calls) == 2:
            raise HTTPError("cnn", 503, "Unavailable", {}, None)
        return io.BytesIO(json.dumps(cnn_fixture).encode())
    monkeypatch.setattr("fear_greed.providers.cnn.urlopen", response)
    assert fetch_payload(config) == cnn_fixture
    assert len(calls) == 3
    assert calls[0]["timeout"] == config.timeout_seconds


def test_truncated_http_response_retries(config, monkeypatch, cnn_fixture):
    calls = []
    def response(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise IncompleteRead(b"partial")
        return io.BytesIO(json.dumps(cnn_fixture).encode())
    monkeypatch.setattr("fear_greed.providers.cnn.urlopen", response)
    assert fetch_payload(config) == cnn_fixture
    assert len(calls) == 2


@pytest.mark.parametrize("status,attempts", [(418, 1), (403, 1), (429, 3), (503, 3)])
def test_http_retry_policy(config, monkeypatch, status, attempts):
    calls = []
    def rejected(*args, **kwargs):
        calls.append(1)
        raise HTTPError("cnn", status, "Rejected", {}, None)
    monkeypatch.setattr("fear_greed.providers.cnn.urlopen", rejected)
    with pytest.raises(DataError, match=f"HTTP {status}"):
        fetch_payload(config)
    assert len(calls) == attempts


@pytest.mark.parametrize("body", [b"<html>blocked</html>", b"[]", b"null", b"\xff"])
def test_malformed_response_not_retried(config, monkeypatch, body):
    calls = []
    def response(*args, **kwargs):
        calls.append(1)
        return io.BytesIO(body)
    monkeypatch.setattr("fear_greed.providers.cnn.urlopen", response)
    with pytest.raises(DataError):
        fetch_payload(config)
    assert len(calls) == 1


def test_cli_stdout_is_json_on_live_failure(config, monkeypatch, capsys):
    def rejected(*args, **kwargs):
        raise HTTPError("cnn", 418, "Rejected", {}, None)
    monkeypatch.setattr("fear_greed.providers.cnn.urlopen", rejected)
    assert main(["--database", str(config.database)]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["fetch_status"] == "failure"
    assert report["observation"] is None


def test_cli_success_and_event_replay(config, monkeypatch, capsys, cnn_fixture):
    from fear_greed.service import prepare_report
    def prepare(settings):
        return prepare_report(settings, now=instant(), fetcher=lambda _: cnn_fixture)
    monkeypatch.setattr("fear_greed.cli.prepare_report", prepare)
    assert main(["--database", str(config.database)]) == 0
    assert json.loads(capsys.readouterr().out)["observation"]["score"] == 31.0571
    assert main(["--database", str(config.database), "--events-after", "0"]) == 0
    assert json.loads(capsys.readouterr().out)["events"] == []


def test_cli_invalid_configuration_is_structured(config, capsys):
    assert main(["--database", str(config.database), "--attempts", "0"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "preparation_failed"
