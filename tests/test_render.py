import numpy as np
import pytest

from sa import geometry as g
from sa import render, shiftadd, synth


def ring_radius(img, centre, window):
    """Intensity-weighted mean distance from `centre` (x, y in array index coords)."""
    cx, cy = centre
    x0, y0 = int(round(cx)) - window, int(round(cy)) - window
    patch = img[y0 : y0 + 2 * window + 1, x0 : x0 + 2 * window + 1, 0].astype(float)
    ys, xs = np.mgrid[y0 : y0 + 2 * window + 1, x0 : x0 + 2 * window + 1]
    return (patch * np.hypot(xs - cx, ys - cy)).sum() / patch.sum()


def dots_at(ring, pixels, depths):
    """World points that project to `pixels` (COLMAP coords) in the ref view at `depths`."""
    rays = np.linalg.inv(ring.K) @ np.c_[pixels, np.ones(len(pixels))].T
    X_ref = (rays * (np.asarray(depths) / rays[2])).T
    return (X_ref - ring.t[ring.ref]) @ ring.R[ring.ref]


def test_blur_matches_circle_of_confusion(ring):
    z0, D, f = 2.0, 0.2, 500.0
    pixels = np.array([[160.5, 120.5], [480.5, 120.5], [160.5, 360.5], [480.5, 360.5]])
    depths = [2.0, 3.0, 4.0, 1.5]
    world = dots_at(ring, pixels, depths)
    frames = [synth.render_dots(world, ring, i) for i in range(len(ring.names))]
    rim = [i for i in range(len(ring.names)) if i != ring.ref]

    plane = g.plane_from_tilt(ring.K, 0, 0, z0)
    (img,) = render.render_planes(lambda i: frames[i], ring, [plane], indices=rim, transfer="linear")

    for px, z in zip(pixels, depths):
        predicted = D * f * abs(1 / z - 1 / z0)
        measured = 2 * ring_radius(img, px - 0.5, window=int(predicted / 2) + 8)
        if predicted == 0:
            assert measured < 4  # just the dot itself
        else:
            assert measured == pytest.approx(predicted, rel=0.06)


def test_tilted_plane_is_sharp_where_fronto_parallel_is_not(ring):
    plane = g.plane_from_tilt(ring.K, tilt=50, azimuth=0, dist=2.0)
    pixels = np.array([[320.5, 60.5], [320.5, 240.5], [320.5, 420.5], [100.5, 100.5]])
    rays = np.linalg.inv(ring.K) @ np.c_[pixels, np.ones(4)].T
    depths = plane.d / (plane.n @ rays) * rays[2]
    assert depths[0] > depths[1] > depths[2]  # recedes toward the top, like ground
    world = dots_at(ring, pixels, depths)
    frames = [synth.render_dots(world, ring, i) for i in range(len(ring.names))]
    load = lambda i: frames[i]

    flat = g.plane_from_tilt(ring.K, 0, 0, 2.0)
    tilted, fronto = render.render_planes(load, ring, [plane, flat], transfer="linear")
    single = frames[ring.ref]

    def peak(img, px):
        x, y = np.round(px - 0.5).astype(int)
        return img[y - 3 : y + 4, x - 3 : x + 4].max()

    for px in pixels:
        assert peak(tilted, px) > 0.8 * peak(single, px)
    assert peak(fronto, pixels[1]) > 0.8 * peak(single, pixels[1])  # the pivot
    assert peak(fronto, pixels[0]) < 0.3 * peak(single, pixels[0])
    assert peak(fronto, pixels[2]) < 0.3 * peak(single, pixels[2])


