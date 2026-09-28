"""Faithful portable port of the 2Lotus ZigZag Scalper V2.0 router."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from math import floor
from statistics import fmean
from typing import Any

PIP_SIZE = 0.01


def _hold(reason: str, checks: list[dict[str, Any]] | None = None, **metadata: Any) -> dict[str, Any]:
    return {"action": "hold", "reason": reason, "size": 0.0, "risk_checks": checks or [], "metadata": {"candidate": False, **metadata}}


def _when(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _candles(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [row for row in payload.get("candles", []) if all(key in row for key in ("timestamp_utc", "open", "high", "low", "close"))]
    return sorted(rows, key=lambda row: _when(str(row["timestamp_utc"])))


def _atr(rows: list[dict[str, Any]], period: int = 14) -> float:
    if len(rows) < 2:
        return 0.0
    selected = rows[-period:]
    start = len(rows) - len(selected)
    true_ranges = [
        max(float(candle["high"]) - float(candle["low"]), abs(float(candle["high"]) - float(rows[index - 1]["close"])), abs(float(candle["low"]) - float(rows[index - 1]["close"])))
        for index, candle in enumerate(selected, start)
    ]
    return fmean(true_ranges) if true_ranges else 0.0


def _ema(values: list[float], period: int = 20) -> float:
    if not values:
        return 0.0
    result = values[0]
    alpha = 2 / (period + 1)
    for value in values[1:]:
        result += alpha * (value - result)
    return result


def _aggregate_completed(candles: list[dict[str, Any]], available_at: datetime, minutes: int = 30) -> list[dict[str, Any]]:
    buckets: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
    available = available_at.astimezone(timezone.utc)
    for candle in candles:
        stamp = _when(str(candle["timestamp_utc"]))
        bucket_minute = stamp.minute - stamp.minute % minutes
        start = stamp.replace(minute=bucket_minute, second=0, microsecond=0)
        if start + timedelta(minutes=minutes) <= available:
            buckets[start].append(candle)
    return [{"timestamp_utc": start, "open": float(rows[0]["open"]), "high": max(float(row["high"]) for row in rows), "low": min(float(row["low"]) for row in rows), "close": float(rows[-1]["close"]), "volume": sum(float(row.get("volume", 0)) for row in rows)} for start, rows in sorted(buckets.items())]


def _pivots(candles: list[dict[str, Any]], span: int = 2) -> tuple[float | None, float | None]:
    pivot_high: float | None = None
    pivot_low: float | None = None
    for index in range(span, len(candles) - span):
        window = candles[index - span:index + span + 1]
        current = candles[index]
        if float(current["high"]) == max(float(row["high"]) for row in window):
            pivot_high = float(current["high"])
        if float(current["low"]) == min(float(row["low"]) for row in window):
            pivot_low = float(current["low"])
    return pivot_high, pivot_low


def _base_setup(payload: dict[str, Any], candles: list[dict[str, Any]], parameters: dict[str, Any]) -> dict[str, Any] | None:
    if len(candles) < 43:
        return None
    m30 = _aggregate_completed(candles, _when(str(payload["timestamp_utc"])))
    if len(m30) < 7:
        return None
    pivot_high, pivot_low = _pivots(m30)
    previous_close = float(candles[-2]["close"])
    bid, ask = float(payload["bid"]), float(payload["ask"])
    buy = pivot_high is not None and previous_close <= pivot_high < ask
    sell = pivot_low is not None and previous_close >= pivot_low > bid
    if not buy and not sell:
        return None
    if buy and sell:
        buy = ask - float(pivot_high) >= float(pivot_low) - bid
        sell = not buy
    side = "buy" if buy else "sell"
    entry = ask if buy else bid
    point_size = float(payload["point_size"])
    stop_points = float(parameters.get("normal_fixed_stop_points", 240))
    target_points = float(parameters.get("normal_fixed_target_points", 1000))
    stop = entry - stop_points * point_size if buy else entry + stop_points * point_size
    target = entry + target_points * point_size if buy else entry - target_points * point_size
    return {"side": side, "entry": entry, "stop": stop, "target": target, "stop_points": stop_points, "breakout_level": float(pivot_high if buy else pivot_low), "atr14": _atr(m30, min(14, len(m30))), "ema20": float(m30[-1]["close"])}


def _check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def _positions(payload: dict[str, Any], symbol: str) -> list[dict[str, Any]]:
    return [row for row in payload.get("positions", []) if str(row.get("symbol", "")).upper() == symbol.upper()]


def _candidate(payload: dict[str, Any], setup: dict[str, Any], checks: list[dict[str, Any]], parameters: dict[str, Any], *, profile: str, reason: str, mode: str, fixed_lot: float, metadata: dict[str, Any], risk_multiplier: float = 1.0) -> dict[str, Any]:
    account = payload.get("account") or {}
    balance = float(account.get("balance") or 0.0)
    value_per_point = float(payload.get("value_per_point_per_lot") or 0.0)
    risk_pct = float(parameters.get("risk_per_trade_pct", 1.0)) * risk_multiplier
    step = float(parameters.get("execution_lot_step", 0.01))
    raw_size = (balance * risk_pct / 100) / (setup["stop_points"] * value_per_point) if value_per_point > 0 and setup["stop_points"] > 0 else 0.0
    risk_size = floor((raw_size + 1e-12) / step) * step if step > 0 else 0.0
    point_size = float(payload["point_size"])
    return {
        "action": "hold", "reason": reason, "size": 0.0, "risk_amount": round(balance * risk_pct / 100, 2),
        "entry_price": setup["entry"], "stop_loss_price": setup["stop"], "take_profit_price": setup["target"],
        "stop_loss_points": round(setup["stop_points"], 2), "take_profit_points": round(abs(setup["target"] - setup["entry"]) / point_size, 2),
        "partial_take_profit_price": setup["target"], "final_take_profit_price": setup["target"], "partial_close_pct": 100.0, "move_stop_to_breakeven": False,
        "risk_checks": checks,
        "metadata": {"candidate": True, "strategy_profile": profile, "suggested_action": setup["side"], "suggested_size": risk_size, "fixed_strategy_lot": fixed_lot, "risk_sizing": "account_balance_percent_floor_to_broker_step", "risk_budget": round(balance * risk_pct / 100, 2), "effective_risk_pct": risk_pct, "setup_type": "happy_gold_zigzag_breakout", "signal_timeframe": "M30", "execution_timeframe": "M5", "fixed_stop_points": setup["stop_points"], "fixed_target_points": abs(setup["target"] - setup["entry"]) / point_size, "v2_mode": mode, "v3_mode": mode, "research_status": "broker_tick_forward_validation_required", **metadata},
    }


def _normal(payload: dict[str, Any], setup: dict[str, Any] | None, parameters: dict[str, Any], profile: str, average: float | None) -> dict[str, Any]:
    stamp = _when(str(payload["timestamp_utc"]))
    positions = _positions(payload, str(payload.get("symbol", "")))
    checks = [_check("symbol_match", str(payload.get("symbol", "")).upper() == "XAUUSD", "expected=XAUUSD"), _check("timeframe_match", str(payload.get("timeframe", "")).upper() == "M5", "expected=M5; signal=M30"), _check("spread_limit", float(payload.get("spread_points", 0)) <= float(parameters.get("max_spread_points", 50)), "max=50"), _check("research_session", time(3, 0) <= stamp.time() < time(19, 0), "03:00-19:00_UTC_proxy"), _check("single_position", not positions, "max_positions_for_symbol=1"), _check("zigzag_breakout", setup is not None, "confirmed_M30_fractal_breakout")]
    if not all(item["passed"] for item in checks[:5]) or setup is None:
        return _hold("zigzag_scalper_v2_filter_block" if setup is not None else "zigzag_scalper_v2_breakout_not_confirmed", checks, strategy_profile=profile, average_m5_range_60=average, v2_mode="v1_normal_volatility")
    return _candidate(payload, setup, checks, parameters, profile=profile, reason="zigzag_scalper_v2_normal_signal", mode="v1_normal_volatility", fixed_lot=.10, metadata={"average_m5_range_60": average})


def _structural(payload: dict[str, Any], setup: dict[str, Any] | None, parameters: dict[str, Any], profile: str, average: float | None) -> dict[str, Any]:
    candles = _candles(payload)
    stamp = _when(str(payload["timestamp_utc"]))
    direction = 0 if setup is None else (1 if setup["side"] == "buy" else -1)
    indicators = payload.get("indicators") or {}
    move_points = float(indicators.get("impulse_900s_move_points", 0))
    move_pips = move_points * float(payload["point_size"]) / PIP_SIZE
    aligned = direction * move_pips
    closes = [float(row["close"]) for row in candles]
    ema20 = _ema(closes[-20:]) if closes else 0.0
    ema_gap = direction * (closes[-1] - ema20) / PIP_SIZE if closes else 0.0
    extension = direction * (setup["entry"] - setup["breakout_level"]) / PIP_SIZE if setup else 0.0
    completed = candles[:-1]
    normalized = None
    if len(completed) >= 15:
        history = completed[-15:]
        atr14 = _atr(history, 14)
        if atr14:
            normalized = (float(history[-1]["high"]) - float(history[-1]["low"])) / atr14
    positions = _positions(payload, str(payload.get("symbol", "")))
    checks = [_check("symbol_match", str(payload.get("symbol", "")).upper() == "XAUUSD", "expected=XAUUSD"), _check("timeframe_match", str(payload.get("timeframe", "")).upper() == "M5", "expected=M5; signal=M30+M5+ticks_900s"), _check("spread_limit", float(payload.get("spread_points", 0)) <= float(parameters.get("max_spread_points", 50)), "max=50"), _check("research_session", time(3, 0) <= stamp.time() < time(19, 0), "03:00-19:00_UTC_proxy"), _check("weekday_filter", stamp.weekday() != 4, "friday_excluded_by_holdout_selector"), _check("single_position", not positions, "max_positions_for_symbol=1"), _check("zigzag_breakout", setup is not None, "confirmed_M30_fractal_breakout"), _check("tick_context_window_ready", indicators.get("impulse_900s_ready") == 1, "window=900s"), _check("tick_context_directional_threshold", bool(setup) and indicators.get("impulse_900s_ready") == 1 and aligned >= float(parameters.get("structural_context_pips", 1000)), f"aligned_min_pips={parameters.get('structural_context_pips', 1000)}"), _check("ema20_directional_gap", bool(setup) and ema_gap >= float(parameters.get("structural_ema20_gap_pips", 900)), f"aligned_min_pips={parameters.get('structural_ema20_gap_pips', 900)}"), _check("pivot_extension", bool(setup) and extension <= float(parameters.get("structural_max_pivot_extension_pips", 50)), f"max_pips={parameters.get('structural_max_pivot_extension_pips', 50)}")]
    metadata = {"average_m5_range_60": average, "impulse_900s_move_points": move_points, "impulse_900s_move_pips": move_pips, "impulse_900s_aligned_move_pips": aligned, "directional_ema20_gap_pips": ema_gap, "pivot_extension_pips": extension, "normalized_prior_m5_range": normalized}
    if not all(item["passed"] for item in checks) or setup is None:
        return _hold("zigzag_scalper_v2_structural_filter_block", checks, strategy_profile=profile, v2_mode="v2_structural_expansion", **metadata)
    point_size = float(payload["point_size"])
    direction = 1 if setup["side"] == "buy" else -1
    setup = dict(setup)
    setup["stop_points"] = float(parameters.get("structural_fixed_stop_pips", 60)) * PIP_SIZE / point_size
    setup["stop"] = setup["entry"] - direction * float(parameters.get("structural_fixed_stop_pips", 60)) * PIP_SIZE
    return _candidate(payload, setup, checks, parameters, profile=profile, reason="zigzag_scalper_v2_structural_signal", mode="v2_structural_expansion", fixed_lot=.40, metadata=metadata)


def evaluate(payload: dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
    symbol = str(payload.get("symbol", "")).upper()
    timeframe = str(payload.get("timeframe", "")).upper()
    if symbol != "XAUUSD" or timeframe != "M5":
        return _hold("zigzag_scalper_v2_market_filter_mismatch", strategy_profile="zigzag_scalper_v3_adaptive_shadow")
    candles = _candles(payload)
    completed = candles[:-1]
    recent = completed[-60:]
    average = fmean(float(row["high"]) - float(row["low"]) for row in recent) if len(recent) == 60 else None
    threshold = float(parameters.get("expansion_threshold", 6.0))
    setup = _base_setup(payload, candles, parameters)
    if average is not None and average >= threshold:
        return _structural(payload, setup, parameters, "zigzag_scalper_v3_adaptive_shadow", average)
    return _normal(payload, setup, parameters, "zigzag_scalper_v3_adaptive_shadow", average)
