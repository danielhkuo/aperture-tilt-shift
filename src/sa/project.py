"""The project folder: every stage reads what the last one left on disk."""

from __future__ import annotations

import json
import time
from pathlib import Path

VIDEO_SUFFIXES = {".mov", ".mp4", ".m4v"}


class Project:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.frames_dir = self.root / "frames"
        self.sparse_dir = self.root / "sparse"
        self.renders_dir = self.root / "renders"
        self.meta_path = self.root / "meta.json"
        self.poses_path = self.root / "poses.json"
        self.plane_path = self.root / "plane.json"
        self.run_path = self.root / "run.json"

    def frame_paths(self) -> list[Path]:
        return sorted(self.frames_dir.glob("*.png"))

    def video(self) -> Path | None:
        return next((p for p in sorted(self.root.glob("video.*")) if p.suffix.lower() in VIDEO_SUFFIXES), None)

    def meta(self) -> dict:
        return json.loads(self.meta_path.read_text()) if self.meta_path.exists() else {}

    def transfer(self) -> str:
        return self.meta().get("transfer", "srgb")

    def log_run(self, stage: str, **params) -> None:
        """Append to run.json so any output can be traced to its settings."""
        runs = json.loads(self.run_path.read_text()) if self.run_path.exists() else []
        runs.append({"stage": stage, "time": time.strftime("%Y-%m-%dT%H:%M:%S"), **params})
        self.run_path.write_text(json.dumps(runs, indent=2))
