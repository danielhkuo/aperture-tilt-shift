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
