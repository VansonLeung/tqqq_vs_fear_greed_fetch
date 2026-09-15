# TQQQ and CNN Fear & Greed charts

Status: implemented under `codes/v1/fear_greed/charts/` and `research/`.
See [CHARTS.md](../../codes/v1/CHARTS.md) for commands, source verification,
calculation definitions, and interpretation limits.

Extend the existing daily data preparation pipeline to generate images for the
user's Telegram integration. Show price direction, sentiment changes, and drawdown
together. Evaluate predictive usefulness separately through historical research.

## Daily image

Prepare a portrait PNG at the existing **08:00 Asia/Hong_Kong** run, showing the
last **six calendar months**. Use three vertically stacked panels sharing the same
date axis:

| Panel | Content |
|---|---|
| TQQQ | Split-adjusted daily close and 20-/50-session simple moving averages |
| CNN F&G | Raw daily score, five-session simple moving average, fixed 0–100 axis, sentiment bands |
| TQQQ drawdown | Percentage below the highest close reached so far within the displayed window |

Draw matching vertical markers across panels when sentiment enters or exits either
extreme category. A first observation in an extreme category is status, not a
proven entry. Use the verified raw-score classification from the existing pipeline.

Place a compact summary above the panels:

- TQQQ close and percentage change from the previous trading session.
- F&G score, category, and change over five trading-session intervals.
- TQQQ position relative to its 50- and 200-session moving averages.
- Latest observation/session date for each source and freshness status.

Use large labels, consistent colors, short legends, and enough space around the
title and source notes. Start with approximately 1200 × 1600 pixels and inspect
the rendered PNG at phone width. Do not use color as the only indicator of status.

A dual-axis overlay is an optional additional view after the aligned-panel version
works. It must label both units clearly and keep the F&G scale fixed at 0–100.

## Trend annotations

Use **20-session TQQQ return** and **20-session F&G point change**, evaluated at
the same comparison session:

| TQQQ return | F&G change | Annotation |
|---|---|---|
| Positive | Positive | Price and sentiment strengthening together |
| Negative | Negative | Price and sentiment weakening together |
| Positive | Negative | Price–sentiment divergence |
| Negative | Positive | Sentiment improving ahead of price confirmation |

Exactly zero produces an unchanged label for that series. Missing inputs produce
an unavailable annotation. An N-session change uses observations N session
intervals apart; it is different from an N-observation moving average.

These are reproducible descriptions of observed movements. Do not present them
as validated buy/sell signals or generate forecast probabilities from them.

## Weekly image

Generate a second PNG showing the latest **five years**, using aligned panels:

- TQQQ daily price on a logarithmic axis, with its 200-session moving average.
- F&G on a fixed 0–100 axis, highlighting extreme periods.
- TQQQ drawdown relative to the running peak within the displayed window.

Default preparation day: **Saturday at 08:00 Asia/Hong_Kong**, using the same daily
job. Allow an explicit request to regenerate either view. Show the actual covered
period if available history is shorter than five years; never imply full coverage.

## Data and calculation requirements

- Add a separate TQQQ provider. Verify the chosen source's price fields, split
  adjustments, history coverage, and timestamp semantics before adopting it.
- Retain provider timestamps, retrieval times, and source provenance for both series.
- Align by US market session using an explicit daily observation-selection policy.
  Verify CNN historical timestamp semantics rather than assuming they are identical
  to the live summary timestamp. Record the latest common comparison session.
- Preserve each series' latest timestamp in the header even if aligned chart data
  ends earlier. Flag differing dates and stale inputs visibly.
- Fetch pre-window history sufficient for all moving averages, including 200-session
  values at the start of the displayed window. Calculate TQQQ indicators on its
  own trading-session series before joining to CNN data.
- Keep gaps visible. Do not interpolate missing sentiment or forward-fill values
  into invented observations. Mark incomplete indicator windows unavailable.
- Use one consistent price adjustment basis throughout a chart. Detect corporate
  action revisions and refresh affected cached history when necessary.
- Label chart calculations as price returns. Any later total-return study must
  explicitly account for distributions and use a consistent adjustment basis.
- Define drawdown as close divided by the running maximum close minus one. Label
  its window; do not describe a window-relative value as an all-time drawdown.
- On days without new observations, reuse or regenerate correctly dated charts
  with a no-new-data label. Do not create new extreme events from repeated values.

## Historical outcomes study — subsequent phase

Start with a predefined question:

> After F&G exits Extreme Fear, how does TQQQ subsequently behave when price is
> above versus below its 200-session moving average?

For each condition, plot subsequent **5-, 20-, and 60-session** return distributions,
median returns, positive-outcome proportions, and the distribution of maximum
drawdown during those horizons. Show distinct event counts and the usable sample
count for each horizon. Exclude observations without a complete forward window.

Compare with unconditional TQQQ outcomes over the same eligible period. Count
distinct events rather than every consecutive extreme day, and account for
overlapping outcome windows when assessing uncertainty.

Develop rules using an earlier period and evaluate them on a later untouched
period. Prevent forward windows from crossing the training/evaluation boundary.
Fix rules and horizons before inspecting evaluation results; identify small or
insufficient samples explicitly.

Trading simulations must enter only after a signal was actually available, with
the required execution-price data and stated costs. Historical CNN values without
verified publication/availability timestamps support retrospective associations;
they must not be presented as a proven executable strategy. Retain live snapshots
going forward to support evaluation without later source revisions.

## Implementation and output

Extend the package with focused modules for TQQQ fetching, historical alignment,
indicators, and chart rendering. Use Matplotlib to render real data into PNGs.
Keep research calculations separate from daily report preparation.

Add an optional chart-generation mode and an additive `artifacts` list to the JSON
report. Each artifact should include kind, absolute path, MIME type, generation
time, displayed period, and per-source freshness. Use dated filenames and atomic
writes; include only successfully created files. Keep outputs outside the package.

If TQQQ fetching or rendering fails, preserve the usable CNN report and return an
explicit chart issue. Cached charts must retain their original data dates. The
existing Telegram integration remains responsible for sending images and avoiding
duplicate deliveries.

Implementation order:

1. Verify TQQQ history and adjustment semantics; add caching and session alignment.
2. Implement indicators and the daily six-month PNG with trend annotations.
3. Add the weekly five-year PNG and artifact metadata to the CLI/report.
4. Inspect real rendered images at phone width and verify numerical calculations.
5. Implement the historical outcomes study as a separate research command.

Acceptance checks cover split adjustments, session alignment, missing data,
moving-average warm-up, drawdown definitions, extreme transitions, five-/20-session
changes, stale-source labels, artifact failures, and correct daily/weekly selection.
Research checks must also verify event counts, incomplete horizons, execution
timing, and separation of training and evaluation periods.

## Implementation notes (2026-09-15)

- Added Nasdaq TQQQ fetching, full-history caching, date alignment, indicators,
  daily/weekly PNGs, source freshness metadata, and optional CLI integration.
- Added a separate research command producing return/drawdown distributions and
  JSON statistics. It implements retrospective close-to-close associations, not
  simulated executions; historical signal availability times are unverified.
- The historical dataset has already been inspected, so the chronological later
  partition is labeled retrospective evaluation, not unseen forward validation.
- Confirmed one missing historical CNN session (2026-03-12); gaps remain visible
  and affected indicator/outcome windows are excluded.
- The optional dual-axis overlay remains optional; the implemented views use
  aligned panels. Telegram delivery and scheduler installation remain with the caller.
