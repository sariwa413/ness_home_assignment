"""Loader for the external, data-driven test inputs."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from src.config import ROOT

SCENARIOS_FILE = ROOT / "data" / "scenarios.json"


def load_scenarios() -> List[Dict[str, Any]]:
    """Read the scenario list from ``data/scenarios.json``."""
    return json.loads(SCENARIOS_FILE.read_text(encoding="utf-8"))["scenarios"]
