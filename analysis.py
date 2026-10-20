"""Transparent technical indicators and deterministic signal rules."""
from __future__ import annotations
import numpy as np
import pandas as pd
from market_data import REQUIRED


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    c, h, l = x["Close"], x["High"], x["Low"]
    x["EMA20"] = c.ewm(span=20, adjust=False).mean()
    x["EMA50"] = c.ewm(span=50, adjust=False).mean()
    x["SMA20"] = c.rolling(20).mean()
    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    rs = gain / loss.replace(0, np.nan)
    x["RSI14"] = 100 - 100 / (1 + rs)
    x.loc[(loss == 0) & (gain > 0), "RSI14"] = 100
    x.loc[(gain == 0) & (loss > 0), "RSI14"] = 0
    fast = c.ewm(span=12, adjust=False).mean()
    slow = c.ewm(span=26, adjust=False).mean()
    x["MACD"] = fast - slow
    x["MACDSignal"] = x["MACD"].ewm(span=9, adjust=False).mean()
    x["MACDHist"] = x["MACD"] - x["MACDSignal"]
    prev_close = c.shift(1)
    tr = pd.concat([(h-l), (h-prev_close).abs(), (l-prev_close).abs()], axis=1).max(axis=1)
    x["ATR14"] = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    up = h.diff()
    down = -l.diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    atr = x["ATR14"].replace(0, np.nan)
    plus_di = 100 * plus_dm.ewm(alpha=1/14, adjust=False, min_periods=14).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1/14, adjust=False, min_periods=14).mean() / atr
    dx = 100 * (plus_di-minus_di).abs() / (plus_di+minus_di).replace(0, np.nan)
    x["ADX14"] = dx.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    x["PlusDI"] = plus_di
    x["MinusDI"] = minus_di
    x["BBMid"] = c.rolling(20).mean()
    sd = c.rolling(20).std(ddof=0)
    x["BBUpper"] = x["BBMid"] + 2*sd
    x["BBLower"] = x["BBMid"] - 2*sd
    x["BBWidth"] = (x["BBUpper"]-x["BBLower"]) / x["BBMid"].replace(0, np.nan)
    # Closed-bar swing levels: a pivot is only known after two bars to its right.
    pivot_high = h.shift(2).rolling(5).max()  # prior 4 bars + candidate bar, no future values
    pivot_low = l.shift(2).rolling(5).min()
    x["SwingResistance"] = np.where(h.shift(2).eq(pivot_high), h.shift(2), np.nan)
    x["SwingSupport"] = np.where(l.shift(2).eq(pivot_low), l.shift(2), np.nan)
    return x


