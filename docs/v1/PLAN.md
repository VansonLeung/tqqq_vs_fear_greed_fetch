# Daily CNN Fear & Greed data preparation

## Objective and scope

Prepare daily CNN Fear & Greed Index data for the existing Telegram integration,
including warnings for Extreme Fear and Extreme Greed.

Source: https://edition.cnn.com/markets/fear-and-greed

Use Python with separation of concerns, subfolders, and small, focused modules.
The implementation covers the CNN index, TQQQ data, combined daily/weekly PNG
charts, and a separate retrospective historical-outcomes study. See
[CHART_PLAN.md](CHART_PLAN.md) for the chart specification and implementation notes.
Existing historical artifacts remain reference material.
Telegram API calls and delivery tracking belong to the existing integration.

## Agreed defaults

- Prepare one report every calendar day at **08:00 Asia/Hong_Kong**.
- Use the latest valid CNN observation available at preparation time. Do not label
  it a final closing value unless the source establishes that.
- Include score, category, change in index points since the previous distinct
  observation, source observation timestamp, fetch timestamp, and extreme status.
- On weekends and US market holidays, retain the actual observation date and
  identify when no new observation is available. Do not manufacture daily values.
- This is daily sampling; it does not detect every intraday threshold crossing.
- Display extreme status every day where applicable. Separately flag entry into
  an extreme category relative to the previous accepted observation.
- On the first run, show current status without claiming an entry event. Change
  since the previous observation is null when no previous observation is stored.
- Expose a reusable Python function and a thin CLI producing versioned JSON.
- Keep message language and formatting in a separate optional formatter.

Provide a one-shot command for an external scheduler. Installing the scheduler is
separate from implementing data preparation.

## Classification and alert rules

- Preserve CNN's original score and category. Normalize recognized categories to
  `extreme_fear`, `fear`, `neutral`, `greed`, and `extreme_greed`.
- Prefer CNN's supplied category. Before implementing numeric fallback rules,
  verify CNN's current boundaries and rounding behavior using an actual response
  or authoritative source. Document exact, non-overlapping intervals and test them.
  The overlapping historical chart ranges are insufficient specifications.
- Use fallback classification for a missing category only after verifying its
  rules. Record whether the category came from CNN or the fallback.
- Validate category/score agreement against verified rules. Expose conflicts as
  quality issues and suppress new entry alerts until they are resolved.
- Preserve source precision for classification and calculations. Live API ratings
  match unrounded boundaries: Extreme Fear `[0,25]`, Fear `(25,45)`, Neutral `[45,55]`,
  Greed `(55,75)`, Extreme Greed `[75,100]`. CNN's web gauge rounds first and can
  differ near boundaries; alerts follow the API. Round only for display, using
  one decimal place for scores and point changes.
- A fresh, valid, newer observation entering either extreme category from a
  different accepted category creates an entry event. Remaining in the same
  extreme category does not. Leaving and later re-entering can create another.
- An entry event describes an observed transition, not its exact intraday time.
- Failed fetches, stale data, duplicates, and revisions to the same observation
  do not create new entry events.

## Source reliability and freshness

Candidate endpoint:
`https://production.dataviz.cnn.io/index/fearandgreed/graphdata`

Initial review requests returned HTTP 418; the installed implementation subsequently
fetched and validated live data successfully. Keep access and response shape under
validation rather than treating the endpoint as a guaranteed public API contract.
Report access failure clearly; do not silently substitute another sentiment index.

- Use timeouts and bounded retries with backoff for transient failures. Avoid
  repeatedly retrying persistent access rejection or malformed responses.
- Validate required fields, finite numeric scores in `[0, 100]`, timestamps, and
  categories before updating the last good observation.
- Store source observation time and successful fetch time separately in UTC.
  Display report times in Asia/Hong_Kong. Preserve the source market date when
  provided; do not blindly truncate UTC timestamps to obtain a trading date.
- Assess freshness against the expected completed US market session, accounting
  for holidays and daylight-saving changes. Verify CNN publication timing before
  fixing the freshness cutoff.
- Keep freshness, fetch outcome, and whether an observation changed as separate
  facts. An unchanged weekend observation can still be current; a successful
  request can return stale data.
- On failure, return the last good observation when available, marked as cached
  with its original timestamps and the fetch issue. Otherwise return unavailable
  status with null score and category.
- Never overwrite the last good snapshot with invalid data or advance alert
  comparison state with stale, invalid, or out-of-order observations.

## Integration contract

