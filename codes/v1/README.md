# Daily CNN Fear & Greed data preparation

Python function and one-shot CLI for the existing Telegram integration. It fetches
CNN's current summary, validates it, checks NYSE-session freshness, saves SQLite
history, and returns a JSON report with extreme status and persistent entry events.
It does not send messages or install a scheduler.

For TQQQ/CNN PNG images and the separate historical-outcomes command, see
[CHARTS.md](CHARTS.md). Enable chart generation with `--charts auto` or `--charts both`.

## Install and run

Requires Python **3.11 or newer**. The macOS system Python 3.9 is insufficient.
From the repository root:

```sh
python3.12 -m venv codes/v1/.venv
codes/v1/.venv/bin/python -m pip install -e 'codes/v1[test]'
codes/v1/.venv/bin/fear-greed --database .runtime/fear-greed.sqlite3
```

Omit `--database` to use `~/.local/share/fear-greed/state.sqlite3`. Use an absolute
database path and executable path in a scheduler. Configure the caller to run once
daily at **08:00 Asia/Hong_Kong**, including weekends. The CLI runs immediately when
invoked; it contains no timer or background process.

Optional plain text output:

```sh
codes/v1/.venv/bin/fear-greed --database .runtime/fear-greed.sqlite3 --format text
```

JSON goes to stdout; diagnostics go to stderr. Exit codes:

- `0`: a current report without quality issues, or successful event replay.
- `1`: a report with unavailable/stale/unknown data, a fetch failure, or another
  quality issue. **The JSON report is still present** and should be read by the caller.
- `2`: configuration/storage failure, with a JSON error object. Argument syntax
  errors use argparse's conventional usage/error output on stderr.

Requests have a 15-second socket timeout and at most three attempts by default.
Configure `--timeout` and `--attempts` if necessary. Transient network errors and
HTTP 408/429/500/502/503/504 receive bounded exponential backoff. Access rejections
such as HTTP 403/418 and malformed payloads are not retried.

## Use from another Python app

### Install from GitHub

In the consuming app's Python **3.11+** environment, with Git installed:

```sh
python -m pip install \
  "cnn-fear-greed-daily @ git+https://github.com/VansonLeung/tqqq_vs_fear_greed_fetch.git@main#subdirectory=codes/v1"
```

