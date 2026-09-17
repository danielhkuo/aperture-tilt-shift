"""Synthetic captures with known geometry, for tests and ``sa demo``."""

from __future__ import annotations

import cv2
import numpy as np

from sa import geometry as g
from sa.poses import Poses


def _rot(rvec) -> np.ndarray:
    return cv2.Rodrigues(np.asarray(rvec, float))[0]


def make_poses(offsets: np.ndarray, width, height, f, jitter_deg=0.0, rng=None, ref=0) -> Poses:
    """Cameras at ``offsets`` (N×2, in the reference image plane) all looking
    roughly the same way, expressed in an arbitrary world frame so nothing can
    rely on the reference pose being the identity."""
    rng = rng or np.random.default_rng(0)
    n = len(offsets)
    K = np.array([[f, 0, width / 2], [0, f, height / 2], [0, 0, 1.0]])
    R_w = _rot([0.3, -0.5, 0.2])  # world → reference-aligned frame
    t_w = np.array([0.7, -1.1, 2.3])
    R, t = [], []
    for i, (ox, oy) in enumerate(offsets):
        R_c = np.eye(3) if i == ref else _rot(np.radians(jitter_deg) * rng.normal(size=3))
        centre = np.array([ox, oy, 0.0])
        R.append(R_c @ R_w)  # X_cam = R_c (R_w X + t_w − centre)
        t.append(R_c @ (t_w - centre))
    return Poses(width, height, K, 0.0, [f"{i + 1:04d}.png" for i in range(n)], np.array(R), np.array(t), ref)


def ring_poses(n, diameter, width, height, f, jitter_deg=0.0, rng=None) -> Poses:
    """``n`` cameras on a rim of ``diameter`` plus a reference at its centre (index ``n``)."""
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    offsets = np.vstack([np.c_[np.cos(a), np.sin(a)] * diameter / 2, [[0, 0]]])
    return make_poses(offsets, width, height, f, jitter_deg, rng, ref=n)


def spiral_offsets(n, diameter, loops=3.5) -> np.ndarray:
    """Centre-out spiral that fills the disc evenly (radius ∝ √time)."""
    s = np.linspace(0, 1, n)
    r, a = np.sqrt(s) * diameter / 2, 2 * np.pi * loops * s
    return np.c_[r * np.cos(a), r * np.sin(a)]


def render_dots(world: np.ndarray, poses: Poses, i: int, sigma: float = 1.2) -> np.ndarray:
    """Gaussian dots at the projections of ``world`` points — by point
    projection, so it does not share the homography code it is used to test."""
    img = np.zeros((poses.height, poses.width), np.float32)
    X = world @ poses.R[i].T + poses.t[i]
    x = X @ poses.K.T
    uv = x[:, :2] / x[:, 2:] - 0.5  # COLMAP → array index
    r = int(np.ceil(4 * sigma))
    for u, v in uv:
        cx, cy = int(round(u)), int(round(v))
        if not (r <= cx < poses.width - r and r <= cy < poses.height - r):
            continue
        ys, xs = np.mgrid[cy - r : cy + r + 1, cx - r : cx + r + 1]
        img[cy - r : cy + r + 1, cx - r : cx + r + 1] += np.exp(-((xs - u) ** 2 + (ys - v) ** 2) / (2 * sigma**2))
    return np.repeat((np.clip(img, 0, 1) * 255).astype(np.uint8)[..., None], 3, axis=2)
