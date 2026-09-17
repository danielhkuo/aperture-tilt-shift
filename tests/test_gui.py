"""GUI API against a hand-built project (no COLMAP): dots on a known tilted plane."""

import dataclasses

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from sa import geometry as g
from sa import synth
from sa.gui.server import create_app
from sa.project import Project


@pytest.fixture
def client(tmp_path, ring, rng):
    truth = g.plane_from_tilt(ring.K, tilt=40, azimuth=0, dist=3.0)
    px = rng.uniform([30, 30], [610, 450], size=(300, 2))
    rays = np.linalg.inv(ring.K) @ np.c_[px, np.ones(300)].T
    X_ref = (rays * (truth.d / (truth.n @ rays))).T
    world = (X_ref - ring.t[ring.ref]) @ ring.R[ring.ref]
    poses = dataclasses.replace(ring, points=world)

    project = Project(tmp_path)
    project.frames_dir.mkdir()
    for i, name in enumerate(poses.names):
        cv2.imwrite(str(project.frames_dir / name), synth.render_dots(world, poses, i))
    poses.save(project.poses_path)
    return TestClient(create_app(str(tmp_path)))


def decode(response):
    assert response.status_code == 200, response.text
    return cv2.imdecode(np.frombuffer(response.content, np.uint8), cv2.IMREAD_COLOR)


def test_state_reports_the_project(client):
    s = client.get("/api/state").json()
    assert s["frames"] == 25 and s["poses"]["registered"] == 25
    assert s["poses"]["D"] == pytest.approx(0.2, rel=1e-3)
    assert s["plane"] is None


def test_three_clicks_then_save_then_state(client):
    body = {"pixels": [[100, 100], [540, 120], [320, 420]], "save": False}
    found = client.post("/api/plane", json=body).json()
    assert found["tilt"] == pytest.approx(40, abs=2)
    assert client.get("/api/state").json()["plane"] is None  # save: False is only a query

    client.post("/api/plane", json={"tilt": found["tilt"], "azimuth": found["azimuth"], "dist": found["dist"]})
    assert client.get("/api/state").json()["plane"]["tilt"] == pytest.approx(found["tilt"])


def test_click_to_focus_returns_depth(client):
    assert client.post("/api/depth", json={"pivot": [320, 240]}).json()["dist"] == pytest.approx(3.0, rel=0.05)


def test_preview_is_sharp_on_the_true_plane_only(client):
    on = decode(client.get("/api/preview.jpg", params={"tilt": 40, "azimuth": 0, "dist": 3.0}))
    off = decode(client.get("/api/preview.jpg", params={"tilt": 0, "azimuth": 0, "dist": 3.0}))
    assert on.shape == (480, 640, 3)
    assert on.max() > 200
    assert np.sort(off[:100].ravel())[-50:].mean() < 0.5 * np.sort(on[:100].ravel())[-50:].mean()


def test_bad_requests(client):
    assert client.post("/api/plane", json={"pixels": [[1, 1], [2, 2]]}).status_code == 422
    assert client.post("/api/run", json={"stage": "render"}).status_code == 400  # no plane saved yet
    assert client.get("/api/render/../poses.json").status_code == 404
