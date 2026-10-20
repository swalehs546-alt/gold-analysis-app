"""Simple chronological, next-bar-open execution backtest; no look-ahead signal use."""
from __future__ import annotations
import pandas as pd
import numpy as np
from analysis import calculate_indicators


def backtest(df: pd.DataFrame, spread: float = 0.0, slippage: float = 0.0, fee_per_trade: float = 0.0, atr_mult: float = 1.5, rr: float = 1.5) -> dict:
    if len(df) < 100: raise ValueError("Backtest requires at least 100 OHLC bars.")
    if min(spread, slippage, fee_per_trade) < 0: raise ValueError("Costs cannot be negative.")
    x = calculate_indicators(df).dropna(subset=["EMA20","EMA50","RSI14","MACD","MACDSignal","ATR14","ADX14"]).copy()
    trades=[]
    # At row i, signal is based on completed row i; entry occurs at next row open.
    # Each trade resolves using bars after entry only; if both stop/target touch in one bar, assume stop first.
    i=0
    while i < len(x)-2:
        row=x.iloc[i]
        long_votes=sum([row.Close > row.EMA20 > row.EMA50, row.MACD > row.MACDSignal, row.RSI14 >= 55, row.PlusDI > row.MinusDI])
        short_votes=sum([row.Close < row.EMA20 < row.EMA50, row.MACD < row.MACDSignal, row.RSI14 <= 45, row.MinusDI > row.PlusDI])
        side=1 if long_votes>=3 and long_votes>short_votes and row.ADX14>=16 else (-1 if short_votes>=3 and short_votes>long_votes and row.ADX14>=16 else 0)
        if side==0 or not np.isfinite(row.ATR14) or row.ATR14<=0:
            i+=1; continue
        entry_idx=i+1; entry=float(x.iloc[entry_idx].Open + side*(spread/2+slippage))
        dist=float(row.ATR14*atr_mult); stop=entry-side*dist; target=entry+side*dist*rr
        exit_price=None; exit_idx=None; outcome="end of data"
        for j in range(entry_idx, len(x)):
            b=x.iloc[j]
            stop_hit = b.Low <= stop if side==1 else b.High >= stop
            target_hit = b.High >= target if side==1 else b.Low <= target
            if stop_hit:
                exit_price=stop; exit_idx=j; outcome="stop"; break
            if target_hit:
                exit_price=target; exit_idx=j; outcome="target"; break
        if exit_price is None:
            exit_idx=len(x)-1; exit_price=float(x.iloc[-1].Close - side*(spread/2+slippage))
        pnl=side*(exit_price-entry)-fee_per_trade
        trades.append({"entry_time":x.index[entry_idx],"exit_time":x.index[exit_idx],"side":"BUY" if side==1 else "SELL","entry":entry,"exit":exit_price,"pnl_price_units":pnl,"outcome":outcome})
        i=exit_idx+1
    t=pd.DataFrame(trades)
    if t.empty:
        return {"trades":t,"count":0,"win_rate_pct":0.0,"expectancy":0.0,"average_win":0.0,"average_loss":0.0,"max_drawdown":0.0,"start":x.index[0],"end":x.index[-1],"note":"No trades triggered. P&L is in price units per one unit exposure, not account currency."}
    pnl=t["pnl_price_units"]
    equity=pnl.cumsum()
    drawdown=equity-equity.cummax()
    wins=pnl[pnl>0]; losses=pnl[pnl<0]
    return {"trades":t,"count":len(t),"win_rate_pct":100*(pnl>0).mean(),"expectancy":float(pnl.mean()),"average_win":float(wins.mean()) if len(wins) else 0.0,"average_loss":float(losses.mean()) if len(losses) else 0.0,"max_drawdown":float(drawdown.min()),"start":t.entry_time.min(),"end":t.exit_time.max(),"note":"Chronological simulation; signal uses completed bars and entry is next bar open. If stop and target both touch within a bar, stop is assumed first. P&L is price units per one unit exposure, not account currency. Costs are simplified."}
