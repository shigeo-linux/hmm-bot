"""
Paper trader: size positions based on current regime.

Rules:
  Bull     → long  1.0x  (only when confidence >= threshold)
  Sideways → flat  0.0x
  Bear     → short 1.0x  (only when confidence >= threshold, if shorting enabled)
  Low confidence → flat 0.0x regardless of regime label
"""
import pandas as pd
import numpy as np


REGIME_POSITION = {
    "Bull": 1.0,
    "Sideways": 0.0,
    "Bear": -1.0,
}

INITIAL_CAPITAL = 10_000.0
DEFAULT_CONFIDENCE_THRESHOLD = 0.70
DEFAULT_FEE_RATE = 0.001  # 0.1% per side (typical crypto taker fee)
DEFAULT_MIN_HOLD = 5       # bars; don't flip until position held this long


def _apply_min_hold(signal: pd.Series, min_hold: int) -> pd.Series:
    """Enforce a minimum holding period: once in a position, stay for min_hold bars."""
    out = signal.copy()
    current = 0.0
    held = 0
    for idx, desired in signal.items():
        if current == 0.0:
            current = desired          # enter freely from flat
            held = 1 if desired != 0.0 else 0
        elif held < min_hold:
            held += 1                  # locked in — ignore signal
        else:
            current = desired          # hold period elapsed, follow signal
            held = 1 if desired != 0.0 else 0
        out[idx] = current
    return out


def backtest(
    ohlcv: pd.DataFrame,
    regimes: pd.DataFrame,
    allow_short: bool = True,
    capital: float = INITIAL_CAPITAL,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    fee_rate: float = DEFAULT_FEE_RATE,
    min_hold: int = DEFAULT_MIN_HOLD,
) -> pd.DataFrame:
    df = ohlcv[["close"]].join(regimes[["state", "confidence"]], how="inner")
    df["signal"] = df["state"].map(REGIME_POSITION).fillna(0.0)
    if not allow_short:
        df["signal"] = df["signal"].clip(lower=0.0)
    df["signal"] = df["signal"].where(df["confidence"] >= confidence_threshold, other=0.0)

    df["position"] = _apply_min_hold(df["signal"], min_hold)

    df["fwd_ret"] = df["close"].pct_change().shift(-1)

    # Cost charged on the traded fraction each time position changes.
    df["trade"] = df["position"].diff().abs().fillna(df["position"].abs())
    df["cost"] = df["trade"] * fee_rate

    df["strat_ret"] = df["position"] * df["fwd_ret"] - df["cost"]
    df.dropna(inplace=True)

    df["equity"] = capital * (1 + df["strat_ret"]).cumprod()
    df["bah_equity"] = capital * (1 + df["fwd_ret"]).cumprod()
    return df


def summary(
    bt: pd.DataFrame,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    bars_per_year: int = 365 * 6,
    fee_rate: float = DEFAULT_FEE_RATE,
    min_hold: int = DEFAULT_MIN_HOLD,
) -> dict:
    strat = bt["strat_ret"]
    bah = bt["fwd_ret"]

    def ann_return(r): return (1 + r).prod() ** (bars_per_year / len(r)) - 1
    def ann_vol(r): return r.std() * np.sqrt(bars_per_year)
    def sharpe(r): return ann_return(r) / ann_vol(r) if ann_vol(r) else 0
    def max_dd(equity): return ((equity / equity.cummax()) - 1).min()

    active_bars = (bt["position"] != 0).sum()
    pct_active = active_bars / len(bt) * 100
    n_trades = (bt["trade"] > 0).sum()
    total_costs = bt["cost"].sum() * 100

    return {
        "Confidence threshold": f"{confidence_threshold * 100:.0f}%",
        "Min hold (bars)": str(min_hold),
        "Fee per side": f"{fee_rate * 100:.2f}%",
        "Trades": str(n_trades),
        "Total cost drag": f"{total_costs:.2f}%",
        "Bars in market": f"{active_bars} / {len(bt)}  ({pct_active:.1f}%)",
        "Total return (strategy)": f"{(bt['equity'].iloc[-1] / bt['equity'].iloc[0] - 1) * 100:.1f}%",
        "Total return (buy & hold)": f"{(bt['bah_equity'].iloc[-1] / bt['bah_equity'].iloc[0] - 1) * 100:.1f}%",
        "Ann. return (strategy)": f"{ann_return(strat) * 100:.1f}%",
        "Ann. return (buy & hold)": f"{ann_return(bah) * 100:.1f}%",
        "Sharpe (strategy)": f"{sharpe(strat):.2f}",
        "Sharpe (buy & hold)": f"{sharpe(bah):.2f}",
        "Max drawdown (strategy)": f"{max_dd(bt['equity']) * 100:.1f}%",
        "Max drawdown (buy & hold)": f"{max_dd(bt['bah_equity']) * 100:.1f}%",
        "Final equity": f"${bt['equity'].iloc[-1]:,.2f}",
    }
