"""Broker-agnostic position sizing. Inputs must be verified against broker contract specs."""
from __future__ import annotations
import math


def size_position(equity: float, risk_pct: float, entry: float, stop: float, contract_units: float | None, value_per_price_unit_per_lot: float | None, max_risk_pct: float = 1.0) -> dict:
    vals = [equity, risk_pct, entry, stop]
    if any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in vals):
        raise ValueError("Enter finite numeric equity, risk %, entry and stop values.")
    if equity <= 0 or entry <= 0 or stop <= 0: raise ValueError("Equity, entry and stop must be positive.")
    if risk_pct <= 0 or risk_pct > max_risk_pct or risk_pct > 5:
        raise ValueError(f"Risk must be above 0 and no more than configured cap ({max_risk_pct:g}%).")
    if entry == stop: raise ValueError("Entry and stop must differ.")
    if not contract_units or not value_per_price_unit_per_lot or contract_units <= 0 or value_per_price_unit_per_lot <= 0:
        raise ValueError("Broker contract units and currency value per $1 price move per lot are required; verify with your broker.")
    risk_cash = equity * risk_pct / 100
    stop_distance = abs(entry-stop)
    loss_per_lot = stop_distance * value_per_price_unit_per_lot
    lots = risk_cash / loss_per_lot
    return {"risk_cash":risk_cash,"stop_distance":stop_distance,"loss_per_lot":loss_per_lot,"lots":lots,"units":lots*contract_units,"formula":"Lots = (equity × risk% ÷ 100) ÷ (|entry − stop| × currency value per $1 price move per lot)."}
