"""Overlaid price/sentiment history and subsequent returns by sentiment category."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, LogLocator
import pandas as pd

from .artifacts import save_figure
from .indicators import forward_performance, trend_label

INK, BLUE, ORANGE = "#182d40", "#2166ac", "#c27620"
ZONES = [(0, 25, "#f4d5cf"), (25, 45, "#fae8cf"), (45, 55, "#eeeddf"),
         (55, 75, "#dcece7"), (75, 100, "#bbddd2")]
ZONE_LABELS = ["Extreme Fear\n0–25", "Fear\n>25 to <45", "Neutral\n45–55",
               "Greed\n>55 to <75", "Extreme Greed\n75–100"]
BAR_COLORS = ["#c45548", "#e89c61", "#d6bd50", "#90b75e", "#489675"]


def number(value, suffix="", signed=False, percent=False):
    if pd.isna(value):
        return "n/a"
    return format(value * (100 if percent else 1), "+.1f" if signed else ".1f") + suffix


def _header(fig, data, sources, kind, generated_at, no_new_data):
    common = data.dropna(subset=["close", "fg"]).iloc[-1]
    price = data.dropna(subset=["close"]).iloc[-1]
    sentiment = data.dropna(subset=["fg"]).iloc[-1]
    subtitle = "Six-month overlay" if kind == "daily" else "Five-year overlay / logarithmic price axis"
    fig.text(.075, .963, "TQQQ × CNN FEAR & GREED", fontsize=25, weight="bold", color=INK)
    fig.text(.075, .932, subtitle, fontsize=15, color=BLUE)
    summary = (
        f"TQQQ ${price.close:,.2f}  |  Daily {number(price.return1, '%', True, True)}"
        f"     •     F&G {sentiment.fg:.1f} / {sentiment.category.replace('_', ' ').title()}"
        f"  |  5 sessions {number(sentiment.fg_change5, ' pts', True)}"
    )
    fig.text(.075, .902, summary, fontsize=13, color=INK)
    fig.text(.925, .934, trend_label(common.return20, common.fg_change20),
             fontsize=13, color=INK, ha="right")
    status = " / ".join(f"{name.upper()} {meta['latest_session']} ({meta['freshness']}"
                        f"{', cached' if meta['is_cached'] else ''})" for name, meta in sources.items())
    foot = f"Sources: Nasdaq / CNN  |  {status}  |  Prepared {generated_at[:19]} UTC\n"
    foot += "20-session outcomes: overlapping historical windows; win = return > 0. Incomplete price windows excluded.\n"
    foot += "Split-adjusted close-to-close returns; distributions and costs excluded. Historical associations; signal availability is unverified. Gaps are not filled."
    if no_new_data:
        foot += "\nChart values unchanged since the previous chart run."
    fig.text(.075, .083, foot, fontsize=10, color="#536579", va="top", linespacing=1.6)


def _performance_panel(axis, performance):
    rows = performance["results"]
    means = [row["mean_return"] * 100 if row["mean_return"] is not None else 0 for row in rows]
    axis.bar(range(5), means, color=BAR_COLORS, width=.56, zorder=3)
    axis.axhline(0, color=INK, lw=1)
    axis.set_ylabel("Mean forward return / %", fontsize=12)
    axis.set_xticks(range(5), [f"{label}\nn = {row['sample_count']:,}" for label, row in zip(ZONE_LABELS, rows)])
    axis.tick_params(axis="x", length=0, pad=10)
    axis.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}%"))
    low, high = min(0, min(means)), max(0, max(means))
    span = max(high - low, 4)
    axis.set_ylim(low - span * .5, high + span * .5)
    for position, (value, row) in enumerate(zip(means, rows)):
        label = (f"{value:+.2f}%\nWin rate {row['win_rate']:.1%}" if row["sample_count"]
                 else "No completed\noutcomes")
        axis.annotate(label, (position, value), xytext=(0, 8 if value >= 0 else -8),
                      textcoords="offset points", ha="center", va="bottom" if value >= 0 else "top",
                      fontsize=12, color=INK)
    period = performance["period"]
    axis.set_title("SUBSEQUENT 20-SESSION TQQQ PERFORMANCE BY STARTING SENTIMENT",
                   loc="left", fontsize=14, weight="bold", pad=32)
    axis.text(0, 1.05, f"History: {period['start']} – {period['end']}  |  Mean return + win rate  |  n = eligible starting sessions",
              transform=axis.transAxes, fontsize=11, color="#536579")


def render_chart(data, sources, destination, kind, generated_at, no_new_data=False):
    common = data.dropna(subset=["close", "fg"])
    if common.empty:
        raise ValueError("No common observations for chart")
    end = data.dropna(subset=["close", "fg"], how="all").index[-1]
    start = end - (pd.DateOffset(months=6) if kind == "daily" else pd.DateOffset(years=5))
    view = data.loc[max(start, common.index[0]):end].copy()
    if len(view) < 2:
        raise ValueError("At least two chart sessions are required")
    history = data.loc[max(end - pd.DateOffset(years=5), common.index[0]):end]
    performance = forward_performance(history)
    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 12, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.labelcolor": INK, "text.color": INK}):
        fig, (price_axis, performance_axis) = plt.subplots(
            2, 1, figsize=(18, 12), gridspec_kw={"height_ratios": [2.5, 1]})
        try:
            fig.patch.set_facecolor("#fafbfd")
            fig.subplots_adjust(left=.075, right=.925, top=.858, bottom=.17, hspace=.48)
            for axis in (price_axis, performance_axis):
                axis.set_facecolor("#ffffff")
                axis.grid(axis="y", alpha=.15, zorder=0)
                axis.tick_params(labelsize=11)
            sentiment_axis = price_axis.twinx()
            sentiment_axis.spines["right"].set_visible(True)
            # Draw sentiment bands/area behind the transparent price axes so
            # the TQQQ trend remains visible wherever the series cross.
            sentiment_axis.set_zorder(0)
            price_axis.set_zorder(1)
            price_axis.patch.set_visible(False)
            for low, high, color in ZONES:
                sentiment_axis.axhspan(low, high, color=color, alpha=.55, lw=0)
            sentiment_axis.fill_between(view.index, view.fg, 0, color=BLUE, alpha=.14)
            fg_line, = sentiment_axis.plot(view.index, view.fg, color=BLUE, lw=1.5, label="CNN F&G (right)")
            sentiment_axis.set(ylim=(0, 100), yticks=[0, 25, 45, 55, 75, 100], ylabel="CNN Fear & Greed / 0–100")
            sentiment_axis.tick_params(axis="y", colors=BLUE)
            sentiment_axis.yaxis.label.set_color(BLUE)
            price_line, = price_axis.plot(view.index, view.close, color=INK, lw=2.2, label="TQQQ close (left)")
            window = 50 if kind == "daily" else 200
            average, = price_axis.plot(view.index, view[f"sma{window}"], lw=1.3, color=ORANGE, alpha=.9, label=f"TQQQ SMA {window}")
            if kind == "weekly":
                price_axis.set_yscale("log")
                price_axis.yaxis.set_major_locator(LogLocator(base=10, subs=(1, 2, 5)))
                price_axis.yaxis.set_minor_formatter(FuncFormatter(lambda value, _: ""))
            price_axis.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"${value:g}"))
            price_axis.margins(y=.18)  # Leave room above the trend for the legend.
            price_axis.set_ylabel("TQQQ / split-adjusted USD" + (" (log)" if kind == "weekly" else ""))
            price_axis.set_title(f"PRICE + SENTIMENT   |   {view.index[0]:%Y-%m-%d} – {view.index[-1]:%Y-%m-%d}",
                                 loc="left", fontsize=14, weight="bold", pad=15)
            handles = [price_line, fg_line, average] + [Patch(facecolor=color, label=label.replace("\n", " "))
                                                       for (_, _, color), label in zip(ZONES, ZONE_LABELS)]
            price_axis.legend(handles=handles, loc="upper left", ncol=4, fontsize=10, framealpha=.93)
            price_axis.xaxis.set_major_locator(mdates.MonthLocator(interval=1 if kind == "daily" else 6))
            price_axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
            price_axis.set_xlim(view.index[0], view.index[-1])
            price_axis.tick_params(axis="x", labelbottom=True, pad=8)
            _performance_panel(performance_axis, performance)
            _header(fig, data, sources, kind, generated_at, no_new_data)
            path = save_figure(fig, destination)
        finally:
            plt.close(fig)
    return {"kind": kind, "path": path, "mime_type": "image/png", "generated_at": generated_at,
            "displayed_period": {"start": str(view.index[0].date()), "end": str(view.index[-1].date())},
            "comparison_session": str(common.index[-1].date()), "sources": sources,
            "forward_performance": performance}
