"""Exp13 warm: decompose observed y axis vs y_hat (wrapper).

Run from ai/experiments:
  python plot/plot_exp13_obs_decompose.py
"""

from __future__ import annotations

from plot_decompose import plot_decompose
from paths import FIGURES_DIR, RECIPE_LIGHTFM_CSV


def main() -> None:
    out_png, out_txt = plot_decompose(
        RECIPE_LIGHTFM_CSV,
        "exp13_obs_y",
        "Experiment 13 — observed (y) axis decomposition vs y_hat (warm only)",
        out_png=FIGURES_DIR / "exp13_obs_y_decompose_scatter.png",
        out_txt=FIGURES_DIR / "exp13_obs_y_decompose_metrics.txt",
    )
    print(f"saved: {out_png}")
    print(f"saved: {out_txt}")


if __name__ == "__main__":
    main()
