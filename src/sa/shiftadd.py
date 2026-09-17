"""M1: shift-and-add. Lock onto one patch by template matching, translate, average.

No pose, no intrinsics — the floor the rest of the project is checked against.
"""

from __future__ import annotations

from typing import Callable

import cv2
import numpy as np

from sa import color


def _gray(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def _subpixel(score: np.ndarray, x: int, y: int) -> tuple[float, float]:
    def vertex(a, b, c):
        denom = a - 2 * b + c
        return 0.0 if abs(denom) < 1e-12 else 0.5 * (a - c) / denom

    dx = vertex(score[y, x - 1], score[y, x], score[y, x + 1]) if 0 < x < score.shape[1] - 1 else 0.0
    dy = vertex(score[y - 1, x], score[y, x], score[y + 1, x]) if 0 < y < score.shape[0] - 1 else 0.0
    return x + dx, y + dy


def locate(frame_gray: np.ndarray, template: np.ndarray, around: tuple[int, int], search: int):
    """Top-left of the best match for ``template`` within ``search`` px of ``around``."""
    th, tw = template.shape
    x0, y0 = max(around[0] - search, 0), max(around[1] - search, 0)
    x1 = min(around[0] + search + tw, frame_gray.shape[1])
    y1 = min(around[1] + search + th, frame_gray.shape[0])
    score = cv2.matchTemplate(frame_gray[y0:y1, x0:x1], template, cv2.TM_CCOEFF_NORMED)
    _, _, _, (mx, my) = cv2.minMaxLoc(score)
    sx, sy = _subpixel(score, mx, my)
    return x0 + sx, y0 + sy


def shift_and_add(
    load: Callable[[int], np.ndarray],
    count: int,
    *,
    ref: int,
    patch: tuple[int, int, int, int],
    search: int | None = None,
    transfer: str = "srgb",
    progress: Callable[[int, int], None] | None = None,
) -> np.ndarray:
    """Average ``count`` frames after translating each so ``patch`` (x, y, w, h in
    the reference frame) stays put. Whatever is at the patch's depth comes out sharp."""
    x, y, pw, ph = patch
    ref_img = load(ref)
    h, w = ref_img.shape[:2]
    template = _gray(ref_img)[y : y + ph, x : x + pw]
    search = search or w // 4
    lut = color.to_linear_lut(transfer)
    ones = np.ones((h, w), np.float32)
    acc, weight = np.zeros((h, w, 3)), np.zeros((h, w))
    for i in range(count):
        img = load(i)
        fx, fy = locate(_gray(img), template, (x, y), search)
        M = np.array([[1, 0, x - fx], [0, 1, y - fy]], float)
        acc += cv2.warpAffine(lut[img], M, (w, h), flags=cv2.INTER_LINEAR)
        weight += cv2.warpAffine(ones, M, (w, h), flags=cv2.INTER_LINEAR)
        if progress:
            progress(i + 1, count)
    return color.from_linear(acc / np.maximum(weight, 1e-6)[..., None], transfer)
