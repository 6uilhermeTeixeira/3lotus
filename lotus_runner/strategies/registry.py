from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    version: str
    enabled: bool
    implementation: str
    parameters: dict[str, Any]
    sha256: str
    aliases: tuple[str, ...] = ()

    @property
    def runnable(self) -> bool:
        return self.enabled and self.implementation in {"builtin.zigzag-v7-shadow", "builtin.zigzag-v2-demo", "builtin.zigzag-v2-faithful"}


def _digest(payload: dict[str, Any]) -> str:
    unsigned = dict(payload)
    unsigned.pop("sha256", None)
    source = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(source).hexdigest()


def load_profiles(directory: Path) -> dict[str, Profile]:
    profiles: dict[str, Profile] = {}
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        expected = str(payload.get("sha256", ""))
        actual = _digest(payload)
        if expected != actual:
            raise ValueError(f"strategy bundle integrity check failed: {path.name}")
        profile = Profile(
            id=str(payload["id"]), name=str(payload["name"]), version=str(payload["version"]),
            enabled=bool(payload.get("enabled", False)), implementation=str(payload.get("implementation", "")),
            parameters=dict(payload.get("parameters", {})), sha256=actual,
            aliases=tuple(str(alias) for alias in payload.get("aliases", [])),
        )
        if profile.id in profiles:
            raise ValueError(f"duplicate strategy id: {profile.id}")
        profiles[profile.id] = profile
        for alias in profile.aliases:
            if alias in profiles:
                raise ValueError(f"duplicate strategy alias: {alias}")
            profiles[alias] = profile
    return profiles
