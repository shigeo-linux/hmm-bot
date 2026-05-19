"""Fetch OHLCV data from Kraken public API (BTC/USD, 4h bars)."""
import requests
import pandas as pd

KRAKEN_URL = "https://api.kraken.com/0/public/OHLC"
# Kraken interval is in minutes: 240 = 4h
INTERVAL_MAP = {"4h": 240, "1h": 60, "1d": 1440}


def fetch_ohlcv(pair: str = "XBTUSD", interval: str = "4h", limit: int = 1000) -> pd.DataFrame:
    params = {"pair": pair, "interval": INTERVAL_MAP.get(interval, 240)}
    resp = requests.get(KRAKEN_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("error"):
        raise ValueError(f"Kraken API error: {data['error']}")

    # Kraken returns {"result": {"XBTUSD": [...], "last": ...}}
    key = [k for k in data["result"] if k != "last"][0]
    raw = data["result"][key]

    df = pd.DataFrame(raw, columns=[
        "time", "open", "high", "low", "close", "vwap", "volume", "count"
    ])
    df["time"] = pd.to_datetime(df["time"], unit="s")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    df.set_index("time", inplace=True)
    df = df.tail(limit)
    return df[["open", "high", "low", "close", "volume"]]
