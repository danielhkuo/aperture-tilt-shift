<p align="center">
  <img src="assets/logo.svg" width="96" alt="">
</p>

<h1 align="center">Synthetic Aperture Tilt-Shift</h1>

<p align="center">
  A handheld phone video becomes a lens the size of your arm span.<br>
  Choose the focus plane, tilted any way you like, after the shot.
</p>

<p align="center">
  <a href="https://aperture-tilt-shift.vercel.app"><b>Live demo</b></a> ·
  <a href="docs/report.pdf">Write-up</a>
</p>

![Before and after: a plain video frame of the O'Connor lobby, and the same scene rendered with the focus plane laid along the upper floor](assets/hero.jpg)

A real lens averages the views from every point across its aperture. Objects
on the focus plane agree in all of those views and stay sharp; everything
else disagrees and blurs. A phone aperture is a few millimetres wide, so
nothing blurs. If you instead move the phone across a disc while it records
video, each frame is one view from one point of a much larger aperture, and
averaging the aligned frames gives the photograph that lens would have taken.

The alignment is what chooses the focus. Two views of any plane are related
by a homography that depends only on the camera motion, the intrinsics and the
plane itself:

```
H = K (R + t nᵀ / d) K⁻¹
```

Nothing in it requires the plane to be visible or textured. Pick a normal and
a distance, warp every frame, average, and that plane is sharp. Tilt it, and
the sharp band cuts diagonally through the scene, which is the one thing a
phone lens can never do. The blur is real parallax, not a filter: a point at
depth *z* smears over `D · f · |1/z − 1/z₀|` pixels, the circle-of-confusion
formula with the sweep diameter standing in for the aperture.

![The Commons dining hall from one video, rendered with two different focus planes](assets/commons.jpg)

## Using it

You need [ffmpeg](https://ffmpeg.org) and [uv](https://docs.astral.sh/uv/).
COLMAP is bundled in the `pycolmap` wheel; there is nothing else to install.

```
brew install ffmpeg uv
uvx --from git+https://github.com/danielhkuo/aperture-tilt-shift sa gui
```

That opens the GUI in your browser. Choose a video, extract frames, solve the
camera poses, then click where you want focus and drag the tilt slider. A
low-resolution preview updates in about a tenth of a second; a full 4K render
takes a few seconds.

The same page is hosted at [aperture-tilt-shift.vercel.app](https://aperture-tilt-shift.vercel.app).
Without the helper running it shows pre-solved scenes, rendered in WebGL on
your own GPU. With the helper running on your Mac, the hosted page drives it
and processes your own footage.

Each stage is also a command:

```
sa ingest  clip.MOV --every 5              # video → frames/
sa pose    clip/                           # COLMAP → poses.json
sa plane   clip/ --tilt 30 --dist 300      # or --pick to click three points
sa render  clip/ --aperture 0.8            # warp + average → renders/
sa render  clip/ --tilt 0:60:10            # a sweep, one pass over the frames
sa export  clip/ --out web/scenes/clip     # bundle for the browser renderer
```

## Shooting

- 4K, 1× lens, focus and exposure locked, HDR video off.
- Keep the phone pointed at the same spot and *move* it: spiral outward from
  the centre over 10–20 seconds, as wide as you can reach. The path you trace
  is the aperture shape.
- The scene needs depth. Looking down from a height at things two, five and
  fifteen metres away works; a wall seen head-on does not blur at all.
- Static subjects. Anyone who walks through the shot averages into a ghost.

## How it is built

`src/sa` is a small Python package: `ingest` (ffmpeg), `pose` (pycolmap,
retuned for the tiny baselines of a hand sweep), `plane`, `render` (linear
light, float accumulation, per-pixel weights), and a FastAPI GUI. `sa export`
writes a scene bundle that `web/` renders in a WebGL shader, which is what the
hosted demo uses. The geometry is tested against synthetic scenes with known
poses; see [docs/design.md](docs/design.md) for conventions and
[docs/report.pdf](docs/report.pdf) for the write-up.

```
uv run pytest
```

Built for ELEC 549 at Rice University. The synthetic-aperture idea follows
Marc Levoy's SynthCam; camera poses come from
[COLMAP](https://colmap.github.io).
