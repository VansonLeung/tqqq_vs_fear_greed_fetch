# Daily charts and retrospective research

Install the updated package from the repository root:

```sh
codes/v1/.venv/bin/python -m pip install -e 'codes/v1[test]'
```

Matplotlib uses its noninteractive Agg backend; no browser or display is required.

## Generate Telegram images

```sh
codes/v1/.venv/bin/fear-greed \
  --database .runtime/daily.sqlite3 \
  --charts both \
  --output-dir .runtime/charts
```

The existing JSON report gains `artifacts` and `chart_issues`. Each artifact contains
an absolute PNG path, MIME type, generation time, actual displayed period, latest
common comparison session, source timestamps/freshness, and a deterministic data
hash. The caller reads the PNG files and sends them through its existing Telegram
integration. `--format text` also prints the generated file paths.

Chart modes:

| Mode | Output |
|---|---|
| `daily` | Six-month price/sentiment overlay |
| `weekly` | Five-year context with logarithmic price axis |
| `both` | Both PNGs immediately |
| `auto` | Daily PNG, plus weekly PNG on Saturday in Asia/Hong_Kong |

Use `--charts auto` in the existing **08:00 Asia/Hong_Kong** scheduler. The command
does not install a scheduler, delay execution until 08:00, or send messages.
Calling it without `--charts` preserves the original CNN-only behavior.

Images are 1800 × 1200 pixels, using the layout of the reference
`docs/v1/tqqq_vs_fear_greed.png`:

- The upper panel overlays the TQQQ close on CNN's Fear & Greed line and filled
  area, with colored horizontal sentiment bands. The left axis is split-adjusted
  USD; the right axis is F&G from 0 to 100. Daily charts include SMA50 and weekly
  charts include SMA200 with logarithmic prices. Date ticks use `YYYY-MM`.
- The lower panel shows mean subsequent **20-session** TQQQ returns by starting
  sentiment category, annotated with win rate and eligible sample count (`n`).
  Both modes use up to five years of history for this comparison, with its period
  explicitly labeled, even when the upper panel shows only six months.
- Headers include TQQQ daily change, five-session sentiment change, and a trend
  description based on the 20-session price/sentiment comparison.

The return comparison uses every eligible starting session, including overlapping
holding windows. A win is a strictly positive close-to-close return. Unfinished
outcomes, missing starting sentiment, and windows with any missing price are
excluded from both the average and the win-rate denominator. Categories without
eligible outcomes show “No completed outcomes.” Exact category boundaries follow
the existing CNN classification rules. These are retrospective associations, not
an execution simulation or validated predictive probabilities. The artifact JSON
includes the period, horizon, counts, mean returns, and win rates in
`forward_performance` (returns and win rates are fractions).

Output names are dated, for example `tqqq-fg-daily-2026-09-15.png`. Files are written
atomically. `latest-daily.json` and `latest-weekly.json` describe the latest successful
artifacts. A rerun replaces that day's image. `data_hash` covers the displayed
five-year data and calculated indicators, so an unchanged chart can be identified
without treating a new retrieval timestamp as new market data. `no_new_data` means
this chart-data fingerprint matches the preceding chart of that kind. Sending and
delivery deduplication remain caller responsibilities.

If one source fails, its last validated full-history response is used when available
and marked cached. If a required history is unavailable or rendering fails, the
CNN report remains usable and the failed artifact is omitted. `chart_issues` names
the problem. The CLI returns exit code 1 when any chart issue exists, even when PNGs
were produced; always inspect the JSON. For example, the verified live CNN history
has a missing session on **2026-03-12**, which is explicitly reported.

Python callers can extend an existing report:

```python
from pathlib import Path
from fear_greed import Config, prepare_report
from fear_greed.charts.service import attach_charts

config = Config(database=Path("/absolute/path/daily.sqlite3"))
report = prepare_report(config)
report = attach_charts(report, config, Path("/absolute/path/charts"), mode="auto")
```

## Sources, alignment, and calculations

