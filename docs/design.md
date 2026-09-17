# sa — design and plan

Implements `Synthetic Aperture Tilt-Shift` (ELEC 549). This file records the
decisions the project note left open and the build plan.

## Decisions

- **Pose backend: `pycolmap`**, not the `colmap` binary. The wheel bundles the
  whole sparse pipeline (SIFT, matching, mapper) and runs on CPU, so there is
  nothing to `brew install` and no text output to parse.
- **GUI: local web app.** `sa gui` starts FastAPI on localhost and opens one
  HTML page. The GUI calls the same stage functions as the CLI; state still
  lives in the project folder.
- **One shared camera, `SIMPLE_RADIAL`.** Frames are undistorted with the
  recovered `k` before warping, so the homography model is exact.
- **Transfer curve is per project.** sRGB by default; if ffprobe reports HLG
  (iPhone HDR video) the HLG curve is used instead so averaging is still done
  in linear light. Shooting with HDR off is still the better option.

- **COLMAP is re-tuned for small baselines.** A hand sweep subtends only a
  degree or two at the scene. With default thresholds (`init_min_tri_angle`
  16°, triangulation/filter angle 1.5°) the mapper finds no initial pair; see
  `pose._small_baseline_options`. Focal length is weakly constrained in this
  regime, so it is seeded at 0.75 × width (iPhone 1× video) rather than
  COLMAP's 1.2. An error in f barely affects renders of *picked* planes — the
  reconstruction stays self-consistent — but it does skew numeric tilt angles.
- **HDR:** the local ffmpeg has no `zscale`, so HLG is not tone-mapped.

## Conventions

COLMAP poses are world-to-camera: `X_cam = R X_world + t`.

The **reference frame** is the registered frame whose centre is nearest the
centroid of all camera centres (the middle of the sweep). The output image is
rendered from that viewpoint, and the plane lives in its camera coordinates:

    n · X_ref = d        n unit, n_z > 0, d > 0 (perpendicular distance)

For frame *i*, relative pose `R = R_i R_refᵀ`, `t = t_i − R t_ref`, so
`X_i = R X_ref + t`. For points on the plane `nᵀX_ref / d = 1`, hence

    H_i = K (R + t nᵀ / d) K⁻¹        maps ref pixels → frame-i pixels

This is the note's `K(R − t nᵀ/d)K⁻¹` with the opposite sign convention for
`t` (camera-motion vs. world-to-camera). The output is
`warpPerspective(frame_i, H_i, WARP_INVERSE_MAP)`.

COLMAP pixel coordinates put the first pixel's centre at (0.5, 0.5); OpenCV at
(0, 0). `geometry.pixel_homography` conjugates H accordingly, and also handles
rendering at reduced scale for previews.

**Numeric plane:** `tilt` (degrees off fronto-parallel), `azimuth` (direction
of the tilt; 0 = plane recedes toward the top of the image, like the ground),
`dist` (z-depth of the plane at the pivot pixel, default image centre).
`n = (sin τ sin φ, sin τ cos φ, cos τ)`, `d = n · (dist · ray_pivot)`.

**Aperture:** `--aperture a` (0–1] keeps only frames whose centre lies within
`a · D/2` of the reference centre, stopping the synthetic lens down.

## Modules

| Module | Does |
| --- | --- |
| `project.py` | project folder paths, JSON I/O, `run.json` log |
| `ingest.py` | ffprobe + ffmpeg → `frames/*.png`, `meta.json` |
| `pose.py` | pycolmap → `sparse/`, `poses.json` (K, k, per-frame R/t, ref, sparse points) |
| `geometry.py` | relative pose, plane homography, tilt↔normal, plane fit |
| `plane.py` | 3-pixel pick → nearest sparse points → plane; numeric plane; `plane.json` |
| `color.py` | sRGB / HLG ↔ linear LUTs |
| `render.py` | undistort → linearise → warp → float64 accumulate → encode; multi-plane in one pass; median; exposure-outlier rejection |
| `shiftadd.py` | M1: template-match a patch, translate, average |
| `synth.py` | synthetic scenes (dots; textured layered miniature) for tests and demo |
| `cli.py` | `sa ingest/pose/plane/render/shiftadd/gui/demo` |
| `gui/` | FastAPI app + `index.html` |

## Plan

1. `geometry`, `color`, `render` test-first against a synthetic dot scene that
   is rendered by point projection (independent of the homography formula):
   in-plane dots sharp; off-plane blur = `D f |1/z − 1/z₀|`; tilted plane sharp
   along the tilt; non-identity reference pose.
2. `shiftadd`, and the M3 check: shift-and-add ≈ computed fronto-parallel warp.
3. `project`, `ingest`, `pose`, `plane`, `cli`.
4. Slow end-to-end test: synthetic textured video → ingest → pose → pick →
   render; picked layer is sharper than the others.
5. GUI; drive it in a browser against the synthetic project.
