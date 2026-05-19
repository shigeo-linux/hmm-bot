# HMM Regime Detection Bot

Detects BTC/USD market regimes (Bull / Bear / Sideways) using a 3-state Gaussian Hidden Markov Model and paper-trades accordingly.

## How it works

1. Fetches 2 years of daily BTC/USD OHLCV data from Kraken's public API
2. Engineers features: log returns, realized volatility, volume z-score, high-low range
3. Trains a 3-state Gaussian HMM with 20 random restarts, keeping the best log-likelihood solution
4. Labels hidden states Bull / Bear / Sideways by their mean log return
5. Sweeps confidence thresholds (60–95%) × holding periods (1–15 days) to find the best risk-adjusted parameters
6. Runs a paper backtest with 0.1% per-side transaction costs

## Features

- **Multi-restart HMM training** — 20 independent EM runs, best log-likelihood wins, avoiding local optima
- **Confidence threshold filter** — only trades when the model's posterior probability exceeds the threshold
- **Minimum holding period** — prevents rapid regime flipping that destroys returns via fees
- **Full backtest** — annualised return, Sharpe ratio, max drawdown vs buy-and-hold baseline
- **Equity curve chart** — price with regime shading + drawdown panel saved to PNG

## Quickstart

```bash
pip install -r requirements.txt
python3 main.py
```

Example output:

```
==================================================
  CURRENT REGIME : BULL
  Confidence     : 99.6%
  p_bull         : 99.6%
  p_sideways     : 0.4%
  p_bear         : 0.0%
==================================================

Threshold × hold-period sweep (long-only, fee: 0.10%/side):
...

Best by Sharpe: threshold=75%  min_hold=1d  →  Sharpe 1.54, ann. return 31.8%
```

## Project structure

```
hmm_bot/
├── data.py          # Kraken OHLCV fetcher (BTC/USD, daily)
├── features.py      # Feature engineering (log returns, vol, volume z-score, HL range)
├── regime.py        # GaussianHMM: multi-restart training, state labelling, posterior probs
├── paper_trader.py  # Backtest engine: confidence filter, min hold, transaction costs, stats
├── plot.py          # Regime-shaded price chart + equity curve + drawdown panel
└── main.py          # Entry point: runs full pipeline and prints results
```

## Configuration

All key parameters are constants at the top of each module:

| File | Parameter | Default | Description |
|------|-----------|---------|-------------|
| `regime.py` | `N_STATES` | 3 | Number of hidden regimes |
| `regime.py` | `N_RESTARTS` | 20 | EM restarts to avoid local optima |
| `regime.py` | `BASE_SEED` | 42 | Base random seed (reproducible) |
| `paper_trader.py` | `DEFAULT_FEE_RATE` | 0.001 | Fee per side (0.1%) |
| `paper_trader.py` | `DEFAULT_MIN_HOLD` | 5 | Minimum bars to hold a position |
| `main.py` | `BARS_PER_YEAR` | 365 | Set to 365×6 for 4h bars |

## Data source

[Kraken public OHLC API](https://docs.kraken.com/api/docs/rest/get-ohlc-data) — no API key required.

## Disclaimer

This is a research and paper-trading tool only. Past backtest performance does not guarantee future results. Do not use this as financial advice.