def analyze(df: pd.DataFrame, data_valid: bool, timeframe: str = "15m", min_rr: float = 1.5, atr_stop_mult: float = 1.5, rsi_low: float = 45, rsi_high: float = 55, min_adx: float = 16) -> dict:
    if not data_valid:
        return {"decision":"WAIT", "reasons":["Data-quality checks failed; directional signals are disabled."], "valid":False, "score":0, "entry":None, "stop":None, "target":None}
    if len(df) < 80:
        return {"decision":"WAIT", "reasons":["At least 80 bars are required for the configured indicators."], "valid":False, "score":0, "entry":None, "stop":None, "target":None}
    x = calculate_indicators(df)
    # Exclude the current possibly forming candle: all decisions use the last completed bar.
    bar = x.iloc[-2]
    prev = x.iloc[-3]
    required = ["EMA20","EMA50","RSI14","MACD","MACDSignal","ATR14","ADX14"]
    if any(pd.isna(bar[k]) for k in required):
        return {"decision":"WAIT", "reasons":["Indicator history is insufficient or indicators are undefined."], "valid":False, "score":0, "entry":None, "stop":None, "target":None, "indicators":x}
    reasons, conflicts = [], []
    long_votes = [bar.Close > bar.EMA20 > bar.EMA50, bar.MACD > bar.MACDSignal, bar.RSI14 >= rsi_high, bar.PlusDI > bar.MinusDI]
    short_votes = [bar.Close < bar.EMA20 < bar.EMA50, bar.MACD < bar.MACDSignal, bar.RSI14 <= rsi_low, bar.MinusDI > bar.PlusDI]
    long_n, short_n = sum(map(bool,long_votes)), sum(map(bool,short_votes))
    score = int(25 * max(long_n, short_n))
    if bar.EMA20 > bar.EMA50: reasons.append("Trend: EMA20 is above EMA50 (bullish structure).")
    elif bar.EMA20 < bar.EMA50: reasons.append("Trend: EMA20 is below EMA50 (bearish structure).")
    else: conflicts.append("EMAs are aligned neither way.")
    reasons.append(f"Momentum: RSI(14)={bar.RSI14:.1f}; MACD histogram={bar.MACDHist:.4f}.")
    reasons.append(f"Trend strength: ADX(14)={bar.ADX14:.1f}; values below {min_adx:g} imply a weaker trend under these rules.")
    reasons.append(f"Volatility: ATR(14)={bar.ATR14:.4f}; this is a price-distance estimate, not a guaranteed maximum loss.")
    # Volatility shock guard: ATR over 2.5x its recent median -> WAIT.
    recent_atr = x["ATR14"].iloc[-32:-2].dropna()
    abnormal = len(recent_atr) >= 10 and bar.ATR14 > 2.5 * recent_atr.median()
    if abnormal: conflicts.append("ATR is unusually high versus recent bars; avoid fresh directional signals.")
    if bar.ADX14 < min_adx: conflicts.append("Trend-strength filter is not met.")
    if long_n >= 3 and long_n > short_n and not abnormal and bar.ADX14 >= min_adx:
        decision = "BUY"
    elif short_n >= 3 and short_n > long_n and not abnormal and bar.ADX14 >= min_adx:
        decision = "SELL"
    else:
        decision = "WAIT"
        conflicts.append("The explicit confluence rule is not met (at least 3 of 4 votes, with ADX and volatility filters).")
    if long_n and short_n: conflicts.append(f"Evidence is mixed: {long_n}/4 bullish votes versus {short_n}/4 bearish votes.")
    entry = stop = target = None
    if decision in ("BUY", "SELL"):
        entry = float(bar.Close)
        distance = float(bar.ATR14 * atr_stop_mult)
        if not np.isfinite(distance) or distance <= 0:
            decision = "WAIT"; conflicts.append("ATR stop distance is invalid; no setup levels shown.")
        else:
            stop = entry-distance if decision == "BUY" else entry+distance
            target = entry + distance*min_rr if decision == "BUY" else entry-distance*min_rr
    levels = x["SwingSupport"].dropna(), x["SwingResistance"].dropna()
    support = float(levels[0].iloc[-1]) if not levels[0].empty else None
    resistance = float(levels[1].iloc[-1]) if not levels[1].empty else None
    if support is not None: reasons.append(f"Last detected swing support: {support:.3f} (algorithmic estimate).")
    if resistance is not None: reasons.append(f"Last detected swing resistance: {resistance:.3f} (algorithmic estimate).")
    return {"decision":decision,"reasons":reasons,"conflicts":conflicts,"valid":True,"score":score,"long_votes":long_n,"short_votes":short_n,"entry":entry,"stop":stop,"target":target,"bar_time":x.index[-2],"indicators":x,"bar":bar,"support":support,"resistance":resistance,"invalidation":"A completed candle closes beyond the planned stop, or the EMA/MACD evidence reverses before entry. Reassess rather than widening a stop to avoid a loss.","rule":"At least 3/4 votes agree (price/EMA trend, MACD, RSI, DI direction), ADX >= threshold, and no ATR shock. Uses last completed bar; not a probability model."}
