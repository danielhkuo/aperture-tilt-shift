# sa — synthetic aperture tilt-shift

Turn a handheld phone video into one photo focused on an arbitrary, possibly
tilted, plane. The blur is real parallax: frames are warped by the homography
the chosen plane induces, `H = K (R + t nᵀ/d) K⁻¹`, and averaged in linear light.

Needs `ffmpeg` (`brew install ffmpeg`) and [uv](https://docs.astral.sh/uv/).
COLMAP comes from the `pycolmap` wheel; nothing else to install.

## GUI

```bash
uv run sa gui
```

Choose a video → **Extract** → **Solve** → click the image to focus (or click
three points to lay the plane through them), drag tilt / azimuth / distance /
aperture with a live preview → **Save plane** → **Render** or **Sweep**.
Green dots are reconstructed points predicted to be in focus (< 2 px blur);
hover any dot for its depth and predicted blur `D·f·|1/z − 1/z₀|`.

No footage yet:

```bash
uv run sa demo demo && uv run sa ingest demo/video.mp4 --project demo --every 1 && uv run sa pose demo && uv run sa gui demo
```

## CLI

```
sa ingest  street.MOV --every 8              # → street/frames/*.png
sa pose    street/                           # → poses.json (K, R, t, sparse cloud)
sa plane   street/ --pick                    # click 3+ points   (or --points u,v u,v u,v)
sa plane   street/ --tilt 40 --dist 12       # numeric: reaches planes with nothing to click
sa render  street/ --out street.png
sa render  street/ --tilt 0:60:10 --out sweep   # 7 renders + strip.png, one pass over the frames
sa shiftadd street/ --patch 1800,900,200,200    # M1: template-matched shift-and-add, no pose
```

`render` options: `--aperture 0.5` (stop down: use the inner half of the sweep),
`--scale 0.5`, `--median` (drops moving subjects), `--pivot u,v`,
`--keep-outliers` (exposure-outlier frames are dropped by default).
Every stage appends its parameters to `run.json`.

## Tests

```bash
uv run pytest
```

Geometry and rendering are tested against dots rendered by point projection
(independent of the homography code): blur diameter matches
`D·f·|1/z − 1/z₀|` to 6 %, tilted planes come out sharp, shift-and-add agrees
with the pose-derived warp (M3). `test_pipeline.py` runs video → COLMAP →
render on a synthetic scene. Conventions and decisions: [docs/design.md](docs/design.md).

## Capture notes

Lock focus and exposure, 1× lens, HDR video off, Enhanced Stabilization off
(stabilisation crops move the principal point frame to frame). Spiral out from
the centre over 10–20 s; translate, don't pan.
