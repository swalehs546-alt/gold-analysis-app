from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from market_data import fetch_yahoo, load_csv, make_demo_data, assess_data
from analysis import calculate_indicators, analyze
from risk import size_position
from backtest import backtest

APP_DIR=Path(__file__).resolve().parent
PREFS=APP_DIR/"local_settings.json"
HISTORY=APP_DIR/"signal_history.csv"
st.set_page_config(page_title="Gold Analysis Desk", page_icon="📈", layout="wide")
st.title("Gold Analysis Desk")
st.caption("Educational XAUUSD analysis • Local dashboard • No broker connection or order execution")

DEFAULTS={"interval":"15m","source":"Yahoo Finance","refresh":60,"min_rr":1.5,"atr_mult":1.5,"equity":1000.0,"risk_pct":0.5,"max_risk_pct":1.0,"contract_units":100.0,"value_per_unit":100.0}
def load_prefs():
    try:
        if PREFS.exists(): return {**DEFAULTS, **json.loads(PREFS.read_text(encoding="utf-8"))}
    except Exception: pass
    return DEFAULTS.copy()
if "prefs" not in st.session_state: st.session_state.prefs=load_prefs()
p=st.session_state.prefs
with st.sidebar:
    st.header("Settings")
    source=st.selectbox("Data source",["Yahoo Finance","CSV import","Demo mode"],index=["Yahoo Finance","CSV import","Demo mode"].index(p.get("source","Yahoo Finance")))
    interval=st.selectbox("Chart timeframe",["1m","5m","15m","30m","1h","4h","1d","1wk"],index=["1m","5m","15m","30m","1h","4h","1d","1wk"].index(p.get("interval","15m")))
    refresh=st.slider("Refresh interval (seconds)",30,300,int(p.get("refresh",60)),step=30)
    min_rr=st.slider("Minimum target R multiple",1.0,4.0,float(p.get("min_rr",1.5)),step=.25)
    atr_mult=st.slider("ATR stop multiplier",0.5,4.0,float(p.get("atr_mult",1.5)),step=.25)
    st.caption("Preferences are saved locally in local_settings.json. No account data is uploaded.")
    if st.button("Save preferences"):
        st.session_state.prefs.update({"source":source,"interval":interval,"refresh":refresh,"min_rr":min_rr,"atr_mult":atr_mult})
        PREFS.write_text(json.dumps(st.session_state.prefs,indent=2),encoding="utf-8")
        st.success("Preferences saved.")
    if st.button("Reset preferences"):
        st.session_state.prefs=DEFAULTS.copy()
        if PREFS.exists(): PREFS.unlink()
        st.rerun()

uploaded=None
if source=="CSV import": uploaded=st.file_uploader("Upload OHLC CSV",type=["csv"],help="Required columns: Open, High, Low, Close; plus Date/Datetime/Timestamp column or datetime index.")
try:
    if source=="Yahoo Finance": result=fetch_yahoo(interval)
    elif source=="CSV import":
        if uploaded is None:
            st.info("Upload a CSV to begin. No signal is available until valid data is supplied.")
            st.stop()
        result=load_csv(uploaded)
    else: result=make_demo_data()
    df=result.frame
except Exception as exc:
    st.error(f"Market data unavailable: {exc}")
    st.warning("No demo data has been substituted. Change to Demo mode explicitly or import a CSV.")
    st.stop()

valid, data_issues, age_min=assess_data(df,interval,result.fetched_at,result.mode)
# Imported data's recency may not match current market; never claim it is live.
if result.mode=="imported":
    st.info("Imported data: freshness depends on the file's timestamps. It is not a live feed.")
if result.mode.startswith("DEMO"):
    st.warning("DEMO MODE — synthetic prices, not real gold prices. Directional signals are disabled.")
