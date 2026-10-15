"""Loader for the external, data-driven test inputs."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from src.config import ROOT

DATA_DIR = ROOT / "data"


def load_scenarios(dataset: Optional[str] = None) -> List[Dict[str, Any]]:
    """Read the scenario list of the active dataset (``DATASET`` env var, default ``smoke``)."""
    dataset = dataset or os.getenv("DATASET", "smoke")
    path = DATA_DIR / f"{dataset}.json"
    if not path.exists():
        raise FileNotFoundError(f"Unknown dataset '{dataset}'. Available: {[p.stem for p in DATA_DIR.glob('*.json')]}")
    return json.loads(path.read_text(encoding="utf-8"))["scenarios"]
