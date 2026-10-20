"""Owns every piece of on-disk evidence a run produces: screenshots and traces."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

try:  # Allure is the reporter; guard the import so helpers stay usable without it.
    import allure
except ImportError:  # pragma: no cover
    allure = None


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "item"


class Artifacts:
    def __init__(self, root: Path) -> None:
        self.screenshots_dir = root / "screenshots"
        self.traces_dir = root / "traces"
        self._sequence = 0
        # Start every session from a clean slate so a report never mixes in old evidence.
        for directory in (self.screenshots_dir, self.traces_dir):
            shutil.rmtree(directory, ignore_errors=True)
            directory.mkdir(parents=True, exist_ok=True)

    def screenshot(self, page, name: str, full_page: bool = False) -> Path:
        self._sequence += 1
        path = self.screenshots_dir / f"{self._sequence:02d}-{_slug(name)}.png"
        page.screenshot(path=str(path), full_page=full_page)
        if allure:
            allure.attach.file(str(path), name=name, attachment_type=allure.attachment_type.PNG)
        return path

    def trace_path(self, name: str) -> Path:
        return self.traces_dir / f"{_slug(name)}.zip"
