import numpy as np
import pytest

from sa import geometry as g


def test_tilt_zero_is_fronto_parallel():
    K = np.array([[500, 0, 320], [0, 500, 240], [0, 0, 1.0]])
    p = g.plane_from_tilt(K, tilt=0, azimuth=0, dist=3.0)
    assert np.allclose(p.n, [0, 0, 1])
    assert p.d == pytest.approx(3.0)


def test_tilt_pivots_about_the_image_centre():
    K = np.array([[500, 0, 320], [0, 500, 240], [0, 0, 1.0]])
    p = g.plane_from_tilt(K, tilt=40, azimuth=0, dist=3.0)
    # the point 3 units down the optical axis stays on the plane
    assert p.n @ np.array([0, 0, 3.0]) == pytest.approx(p.d)
    # azimuth 0 tilts like the ground: normal leans toward +y (image down)
    assert p.n[1] > 0 and p.n[0] == pytest.approx(0)
    assert np.degrees(np.arccos(p.n[2])) == pytest.approx(40)


def test_tilt_round_trip_with_pivot():
    K = np.array([[500, 0, 320], [0, 500, 240], [0, 0, 1.0]])
    p = g.plane_from_tilt(K, tilt=25, azimuth=70, dist=4.0, pivot=(100, 400))
    tilt, az, dist = g.tilt_from_plane(K, p, pivot=(100, 400))
    assert (tilt, az, dist) == pytest.approx((25, 70, 4.0))


def test_fit_plane_three_points_and_orientation():
    pts = np.array([[0, 0, 2.0], [1, 0, 2.0], [0, 1, 3.0]])
    p = g.fit_plane(pts)
    assert np.allclose(pts @ p.n, p.d)
    assert p.n[2] > 0 and p.d > 0
    assert np.linalg.norm(p.n) == pytest.approx(1)


def test_fit_plane_rejects_collinear():
    with pytest.raises(ValueError):
        g.fit_plane(np.array([[0, 0, 1.0], [1, 1, 2.0], [2, 2, 3.0]]))


def test_homography_maps_plane_points_between_views(ring):
    K, ref = ring.K, ring.ref
    plane = g.plane_from_tilt(K, tilt=35, azimuth=20, dist=2.5)
    # 3D points on the plane, in ref camera coordinates
    rays = np.linalg.inv(K) @ np.array([[100, 80, 1], [500, 400, 1], [320, 240, 1.0]]).T
    X_ref = (rays * (plane.d / (plane.n @ rays))).T
    for i in (0, 7, 19):
        R, t = g.relative_pose(ring.R[ref], ring.t[ref], ring.R[i], ring.t[i])
        H = g.plane_homography(K, R, t, plane)
        x_ref = (K @ X_ref.T).T
        x_i = (K @ (X_ref @ R.T + t).T).T
        mapped = (H @ x_ref.T).T
        assert np.allclose(mapped[:, :2] / mapped[:, 2:], x_i[:, :2] / x_i[:, 2:], atol=1e-9)


def test_pixel_homography_identity_at_any_scale():
    assert np.allclose(g.pixel_homography(np.eye(3), 0.25), np.eye(3))


def test_sweep_diameter(ring):
    assert g.sweep_diameter(ring.centres(), ring.R[ring.ref]) == pytest.approx(0.2, rel=1e-6)
