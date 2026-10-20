"""Typed configuration loaded from a YAML profile and overridable by environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILE = ROOT / "config" / "config.yaml"

# Load .env before anything reads the environment, so a developer can set any override
# below in one file instead of exporting it per shell. Real environment variables take
# precedence, which keeps CI and one-off `$env:ENV="local"` runs in charge.
# utf-8-sig because PowerShell's Set-Content writes a BOM, which would otherwise be
# glued onto the first key and silently drop that one variable.
load_dotenv(ROOT / ".env", override=False, encoding="utf-8-sig")


def _to_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


@dataclass(frozen=True)
class AuthConfig:
    mode: str
    username: str
    password: str


@dataclass(frozen=True)
class Config:
    profile: str
    base_url: str
    cart_url: str
    browser: str
    headless: bool
    locale: str
    user_agent: str
    timeout_ms: int
    slow_mo_ms: int
    navigation_retries: int
    random_seed: Optional[int]
    artifacts_dir: Path
    auth: AuthConfig

    @classmethod
    def load(cls, profile: Optional[str] = None) -> "Config":
        profile = profile or os.getenv("ENV", "default")
        profiles: Dict[str, Any] = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
        if profile not in profiles:
            raise ValueError(f"Unknown profile '{profile}'. Available: {sorted(profiles)}")

        data = profiles[profile]
        auth = data.get("auth", {})
        artifacts_dir = Path(os.getenv("ARTIFACTS_DIR", data["artifacts_dir"]))

        return cls(
            profile=profile,
            base_url=os.getenv("BASE_URL", data["base_url"]).rstrip("/"),
            cart_url=os.getenv("CART_URL", data["cart_url"]).rstrip("/"),
            browser=os.getenv("BROWSER", data["browser"]),
            headless=_to_bool(os.getenv("HEADLESS", data["headless"])),
            locale=os.getenv("LOCALE", data["locale"]),
            user_agent=os.getenv("USER_AGENT", data["user_agent"]),
            timeout_ms=int(os.getenv("TIMEOUT_MS", data["timeout_ms"])),
            slow_mo_ms=int(os.getenv("SLOW_MO_MS", data["slow_mo_ms"])),
            navigation_retries=int(os.getenv("NAVIGATION_RETRIES", data["navigation_retries"])),
            random_seed=int(os.getenv("RANDOM_SEED", data["random_seed"])),
            artifacts_dir=artifacts_dir if artifacts_dir.is_absolute() else ROOT / artifacts_dir,
            auth=AuthConfig(
                mode=os.getenv("AUTH_MODE", auth.get("mode", "guest")),
                username=os.getenv("EBAY_USERNAME", auth.get("username", "")),
                password=os.getenv("EBAY_PASSWORD", auth.get("password", "")),
            ),
        )
