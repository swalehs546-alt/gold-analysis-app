"""Market data retrieval and validation. No broker connection or order execution."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd

REQUIRED = ["Open", "High", "Low", "Close"]

@dataclass
class DataResult:
    frame: pd.DataFrame
    provider: str
    mode: str
    fetched_at: datetime
    note: str = ""
    error: str = ""


def normalize_ohlc(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize common OHLC column spellings and reject invalid bars."""
    if frame is None or frame.empty:
        raise ValueError("No rows were returned.")
    df = frame.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [str(c[0]) for c in df.columns]
    rename = {str(c).strip().lower(): str(c).strip().title() for c in df.columns}
    df = df.rename(columns=rename)
    # Handle common aliases.
    aliases = {"Adj Close": "Adj Close", "Datetime": "Datetime", "Timestamp": "Timestamp"}
    for col in list(df.columns):
        if col.lower() in ("open", "high", "low", "close", "volume"):
            df = df.rename(columns={col: col.capitalize()})
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError("CSV/data must contain Open, High, Low and Close columns. Missing: " + ", ".join(missing))
    if not isinstance(df.index, pd.DatetimeIndex):
        time_col = next((c for c in df.columns if c.lower() in ("datetime", "timestamp", "date", "time")), None)
        if time_col:
            df[time_col] = pd.to_datetime(df[time_col], utc=True, errors="coerce")
            df = df.set_index(time_col)
        else:
            df.index = pd.to_datetime(df.index, utc=True, errors="coerce")
    idx = pd.to_datetime(df.index, utc=True, errors="coerce")
    df.index = idx
    df = df.loc[~df.index.isna()].sort_index()
    df = df[~df.index.duplicated(keep="last")]
    for col in REQUIRED + (["Volume"] if "Volume" in df.columns else []):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=REQUIRED)
    if df.empty:
        raise ValueError("No valid OHLC bars remain after cleaning.")
    if (df["High"] < df[["Open", "Close", "Low"]].max(axis=1)).any() or (df["Low"] > df[["Open", "Close", "High"]].min(axis=1)).any():
        raise ValueError("Invalid OHLC bar: High/Low conflicts with Open, Close or Low/High.")
    if (df[REQUIRED] <= 0).any().any():
        raise ValueError("OHLC prices must be positive.")
    return df


def fetch_yahoo(interval: str = "15m", period: str = "60d") -> DataResult:
    """Fetch indicative Yahoo Finance GC=F data; availability is not guaranteed."""
    import yfinance as yf
    interval_map = {"1m": ("1m", "7d"), "5m": ("5m", "60d"), "15m": ("15m", "60d"), "30m": ("30m", "60d"), "1h": ("60m", "730d"), "4h": ("60m", "730d"), "1d": ("1d", "10y"), "1wk": ("1wk", "max")}
    yf_interval, default_period = interval_map.get(interval, ("15m", "60d"))
    use_period = period if period else default_period
    raw = yf.download("GC=F", period=use_period, interval=yf_interval, auto_adjust=False, progress=False, threads=False, timeout=15)
    if raw is None or raw.empty:
        raise RuntimeError("Yahoo Finance returned no bars. Try later or import a CSV.")
    df = normalize_ohlc(raw)
    if interval == "4h":
        df = df.resample("4h").agg({"Open":"first", "High":"max", "Low":"min", "Close":"last", **({"Volume":"sum"} if "Volume" in df.columns else {})}).dropna(subset=REQUIRED)
    return DataResult(df, "Yahoo Finance (GC=F)", "downloaded / indicative; may be delayed", datetime.now(timezone.utc), "Yahoo data availability, delays and rate limits are outside this app's control. Volume may be absent or not representative of the global spot-gold market.")


def load_csv(uploaded_file) -> DataResult:
    raw = pd.read_csv(uploaded_file)
    df = normalize_ohlc(raw)
    return DataResult(df, f"Imported CSV: {getattr(uploaded_file, 'name', 'uploaded file')}", "imported", datetime.now(timezone.utc), "CSV timestamps are interpreted as UTC if no timezone is provided.")


def make_demo_data(rows: int = 500, seed: int = 7) -> DataResult:
    """Deterministic synthetic data, visibly labeled demo; never used as a fallback."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(end=pd.Timestamp.now(tz="UTC").floor("15min"), periods=rows, freq="15min")
    steps = rng.normal(0.015, 1.7, rows)
    close = 2300 + np.cumsum(steps)
    open_ = np.r_[close[0], close[:-1]] + rng.normal(0, .35, rows)
    high = np.maximum(open_, close) + rng.uniform(.1, 1.5, rows)
    low = np.minimum(open_, close) - rng.uniform(.1, 1.5, rows)
    df = pd.DataFrame({"Open":open_, "High":high, "Low":low, "Close":close, "Volume":np.nan}, index=idx)
    return DataResult(df, "Synthetic demo generator", "DEMO — NOT MARKET DATA", datetime.now(timezone.utc), "Synthetic prices for interface/testing only. Do not trade from demo data.")


def assess_data(df: pd.DataFrame, interval: str, fetched_at: datetime, mode: str, min_bars: int = 80) -> tuple[bool, list[str], Optional[float]]:
    reasons = []
    if df is None or len(df) < min_bars:
        reasons.append(f"Insufficient history: need at least {min_bars} valid bars.")
    if df is None or df.empty:
        return False, reasons or ["No market data."], None
    if df.index.has_duplicates or not df.index.is_monotonic_increasing:
        reasons.append("Timestamps are duplicated or out of order.")
    if df[REQUIRED].isna().any().any() or not np.isfinite(df[REQUIRED].to_numpy()).all():
        reasons.append("OHLC data contains missing or non-finite values.")
    if mode.startswith("DEMO"):
        reasons.append("Demo data cannot support a live-market directional signal.")
    last = df.index[-1]
    age_min = max(0.0, (datetime.now(timezone.utc) - last.to_pydatetime()).total_seconds() / 60)
    max_age = {"1m": 8, "5m": 20, "15m": 50, "30m": 100, "1h": 180, "4h": 600, "1d": 60*60, "1wk": 60*60*24*10}.get(interval, 60)
    if not mode.startswith("DEMO") and age_min > max_age:
        reasons.append(f"Latest bar is stale for {interval} data ({age_min:.0f} minutes old; threshold {max_age} minutes).")
    return not reasons, reasons, age_min
