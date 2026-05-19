"""Engineer features for HMM from OHLCV data."""
import numpy as np
import pandas as pd


def build_features(df: pd.DataFrame, bars_per_year: int = 365 * 6) -> pd.DataFrame:
    feat = pd.DataFrame(index=df.index)

    feat["log_ret"] = np.log(df["close"] / df["close"].shift(1))

    # Scale rolling windows relative to timeframe:
    # 4h → vol window=6 bars (~1 day), vol_z window=24 bars (~4 days)
    # 1d → vol window=10 bars (~2 weeks), vol_z window=30 bars (~1 month)
    is_daily = bars_per_year <= 365
    vol_window = 10 if is_daily else 6
    vz_window = 30 if is_daily else 24

    feat["vol"] = feat["log_ret"].rolling(vol_window).std()

    vol_mean = df["volume"].rolling(vz_window).mean()
    vol_std = df["volume"].rolling(vz_window).std()
    feat["vol_z"] = (df["volume"] - vol_mean) / (vol_std + 1e-9)

    feat["hl_range"] = (df["high"] - df["low"]) / df["close"]

    feat.dropna(inplace=True)
    return feat
