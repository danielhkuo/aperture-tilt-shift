"""Stage 2: frames → camera poses, intrinsics and a sparse cloud (pycolmap, CPU)."""

from __future__ import annotations

import shutil
from typing import Callable

import numpy as np

from sa import geometry as g
from sa.poses import Poses
from sa.project import Project

MAX_POINTS = 10_000
EXHAUSTIVE_LIMIT = 100  # frames; beyond this, match sequentially


def _small_baseline_options():
    """COLMAP's defaults expect photos taken metres apart. A hand sweep subtends
    a degree or two at the scene, so its angle gates must come down or the
    mapper finds no initial pair and throws away every triangulated point."""
    import pycolmap

    o = pycolmap.IncrementalPipelineOptions()
    o.multiple_models = False
    o.mapper.init_min_tri_angle = 2.0  # COLMAP halves this again if it has to
    o.mapper.filter_min_tri_angle = 0.2
    o.mapper.ba_local_min_tri_angle = 1.0
    o.triangulation.min_angle = 0.2
    return o


def pose(project: Project, matcher: str = "auto", max_image_size: int = 2000, focal_factor: float = 0.75,
         log: Callable[[str], None] = print) -> Poses:
    """``focal_factor`` × image width seeds the focal length (0.75 ≈ iPhone 1× video);
    bundle adjustment refines it, but a small sweep constrains it only weakly."""
    import pycolmap

    frames = project.frame_paths()
    if len(frames) < 3:
        raise RuntimeError("need frames first: sa ingest")
    shutil.rmtree(project.sparse_dir, ignore_errors=True)
    project.sparse_dir.mkdir()
    db = project.sparse_dir / "database.db"

    log(f"extracting features from {len(frames)} frames…")
    reader = pycolmap.ImageReaderOptions()
    reader.camera_model = "SIMPLE_RADIAL"
    reader.default_focal_length_factor = focal_factor
    extraction = pycolmap.FeatureExtractionOptions()
    extraction.max_image_size = max_image_size
    pycolmap.extract_features(db, project.frames_dir, camera_mode=pycolmap.CameraMode.SINGLE,
                              reader_options=reader, extraction_options=extraction)

    if matcher == "auto":
        matcher = "exhaustive" if len(frames) <= EXHAUSTIVE_LIMIT else "sequential"
    log(f"matching ({matcher})…")
    if matcher == "exhaustive":
        pycolmap.match_exhaustive(db)
    else:
        pairing = pycolmap.SequentialPairingOptions()
        pairing.overlap = 15
        pycolmap.match_sequential(db, pairing_options=pairing)

    log("mapping…")
    models = pycolmap.incremental_mapping(db, project.frames_dir, project.sparse_dir, _small_baseline_options())
    if not models:
        raise RuntimeError("COLMAP could not reconstruct the scene — more texture, more frames, or a wider sweep")
    rec = max(models.values(), key=lambda r: r.num_reg_images())

    images = sorted((im for im in rec.images.values() if im.has_pose), key=lambda im: im.name)
    cam = images[0].camera
    f, cx, cy, k = cam.params
    R = np.array([im.cam_from_world().rotation.matrix() for im in images])
    t = np.array([im.cam_from_world().translation for im in images])
    centres = -np.einsum("nji,nj->ni", R, t)
    ref = int(np.argmin(np.linalg.norm(centres - centres.mean(axis=0), axis=1)))
    points = np.array([p.xyz for p in rec.points3D.values() if p.track.length() >= 3 and p.error < 2.0])
    if len(points) > MAX_POINTS:  # plenty for plane picking; keeps poses.json and the GUI light
        points = points[np.random.default_rng(0).choice(len(points), MAX_POINTS, replace=False)]

    poses = Poses(cam.width, cam.height, np.array([[f, 0, cx], [0, f, cy], [0, 0, 1.0]]), float(k),
                  [im.name for im in images], R, t, ref, points.reshape(-1, 3))
    poses.save(project.poses_path)

    error = rec.compute_mean_reprojection_error()
    D = g.sweep_diameter(centres, R[ref])
    depth = float(np.median(poses.points_in_ref()[:, 2])) if len(points) else float("nan")
    project.log_run("pose", matcher=matcher, focal_factor=focal_factor, registered=len(images), frames=len(frames), focal_px=float(f),
                    radial_k=float(k), reprojection_error_px=error, sweep_diameter=D, ref=poses.names[ref])
    log(f"registered {len(images)}/{len(frames)} frames, {len(points)} points, "
        f"reprojection error {error:.2f} px")
    log(f"f = {f:.0f} px, k = {k:+.4f}, sweep D = {D:.3g} units, median scene depth = {depth:.3g} units, "
        f"reference frame {poses.names[ref]}")
    if len(images) < 0.8 * len(frames):
        log("warning: many frames failed to register; expect a smaller effective aperture")
    return poses
