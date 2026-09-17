"""Warp every frame onto the focus plane and average — the synthetic aperture."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterator, Sequence

import cv2
import numpy as np

from sa import color
from sa import geometry as g
from sa.poses import Poses

Loader = Callable[[int], np.ndarray]  # frame index → uint8 H×W×3, any uniform scale
MEDIAN_BYTES_LIMIT = 12e9


def _undistorter(poses: Poses, size: tuple[int, int], scale: float):
    if abs(poses.k) < 1e-7:
        return lambda img: img
    K = np.diag([scale, scale, 1.0]) @ poses.K
    K[:2, 2] -= 0.5  # COLMAP → OpenCV pixel centres
    maps = cv2.initUndistortRectifyMap(K, np.array([poses.k, 0, 0, 0.0]), None, K, size, cv2.CV_32FC1)
    return lambda img: cv2.remap(img, *maps, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def _prefetch(fn, items: Sequence, workers: int = 6) -> Iterator:
    """Ordered ``map`` on threads that never holds more than ``workers`` results."""
    with ThreadPoolExecutor(workers) as pool:
        pending = []
        for item in items:
            pending.append(pool.submit(fn, item))
            if len(pending) >= workers:
                yield pending.pop(0).result()
        for fut in pending:
            yield fut.result()


def homographies(poses: Poses, plane: g.Plane, indices: Sequence[int], scale: float) -> list[np.ndarray]:
    R_ref, t_ref = poses.R[poses.ref], poses.t[poses.ref]
    out = []
    for i in indices:
        R, t = g.relative_pose(R_ref, t_ref, poses.R[i], poses.t[i])
        out.append(g.pixel_homography(g.plane_homography(poses.K, R, t, plane), scale))
    return out


def render_planes(
    load: Loader,
    poses: Poses,
    planes: Sequence[g.Plane],
    *,
    indices: Sequence[int] | None = None,
    transfer: str = "srgb",
    median: bool = False,
    progress: Callable[[int, int], None] | None = None,
) -> list[np.ndarray]:
    """One image per plane, all from a single pass over the frames.

    Frames may be loaded at any uniform scale of the posed size; the output
    matches the loaded size, which is what makes low-res previews cheap.
    """
    indices = list(range(len(poses.names))) if indices is None else list(indices)
    if not indices:
        raise ValueError("no frames selected")
    first = load(indices[0])
    h, w = first.shape[:2]
    scale = w / poses.width
    undistort = _undistorter(poses, (w, h), scale)
    Hs = [homographies(poses, p, indices, scale) for p in planes]
    warp = dict(dsize=(w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)

    if median:
        if len(indices) * len(planes) * h * w * 3 > MEDIAN_BYTES_LIMIT:
            raise MemoryError("median needs every warped frame in memory; use fewer frames or a smaller scale")
        stacks = [np.empty((len(indices), h, w, 3), np.uint8) for _ in planes]
        for j, img in enumerate(_prefetch(lambda i: undistort(load(i)), indices)):
            for stack, H in zip(stacks, Hs):
                cv2.warpPerspective(img, H[j], dst=stack[j], borderMode=cv2.BORDER_REPLICATE, **warp)
            if progress:
                progress(j + 1, len(indices))
        out = []
        for stack in stacks:
            img = np.empty((h, w, 3), np.uint8)
            for y in range(0, h, 64):  # strips bound np.median's temporaries
                img[y : y + 64] = np.median(stack[:, y : y + 64], axis=0)
            out.append(img)
        return out

    lut = color.to_linear_lut(transfer)
    ones = np.full((h, w), 1.0, np.float32)
    acc = [np.zeros((h, w, 3), np.float64) for _ in planes]
    weight = [np.zeros((h, w), np.float64) for _ in planes]
    for j, lin in enumerate(_prefetch(lambda i: lut[undistort(load(i))], indices)):
        for a, wt, H in zip(acc, weight, Hs):
            a += cv2.warpPerspective(lin, H[j], **warp)
            wt += cv2.warpPerspective(ones, H[j], **warp)
        if progress:
            progress(j + 1, len(indices))
    return [color.from_linear(a / np.maximum(wt, 1e-6)[..., None], transfer) for a, wt in zip(acc, weight)]


# --- project level ---


def exposure_outliers(project, names: Sequence[str], threshold: float = 4.0) -> set[str]:
    """Frames whose mean brightness is a robust outlier (auto-exposure drift → banding)."""
    import json

    cache_path = project.root / "exposure.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    missing = [n for n in names if n not in cache]
    if missing:
        means = _prefetch(
            lambda n: float(cv2.imread(str(project.frames_dir / n), cv2.IMREAD_REDUCED_GRAYSCALE_8).mean()), missing
        )
        cache.update(zip(missing, means))
        cache_path.write_text(json.dumps(cache))
    v = np.array([cache[n] for n in names])
    mad = np.median(np.abs(v - np.median(v)))
    sigma = max(1.4826 * mad, 0.5)  # floor: never reject on sub-code-value wobble
    return {n for n, x in zip(names, v) if abs(x - np.median(v)) > threshold * sigma}


def select_frames(project, poses: Poses, *, aperture: float = 1.0, max_frames: int | None = None,
                  keep_outliers: bool = False, log=print) -> list[int]:
    idx = list(range(len(poses.names)))
    centres = poses.centres()
    if aperture < 1.0:
        off = g.in_plane_offsets(centres, poses.R[poses.ref], centres[poses.ref])
        radius = aperture * g.sweep_diameter(centres, poses.R[poses.ref]) / 2
        idx = [i for i in idx if np.linalg.norm(off[i]) <= radius]
    if not keep_outliers:
        bad = exposure_outliers(project, [poses.names[i] for i in idx])
        if bad:
            log(f"dropping {len(bad)} exposure outliers: {', '.join(sorted(bad))}")
            idx = [i for i in idx if poses.names[i] not in bad or i == poses.ref]
    if max_frames and len(idx) > max_frames:
        idx = [idx[j] for j in np.linspace(0, len(idx) - 1, max_frames).round().astype(int)]
    return idx


def frame_loader(project, poses: Poses, scale: float = 1.0) -> Loader:
    def load(i: int) -> np.ndarray:
        img = cv2.imread(str(project.frames_dir / poses.names[i]), cv2.IMREAD_COLOR)
        if img is None:
            raise FileNotFoundError(project.frames_dir / poses.names[i])
        if scale != 1.0:
            size = (round(img.shape[1] * scale), round(img.shape[0] * scale))
            img = cv2.resize(img, size, interpolation=cv2.INTER_AREA)
        return img

    return load


def render_project(project, poses: Poses, planes: Sequence[g.Plane], outputs: Sequence, *, scale: float = 1.0,
                   aperture: float = 1.0, median: bool = False, max_frames: int | None = None,
                   keep_outliers: bool = False, log=print) -> None:
    """Render ``planes`` to ``outputs`` and record every parameter in run.json."""
    idx = select_frames(project, poses, aperture=aperture, max_frames=max_frames, keep_outliers=keep_outliers, log=log)
    log(f"rendering {len(planes)} plane(s) from {len(idx)} frames at scale {scale:g}")
    step = max(len(idx) // 10, 1)
    images = render_planes(
        frame_loader(project, poses, scale), poses, planes, indices=idx, transfer=project.transfer(), median=median,
        progress=lambda j, n: log(f"  {j}/{n}") if j % step == 0 or j == n else None,
    )
    centres = poses.centres()[idx]
    for plane, img, out in zip(planes, images, outputs):
        out.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out), img)
        tilt, azimuth, dist = g.tilt_from_plane(poses.K, plane)
        project.log_run("render", out=str(out), n=plane.n.tolist(), d=plane.d, tilt=tilt, azimuth=azimuth, dist=dist,
                        frames=len(idx), sweep_diameter=g.sweep_diameter(centres, poses.R[poses.ref]),
                        focal_px=float(poses.K[0, 0]), aperture=aperture, scale=scale, median=median,
                        transfer=project.transfer(), ref=poses.names[poses.ref])
        log(f"→ {out}")


def contact_strip(paths: Sequence, labels: Sequence[str], out, panel_width: int = 640) -> None:
    """Side-by-side strip of renders — the tilt-sweep figure."""
    panels = []
    for path, label in zip(paths, labels):
        img = cv2.imread(str(path))
        img = cv2.resize(img, (panel_width, round(img.shape[0] * panel_width / img.shape[1])), interpolation=cv2.INTER_AREA)
        cv2.putText(img, label, (16, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 5, cv2.LINE_AA)
        cv2.putText(img, label, (16, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)
        panels.append(img)
    cv2.imwrite(str(out), np.hstack(panels))
