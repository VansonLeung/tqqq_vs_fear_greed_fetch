"""Separate return and drawdown distributions for development/evaluation periods."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from ..charts.artifacts import save_figure


def render_study(study, destination, metric):
    is_return = metric == "price_return"
    title = "SUBSEQUENT PRICE RETURNS" if is_return else "HOLDING-WINDOW DRAWDOWNS"
    horizons = study["horizons"]
    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 11,
                         "axes.spines.top": False, "axes.spines.right": False}):
        fig, axes = plt.subplots(len(horizons), 2, figsize=(12, 16), squeeze=False, sharey="row")
        try:
            fig.patch.set_facecolor("#fafbfd")
            fig.subplots_adjust(left=.09, right=.96, top=.84, bottom=.15, hspace=.55, wspace=.3)
            fig.text(.09, .96, title, fontsize=23, weight="bold", color="#182d40")
            fig.text(.09, .93, "After exiting Extreme Fear / TQQQ above vs below SMA200", fontsize=14)
            fig.text(.09, .895, f"Retrospective associations | Chronological split: {study['split_date']}\n"
                     "Fixed rule; no trading simulation or forecast probabilities", fontsize=12, linespacing=1.7)
            for row, horizon in enumerate(horizons):
                for column, period in enumerate(("development", "evaluation")):
                    axis = axes[row][column]
                    stats = study["results"][period][str(horizon)]
                    labels = []
                    for position, group in enumerate(("baseline", "above", "below"), 1):
                        entry = stats[group]
                        values = [100 * sample[metric] for sample in entry["samples"]]
                        labels.append(f"{group.title()}\nn={len(values)}" + (" / small" if entry["small_sample"] else ""))
                        if is_return and values:
                            labels[-1] += f"\nPositive: {entry['positive_fraction']:.0%}"
                        if values:
                            axis.boxplot([values], positions=[position], widths=.5, patch_artist=True,
                                         boxprops={"facecolor": ["#d6dce3", "#b7d9d0", "#eed0c5"][position-1]},
                                         medianprops={"color": "#182d40", "linewidth": 2},
                                         flierprops={"marker": ".", "markersize": 5})
                        else:
                            axis.text(position, .5, "No samples", transform=axis.get_xaxis_transform(),
                                      ha="center", fontsize=10, color="#777777")
                    axis.set_xticks([1, 2, 3], labels)
                    axis.set_xlim(.5, 3.5)
                    axis.tick_params(labelleft=True)
                    axis.axhline(0, color="#657588", lw=.8)
                    axis.grid(axis="y", alpha=.15)
                    axis.set_ylabel("Price return / %" if is_return else "Max drawdown / %")
                    axis.set_title(f"{horizon} sessions / {period.title()}", loc="left", weight="bold", pad=12)
            fig.text(.09, .105,
                     f"Coverage: {study['period']['start']} to {study['period']['end']}\n"
                     "Distinct exits; overlapping windows removed. Windows crossing the split are excluded.\n"
                     f"Small = fewer than {study['minimum_samples']} usable samples. Missing/incomplete outcomes are excluded.\n"
                     "Prices are split-adjusted; distributions and costs excluded. No publication-time assumption.\n"
                     "Boxes: median and middle 50%; whiskers: 1.5×IQR; dots: outliers. See JSON for all samples.",
                     fontsize=10.5, color="#536579", va="top", linespacing=1.65)
            return save_figure(fig, destination)
        finally:
            plt.close(fig)
