from __future__ import annotations

from typing import Any

from .config import Settings
from .strategies.registry import Profile


def hold(reason: str, **metadata: Any) -> dict[str, Any]:
    return {"action": "hold", "reason": reason, "size": 0.0, "risk_checks": [], "metadata": metadata}


def decide(payload: dict[str, Any], profile: Profile | None, settings: Settings) -> dict[str, Any]:
    """Fail closed. A bundle never generates orders until its implementation is validated."""
    if profile is None:
        return hold("configured strategy was not found")
    account = payload.get("account") or {}
    account_login = int(account.get("login") or 0)
    if settings.execution_enabled and account_login != settings.allowed_account_login:
        return hold("account login does not match the execution allowlist", strategy=profile.id)
    if not profile.enabled:
        return hold("strategy bundle is disabled", strategy=profile.id, version=profile.version)
    if not profile.runnable:
        return hold(
            "strategy implementation has not been imported and validated",
            strategy=profile.id, version=profile.version, implementation=profile.implementation,
        )
    # Reserved for the audited V3-compatible implementation. No inferred V7/V8 logic is executed.
    return hold("no validated entry signal", strategy=profile.id, version=profile.version)