if result.note: st.caption(result.note)
last_time=df.index[-1]
col1,col2,col3,col4=st.columns(4)
col1.metric("Instrument","XAUUSD")
col2.metric("Provider",result.provider)
col3.metric("Latest bar (UTC)",last_time.strftime("%Y-%m-%d %H:%M"))
col4.metric("Data age",f"{age_min:.0f} min" if age_min is not None else "Unknown")
st.caption(f"Mode: **{result.mode}** · Selected timeframe: **{interval}** · Chart timezone: UTC · Retrieved at: {result.fetched_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
if data_issues:
    for issue in data_issues: st.warning(issue)

analysis=analyze(df,valid and not result.mode.startswith("DEMO"),interval,min_rr,atr_mult)
chart_df=calculate_indicators(df)
show_indicators=st.checkbox("Show RSI and MACD panels",value=True)
fig=go.Figure(data=[go.Candlestick(x=chart_df.index,open=chart_df.Open,high=chart_df.High,low=chart_df.Low,close=chart_df.Close,name="XAUUSD")])
fig.add_trace(go.Scatter(x=chart_df.index,y=chart_df.EMA20,name="EMA 20",line=dict(width=1.4)))
fig.add_trace(go.Scatter(x=chart_df.index,y=chart_df.EMA50,name="EMA 50",line=dict(width=1.4)))
if analysis.get("support") is not None: fig.add_hline(y=analysis["support"],line_dash="dot",annotation_text="Swing support")
if analysis.get("resistance") is not None: fig.add_hline(y=analysis["resistance"],line_dash="dot",annotation_text="Swing resistance")
if analysis.get("entry") is not None:
    fig.add_hline(y=analysis["entry"],line_dash="solid",annotation_text="Illustrative entry")
    fig.add_hline(y=analysis["stop"],line_dash="dash",annotation_text="Illustrative stop")
    fig.add_hline(y=analysis["target"],line_dash="dash",annotation_text="Illustrative target")
fig.update_layout(height=520,margin=dict(l=10,r=10,t=30,b=10),xaxis_title="Time (UTC)",yaxis_title="Price (USD per troy ounce, indicative feed)",xaxis_rangeslider_visible=False,legend_orientation="h")
st.plotly_chart(fig,use_container_width=True)

a,b=st.columns([1,2])
with a:
    st.subheader("Current decision")
    st.markdown(f"## {analysis['decision']}")
    st.write(f"Decision bar: {analysis.get('bar_time','Unavailable')}")
    st.write(f"Confluence score: {analysis.get('score',0)}/100 — **not** a probability of success.")
    st.caption(analysis.get("rule","No valid signal rule available."))
    if analysis.get("entry") is not None:
        st.metric("Illustrative entry",f"{analysis['entry']:.3f}")
        st.metric("Stop-loss level",f"{analysis['stop']:.3f}")
        st.metric("Target level",f"{analysis['target']:.3f}")
        st.warning("Levels are analytical examples only. Spread, slippage, gaps and broker contract specifications may change actual outcomes.")
with b:
    st.subheader("Why the app decided this")
    for reason in analysis.get("reasons",[]): st.write("• "+reason)
    for reason in analysis.get("conflicts",[]): st.warning(reason)
    if not analysis.get("valid",False): st.error("Signal withheld because data or indicator requirements were not met.")
    if analysis.get("invalidation"): st.info("Invalidation: "+analysis["invalidation"])

if show_indicators:
    c1,c2=st.columns(2)
    with c1:
        st.subheader("RSI (14)")
        rfig=go.Figure(go.Scatter(x=chart_df.index,y=chart_df.RSI14,name="RSI")); rfig.add_hline(y=70,line_dash="dash"); rfig.add_hline(y=30,line_dash="dash"); rfig.update_layout(height=220,margin=dict(l=5,r=5,t=10,b=5),yaxis_range=[0,100]); st.plotly_chart(rfig,use_container_width=True)
    with c2:
        st.subheader("MACD")
        mfig=go.Figure(); mfig.add_trace(go.Scatter(x=chart_df.index,y=chart_df.MACD,name="MACD")); mfig.add_trace(go.Scatter(x=chart_df.index,y=chart_df.MACDSignal,name="Signal")); mfig.update_layout(height=220,margin=dict(l=5,r=5,t=10,b=5)); st.plotly_chart(mfig,use_container_width=True)

st.divider(); st.header("Risk planner")
st.caption("Sizing is only as accurate as your broker-specific contract assumptions. Verify contract size, lot increment, minimum lot and P&L value with Pepperstone before relying on any calculation.")
r1,r2,r3=st.columns(3)
with r1: equity=st.number_input("Account equity (account currency)",min_value=0.0,value=float(p.get("equity",1000)),step=100.0)
with r2: risk_pct=st.number_input("Risk per trade (%)",min_value=.01,max_value=5.0,value=float(p.get("risk_pct",.5)),step=.1)
with r3: maxrisk=st.number_input("Configured risk cap (%)",min_value=.1,max_value=5.0,value=float(p.get("max_risk_pct",1.0)),step=.1)
r4,r5,r6=st.columns(3)
with r4: entry=st.number_input("Entry price",min_value=0.0,value=float(analysis.get("entry") or float(df.Close.iloc[-1])),format="%.3f")
with r5: stop=st.number_input("Stop price",min_value=0.0,value=float(analysis.get("stop") or max(.01,float(df.Close.iloc[-1])-float(calculate_indicators(df).ATR14.iloc[-2] or 1)*atr_mult)),format="%.3f")
with r6: target=st.number_input("Target price (for R:R)",min_value=0.0,value=float(analysis.get("target") or float(df.Close.iloc[-1])+1),format="%.3f")
r7,r8=st.columns(2)
with r7: contract_units=st.number_input("Contract units per lot (verify broker)",min_value=0.0,value=float(p.get("contract_units",100)),step=1.0)
with r8: value_per_unit=st.number_input("Account-currency value of $1 move per lot (verify)",min_value=0.0,value=float(p.get("value_per_unit",100)),step=1.0)
if entry and stop and target and entry!=stop:
    risk_dist=abs(entry-stop); reward_dist=abs(target-entry); rr=reward_dist/risk_dist
    st.metric("Reward-to-risk ratio",f"{rr:.2f}:1")
    if rr < min_rr: st.warning(f"Target is below the configured minimum {min_rr:.2f}:1 reward-to-risk. This does not make a trade safe.")
    try:
        sized=size_position(equity,risk_pct,entry,stop,contract_units,value_per_unit,maxrisk)
        st.write(f"Estimated risk budget: {sized['risk_cash']:.2f} account-currency units")
        st.write(f"Estimated size: {sized['lots']:.4f} lots / {sized['units']:.2f} units (before broker lot-step rounding)")
        st.caption(sized["formula"])
        st.caption(f"Estimated stop distance: {sized['stop_distance']:.4f}; estimated loss per lot: {sized['loss_per_lot']:.2f}. Excludes variable spread, commissions, slippage and gaps.")
    except ValueError as exc: st.error(str(exc))
else: st.warning("Enter valid, different entry and stop prices to calculate position size.")
st.info("Why this matters: risk percentage sets the planned loss budget, not the probability of winning. Never increase risk to recover a loss.")

st.divider(); st.header("Historical evaluation")
st.write("This backtest uses the same broad 3-of-4 confluence concept, completed-bar signals, and next-bar-open entries. It is a simplified research tool; it is not a broker-accurate execution simulator.")
b1,b2,b3=st.columns(3)
with b1: spread=st.number_input("Spread (price units)",min_value=0.0,value=.30,step=.05)
with b2: slippage=st.number_input("Slippage per side (price units)",min_value=0.0,value=.10,step=.05)
with b3: fee=st.number_input("Fee per round trip (price units per unit exposure)",min_value=0.0,value=0.0,step=.1)
if st.button("Run chronological backtest"):
    try:
        bt=backtest(df,spread,slippage,fee,atr_mult,min_rr)
        k1,k2,k3,k4=st.columns(4)
        k1.metric("Trades",bt["count"]); k2.metric("Win rate",f"{bt['win_rate_pct']:.1f}%"); k3.metric("Expectancy",f"{bt['expectancy']:.4f}"); k4.metric("Max drawdown",f"{bt['max_drawdown']:.4f}")
        st.write(f"Average win: {bt['average_win']:.4f} · Average loss: {bt['average_loss']:.4f} · Test period: {bt['start']} to {bt['end']}")
        st.caption(bt["note"]+" Historical performance does not predict future results. Do not optimize parameters against the same test period.")
        if not bt["trades"].empty: st.dataframe(bt["trades"],use_container_width=True)
    except Exception as exc: st.error(f"Backtest could not run: {exc}")

st.divider(); st.header("Signal history")
if st.button("Record current app decision"):
    row={"recorded_at_utc":datetime.now(timezone.utc).isoformat(),"bar_time":str(analysis.get("bar_time","")),"decision":analysis["decision"],"price":float(df.Close.iloc[-2]) if len(df)>1 else float(df.Close.iloc[-1]),"provider":result.provider,"mode":result.mode,"timeframe":interval,"score":analysis.get("score",0)}
    pd.DataFrame([row]).to_csv(HISTORY,mode="a",header=not HISTORY.exists(),index=False)
    st.success("Decision recorded locally. This is a historical observation, not a prediction.")
if HISTORY.exists():
    hist=pd.read_csv(HISTORY)
    st.dataframe(hist.tail(100),use_container_width=True)
    st.caption("Outcomes are not automatically labeled as wins/losses; doing so correctly requires an explicit entry, exit, costs and horizon policy. Recorded signals alone are not performance evidence.")
else: st.caption("No signals recorded yet.")

with st.expander("Learning notes"):
    st.markdown("""
    - **EMA 20/50:** smoothed prices used as a trend filter; they lag and can whipsaw in sideways markets.
    - **RSI:** measures recent directional momentum on a 0–100 scale; overbought does not automatically mean sell.
    - **MACD:** compares moving averages to describe momentum changes; it is not an independent guarantee.
    - **ATR:** estimates recent price range. An ATR-based stop is a planning convention, not a maximum-loss guarantee.
    - **ADX / DI:** ADX estimates trend strength; +DI and -DI compare directional movement. ADX alone does not indicate direction.
    - **Support/resistance:** swing-based historical levels can break; they are zones of interest, not barriers.
    - **Confluence score:** counts rule votes. It is not a calibrated probability of success.
    - **Data quality:** Yahoo Finance's XAUUSD=X is an indicative feed and may be delayed, unavailable, cached upstream, or rate limited. It is not your Pepperstone executable quote. Spot-market volume may be absent or non-representative.
    """)
