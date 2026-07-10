"""Shared matplotlib helpers for experiment plots."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import pearsonr, spearmanr


def scatter_obs_vs_pred(
    ax: plt.Axes,
    x: np.ndarray,
    y: np.ndarray,
    *,
    xlabel: str,
    ylabel: str,
    title: str,
    color: str = "#2563eb",
    point_size: int = 24,
) -> None:
    ax.scatter(x, y, alpha=0.5, s=point_size, edgecolors="none", c=color)
    if len(x) >= 2:
        rho = spearmanr(y, x).statistic
        r = pearsonr(y, x).statistic
        stat = f"n={len(x)}  Spearman={rho:.3f}  Pearson={r:.3f}"
    else:
        stat = f"n={len(x)}"
    lo = min(float(np.min(x)), float(np.min(y)))
    hi = max(float(np.max(x)), float(np.max(y)))
    pad = (hi - lo) * 0.05 if hi > lo else 0.1
    lo -= pad
    hi += pad
    ax.plot([lo, hi], [lo, hi], ls="--", c="#94a3b8", lw=1, label="y=x")
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(f"{title}\n{stat}", fontsize=9)
    ax.legend(loc="lower right", fontsize=7)
    ax.grid(True, alpha=0.25)


def save_figure(fig: plt.Figure, path, **kwargs) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, **kwargs)
