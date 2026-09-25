"""A one-page chart of every lithology code in a legend."""

from __future__ import annotations

import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .patterns import Legend, draw_interval  # noqa: E402


def legend_chart(legend: Legend, path, cols: int = 3):
    types = list(legend)  # keeps the grouped order of the legend
    rows = math.ceil(len(types) / cols)
    w_mm, row_h = 210.0, 11.0
    h_mm = 24 + rows * row_h
    fig = plt.figure(figsize=(w_mm / 25.4, h_mm / 25.4))
    fig.text(0.5, 1 - 8 / h_mm, "LithoLog lithology legend", ha="center", va="center",
             fontsize=12, fontweight="bold")
    cw = (w_mm - 20) / cols
    for i, t in enumerate(types):
        c, r = divmod(i, rows)
        x, y = 10 + c * cw, 18 + r * row_h
        ax = fig.add_axes([x / w_mm, 1 - (y + 8) / h_mm, 16 / w_mm, 8 / h_mm])
        ax.set_xlim(0, 1)
        ax.set_ylim(8, 0)
        ax.set_axis_off()
        draw_interval(ax, 0, 1, 0, 8, t)
        fig.text((x + 18) / w_mm, 1 - (y + 2.8) / h_mm, t.name, fontsize=7, va="center")
        fig.text((x + 18) / w_mm, 1 - (y + 6.3) / h_mm, f"{t.code}  ·  {t.pattern}", fontsize=5.5,
                 va="center", color="#666666")
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path
