"""Predefined Extreme Fear exit study with chronological splits and purged windows."""

import numpy as np
import pandas as pd


def _summary(samples, candidate_count, minimum):
    returns = [sample["price_return"] for sample in samples]
    drawdowns = [sample["max_drawdown"] for sample in samples]
    return {"candidate_count": candidate_count, "sample_count": len(samples),
            "small_sample": len(samples) < minimum,
            "median_price_return": float(np.median(returns)) if returns else None,
            "positive_fraction": float(np.mean(np.array(returns) > 0)) if returns else None,
            "median_max_drawdown": float(np.median(drawdowns)) if drawdowns else None,
            "worst_max_drawdown": float(min(drawdowns)) if drawdowns else None,
            "samples": samples}


def _nonoverlapping(candidates):
    selected, last_end = [], -1
    for sample in candidates:
        if sample["start_position"] > last_end:
            selected.append(sample)
            last_end = sample["end_position"]
    return selected


def study_outcomes(data, split_date="2025-01-01", horizons=(5, 20, 60), minimum=10):
    split = pd.Timestamp(split_date)
    if minimum < 1 or any(not isinstance(h, int) or h < 1 for h in horizons):
        raise ValueError("Positive horizons and minimum sample count are required")
    usable = data.dropna(subset=["close", "fg", "sma200"])
    if usable.empty or not usable.index[0] < split <= usable.index[-1]:
        raise ValueError("Split date must separate usable earlier and later observations")
    data = data.loc[usable.index[0]:].copy()
    exits = (data.category.shift(1) == "extreme_fear") & data.category.notna() & (data.category != "extreme_fear")
    groups = {}
    for period in ("development", "evaluation"):
        period_results = {}
        for horizon in horizons:
            baseline, events = [], []
            for i in range(len(data) - horizon):
                start, end = data.index[i], data.index[i + horizon]
                if period == "development" and not (start < split and end < split):
                    continue  # Purge forward windows crossing the split.
                if period == "evaluation" and start < split:
                    continue
                row = data.iloc[i]
                path = data.close.iloc[i:i + horizon + 1]
                if pd.isna(row.sma200) or path.isna().any():
                    continue
                regime = "above" if row.close > row.sma200 else "below" if row.close < row.sma200 else "at"
                sample = {"session": str(start.date()), "end_session": str(end.date()),
                          "start_position": i, "end_position": i + horizon,
                          "regime": regime, "price_return": float(path.iloc[-1] / path.iloc[0] - 1),
                          "max_drawdown": float((path / path.cummax() - 1).min())}
                baseline.append(sample)
                if exits.iloc[i] and regime != "at":
                    events.append(sample)
            # Thin events jointly before dividing by regime: above/below groups
            # cannot contain overlapping holding windows with each other.
            selected_events = _nonoverlapping(events)
            result = {"baseline": _summary(_nonoverlapping(baseline), len(baseline), minimum)}
            for regime in ("above", "below"):
                result[regime] = _summary([s for s in selected_events if s["regime"] == regime],
                                         sum(s["regime"] == regime for s in events), minimum)
            period_results[str(horizon)] = result
        groups[period] = period_results
    return {
        "schema_version": "1", "study": "Exit Extreme Fear by TQQQ vs SMA200",
        "split_date": str(split.date()), "horizons": list(horizons), "minimum_samples": minimum,
        "period": {"start": str(data.index[0].date()), "end": str(data.index[-1].date())},
        "method": "Fixed chronological split; earliest non-overlapping windows within each period/horizon",
        "execution": "Retrospective close-to-close associations; no executable strategy or assumed signal publication time",
        "evaluation_status": "Retrospective evaluation of previously available data, not a claim of unseen forward validation",
        "limitations": ["Price returns exclude distributions and trading costs",
                        "Non-overlapping windows can still share market regimes; no independence or significance claim",
                        "Baseline uses deterministic non-overlapping windows and is sensitive to its starting date",
                        "Historical CNN values may have been revised after their labeled date",
                        "Small groups are insufficient for reliable predictive probabilities"],
        "results": groups,
    }
