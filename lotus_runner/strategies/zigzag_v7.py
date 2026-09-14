"""Portable shadow implementation of 2Lotus ZigZag V7.

The strategy remains observation-only.  It preserves the V7 directional gate
and the V5 V1/V4 branch; the structural V2 branch is refused until a complete
900-second tick context is supplied by the MT5 bridge.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import fmean
from typing import Any


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


def _at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _ema(values: list[float], period: int) -> float:
    result = values[0]
    alpha = 2 / (period + 1)
    for value in values[1:]:
        result += alpha * (value - result)
    return result


def _stochastic(candles: list[Candle], period: int = 14, smooth: int = 3) -> tuple[list[float], list[float]]:
    raw: list[float] = []
    for index in range(period - 1, len(candles)):
        window = candles[index - period + 1:index + 1]
        low, high = min(c.low for c in window), max(c.high for c in window)
        raw.append(50.0 if high == low else (candles[index].close - low) / (high - low) * 100)
    k = [fmean(raw[max(0, i - smooth + 1):i + 1]) for i in range(len(raw))]
    d = [fmean(k[max(0, i - smooth + 1):i + 1]) for i in range(len(k))]
    return k, d


def _hourly(candles: list[Candle]) -> list[Candle]:
    buckets: dict[datetime, list[Candle]] = {}
    for candle in candles:
        hour = candle.timestamp.replace(minute=0, second=0, microsecond=0)
        buckets.setdefault(hour, []).append(candle)
    result: list[Candle] = []
    for hour, group in sorted(buckets.items()):
        group.sort(key=lambda item: item.timestamp)
        expected = [hour + timedelta(minutes=5 * i) for i in range(12)]
        if len(group) == 12 and [item.timestamp for item in group] == expected:
            result.append(Candle(hour, group[0].open, max(item.high for item in group), min(item.low for item in group), group[-1].close, sum(item.volume for item in group)))
    return result


def _regime(candles: list[Candle]) -> tuple[str, str]:
    hourly = _hourly(candles)
    if len(hourly) < 205:
        return "insufficient_history", "none"
    closes = [item.close for item in hourly]
    ema50 = _ema(closes[-50:], 50)
    previous_ema50 = _ema(closes[-51:-1], 50)
    ema200 = _ema(closes[-200:], 200)
    direction = "buy" if ema50 > ema200 and ema50 > previous_ema50 else "sell" if ema50 < ema200 and ema50 < previous_ema50 else "none"
    # V7 only vetoes a confirmed H1 selling trend. A non-directional H1 state is allowed.
    return ("trend", direction) if direction != "none" else ("transition", "none")


def _m30(candles: list[Candle]) -> list[Candle]:
    buckets: dict[datetime, list[Candle]] = {}
    for candle in candles:
        minute = candle.timestamp.minute - candle.timestamp.minute % 30
        start = candle.timestamp.replace(minute=minute, second=0, microsecond=0)
        buckets.setdefault(start, []).append(candle)
    output: list[Candle] = []
    for start, group in sorted(buckets.items()):
        group.sort(key=lambda item: item.timestamp)
        if len(group) == 6:
            output.append(Candle(start, group[0].open, max(item.high for item in group), min(item.low for item in group), group[-1].close, sum(item.volume for item in group)))
    return output


def _pivots(candles: list[Candle], span: int = 2) -> tuple[float | None, float | None]:
    high: float | None = None
    low: float | None = None
    for index in range(span, len(candles) - span):
        window = candles[index - span:index + span + 1]
        if candles[index].high == max(item.high for item in window):
            high = candles[index].high
        if candles[index].low == min(item.low for item in window):
            low = candles[index].low
    return high, low


def _calendar_allows(timestamp: datetime, side: str) -> tuple[bool, str]:
    schedule = {
        0: (4, 14, "buy", "monday_buy_04_14"),
        1: (3, 10, "buy", "tuesday_buy_03_10"),
        2: (3, 19, "buy", "wednesday_buy_03_19"),
        3: (3, 12, None, "thursday_03_12"),
        4: (3, 12, "sell", "friday_sell_03_12"),
    }
    start, end, allowed, rule = schedule.get(timestamp.weekday(), (0, 0, None, "weekend_block"))
    return start <= timestamp.hour < end and (allowed is None or side == allowed), rule


def _hold(reason: str, **metadata: Any) -> dict[str, Any]:
    return {"action": "hold", "reason": reason, "size": 0.0, "risk_checks": [], "metadata": {"candidate": False, "strategy_profile": "zigzag_scalper_v7_directional_shadow", "experimental_shadow_lock": True, **metadata}}


def evaluate(payload: dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
    try:
        now = _at(str(payload["timestamp_utc"]))
        candles = sorted([Candle(_at(str(row["timestamp_utc"])), float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]), float(row.get("volume", 0))) for row in payload.get("candles", [])], key=lambda item: item.timestamp)
    except (KeyError, TypeError, ValueError) as error:
        return _hold("v7_invalid_market_snapshot", detail=str(error))
    completed = [item for item in candles if item.timestamp + timedelta(minutes=5) <= now]
    if len(completed) < 60:
        return _hold("v7_warmup", completed_candles=len(completed), required_candles=60)
    regime, direction = _regime(completed)
    if regime == "insufficient_history":
        return _hold("v7_h1_history_warmup", completed_candles=len(completed), required_m5_candles=2460)
    point = float(payload.get("point_size", 0) or 0)
    bid, ask = float(payload.get("bid", 0) or 0), float(payload.get("ask", 0) or 0)
    if point <= 0 or bid <= 0 or ask <= 0 or ask < bid:
        return _hold("v7_invalid_quote")
    average_range = fmean(item.high - item.low for item in completed[-60:])
    expansion = float(parameters.get("expansion_threshold", 6.0))
    calendar_floor = float(parameters.get("calendar_range_floor", 4.5))
    if average_range >= expansion:
        return _hold("v7_v5_structural_branch_waiting_for_tick_context", v5_mode="v2_structural_expansion", average_m5_range_60=round(average_range, 6))
    bars30 = _m30(completed)
    if len(bars30) < 7:
        return _hold("v7_m30_history_warmup")
    pivot_high, pivot_low = _pivots(bars30)
    previous = completed[-1].close
    buy = pivot_high is not None and previous <= pivot_high < ask
    sell = pivot_low is not None and previous >= pivot_low > bid
    if not buy and not sell:
        return _hold("v7_zigzag_breakout_not_confirmed", v5_mode="v1")
    side = "buy" if buy else "sell"
    allowed = not (regime == "trend" and direction == "sell")
    checks = [{"name": "v7_h1_context", "passed": allowed, "detail": f"{regime}:{direction}"}]
    metadata: dict[str, Any] = {"candidate": allowed, "suggested_action": side, "v7_regime": regime, "v7_direction": direction, "v7_late_sell": side == "sell" and now.hour >= 12, "v5_average_m5_range_60": round(average_range, 6), "v5_mode": "v1_transition_calendar_gate" if calendar_floor <= average_range < expansion else "v1_normal_volatility"}
    if side == "sell":
        ema50 = _ema([item.close for item in completed[-50:]], 50)
        below = completed[-1].close < ema50
        k, d = _stochastic(completed[-60:])
        extreme = max(k[-2], d[-2]) if len(k) >= 2 else 0.0
        late_ok = now.hour < 12 or extreme >= 65
        checks.extend([{"name": "v7_m5_below_ema50", "passed": below, "detail": "m5_below_ema50"}, {"name": "v7_late_stochastic_65", "passed": late_ok, "detail": "late_stochastic_65"}])
        metadata.update({"candidate": allowed and below and late_ok, "v7_previous_stochastic_extreme": round(extreme, 6)})
    if calendar_floor <= average_range < expansion:
        calendar_ok, rule = _calendar_allows(now, side)
        checks.append({"name": "v5_v4_calendar_gate", "passed": calendar_ok, "detail": rule})
        metadata.update({"candidate": bool(metadata["candidate"]) and calendar_ok, "v5_calendar_gate_active": True, "v5_calendar_rule": rule})
    else:
        metadata.update({"v5_calendar_gate_active": False, "v5_calendar_rule": "not_active"})
    candidate = bool(metadata["candidate"])
    entry = ask if side == "buy" else bid
    metadata.update({"entry_price": entry, "stop_loss_price": entry - 240 * point if side == "buy" else entry + 240 * point, "take_profit_price": entry + 1000 * point if side == "buy" else entry - 1000 * point, "suggested_size": 0.10, "research_status": "provisional_requires_independent_replay"})
    return {"action": "hold", "reason": "v7_shadow_signal" if candidate else "v7_directional_block", "size": 0.0, "risk_checks": checks + [{"name": "experimental_shadow_lock", "passed": True, "detail": "execution_permanently_disabled"}], "metadata": {"strategy_profile": "zigzag_scalper_v7_directional_shadow", "experimental_shadow_lock": True, **metadata}}
