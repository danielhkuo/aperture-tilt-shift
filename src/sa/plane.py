"""Stage 3: choose the focus plane, by clicking scene points or by numbers."""

from __future__ import annotations

import json

import numpy as np

from sa import geometry as g
from sa.poses import Poses
from sa.project import Project


def project_points(poses: Poses) -> tuple[np.ndarray, np.ndarray]:
    """Sparse points visible in the reference frame: (pixels N×2, ref-frame XYZ N×3).

    Pixels ignore the (small) radial term: they are coordinates in the
    undistorted reference view, which is the image the renderer produces.
    """
    X = poses.points_in_ref()
    X = X[X[:, 2] > 1e-9]
    x = X @ poses.K.T
    uv = x[:, :2] / x[:, 2:]
    inside = (uv[:, 0] >= 0) & (uv[:, 0] < poses.width) & (uv[:, 1] >= 0) & (uv[:, 1] < poses.height)
    return uv[inside], X[inside]


def point_at(poses: Poses, pixel, k: int = 5, radius: float | None = None) -> np.ndarray:
    """3D point under ``pixel``: on its ray, at the median depth of the nearest sparse points."""
    uv, X = project_points(poses)
    radius = radius or 0.05 * poses.width
    dist = np.linalg.norm(uv - np.asarray(pixel, float), axis=1)
    near = np.argsort(dist)[:k]
    near = near[dist[near] <= radius]
    if len(near) == 0:
        raise ValueError(f"no reconstructed points near pixel {tuple(pixel)} — click on something textured")
    return g.pixel_ray(poses.K, pixel) * float(np.median(X[near, 2]))


def plane_from_pixels(poses: Poses, pixels) -> g.Plane:
    """Plane through the scene points under ≥ 3 clicked pixels of the reference frame."""
    return g.fit_plane(np.array([point_at(poses, p) for p in pixels]))


def save(project: Project, poses: Poses, plane: g.Plane, source: dict) -> None:
    tilt, azimuth, dist = g.tilt_from_plane(poses.K, plane)
    data = {"n": plane.n.tolist(), "d": plane.d, "ref": poses.names[poses.ref],
            "tilt": tilt, "azimuth": azimuth, "dist": dist, "source": source}
    project.plane_path.write_text(json.dumps(data, indent=2))
    project.log_run("plane", **data)


def load(project: Project) -> g.Plane:
    data = json.loads(project.plane_path.read_text())
    return g.Plane(np.array(data["n"], float), float(data["d"]))


def pick_interactively(project: Project, poses: Poses) -> list[tuple[float, float]]:
    """OpenCV window on the reference frame: click ≥ 3 points, Enter to accept."""
    import cv2

    img = cv2.imread(str(project.frames_dir / poses.names[poses.ref]))
    scale = min(1.0, 1600 / img.shape[1])
    view = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    for u, v in project_points(poses)[0]:
        cv2.circle(view, (int(u * scale), int(v * scale)), 2, (0, 255, 0), -1)
    clicks: list[tuple[float, float]] = []

    def on_mouse(event, x, y, *_):
        if event == cv2.EVENT_LBUTTONDOWN:
            clicks.append(((x + 0.5) / scale, (y + 0.5) / scale))
            cv2.circle(view, (x, y), 8, (0, 0, 255), 2)

    title = "click 3+ points on the focus plane - Enter accepts, Esc cancels"
    cv2.namedWindow(title)
    cv2.setMouseCallback(title, on_mouse)
    while True:
        cv2.imshow(title, view)
        key = cv2.waitKey(30) & 0xFF
        if key in (13, 10) and len(clicks) >= 3:
            break
        if key == 27:
            clicks.clear()
            break
    cv2.destroyAllWindows()
    return clicks
