from __future__ import annotations

from typing import Any

from .config import Settings
from .strategies.registry import Profile
from .strategies.zigzag_v7 import evaluate as evaluate_zigzag_v7
from .strategies.zigzag_v2 import evaluate as evaluate_zigzag_v2


def hold(reason: str, **metadata: Any) -> dict[str, Any]:
    return {"action": "hold", "reason": reason, "size": 0.0, "risk_checks": [], "metadata": metadata}


def decide(payload: dict[str, Any], profile: Profile | None, settings: Settings) -> dict[str, Any]:
    """Evaluate a strategy and promote only an approved demo candidate to an order."""
    if profile is None:
        return hold("configured strategy was not found")
    account = payload.get("account") or {}
    account_login = int(account.get("login") or 0)
    if settings.execution_enabled and account_login != settings.allowed_account_login:
        return hold("account login does not match the execution allowlist", strategy=profile.id)
    if settings.execution_enabled and str(account.get("trade_mode", "")).lower() != "demo":
        return hold("execution is restricted to demo accounts", strategy=profile.id)
    if not profile.enabled:
        return hold("strategy bundle is disabled", strategy=profile.id, version=profile.version)
    if not profile.runnable:
        return hold(
            "strategy implementation has not been imported and validated",
            strategy=profile.id, version=profile.version, implementation=profile.implementation,
        )
    if profile.implementation in {"builtin.zigzag-v7-shadow", "builtin.zigzag-v2-demo", "builtin.zigzag-v2-faithful"}:
        result = evaluate_zigzag_v7(payload, profile.parameters) if profile.implementation == "builtin.zigzag-v7-shadow" else evaluate_zigzag_v2(payload, profile.parameters)
        metadata = result.get("metadata") or {}
        if settings.execution_enabled and bool(metadata.get("candidate")):
            side = str(metadata.get("suggested_action", ""))
            if side not in {"buy", "sell"}:
                return hold("candidate did not contain a valid order side", strategy=profile.id)
            result["action"] = side
            result["size"] = min(float(metadata.get("suggested_size", settings.max_live_lot)), settings.max_live_lot)
            for field in ("entry_price", "stop_loss_price", "take_profit_price"):
                value = metadata.get(field)
                if value is None or float(value) <= 0:
                    return hold(f"candidate did not contain a valid {field}", strategy=profile.id)
                result[field] = float(value)
            result.setdefault("risk_checks", []).append({"name": "demo_execution_gate", "passed": True, "detail": "allowlisted_demo_account"})
            result["metadata"] = {**metadata, "execution_mode": "demo", "execution_cap_lot": settings.max_live_lot}
        return result
    return hold("unsupported strategy implementation", strategy=profile.id)