The function returns a structured report; the CLI emits equivalent JSON to stdout
and sends diagnostic logs to stderr.

| Field | Meaning |
|---|---|
| `schema_version` | Output contract version |
| `report_date` | Daily report date in Asia/Hong_Kong |
| `generated_at` | UTC preparation time |
| `source` | Provider and source URL |
| `observation` | Score, normalized/original category, source timestamp, market date when available |
| `fetched_at` | Last successful retrieval time for the returned observation |
| `previous_observation` | Previous accepted distinct observation, or null |
| `change_points` | Difference from that observation, or null |
| `classification_source` | CNN, verified fallback, or null |
| `freshness` | Current, stale, unknown, or unavailable |
| `fetch_status` | Success or failure for this attempt |
| `is_cached` | Whether this attempt uses stored data after failure or an ignored candidate |
| `is_new_observation` | Whether a newer distinct source observation was accepted |
| `extreme_status` | Extreme fear, extreme greed, or null |
| `entry_event` | Stable event ID, destination category, observation time, or null |
| `quality_issues` | Structured fetch, freshness, or validation issues |

Persist generated events. Rerunning preparation for the same observation must
return the same event ID, rather than create a duplicate or lose an event before
Telegram receives it. The existing integration owns delivery and deduplication of
sent messages; data preparation must not mark events as sent.

## Suggested structure and storage

```text
codes/v1/
  fear_greed/
    __init__.py
    config.py
    models.py
    providers/
      __init__.py
      cnn.py
    validation.py
    rules.py
    storage.py
    service.py
    formatters/
      __init__.py
      text.py
    cli.py
  tests/
    fixtures/
  pyproject.toml
  README.md
```

Use a configurable local SQLite database for observation history, the last good
snapshot, and generated events. Commit observation and event updates together.
Retain successful raw payloads or equivalent provenance for diagnosing source
changes. Keep runtime state outside the package and exclude it from version control.

## Implementation order

1. Verify source access, timestamp semantics, category boundaries, and publication
   timing. Save a representative response as a test fixture.
2. Implement fetching, validation, and freshness evaluation.
3. Implement storage, classification, transition rules, and stable event IDs.
4. Add the Python function, JSON CLI, and optional formatter. Document caller
   behavior and scheduler invocation.
5. Verify the preparation flow with fixtures and a live fetch when available.

## Acceptance checks

- Exact category boundaries, nearby decimal values, and display rounding.
- First run, repeated extremes, exit/re-entry, and direct transitions between the
  two extreme categories.
- Duplicate runs, same-timestamp revisions, out-of-order records, and restarts:
  no new duplicate events or lost persisted events.
- Weekends, holidays, daylight-saving changes, delayed updates, and stale data
  returned by successful requests.
- Timeout, access rejection, malformed payload, invalid score/category, and failure
  both with and without a stored snapshot.
- Machine-readable JSON without log text and correct nullable fields on failure.

## Reference artifact cleanup backlog

- `analysis_report.md` lists absent `stats.json` and `build_chart.py`. Restore them
  if available or correct the inventory.
- Fix the nonexistent `tqqq-fear-greed/` prefix in `SAMPLE_RESULT.md` links.
- Replace the sample's unsupported excess-return claim with an observed historical
  association consistent with the report's limitations.
- Fix the HTML `2025–2026` selector, which currently selects only 2025.
- Fix the PNG title overlapping its source annotation.
- Treat the existing CSV as historical reference: it lacks source timestamps and
  categories required for live freshness and alert validation.

## Implementation notes (2026-09-15)

- Implemented the Python package, SQLite persistence, JSON/text CLI, event replay,
  and tests under `codes/v1`; see its README for installation and integration.
- Verified category predicates from CNN's page JavaScript and unrounded API ratings
  from live historical observations. The web gauge's additional integer rounding
  can produce a different label near boundaries; the implementation follows the API.
- Initial requests returned HTTP 418, but the installed CLI and Python provider
  subsequently fetched live data successfully. Captured live summary and boundary
  fixtures, source evidence, and a separately labeled synthetic fixture are retained.
- No publication SLA was found. Freshness conservatively requires an observation
  at or after the latest completed NYSE close; it does not claim finality or apply
  an invented publication-delay allowance.
- Scheduler installation, Telegram calls, and reference artifact cleanup remain
  separate from the data preparation implementation.
- Implemented the chart extension and research command; live Nasdaq/CNN fetching
  generated both daily and weekly PNGs. All 104 tests passed. The missing CNN
  history session on 2026-03-12 is retained as a gap and exposed as a chart issue.