The distribution name is `cnn-fear-greed-daily`; the Python import is `fear_greed`.
The `subdirectory=codes/v1` suffix points pip to the package's `pyproject.toml`.
No editable checkout or PyPI publication is needed. See
[pip's Git installation documentation](https://pip.pypa.io/en/stable/topics/vcs-support/).

For repeatable deployments, replace `main` with a full commit hash or a release
tag that exists in the repository. Add the same dependency to the consuming app's
`requirements.txt`, without shell quotes:

```text
cnn-fear-greed-daily @ git+https://github.com/VansonLeung/tqqq_vs_fear_greed_fetch.git@FULL_COMMIT_HASH#subdirectory=codes/v1
```

Replace `FULL_COMMIT_HASH` before installing with `python -m pip install -r requirements.txt`.

### Fetch a report and generate PNGs

This example uses the current Python API:

```python
from pathlib import Path

from fear_greed import Config, prepare_report
from fear_greed.charts.service import attach_charts

state_dir = Path("./app-data/fear-greed").resolve()
state_dir.mkdir(parents=True, exist_ok=True)

config = Config(
    database=state_dir / "state.sqlite3",
    timeout_seconds=15,
    attempts=3,
)

report = prepare_report(config)

# Optional: omit this call if the app only needs the CNN report.
report = attach_charts(
    report,
    config,
    output_dir=state_dir / "charts",
    mode="both",
)

observation = report["observation"]
if observation is not None:
    print(observation["score"], observation["category"])
    print("Freshness:", report["freshness"])
    print("Cached:", report["is_cached"])

for artifact in report.get("artifacts", []):
    print("PNG:", artifact["path"])
    print("Return statistics:", artifact["forward_performance"])

print("Data issues:", report["quality_issues"])
print("Chart issues:", report.get("chart_issues", []))
```

`prepare_report()` fetches CNN data, updates persistent SQLite state, and returns
a JSON-safe dictionary. `attach_charts()` extends that dictionary with `artifacts`
and `chart_issues`, fetching historical CNN and TQQQ data as needed. PNGs are written
to disk; each artifact's `path` is an absolute local path, not a public URL.
The consuming app can serve those files or attach them to its own notifications.

Chart modes are `daily` (six-month overlay), `weekly` (five-year overlay), `both`,
and `auto` (daily, plus weekly on Saturdays in Asia/Hong_Kong). Each image includes
the subsequent 20-session return and win-rate comparison. Artifact
`forward_performance` contains its period, horizon, sample counts, mean returns,
and win rates; returns and win rates are fractions. See [CHARTS.md](CHARTS.md) for
the calculation rules and historical-data limitations.

### Application responsibilities

Recommended flow:

```text
App's scheduled background job
    → prepare_report()
    → attach_charts() when images are needed
    → save report JSON and PNGs
    → dashboard or notification system reads the saved results
```

| Responsibility | Guidance |
|---|---|
| Scheduling | Use the app's scheduler; the package runs immediately and installs no background job. |
| Persistence | Use a stable, writable database path. For deployment, configure an absolute directory on persistent storage. |
| Web and async apps | Fetching and rendering are blocking operations. Run them in a background worker and serve saved results. |
| Multiple workers | Use one chart-generation worker per output directory to avoid competing writes to dated images and manifests. |
| Source failures | Inspect `fetch_status`, `freshness`, `is_cached`, and `quality_issues`; a cached observation can still be returned. |
| Chart failures | Inspect `chart_issues` and iterate the actual `artifacts`; a chart issue can coexist with successfully generated PNGs. |
| Local failures | Handle configuration and SQLite/filesystem exceptions from report preparation in the consuming app. |
| Notifications | Deduplicate using `event_id`; persist a delivery cursor and use `read_events()` for recovery, as described below. |

When using the installed CLI instead of imports, call `fear-greed` from the app's
environment. Exit code **1** can still include usable JSON and generated PNGs
(for example, when CNN history has a gap); inspect the report before deciding
whether the job failed. Python callers receive the report directly, without a CLI
exit code.

## Current source verification

On 2026-09-15, initial probes of the data endpoint returned **HTTP 418**. The
installed CLI subsequently fetched and validated a live response successfully,
returning exit code 0 with current freshness and no quality issues. Another request
through the Python provider captured the real summary in `cnn_summary.live.json`.
These results establish that access works in this runtime, but access rejections
remain a handled failure mode. No alternative sentiment index is substituted.

The [CNN page](https://edition.cnn.com/markets/fear-and-greed) JavaScript confirms
the endpoint, timestamp interpretation, and classification predicates. Live API
ratings also verify the use of unrounded scores. Evidence metadata is saved in
`tests/fixtures/cnn_page_evidence.json`, with captured API boundary examples in
`cnn_historical_boundaries.live.json`. `cnn_summary.synthetic.json` is a separate,
explicitly synthetic fixture; its timestamp is not a CNN publication observation.

No CNN publication SLA was verified. Freshness therefore uses a conservative
operational rule: the observation timestamp must be at or after the latest
completed NYSE regular-session close, and its market date must be no earlier than
that session. `current` means it passes this rule, **not** that CNN guarantees a
final closing value. A pre-close observation remains stale after the close even
if its date matches. Reassess this conservative cutoff as publication behavior is
observed over subsequent runs.

NYSE holidays, early closes, and daylight-saving changes come from
[pandas_market_calendars](https://pandas-market-calendars.readthedocs.io/en/latest/usage.html).
No unverified publication-delay allowance is applied. Calendar lookup failures
produce `unknown` freshness and suppress new entry events.

## Classification

Use these non-overlapping intervals on the **raw score**, matching CNN API ratings:

| Category | Raw-score interval |
|---|---|
| Extreme Fear | `[0, 25]` |
| Fear | `(25, 45)` |
| Neutral | `[45, 55]` |
| Greed | `(55, 75)` |
| Extreme Greed | `[75, 100]` |

Supplied CNN categories are preferred and validated against these rules; missing
categories use `cnn_raw_score_fallback`. Unrecognized or conflicting ratings reject
the candidate, retain the last good snapshot, and expose a quality issue.

The CNN web gauge rounds to an integer before applying its predicates, which can
produce a different label near a boundary. Captured API observations label scores
25.2571 and 25.4286 as Fear, whereas the rounded gauge would show Extreme Fear.
Alerts follow the API/raw-score category, preserving the full numerical score.

The text formatter shows one decimal place with half-up rounding. Display rounding
is independent of classification: a raw 25.01 displays as 25.0 while remaining Fear.

## Python integration and event recovery

```python
from pathlib import Path
from fear_greed import Config, prepare_report, read_events

config = Config(database=Path("/absolute/path/fear-greed.sqlite3"))
report = prepare_report(config)
# Pass report to the existing message formatter/delivery integration.

events = read_events(config.database, after_sequence=0)
# The existing integration owns its cursor and advances it after delivery.
```

The function returns source failures as reports; configuration and local storage
errors raise exceptions. The JSON field contract is in `docs/v1/PLAN.md` relative
to the repository root. All machine timestamps are UTC; `report_date` is Hong Kong
time. `observation` is null when no usable data exists. `change_points` compares
against the previous accepted distinct observation, not the previous calendar day.

- First run: show current extreme status without inventing an entry event.
- Later fresh observations: create an event only on entry into either extreme
  category. Consecutive observations in the same category do not create events.
- Duplicate runs: retain the same event ID and return the same previous-observation
  comparison. A duplicate successful fetch updates its retrieval timestamp.
- Same-timestamp revisions and older observations: keep the stored snapshot, save
  the incoming payload in provenance, and flag the issue. Do not rewrite events.
- Stale or unknown observations: can be retained as snapshots but do not advance
  the accepted comparison state or create entry events.
- Fetch/validation failure: return a marked cached snapshot with original timestamps
  if possible. A successful HTTP response can still fail payload validation.

`is_cached` means the returned observation came from storage because this attempt
failed or its candidate was ignored. `is_new_observation` means a new observation
was accepted into the comparison state on this run. Neither is a delivery flag.

`entry_event` may replay an existing event even on a later failed or stale run;
it is never a newly generated alert in that case. The caller should use freshness
and its delivery cursor when deciding how to present a replay. An event includes
a stable `event_id` and increasing `sequence`. Data preparation never marks it sent.

Recover events even after newer observations arrive:

```sh
codes/v1/.venv/bin/fear-greed --database .runtime/fear-greed.sqlite3 --events-after 0
```

This performs no CNN fetch and returns all events after the supplied sequence.
The caller decides whether older recovered events need a historical label.

SQLite writes use a transaction and serialize simultaneous runs. Attempts retain
the decoded source payload and quality issues; accepted observations and their
events are committed together. Runtime data is excluded from version control.
There is no automatic retention deletion in v1.

## Verification

```sh
cd codes/v1
.venv/bin/python -m pytest -q
```

Tests cover category boundaries, rounding, first run, transitions, duplicate and
concurrent runs, restarts/event replay, revisions, stale data, holidays, early
closes, daylight-saving changes, malformed data, retries, and CLI JSON output.

For deterministic offline replay, the Python function accepts `now` (an aware
datetime) and `fetcher` (a callable receiving `Config` and returning a CNN-shaped
dictionary). Always use a separate temporary database for synthetic inputs.
