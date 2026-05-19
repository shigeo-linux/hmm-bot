"""Save regime + equity charts to PNG."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

COLORS = {"Bull": "#26a69a", "Bear": "#ef5350", "Sideways": "#bdbdbd"}
BG = "#0d0d1a"
PANEL_BG = "#1a1a2e"


def save_chart(bt: pd.DataFrame, path: str = "regime_chart.png"):
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 10), sharex=True,
                                         gridspec_kw={"height_ratios": [2, 1, 1]})
    fig.suptitle("BTC/USDT 4h — HMM Regime Detection (Paper Trading)", fontsize=13)

    # Price + regime shading
    ax1.plot(bt.index, bt["close"], color="white", linewidth=0.8, zorder=2)
    ax1.set_facecolor("#1a1a2e")
    ax1.set_ylabel("Price (USDT)")
    prev_state = None
    start = bt.index[0]
    for i, (ts, row) in enumerate(bt.iterrows()):
        if row["state"] != prev_state:
            if prev_state is not None:
                ax1.axvspan(start, ts, alpha=0.25, color=COLORS.get(prev_state, "grey"), zorder=1)
            start = ts
            prev_state = row["state"]
    ax1.axvspan(start, bt.index[-1], alpha=0.25, color=COLORS.get(prev_state, "grey"), zorder=1)
    patches = [mpatches.Patch(color=c, alpha=0.6, label=l) for l, c in COLORS.items()]
    ax1.legend(handles=patches, loc="upper left", fontsize=8)

    # Equity curves
    ax2.plot(bt.index, bt["equity"], label="Strategy", color="#29b6f6", linewidth=1)
    ax2.plot(bt.index, bt["bah_equity"], label="Buy & Hold", color="#ffa726",
             linewidth=1, linestyle="--")
    ax2.set_facecolor("#1a1a2e")
    ax2.set_ylabel("Equity ($)")
    ax2.legend(loc="upper left", fontsize=8)

    # Regime confidence
    ax3.plot(bt.index, bt["confidence"], color="#ce93d8", linewidth=0.8)
    ax3.axhline(0.7, color="grey", linestyle="--", linewidth=0.6)
    ax3.set_facecolor("#1a1a2e")
    ax3.set_ylabel("Confidence")
    ax3.set_ylim(0, 1)

    for ax in (ax1, ax2, ax3):
        ax.tick_params(colors="grey")
        for spine in ax.spines.values():
            spine.set_edgecolor("#333")
    fig.patch.set_facecolor(BG)

    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Chart saved → {path}")


def save_equity_curve(bt: pd.DataFrame, threshold: float, path: str = "equity_curve.png"):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True,
                                    gridspec_kw={"height_ratios": [3, 1]})
    fig.suptitle(
        f"BTC/USD Daily — HMM Equity Curve  |  Confidence threshold: {threshold*100:.0f}%  "
        f"|  Long-only",
        fontsize=13, color="white",
    )

    # ── Equity curves ────────────────────────────────────────────────────
    ax1.plot(bt.index, bt["equity"], label=f"HMM strategy ({threshold*100:.0f}% threshold)",
             color="#29b6f6", linewidth=1.5, zorder=3)
    ax1.plot(bt.index, bt["bah_equity"], label="Buy & Hold",
             color="#ffa726", linewidth=1.2, linestyle="--", zorder=2)

    # Fill between the two curves (green where strategy leads, red where it lags)
    ax1.fill_between(bt.index, bt["equity"], bt["bah_equity"],
                     where=bt["equity"] >= bt["bah_equity"],
                     interpolate=True, alpha=0.15, color="#26a69a", zorder=1)
    ax1.fill_between(bt.index, bt["equity"], bt["bah_equity"],
                     where=bt["equity"] < bt["bah_equity"],
                     interpolate=True, alpha=0.15, color="#ef5350", zorder=1)

    # Annotate final values
    final_strat = bt["equity"].iloc[-1]
    final_bah = bt["bah_equity"].iloc[-1]
    ax1.annotate(f"${final_strat:,.0f}", xy=(bt.index[-1], final_strat),
                 xytext=(8, 0), textcoords="offset points",
                 color="#29b6f6", fontsize=9, va="center")
    ax1.annotate(f"${final_bah:,.0f}", xy=(bt.index[-1], final_bah),
                 xytext=(8, 0), textcoords="offset points",
                 color="#ffa726", fontsize=9, va="center")

    ax1.set_facecolor(PANEL_BG)
    ax1.set_ylabel("Portfolio value ($)", color="grey")
    ax1.yaxis.set_major_formatter(mticker.StrMethodFormatter("${x:,.0f}"))
    ax1.legend(loc="upper left", fontsize=9, framealpha=0.3)
    ax1.axhline(10_000, color="#555", linewidth=0.5, linestyle=":")

    # ── Drawdown ──────────────────────────────────────────────────────────
    strat_dd = (bt["equity"] / bt["equity"].cummax()) - 1
    bah_dd = (bt["bah_equity"] / bt["bah_equity"].cummax()) - 1

    ax2.fill_between(bt.index, strat_dd * 100, 0, alpha=0.7, color="#29b6f6", label="Strategy DD")
    ax2.plot(bt.index, bah_dd * 100, color="#ffa726", linewidth=0.8,
             linestyle="--", label="Buy & Hold DD")
    ax2.set_facecolor(PANEL_BG)
    ax2.set_ylabel("Drawdown (%)", color="grey")
    ax2.yaxis.set_major_formatter(mticker.StrMethodFormatter("{x:.0f}%"))
    ax2.legend(loc="lower left", fontsize=8, framealpha=0.3)

    for ax in (ax1, ax2):
        ax.tick_params(colors="grey")
        ax.xaxis.label.set_color("grey")
        for spine in ax.spines.values():
            spine.set_edgecolor("#333")
    fig.patch.set_facecolor(BG)

    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Equity curve saved → {path}")
