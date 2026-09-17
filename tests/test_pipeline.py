"""End to end on a synthetic capture: video → frames → COLMAP → plane → render."""

import json

import cv2
import numpy as np
import pytest

from sa import cli, synth
from sa import geometry as g
from sa.poses import Poses
from sa.project import Project


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    root = tmp_path_factory.mktemp("demo")
    scene, truth = synth.write_demo_video(root / "video.mp4", width=640, height=360, frames=30, log=lambda *_: None)
    cli.main(["ingest", str(root / "video.mp4"), "--project", str(root), "--every", "1"])
    cli.main(["pose", str(root)])
    return Project(root), scene, truth


def sharpness(img, box):
    """Laplacian energy above the pixel scale, where a single frame's texture aliasing lives."""
    x0, y0, x1, y1 = box
    gray = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (0, 0), 1.5)
    return cv2.Laplacian(gray[y0:y1, x0:x1], cv2.CV_64F).var()


def test_pose_recovers_the_camera(demo):
    project, _, truth = demo
    poses = Poses.load(project.poses_path)
    assert len(poses.names) >= 27
    assert poses.K[0, 0] == pytest.approx(truth.K[0, 0], rel=0.05)
    assert abs(poses.k) < 0.02
    # sweep diameter over scene depth is scale-free, so it must match the truth
    depth = np.median(poses.points_in_ref()[:, 2])
    ratio = g.sweep_diameter(poses.centres(), poses.R[poses.ref]) / depth
    assert ratio == pytest.approx(3.0 / 38, rel=0.25)


def test_clicking_the_ground_finds_the_ground_plane(demo):
    project, scene, _ = demo
    # three road/grass pixels in the 640×360 reference view
    cli.main(["plane", str(project.root), "--points", "325,325", "575,150", "450,60"])
    plane = json.loads(project.plane_path.read_text())
    assert plane["tilt"] == pytest.approx(55, abs=3)
    assert plane["azimuth"] == pytest.approx(0, abs=5) or plane["azimuth"] == pytest.approx(360, abs=5)


def test_tilted_render_keeps_the_whole_ground_sharp(demo):
    project, _, _ = demo
    cli.main(["plane", str(project.root), "--points", "325,325", "575,150", "450,60"])
    cli.main(["render", str(project.root), "--out", "ground.png"])
    cli.main(["render", str(project.root), "--tilt", "0", "--out", "fronto.png"])
    ground = cv2.imread(str(project.renders_dir / "ground.png"))
    fronto = cv2.imread(str(project.renders_dir / "fronto.png"))
    still = cv2.imread(str(project.frames_dir / Poses.load(project.poses_path).names[0]))
    far, near = (420, 10, 620, 70), (300, 290, 500, 350)  # ground only, top and bottom of frame
    for box in (far, near):
        assert sharpness(ground, box) > 0.5 * sharpness(still, box)
        assert sharpness(fronto, box) < 0.3 * sharpness(still, box)

    runs = json.loads(project.run_path.read_text())
    last = runs[-1]
    assert last["stage"] == "render" and last["frames"] >= 27 and last["sweep_diameter"] > 0


def test_tilt_sweep_writes_a_strip(demo):
    project, _, _ = demo
    cli.main(["render", str(project.root), "--tilt", "0:60:30", "--scale", "0.5", "--out", "sweep"])
    names = sorted(p.name for p in (project.renders_dir / "sweep").iterdir())
    assert names == ["strip.png", "tilt_00.0.png", "tilt_30.0.png", "tilt_60.0.png"]