def test_preview_scale_matches_full_render(ring):
    import cv2

    world = dots_at(ring, np.array([[200.5, 200.5], [400.5, 300.5]]), [2.0, 3.0])
    frames = [synth.render_dots(world, ring, i, sigma=3.0) for i in range(len(ring.names))]
    small = [cv2.resize(f, (320, 240), interpolation=cv2.INTER_AREA) for f in frames]
    plane = g.plane_from_tilt(ring.K, 0, 0, 2.0)
    (full,) = render.render_planes(lambda i: frames[i], ring, [plane], transfer="linear")
    (half,) = render.render_planes(lambda i: small[i], ring, [plane], transfer="linear")
    assert half.shape == (240, 320, 3)
    expected = cv2.resize(full, (320, 240), interpolation=cv2.INTER_AREA)

    def centroid(img):  # of the in-focus dot at full-res (200, 200)
        ys, xs = np.mgrid[80:120, 80:120]
        p = img[80:120, 80:120, 0].astype(float)
        return np.array([(p * xs).sum(), (p * ys).sum()]) / p.sum()

    # a half-pixel convention slip would show up as a 0.25 px offset here
    assert np.abs(centroid(half) - centroid(expected)).max() < 0.05
    assert np.abs(half.astype(int) - expected.astype(int)).max() <= 15  # only interpolation softening


def test_average_is_taken_in_linear_light():
    import dataclasses

    poses = synth.ring_poses(n=1, diameter=0.0, width=32, height=32, f=30.0)
    poses = dataclasses.replace(
        poses, names=["a", "b"], R=np.stack([poses.R[0]] * 2), t=np.stack([poses.t[0]] * 2), ref=0
    )
    frames = [np.zeros((32, 32, 3), np.uint8), np.full((32, 32, 3), 255, np.uint8)]
    plane = g.plane_from_tilt(poses.K, 0, 0, 1.0)
    (img,) = render.render_planes(lambda i: frames[i], poses, [plane], transfer="srgb")
    assert img[16, 16, 0] == pytest.approx(188, abs=1)  # not 128


def test_borders_are_not_darkened(ring):
    frames = [np.full((480, 640, 3), 200, np.uint8)] * len(ring.names)
    plane = g.plane_from_tilt(ring.K, 0, 0, 0.5)  # near plane → large shifts
    (img,) = render.render_planes(lambda i: frames[i], ring, [plane], transfer="srgb")
    assert img.min() >= 199


def test_median_drops_a_transient(ring):
    frames = [np.full((480, 640, 3), 100, np.uint8) for _ in ring.names]
    frames[3] = frames[3].copy()
    frames[3][200:280, 300:380] = 255  # a car in one frame
    plane = g.plane_from_tilt(ring.K, 0, 0, 1e6)
    load = lambda i: frames[i]
    (mean,) = render.render_planes(load, ring, [plane], transfer="linear")
    (med,) = render.render_planes(load, ring, [plane], transfer="linear", median=True)
    assert mean[240, 340, 0] > 103
    assert med[240, 340, 0] == 100


def test_shift_and_add_matches_computed_warp(rng):
    """M3: feature alignment and the pose-derived warp agree for a fronto-parallel plane."""
    poses = synth.ring_poses(n=16, diameter=0.2, width=640, height=480, f=500.0, jitter_deg=0, rng=rng)
    px = rng.uniform([60, 60], [580, 420], size=(40, 2))
    depths = rng.uniform(1.5, 6.0, size=40)
    # a cluster of dots at z = 2 to lock on to
    patch_px = np.array([[300.5, 220.5], [330.5, 250.5], [310.5, 262.5], [342.5, 226.5]])
    px, depths = np.vstack([px, patch_px]), np.r_[depths, [2.0] * 4]
    world = dots_at(poses, px, depths)
    frames = [synth.render_dots(world, poses, i) for i in range(len(poses.names))]

    plane = g.plane_from_tilt(poses.K, 0, 0, 2.0)
    (warped,) = render.render_planes(lambda i: frames[i], poses, [plane], transfer="linear")
    added = shiftadd.shift_and_add(
        lambda i: frames[i], len(frames), ref=poses.ref, patch=(285, 205, 75, 75), transfer="linear"
    )
    inner = np.s_[60:-60, 60:-60]
    diff = np.abs(warped[inner].astype(int) - added[inner].astype(int))
    assert diff.mean() < 1.0
    assert added[220, 300, 0] > 150  # the locked patch stayed sharp
