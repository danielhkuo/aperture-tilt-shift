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


# --- textured miniature: a ground plane seen from above, with upright "buildings" ---


def _noise(rng, h, w, octaves=(1, 2, 4, 16, 64, 256)) -> np.ndarray:
    out = np.zeros((h, w), np.float32)
    for o in octaves:
        small = rng.random((max(h // o, 2), max(w // o, 2))).astype(np.float32)
        out += cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)
    return out / len(octaves)


def _ground_texture(rng, w, h, metres_x) -> np.ndarray:
    px = w / metres_x  # pixels per metre
    n = _noise(rng, h, w)[..., None]
    tex = np.array([70, 120, 80], np.float32) * (0.4 + 1.2 * n)  # grass, BGR
    for x in np.arange(0.05, 0.95, 0.125) * w:  # roads with parked cars
        x0, x1 = int(x), int(x + 7 * px)
        tex[:, x0:x1] = 60 + 120 * n[:, x0:x1]
        for y in range(0, h, int(5.5 * px)):
            tex[y : y + int(1.5 * px), (x0 + x1) // 2 - 1 : (x0 + x1) // 2 + 2] = 230
            for lane in (x0 + int(0.6 * px), x1 - int(2.6 * px)):
                if rng.random() < 0.6:
                    tex[y + int(0.5 * px) : y + int(4.6 * px), lane : lane + int(2 * px)] = rng.uniform(30, 255, 3)
    for _ in range(500):  # trees
        c = (int(rng.uniform(0, w)), int(rng.uniform(0, h)))
        cv2.circle(tex, c, int(rng.uniform(0.8, 2.0) * px), (30, float(rng.uniform(60, 130)), 40), -1)
    tex[..., :3] *= (0.7 + 0.6 * _noise(rng, h, w, (1, 2, 4)))[..., None]
    return np.dstack([np.clip(tex, 0, 255), np.full((h, w), 255, np.float32)]).astype(np.uint8)


def _building_texture(rng, w_m, h_m, px=24) -> np.ndarray:
    w, h = int(w_m * px), int(h_m * px)
    tex = np.empty((h, w, 3), np.float32)
    tex[:] = rng.uniform(90, 230, 3)
    tex *= (0.6 + 0.8 * _noise(rng, h, w, (1, 2, 8, 32)))[..., None]
    step = int(3.0 * px)
    for y in range(step // 3, h - step // 2, step):
        for x in range(step // 3, w - step // 2, step):
            tex[y : y + step // 2, x : x + step // 2] = rng.uniform(20, 90) if rng.random() < 0.8 else 240
    return np.dstack([np.clip(tex, 0, 255), np.full((h, w), 255, np.float32)]).astype(np.uint8)


class MiniatureScene:
    """Camera ``height`` above flat ground, pitched ``pitch_deg`` down. All
    geometry is in reference-camera coordinates; surfaces are planar patches
    ``X = origin + a·e1 + b·e2`` painted far-to-near."""

    def __init__(self, rng=None, pitch_deg=35.0, height=25.0, buildings=16):
        rng = rng or np.random.default_rng(1)
        th = np.radians(pitch_deg)
        self.up = np.array([0, -np.cos(th), -np.sin(th)])
        self.fwd = np.array([0, -np.sin(th), np.cos(th)])
        self.right = np.array([1.0, 0, 0])
        self.ground = g.Plane(-self.up, height)
        self.focus_depth = height / np.sin(th)  # where the optical axis meets the ground
        foot = -self.up * height  # ground point under the camera
        self.surfaces = [dict(origin=foot, e1=self.right, e2=self.fwd, extent=(-70, 70, 10, 100),
                              texture=_ground_texture(rng, 4096, 2633, 140))]
        spots = sorted(((rng.uniform(-35, 35), rng.uniform(25, 85)) for _ in range(buildings)), key=lambda s: -s[1])
        for a, b in spots:
            w_m, h_m = rng.uniform(6, 12), rng.uniform(6, 22)
            self.surfaces.append(dict(origin=foot + a * self.right + b * self.fwd, e1=self.right, e2=self.up,
                                      extent=(-w_m / 2, w_m / 2, 0, h_m), texture=_building_texture(rng, w_m, h_m)))

    def render(self, poses: Poses, i: int) -> np.ndarray:
        R, t = g.relative_pose(poses.R[poses.ref], poses.t[poses.ref], poses.R[i], poses.t[i])
        size = (poses.width, poses.height)
        img = np.empty((poses.height, poses.width, 3), np.float32)
        img[:] = (235, 190, 150)  # sky
        to_index = np.array([[1, 0, -0.5], [0, 1, -0.5], [0, 0, 1.0]])
        for s in self.surfaces:
            a0, a1, b0, b1 = s["extent"]
            th, tw = s["texture"].shape[:2]
            A = np.array([[(a1 - a0) / tw, 0, a0 + 0.5 * (a1 - a0) / tw],
                          [0, -(b1 - b0) / th, b1 - 0.5 * (b1 - b0) / th],
                          [0, 0, 1]])
            M = np.c_[s["e1"], s["e2"], s["origin"]]
            H = to_index @ poses.K @ (R @ M + np.outer(t, [0, 0, 1])) @ A
            warped = cv2.warpPerspective(s["texture"], H, size, flags=cv2.INTER_LINEAR).astype(np.float32)
            alpha = warped[..., 3:] / 255
            img = img * (1 - alpha) + warped[..., :3] * alpha
        return img.astype(np.uint8)


def write_demo_video(path, width=1280, height=720, frames=60, diameter=3.0, log=print) -> tuple[MiniatureScene, Poses]:
    """Encode a synthetic handheld sweep over the miniature scene to ``path``."""
    import subprocess
    import tempfile
    from pathlib import Path

    rng = np.random.default_rng(2)
    scene = MiniatureScene()
    poses = make_poses(spiral_offsets(frames, diameter), width, height, f=width / 1.28, jitter_deg=0.7, rng=rng)
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(frames):
            cv2.imwrite(f"{tmp}/{i:04d}.png", scene.render(poses, i))
        log(f"encoding {frames} synthetic frames → {path}")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "30", "-i", f"{tmp}/%04d.png",
                        "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p", str(path)], check=True)
    return scene, poses
