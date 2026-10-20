import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
import pytest
from market_data import normalize_ohlc, assess_data, make_demo_data
from analysis import calculate_indicators, analyze
from risk import size_position
from backtest import backtest


def sample(n=250):
    idx=pd.date_range("2024-01-01",periods=n,freq="15min",tz="UTC")
    c=2000+np.arange(n)*.2+np.sin(np.arange(n)/4)*2
    o=np.r_[c[0],c[:-1]]
    return pd.DataFrame({"Open":o,"High":np.maximum(o,c)+.7,"Low":np.minimum(o,c)-.7,"Close":c},index=idx)

def test_indicators_produce_values():
    x=calculate_indicators(sample())
    assert x.EMA20.notna().sum()>200
    assert x.RSI14.dropna().between(0,100).all()
    assert (x.ATR14.dropna()>0).all()

def test_position_sizing_formula_and_rejects_unsafe_risk():
    result=size_position(1000,.5,2000,1990,100,100,1)
    assert result["risk_cash"]==pytest.approx(5)
    assert result["lots"]==pytest.approx(.005)
    with pytest.raises(ValueError): size_position(1000,2,2000,1990,100,100,1)
    with pytest.raises(ValueError): size_position(1000,.5,2000,2000,100,100,1)

def test_demo_data_never_passes_live_signal_gate():
    d=make_demo_data()
    valid,reasons,_=assess_data(d.frame,"15m",d.fetched_at,d.mode)
    assert not valid
    assert any("Demo" in r or "demo" in r for r in reasons)
    assert analyze(d.frame,False)["decision"]=="WAIT"

def test_normalize_rejects_missing_columns_and_invalid_ohlc():
    with pytest.raises(ValueError): normalize_ohlc(pd.DataFrame({"Close":[2]}))
    bad=pd.DataFrame({"Open":[3],"High":[2],"Low":[1],"Close":[2]},index=pd.to_datetime(["2024-01-01"],utc=True))
    with pytest.raises(ValueError): normalize_ohlc(bad)

def test_backtest_entry_is_next_bar_not_same_bar():
    df=sample(300)
    bt=backtest(df,spread=0,slippage=0)
    if not bt["trades"].empty:
        first=bt["trades"].iloc[0]
        # The first trade must enter at the next bar's open; its timestamp cannot precede signal data.
        assert first["entry_time"] > df.index[0]
        expected=df.loc[first["entry_time"],"Open"]
        assert first["entry"]==pytest.approx(expected)
