"""Indicators on the full trading-session index; no filling across missing data."""

import math

import pandas as pd

from ..rules import EXTREMES, classify

CATEGORIES = ("extreme_fear", "fear", "neutral", "greed", "extreme_greed")


def forward_performance(frame, horizon=20):
    """Subsequent price returns by starting sentiment, on the session index.

    Windows overlap. Require every price in the holding window, including the
    starting close; unfinished outcomes never enter the win-rate denominator.
    """
    future = frame.close.shift(-horizon) / frame.close - 1
    complete = frame.close.rolling(horizon + 1, min_periods=horizon + 1).count().shift(-horizon)
    future = future.where(complete == horizon + 1)
    categories = frame.fg.map(lambda value: classify(value) if pd.notna(value) else None)
    results = []
    for category in CATEGORIES:
        values = future[categories == category].dropna()
        results.append({"category": category, "sample_count": len(values),
                        "mean_return": float(values.mean()) if len(values) else None,
                        "win_rate": float((values > 0).mean()) if len(values) else None})
    return {"horizon_sessions": horizon, "period": {
                "start": str(frame.index[0].date()), "end": str(frame.index[-1].date())},
            "overlapping_windows": True, "win_definition": "Forward price return > 0",
            "results": results}


def add_indicators(frame):
    result = frame.copy()
    for window in (20, 50, 200):
        result[f"sma{window}"] = result.close.rolling(window, min_periods=window).mean()
    result["fg_sma5"] = result.fg.rolling(5, min_periods=5).mean()
    for window in (1, 20):
        values = result.close / result.close.shift(window) - 1
        result[f"return{window}"] = values.where(result.close.rolling(window + 1).count() == window + 1)
    for window in (5, 20):
        values = result.fg - result.fg.shift(window)
        result[f"fg_change{window}"] = values.where(result.fg.rolling(window + 1).count() == window + 1)
    result["category"] = result.fg.map(lambda x: classify(x) if pd.notna(x) else None)
    return result


def extreme_transitions(frame):
    events = []
    previous = None
    for session, row in frame.iterrows():
        current = row["category"] if pd.notna(row["category"]) else None
        if previous and current and previous != current:
            if previous in EXTREMES:
                events.append((session, "exit", previous))
            if current in EXTREMES:
                events.append((session, "enter", current))
        previous = current  # A missing session breaks transition inference.
    return events


def drawdown(close):
    return close / close.cummax() - 1


def trend_label(price_return, sentiment_change):
    if not math.isfinite(price_return) or not math.isfinite(sentiment_change):
        return "Trend comparison unavailable"
    if price_return == 0 or sentiment_change == 0:
        return "TQQQ unchanged" if price_return == 0 else "Sentiment unchanged"
    if price_return > 0:
        return "Price and sentiment strengthening" if sentiment_change > 0 else "Price-sentiment divergence"
    return "Sentiment improving; price falling" if sentiment_change > 0 else "Price and sentiment weakening"