Nasdaq's TQQQ historical API supplies the daily closes. On 2026-09-15 all **1,262**
overlapping closes matched the existing split-adjusted CSV. The pre-split
2025-11-19 close was already $50.025; do not apply the subsequent 2:1 split again.
The split is documented by
[ProShares](https://www.proshares.com/press-releases/proshares-announces-etf-share-splits5).
These are split-adjusted price returns, not returns including distributions.

Both sources are refreshed as full snapshots; Nasdaq requests six years for
five-year chart coverage plus moving-average warm-up. Pagination/truncation is
checked using Nasdaq's record count. Validated payloads and retrieval times are
retained in SQLite. Changes to overlapping values are counted as `revised_rows`,
and the entire cached snapshot is replaced, so historical split adjustments are
not mixed with an older price basis. This records provider revisions without
assuming every revision is a corporate action.

CNN dated historical `x` fields are midnight-UTC date labels in milliseconds. Keep
their UTC calendar date; converting them to New York time would shift them back one
day. CNN can append a non-midnight point matching the live summary's timestamp and
score. That verified final point is excluded from the historical series, rather
than rounded into a date or allowed to overwrite a dated score. The live summary's
ISO observation timestamp has different semantics. Current,
validated live summary data may update its corresponding market-date chart point.
Historical labels do not establish when that score became available to investors.
Identical duplicated historical tail rows are deduplicated; conflicting duplicates
or unrecognized non-midnight points reject that payload.

An older parser rejected the appended live point with `Historical timestamps no
longer represent midnight UTC dates`, leaving `artifacts: []` when no valid cached
CNN history was available. The parser now accepts this verified tail. Generated
images default to `.runtime/charts` relative to the working directory; on a Tuesday,
`--charts auto` creates only the daily PNG. Use `--charts both` for both images.

Only completed NYSE calendar sessions enter the combined frame. Future/current
unfinished sessions are excluded. Each source keeps its own latest session and
timestamp metadata; a stale series is never labeled as current merely because the
other one updated. Here, historical freshness means coverage through the latest
completed session, not a guarantee of CNN publication finality.

The full session index preserves missing observations as gaps. Moving averages
require complete windows; an N-session change requires N+1 observations with no
missing intervening sessions. Missing sentiment breaks extreme-transition inference.
TQQQ averages are calculated before selecting the visible window or requiring CNN
coverage. No sentiment interpolation or forward filling is performed.

Actual response excerpts and source-check metadata are in `tests/fixtures/`:
`nasdaq_history.excerpt.json`, `cnn_history.excerpt.json`, and
`chart_sources_evidence.json`. Source access and schemas are not guaranteed APIs.

## Historical outcomes command

```sh
codes/v1/.venv/bin/fear-greed-research \
  --database .runtime/daily.sqlite3 \
  --output-dir .runtime/research \
  --split-date 2025-01-01
```

This command generates separate return-distribution and drawdown-distribution PNGs
plus a JSON study containing every included observation and summary statistic.
It does not affect live alert comparison state or generate notification events.

The fixed research question is: after F&G exits Extreme Fear, how do TQQQ outcomes
compare above versus below its 200-session simple moving average? Exactly at the
average is excluded from those two conditional groups.

- Horizons are 5, 20, and 60 trading sessions.
- Earlier observations are development data; later observations are retrospective
  evaluation data. Development outcome windows crossing the split are purged.
- Only complete close-to-close price paths are used. The starting close is included
  when computing the holding window's maximum drawdown.
- Consecutive extreme days are not independent events. Distinct exits are selected,
  then overlapping outcome windows are removed in chronological order jointly
  across both trend groups, separately for each horizon and period.
- Baseline windows are unconditioned on sentiment and use deterministic,
  non-overlapping TQQQ paths over the eligible period. Their starting-date choice
  affects the baseline; it is documented rather than optimized.
- JSON records candidate and retained sample counts, median return, positive-outcome
  fraction, median/worst drawdown, and individual outcome paths' start/end sessions.
  Groups with fewer than 10 retained samples are marked small.

There is no execution-price simulation or assumption that the historical score was
tradable at its labeled close. Distributions and trading costs are excluded.
The existing five-year dataset has already been inspected, so the later partition
is not claimed to be an untouched validation set. Non-overlapping samples can still
share market regimes; no statistical-significance or predictive-probability claim
is made. A genuine forward evaluation requires future observations and verified
signal availability times, which the daily snapshot pipeline retains going forward.

Tests: `cd codes/v1 && .venv/bin/python -m pytest -q`.
