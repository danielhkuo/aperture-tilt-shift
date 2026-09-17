"""Camera poses and intrinsics recovered by the pose stage (``poses.json``)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class Poses:
    """World-to-camera poses (``X_cam = R @ X_world + t``) sharing one camera.

    ``K`` uses COLMAP pixel coordinates (first pixel centre at 0.5, 0.5) at the
    full frame size ``width`` x ``height``. ``k`` is the SIMPLE_RADIAL term.
    """

    width: int
    height: int
    K: np.ndarray
    k: float
    names: list[str]
    R: np.ndarray  # (N, 3, 3)
    t: np.ndarray  # (N, 3)
    ref: int
    points: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))  # sparse cloud, world

    def centres(self) -> np.ndarray:
        return -np.einsum("nji,nj->ni", self.R, self.t)

    def points_in_ref(self) -> np.ndarray:
        return self.points @ self.R[self.ref].T + self.t[self.ref]

    def save(self, path: Path) -> None:
        data = {
            "width": self.width,
            "height": self.height,
            "K": self.K.tolist(),
            "k": self.k,
            "ref": self.names[self.ref],
            "frames": [
                {"name": n, "R": R.tolist(), "t": t.tolist()} for n, R, t in zip(self.names, self.R, self.t)
            ],
            "points": np.round(self.points, 6).tolist(),
        }
        Path(path).write_text(json.dumps(data))

    @classmethod
    def load(cls, path: Path) -> Poses:
        data = json.loads(Path(path).read_text())
        names = [f["name"] for f in data["frames"]]
        return cls(
            width=data["width"],
            height=data["height"],
            K=np.array(data["K"], float),
            k=float(data["k"]),
            names=names,
            R=np.array([f["R"] for f in data["frames"]], float),
            t=np.array([f["t"] for f in data["frames"]], float),
            ref=names.index(data["ref"]),
            points=np.array(data["points"], float).reshape(-1, 3),
        )
