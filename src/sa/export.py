"""Write a self-contained scene bundle the browser can render on its own:
undistorted, downscaled JPEG frames plus one JSON with everything the WebGL
renderer needs (K, per-frame R/t, sparse points, sweep diameter)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import cv2
import numpy as np

from sa import geometry as g
from sa import plane as plane_mod
from sa import render
from sa.poses import Poses
from sa.project import Project


def export(project: Project, out: Path, width: int = 960, max_frames: int = 60, quality: int = 85,
           title: str | None = None, log=print) -> Path:
    poses = Poses.load(project.poses_path)
    scale = min(1.0, width / poses.width)
    idx = render.select_frames(project, poses, max_frames=max_frames, log=log)
    if poses.ref not in idx:  # the bundle is rendered from the reference view, so it must be there
        idx[int(np.argmin(np.abs(np.array(idx) - poses.ref)))] = poses.ref
        idx.sort()

    out = Path(out)
    shutil.rmtree(out, ignore_errors=True)
    (out / "frames").mkdir(parents=True)
    load = render.frame_loader(project, poses, scale)
    first = load(idx[0])
    h, w = first.shape[:2]
    undistort = render._undistorter(poses, (w, h), scale)
    for i in idx:
        cv2.imwrite(str(out / "frames" / f"{i:04d}.jpg"), undistort(load(i)), [cv2.IMWRITE_JPEG_QUALITY, quality])

    K = np.diag([scale, scale, 1.0]) @ poses.K
    uv, X = plane_mod.project_points(poses)
    if len(uv) > 4000:
        keep = np.random.default_rng(0).choice(len(uv), 4000, replace=False)
        uv, X = uv[keep], X[keep]
    depths = X[:, 2]
    scene = {
        "title": title or project.root.name,
        "width": w, "height": h, "K": K.tolist(), "transfer": project.transfer(),
        "ref": idx.index(poses.ref),
        "frames": [{"file": f"frames/{i:04d}.jpg", "R": poses.R[i].tolist(), "t": poses.t[i].tolist()} for i in idx],
        "D": g.sweep_diameter(poses.centres()[idx], poses.R[poses.ref]),
        "points": {"uv": np.round(uv * scale, 1).tolist(), "z": np.round(depths, 5).tolist()},
        "depths": np.percentile(depths, [2, 50, 98]).tolist() if len(depths) else [0.5, 1, 2],
        "plane": json.loads(project.plane_path.read_text()) if project.plane_path.exists() else None,
    }
    (out / "scene.json").write_text(json.dumps(scene))
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    log(f"{len(idx)} frames at {w}×{h} → {out} ({size / 1e6:.1f} MB)")
    return out
