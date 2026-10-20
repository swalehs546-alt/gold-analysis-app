# Gold Analysis Desk

A local Streamlit dashboard for educational XAUUSD technical analysis. It does not connect to a broker or place trades.

## Requirements
- Windows 10/11
- Python 3.11+ installed from python.org; enable **Add Python to PATH**
- Internet access for Yahoo Finance data (optional; CSV and demo modes work without it)

## Install and launch
Open Command Prompt in this folder and run:

```bat
py -3 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pytest -q
python -m streamlit run app.py
```

Or double-click `run.bat`; it creates the environment, installs requirements and launches Streamlit. The browser opens on a local address (usually http://localhost:8501). Stop with Ctrl+C in the command window.

## Data sources and integrity
- Default: Yahoo Finance symbol `XAUUSD=X`, an indicative spot-gold feed. Yahoo controls availability, delay and rate limits. It is not a Pepperstone quote and may not be suitable for execution decisions.
- CSV: select **CSV import** and upload bars containing `Open, High, Low, Close` and a date/time column (Date, Datetime, Timestamp or Time). Timestamps without a timezone are interpreted as UTC. CSV is imported historical data, not live data.
- Demo: select **Demo mode** deliberately. Synthetic data is labeled and directional signals are disabled. Demo data is never a silent fallback.
- The dashboard shows provider, mode, latest bar, data age and retrieval time. Stale or insufficient data disables directional signals.
- Spot-gold volume is not used as reliable evidence; the provider may omit it or provide volume that does not represent the whole OTC market.

## Configuration and privacy
Settings can be saved locally to `local_settings.json`. Signal records are written to `signal_history.csv` only when you press the record button. These files may contain your local preferences and should not be shared publicly. No API key is required for the Yahoo/CSV/demo paths. No account settings are sent to an external service by this app.

## Analysis rules
Signals use the last completed candle, not the currently forming candle. The deterministic rule requires at least 3 of 4 votes (price/EMA trend, MACD, RSI, DI direction), ADX above a threshold and no unusually large ATR shock. It often returns WAIT. The confluence score is a rule count, not a win probability. Indicators lag and are not proof of future movement.

## Risk planner limitations
Sizing formula: `lots = (equity × risk% / 100) / (|entry − stop| × account-currency value of a $1 price move per lot)`. Verify contract units, P&L conversion, minimum lot and lot step, spread, commission, leverage and margin with your broker. Defaults are illustrative and must not be assumed correct for your account. Gaps and slippage can exceed the planned loss. Never increase risk to recover losses.

## Backtesting
The backtest uses completed-bar signals and next-bar-open entries, then checks only subsequent bars. If stop and target are both touched in one bar, it assumes stop first. Spread/slippage/fees are simplified. P&L is expressed in price units per one unit exposure, not account currency; the results are not broker-accurate. Use chronological out-of-sample periods and avoid tuning on the same test data. Historical results do not predict future performance.

## Troubleshooting
- `py` not recognized: reinstall Python and enable PATH, or use `python` in place of `py -3`.
- Yahoo returns no bars / rate limit: wait, retry later, or import a CSV. The app will not substitute demo data automatically.
- Browser not opening: visit `http://localhost:8501` manually.
- Port occupied: run `python -m streamlit run app.py --server.port 8502`.
- CSV validation error: check exact OHLC columns and timestamps, and ensure High >= Open/Close/Low and Low <= Open/Close/High.
- Tests: run `python -m pytest -q` from this folder.

## Responsible use
This is an educational analysis tool, not financial advice or an automated trading system. No trading performance is promised. Review signals yourself and test in a separate, realistic process before considering any live decision.
