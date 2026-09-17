"""Plane-induced homographies. Conventions are documented in docs/design.md."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Plane:
    """``n @ X = d`` in reference-camera coordinates; ``n`` unit, ``d`` > 0."""

    n: np.ndarray
    d: float


def relative_pose(R_ref, t_ref, R_i, t_i):
    """(R, t) with ``X_i = R @ X_ref + t`` from two world-to-camera poses."""
    R = R_i @ R_ref.T
    return R, t_i - R @ t_ref


def plane_homography(K, R, t, plane: Plane) -> np.ndarray:
    """Maps reference pixels to frame pixels for points on ``plane``."""
    return K @ (R + np.outer(t, plane.n) / plane.d) @ np.linalg.inv(K)


def pixel_homography(H: np.ndarray, scale: float) -> np.ndarray:
    """Re-express a COLMAP-coordinate homography in OpenCV pixel indices of
    images resized by ``scale`` (index ``u`` ↔ COLMAP ``(u + 0.5) / scale``)."""
    T = np.array([[1 / scale, 0, 0.5 / scale], [0, 1 / scale, 0.5 / scale], [0, 0, 1]])
    return np.linalg.inv(T) @ H @ T


def pixel_ray(K, pixel) -> np.ndarray:
    """Direction through a COLMAP pixel, normalised to z = 1."""
    return np.linalg.inv(K) @ np.array([pixel[0], pixel[1], 1.0])


def _centre(K):
    return (K[0, 2], K[1, 2])


def plane_from_tilt(K, tilt: float, azimuth: float, dist: float, pivot=None) -> Plane:
    """Plane ``tilt`` degrees off fronto-parallel, at z-depth ``dist`` where the
    ray through ``pivot`` (default: principal point) meets it. Azimuth 0 makes
    the plane recede toward the top of the image, as the ground does."""
    tau, phi = np.radians(tilt), np.radians(azimuth)
    n = np.array([np.sin(tau) * np.sin(phi), np.sin(tau) * np.cos(phi), np.cos(tau)])
    d = float(n @ (dist * pixel_ray(K, pivot or _centre(K))))
    if d <= 0:
        raise ValueError("plane does not pass in front of the camera at the pivot")
    return Plane(n, d)


def tilt_from_plane(K, plane: Plane, pivot=None) -> tuple[float, float, float]:
    """Inverse of :func:`plane_from_tilt`: (tilt, azimuth, dist)."""
    n = plane.n
    tilt = np.degrees(np.arccos(np.clip(n[2], -1, 1)))
    azimuth = np.degrees(np.arctan2(n[0], n[1])) % 360 if tilt > 1e-9 else 0.0
    dist = plane.d / (n @ pixel_ray(K, pivot or _centre(K)))
    return float(tilt), float(azimuth), float(dist)


def fit_plane(points: np.ndarray) -> Plane:
    """Least-squares plane through ≥ 3 reference-frame points."""
    points = np.asarray(points, float)
    if len(points) < 3:
        raise ValueError("need at least 3 points")
    centroid = points.mean(axis=0)
    _, s, vt = np.linalg.svd(points - centroid)
    if s[1] < 1e-6 * s[0]:
        raise ValueError("points are collinear")
    n = vt[2]
    d = float(n @ centroid)
    if d < 0:
        n, d = -n, -d
    return Plane(n, d)


def in_plane_offsets(centres: np.ndarray, R_ref: np.ndarray, centre_ref: np.ndarray) -> np.ndarray:
    """Camera centres relative to the reference, projected onto its image plane."""
    return (centres - centre_ref) @ R_ref[:2].T


def sweep_diameter(centres: np.ndarray, R_ref: np.ndarray) -> float:
    """Aperture diameter D: largest camera separation perpendicular to the view."""
    p = centres @ R_ref[:2].T
    return float(np.sqrt(((p[:, None] - p[None]) ** 2).sum(-1)).max())
