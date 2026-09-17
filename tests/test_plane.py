import dataclasses

import numpy as np
import pytest

from sa import geometry as g
from sa import plane


@pytest.fixture
def cloud(ring, rng):
    """Poses plus a sparse cloud lying on a known tilted plane."""
    truth = g.plane_from_tilt(ring.K, tilt=40, azimuth=30, dist=3.0)
    px = rng.uniform([20, 20], [620, 460], size=(400, 2))
    rays = np.linalg.inv(ring.K) @ np.c_[px, np.ones(400)].T
    X_ref = (rays * (truth.d / (truth.n @ rays))).T
    world = (X_ref - ring.t[ring.ref]) @ ring.R[ring.ref]
    return dataclasses.replace(ring, points=world), truth


def test_three_clicks_recover_the_plane(cloud):
    poses, truth = cloud
    got = plane.plane_from_pixels(poses, [(100, 100), (540, 120), (320, 420)])
    assert np.degrees(np.arccos(got.n @ truth.n)) < 2
    assert got.d == pytest.approx(truth.d, rel=0.03)


def test_click_far_from_any_point_is_an_error(cloud):
    poses, _ = cloud
    sparse = dataclasses.replace(poses, points=poses.points[:1])
    with pytest.raises(ValueError, match="no reconstructed points"):
        plane.point_at(sparse, (5, 5), radius=3)


def test_poses_round_trip(tmp_path, cloud):
    from sa.poses import Poses

    poses, _ = cloud
    poses.save(tmp_path / "poses.json")
    back = Poses.load(tmp_path / "poses.json")
    assert back.ref == poses.ref and back.names == poses.names
    assert np.allclose(back.R, poses.R) and np.allclose(back.t, poses.t)
    assert np.allclose(back.points, poses.points, atol=1e-5)
