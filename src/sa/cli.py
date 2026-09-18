"""``sa`` — one command per pipeline stage; state lives in the project folder."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np


def _pair(text: str) -> tuple[float, float]:
    u, v = (float(x) for x in text.split(","))
    return u, v


def _tilts(text: str) -> list[float]:
    """``40`` or ``0:60:10`` (inclusive)."""
    if ":" not in text:
        return [float(text)]
    start, stop, step = (float(x) for x in text.split(":"))
    return list(np.arange(start, stop + step / 2, step))


def _load(root):
    from sa.poses import Poses
    from sa.project import Project

    project = Project(root)
    if not project.poses_path.exists():
        sys.exit(f"{project.poses_path} not found — run: sa pose {root}")
    return project, Poses.load(project.poses_path)


def cmd_ingest(a):
    from sa.ingest import ingest

    ingest(a.video, a.project, every=a.every)


def cmd_pose(a):
    from sa.pose import pose
    from sa.project import Project

    pose(Project(a.project), matcher=a.matcher, max_image_size=a.max_image_size, focal_factor=a.focal_factor)


def cmd_plane(a):
    from sa import geometry as g
    from sa import plane

    project, poses = _load(a.project)
    if a.pick or a.points:
        pixels = a.points or plane.pick_interactively(project, poses)
        if len(pixels) < 3:
            sys.exit("need 3 or more points")
        chosen, source = plane.plane_from_pixels(poses, pixels), {"pixels": [list(p) for p in pixels]}
    elif a.dist is not None:
        chosen = g.plane_from_tilt(poses.K, a.tilt, a.azimuth, a.dist, a.pivot)
        source = {"tilt": a.tilt, "azimuth": a.azimuth, "dist": a.dist, "pivot": a.pivot}
    else:
        sys.exit("give --pick, --points, or --dist (with optional --tilt/--azimuth)")
    plane.save(project, poses, chosen, source)
    tilt, azimuth, dist = g.tilt_from_plane(poses.K, chosen)
    print(f"plane: tilt {tilt:.1f}°, azimuth {azimuth:.1f}°, depth at centre {dist:.4g} → {project.plane_path}")


def cmd_render(a):
    from sa import geometry as g
    from sa import plane, render

    project, poses = _load(a.project)
    if a.dist is None and not project.plane_path.exists():
        sys.exit("no plane: run sa plane, or pass --dist")
    if project.plane_path.exists():
        base_tilt, base_az, base_dist = g.tilt_from_plane(poses.K, plane.load(project), a.pivot)
    else:
        base_tilt, base_az, base_dist = 0.0, 0.0, a.dist
    azimuth = base_az if a.azimuth is None else a.azimuth
    dist = base_dist if a.dist is None else a.dist
    tilts = _tilts(a.tilt) if a.tilt else [base_tilt]
    if a.tilt is None and a.dist is None and a.azimuth is None:
        planes = [plane.load(project)]
    else:
        planes = [g.plane_from_tilt(poses.K, t, azimuth, dist, a.pivot) for t in tilts]

    out = Path(a.out) if a.out else None
    if out and not out.is_absolute() and out.parts[0] not in (".", ".."):
        out = project.renders_dir / out
    if len(planes) > 1:
        folder = out or project.renders_dir / "sweep"
        outputs = [folder / f"tilt_{t:04.1f}.png" for t in tilts]
    else:
        t, az, d = g.tilt_from_plane(poses.K, planes[0])
        outputs = [out or project.renders_dir / f"tilt{t:.0f}_az{az:.0f}_d{d:.3g}.png"]

    render.render_project(project, poses, planes, outputs, scale=a.scale, aperture=a.aperture, median=a.median,
                          max_frames=a.max_frames, keep_outliers=a.keep_outliers)
    if len(planes) > 1:
        render.contact_strip(outputs, [f"{t:g} deg" for t in tilts], outputs[0].parent / "strip.png")
        print(f"→ {outputs[0].parent / 'strip.png'}")


def cmd_shiftadd(a):
    import cv2

    from sa import shiftadd
    from sa.project import Project

    project = Project(a.project)
    frames = project.frame_paths()
    if not frames:
        sys.exit(f"no frames in {project.frames_dir} — run sa ingest")
    ref = len(frames) // 2 if a.ref is None else a.ref
    x, y, w, h = (int(v) for v in a.patch.split(","))
    step = max(len(frames) // 10, 1)
    img = shiftadd.shift_and_add(
        lambda i: cv2.imread(str(frames[i])), len(frames), ref=ref, patch=(x, y, w, h), transfer=project.transfer(),
        progress=lambda j, n: print(f"  {j}/{n}") if j % step == 0 else None,
    )
    out = project.renders_dir / (a.out or "shiftadd.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), img)
    project.log_run("shiftadd", out=str(out), patch=[x, y, w, h], ref=frames[ref].name, frames=len(frames))
    print(f"→ {out}")


def cmd_demo(a):
    from sa import synth

    path = Path(a.project) / "video.mp4"
    synth.write_demo_video(path)
    print(f"next: sa ingest {path} --project {a.project} --every 1 && sa pose {a.project} && sa gui {a.project}")


def cmd_export(a):
    from sa.export import export
    from sa.project import Project

    project = Project(a.project)
    if not project.poses_path.exists():
        sys.exit(f"{project.poses_path} not found — run: sa pose {a.project}")
    export(project, a.out, width=a.width, max_frames=a.max_frames, title=a.title)


def cmd_gui(a):
    from sa.gui.server import serve

    serve(a.project, port=a.port, open_browser=not a.no_browser, extra_origins=a.allow_origin)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="sa", description="Synthetic-aperture tilt-shift from a handheld video.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("ingest", help="video → frames")
    s.add_argument("video")
    s.add_argument("--project", help="project folder (default: ./<video name>)")
    s.add_argument("--every", type=int, default=8, help="keep every Nth frame")
    s.set_defaults(fn=cmd_ingest)

    s = sub.add_parser("pose", help="frames → poses.json (COLMAP sparse)")
    s.add_argument("project")
    s.add_argument("--matcher", choices=["auto", "exhaustive", "sequential"], default="auto")
    s.add_argument("--max-image-size", type=int, default=2000, help="feature-extraction size cap, px")
    s.add_argument("--focal-factor", type=float, default=0.75, help="initial focal length / image width")
    s.set_defaults(fn=cmd_pose)

    s = sub.add_parser("plane", help="choose the focus plane → plane.json")
    s.add_argument("project")
    s.add_argument("--pick", action="store_true", help="click 3+ points in a window")
    s.add_argument("--points", nargs="+", type=_pair, metavar="U,V", help="3+ reference-frame pixels")
    s.add_argument("--tilt", type=float, default=0.0, help="degrees off fronto-parallel")
    s.add_argument("--azimuth", type=float, default=0.0, help="tilt direction; 0 recedes toward image top")
    s.add_argument("--dist", type=float, help="depth at the pivot, COLMAP units")
    s.add_argument("--pivot", type=_pair, metavar="U,V", help="pixel the tilt pivots about (default: centre)")
    s.set_defaults(fn=cmd_plane)

    s = sub.add_parser("render", help="warp + average → image(s)")
    s.add_argument("project")
    s.add_argument("--out", help="file (or folder for a sweep), relative to renders/")
    s.add_argument("--tilt", help="override tilt: 40, or a sweep 0:60:10")
    s.add_argument("--azimuth", type=float)
    s.add_argument("--dist", type=float)
    s.add_argument("--pivot", type=_pair, metavar="U,V")
    s.add_argument("--aperture", type=float, default=1.0, help="fraction of the sweep diameter to use (0–1]")
    s.add_argument("--scale", type=float, default=1.0, help="output scale, e.g. 0.5 for a quick look")
    s.add_argument("--median", action="store_true", help="median instead of mean: drops moving subjects")
    s.add_argument("--max-frames", type=int)
    s.add_argument("--keep-outliers", action="store_true", help="keep exposure-outlier frames")
    s.set_defaults(fn=cmd_render)

    s = sub.add_parser("shiftadd", help="M1: align on one patch by template matching, no pose")
    s.add_argument("project")
    s.add_argument("--patch", required=True, metavar="X,Y,W,H", help="patch in the reference frame")
    s.add_argument("--ref", type=int, help="reference frame index (default: middle)")
    s.add_argument("--out")
    s.set_defaults(fn=cmd_shiftadd)

    s = sub.add_parser("demo", help="write a synthetic capture to try the pipeline on")
    s.add_argument("project", nargs="?", default="demo")
    s.set_defaults(fn=cmd_demo)

    s = sub.add_parser("export", help="scene bundle for the in-browser (WebGL) renderer")
    s.add_argument("project")
    s.add_argument("--out", required=True, help="bundle folder, e.g. web/scenes/street")
    s.add_argument("--width", type=int, default=960)
    s.add_argument("--max-frames", type=int, default=60)
    s.add_argument("--title")
    s.set_defaults(fn=cmd_export)

    s = sub.add_parser("gui", help="open the browser GUI")
    s.add_argument("project", nargs="?", help="project folder or video")
    s.add_argument("--port", type=int, default=8549)
    s.add_argument("--no-browser", action="store_true")
    s.add_argument("--allow-origin", action="append", default=[], help="extra web origin allowed to drive this helper")
    s.set_defaults(fn=cmd_gui)

    a = p.parse_args(argv)
    try:
        a.fn(a)
    except (RuntimeError, ValueError, FileNotFoundError, MemoryError) as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
