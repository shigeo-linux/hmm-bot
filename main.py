#!/usr/bin/env python3
"""
HMM Regime Detection Bot — BTC/USD daily
Detects Bull / Bear / Sideways regimes and paper trades accordingly.
"""
from tabulate import tabulate

from data import fetch_ohlcv
from features import build_features
from regime import train, regime_series
from paper_trader import backtest, summary, DEFAULT_CONFIDENCE_THRESHOLD, DEFAULT_FEE_RATE, DEFAULT_MIN_HOLD
from plot import save_chart, save_equity_curve

BARS_PER_YEAR = 365  # daily bars


def main():
    pair = "XBTUSD"
    interval = "1d"
    limit = 730  # ~2 years of daily bars

    print(f"Fetching {interval} bars for {pair} from Kraken...")
    ohlcv = fetch_ohlcv(pair, interval, limit)
    print(f"  Got {len(ohlcv)} bars  ({ohlcv.index[0].date()} → {ohlcv.index[-1].date()})")

    print("Building features...")
    features = build_features(ohlcv, bars_per_year=BARS_PER_YEAR)

    print(f"Training 3-state Gaussian HMM ({20} restarts, keeping best log-likelihood)...")
    model = train(features)

    print("Inferring regimes...")
    regimes = regime_series(model, features)

    # Current regime
    latest = regimes.iloc[-1]
    print(f"\n{'='*50}")
    print(f"  CURRENT REGIME : {latest['state'].upper()}")
    print(f"  Confidence     : {latest['confidence']*100:.1f}%")
    print(f"  p_bull         : {latest.get('p_bull', 0)*100:.1f}%")
    print(f"  p_sideways     : {latest.get('p_sideways', 0)*100:.1f}%")
    print(f"  p_bear         : {latest.get('p_bear', 0)*100:.1f}%")
    print(f"{'='*50}\n")

    # Regime distribution
    dist = regimes["state"].value_counts()
    print("Regime distribution over history:")
    for regime, count in dist.items():
        pct = count / len(regimes) * 100
        bar = "█" * int(pct / 2)
        print(f"  {regime:<10} {bar:<25} {pct:.1f}%")
    print()

    fee_rate = DEFAULT_FEE_RATE

    def _metrics(bt_t):
        strat = bt_t["strat_ret"]
        ann_ret = (1 + strat).prod() ** (BARS_PER_YEAR / len(strat)) - 1
        ann_v = strat.std() * (BARS_PER_YEAR ** 0.5)
        return {
            "sharpe":    ann_ret / ann_v if ann_v else 0.0,
            "ann_ret":   ann_ret,
            "total_ret": bt_t["equity"].iloc[-1] / bt_t["equity"].iloc[0] - 1,
            "max_dd":    ((bt_t["equity"] / bt_t["equity"].cummax()) - 1).min(),
            "trades":    int((bt_t["trade"] > 0).sum()),
            "cost_drag": bt_t["cost"].sum() * 100,
        }

    # ── Threshold × hold-period grid sweep ────────────────────────────────
    thresholds = [t / 100 for t in range(60, 96, 5)]
    hold_periods = [1, 3, 5, 7, 10, 15]

    sweep_rows = []
    sweep_bts = {}
    for thresh in thresholds:
        for hold in hold_periods:
            bt_t = backtest(ohlcv, regimes, allow_short=False,
                            confidence_threshold=thresh, fee_rate=fee_rate, min_hold=hold)
            m = _metrics(bt_t)
            sweep_rows.append({
                "Threshold": f"{thresh*100:.0f}%",
                "Min hold": str(hold),
                "Trades": str(m["trades"]),
                "Cost drag": f"{m['cost_drag']:.2f}%",
                "Total ret": f"{m['total_ret']*100:.1f}%",
                "Ann. ret": f"{m['ann_ret']*100:.1f}%",
                "Sharpe": f"{m['sharpe']:.2f}",
                "Max DD": f"{m['max_dd']*100:.1f}%",
            })
            sweep_bts[(thresh, hold)] = (bt_t, m["sharpe"], m["ann_ret"])

    # Print grouped by threshold for readability
    print(f"\nThreshold × hold-period sweep (long-only, fee: {fee_rate*100:.2f}%/side):")
    print(tabulate([r.values() for r in sweep_rows],
                   headers=sweep_rows[0].keys(), tablefmt="rounded_outline"))

    best_key = max(sweep_bts, key=lambda k: sweep_bts[k][1])
    best_thresh, best_hold = best_key
    best_bt, best_sharpe, best_ann = sweep_bts[best_key]
    print(f"\nBest by Sharpe: threshold={best_thresh*100:.0f}%  min_hold={best_hold}d  "
          f"→  Sharpe {best_sharpe:.2f}, ann. return {best_ann*100:.1f}%")

    # ── Full stats for the winner ──────────────────────────────────────────
    print(f"\nFull stats (threshold={best_thresh*100:.0f}%, min_hold={best_hold}d):")
    stats = summary(best_bt, best_thresh, bars_per_year=BARS_PER_YEAR,
                    fee_rate=fee_rate, min_hold=best_hold)
    print(tabulate(stats.items(), headers=["Metric", "Value"], tablefmt="rounded_outline"))

    # ── Charts ─────────────────────────────────────────────────────────────
    print("\nGenerating charts...")
    save_chart(best_bt, "/home/waas/Claude/hmm_bot/regime_chart.png")
    save_equity_curve(best_bt, best_thresh, "/home/waas/Claude/hmm_bot/equity_curve.png")

    # ── Live signal ────────────────────────────────────────────────────────
    print(f"\nLast 10 regime signals (threshold: {best_thresh*100:.0f}%):")
    tail = regimes.tail(10)[["state", "confidence"]].copy()
    tail["signal"] = tail.apply(
        lambda r: r["state"] if r["confidence"] >= best_thresh else "FLAT", axis=1
    )
    tail["confidence"] = (tail["confidence"] * 100).round(1).astype(str) + "%"
    print(tabulate(tail, headers=["Time", "Regime", "Confidence", "Signal"], tablefmt="rounded_outline"))


if __name__ == "__main__":
    main()
