"""Browser GUI. Long stages run as ``sa`` subprocesses (same code path as the
CLI, cancellable, and COLMAP's native logging is captured); only the low-res
live preview renders in-process."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from sa import geometry as g
from sa import plane as plane_mod
from sa import render
from sa.poses import Poses
from sa.project import VIDEO_SUFFIXES, Project

PREVIEW_WIDTH = 960
PREVIEW_FRAMES = 64
OVERLAY_POINTS = 4000
_GLOG = re.compile(r"^[IWE]\d{8} ")


class Job:
    def __init__(self, name: str, argv: list[str]):
        self.name, self.lines, self.returncode = name, [f"$ sa {' '.join(argv)}"], None
        self.proc = subprocess.Popen([sys.executable, "-m", "sa", *argv], stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, env={**os.environ, "PYTHONUNBUFFERED": "1"})
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for line in self.proc.stdout:
            for part in line.rstrip().split("\r"):
                if _GLOG.match(part):  # COLMAP chatter: keep only the mapper's heartbeat
                    if "Registering image" in part:
                        self.lines.append("  " + part.split("] ", 1)[-1])
                elif part.strip():
                    self.lines.append(part)
        self.returncode = self.proc.wait()
        self.lines.append("done" if self.returncode == 0 else f"failed (exit {self.returncode})")

    @property
    def running(self) -> bool:
        return self.returncode is None


class State:
    def __init__(self):
        self.project: Project | None = None
        self.video: Path | None = None
        self.job: Job | None = None
        self._poses: tuple[float, Poses] | None = None
        self._frames: tuple[float, dict[int, np.ndarray]] | None = None
        self.loading = [0, 0]
        self.lock = threading.Lock()

    def open(self, path: Path):
        path = path.expanduser().resolve()
        if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES:
            inside = path.parent if path.stem == "video" else path.parent / path.stem
            self.project, self.video = Project(inside), path
        elif path.is_dir():
            self.project = Project(path)
            self.video = self.project.video()
        else:
            raise HTTPException(400, f"not a video or a project folder: {path}")
        self._poses = self._frames = None

    def need_project(self) -> Project:
        if not self.project:
            raise HTTPException(400, "open a video or project first")
        return self.project

    def poses(self) -> Poses:
        project = self.need_project()
        if not project.poses_path.exists():
            raise HTTPException(400, "run the pose stage first")
        mtime = project.poses_path.stat().st_mtime
        if not self._poses or self._poses[0] != mtime:
            self._poses = (mtime, Poses.load(project.poses_path))
        return self._poses[1]

    def preview_frames(self) -> dict[int, np.ndarray]:
        """Every posed frame at preview size, decoded once and kept in memory."""
        project, poses = self.need_project(), self.poses()
        mtime = project.poses_path.stat().st_mtime
        with self.lock:
            if not self._frames or self._frames[0] != mtime:
                load = render.frame_loader(project, poses, min(1.0, PREVIEW_WIDTH / poses.width))
                self.loading = [0, len(poses.names)]
                frames = {}
                for i, img in enumerate(render._prefetch(load, range(len(poses.names)))):
                    frames[i] = img
                    self.loading[0] = i + 1
                self._frames = (mtime, frames)
            return self._frames[1]


class OpenBody(BaseModel):
    path: str


class RunBody(BaseModel):
    stage: str
    every: int = 8
    scale: float = 1.0
    aperture: float = 1.0
    median: bool = False
    sweep: list[float] | None = None  # [start, stop, step]
    name: str | None = None


class PlaneBody(BaseModel):
    tilt: float = 0.0
    azimuth: float = 0.0
    dist: float | None = None
    pivot: tuple[float, float] | None = None
    pixels: list[tuple[float, float]] | None = None
    save: bool = True


def _jpeg(img: np.ndarray, quality: int = 88) -> Response:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return Response(buf.tobytes(), media_type="image/jpeg", headers={"Cache-Control": "no-store"})


def create_app(initial: str | None = None) -> FastAPI:
    app, state = FastAPI(title="sa"), State()
    if initial:
        state.open(Path(initial))

    @app.get("/")
    def index():
        return FileResponse(Path(__file__).with_name("index.html"), headers={"Cache-Control": "no-store"})

    @app.get("/api/state")
    def get_state():
        out: dict = {"project": None, "job": None, "loading": state.loading}
        if state.job:
            out["job"] = {"name": state.job.name, "running": state.job.running, "returncode": state.job.returncode}
        project = state.project
        if not project:
            return out
        out.update(project=str(project.root), video=str(state.video) if state.video else None,
                   frames=len(project.frame_paths()), meta=project.meta(), poses=None, plane=None, renders=[])
        if project.poses_path.exists():
            poses = state.poses()
            depths = poses.points_in_ref()[:, 2]
            depths = depths[depths > 0]
            out["poses"] = {
                "width": poses.width, "height": poses.height, "f": poses.K[0, 0], "k": poses.k,
                "cx": poses.K[0, 2], "cy": poses.K[1, 2],
                "registered": len(poses.names), "ref": poses.names[poses.ref],
                "D": g.sweep_diameter(poses.centres(), poses.R[poses.ref]),
                "depths": np.percentile(depths, [2, 50, 98]).tolist() if len(depths) else None,
            }
        if project.plane_path.exists():
            out["plane"] = json.loads(project.plane_path.read_text())
        if project.renders_dir.exists():
            files = [p for p in project.renders_dir.rglob("*") if p.suffix.lower() in (".png", ".jpg")]
            files.sort(key=lambda p: -p.stat().st_mtime)
            out["renders"] = [str(p.relative_to(project.renders_dir)) for p in files]
        return out

    @app.post("/api/open")
    def open_path(body: OpenBody):
        state.open(Path(body.path))
        return get_state()

    @app.post("/api/browse/{kind}")
    def browse(kind: str):
        """Native macOS chooser — a browser cannot hand a local path to the server."""
        script = ('POSIX path of (choose file with prompt "Choose a video" of type {"public.movie"})'
                  if kind == "video" else 'POSIX path of (choose folder with prompt "Choose a project folder")')
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        if result.returncode != 0:
            return {"path": None}  # cancelled
        state.open(Path(result.stdout.strip()))
        return get_state()

    @app.post("/api/run")
    def run(body: RunBody):
        project = state.need_project()
        if state.job and state.job.running:
            raise HTTPException(409, f"{state.job.name} is still running")
        root = str(project.root)
        if body.stage == "ingest":
            if not state.video:
                raise HTTPException(400, "no video in this project")
            argv = ["ingest", str(state.video), "--project", root, "--every", str(body.every)]
        elif body.stage == "pose":
            argv = ["pose", root]
        elif body.stage == "render":
            if not project.plane_path.exists():
                raise HTTPException(400, "save a focus plane first")
            argv = ["render", root, "--scale", str(body.scale), "--aperture", str(body.aperture)]
            if body.median:
                argv.append("--median")
            if body.sweep:
                argv += ["--tilt", ":".join(f"{v:g}" for v in body.sweep)]
            if body.name:
                argv += ["--out", body.name]
        else:
            raise HTTPException(400, f"unknown stage {body.stage}")
        state.job = Job(body.stage, argv)
        return {"ok": True}

    @app.post("/api/cancel")
    def cancel():
        if state.job and state.job.running:
            state.job.proc.terminate()
        return {"ok": True}

    @app.get("/api/log")
    def log(since: int = 0):
        lines = state.job.lines if state.job else []
        return {"lines": lines[since:], "next": len(lines), "running": bool(state.job and state.job.running)}

    @app.get("/api/ref.jpg")
    def ref_image():
        poses = state.poses()
        return _jpeg(state.preview_frames()[poses.ref])

    @app.get("/api/points")
    def points():
        poses = state.poses()
        uv, X = plane_mod.project_points(poses)
        if len(uv) > OVERLAY_POINTS:
            keep = np.random.default_rng(0).choice(len(uv), OVERLAY_POINTS, replace=False)
            uv, X = uv[keep], X[keep]
        return {"uv": np.round(uv, 1).tolist(), "z": np.round(X[:, 2], 5).tolist()}

    @app.post("/api/depth")
    def depth(body: PlaneBody):
        try:
            return {"dist": float(plane_mod.point_at(state.poses(), body.pivot)[2])}
        except ValueError as e:
            raise HTTPException(422, str(e))

    def _plane(poses: Poses, body: PlaneBody) -> g.Plane:
        try:
            if body.pixels:
                return plane_mod.plane_from_pixels(poses, body.pixels)
            if body.dist is None:
                raise ValueError("dist is required")
            return g.plane_from_tilt(poses.K, body.tilt, body.azimuth, body.dist, body.pivot)
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.post("/api/plane")
    def set_plane(body: PlaneBody):
        project, poses = state.need_project(), state.poses()
        chosen = _plane(poses, body)
        if body.save:
            plane_mod.save(project, poses, chosen, body.model_dump(exclude={"save"}, exclude_none=True))
        tilt, azimuth, dist = g.tilt_from_plane(poses.K, chosen)
        return {"n": chosen.n.tolist(), "d": chosen.d, "tilt": tilt, "azimuth": azimuth, "dist": dist}

    @app.get("/api/preview.jpg")
    def preview(tilt: float = 0.0, azimuth: float = 0.0, dist: float = 1.0, pu: float | None = None,
                pv: float | None = None, aperture: float = 1.0):
        project, poses = state.need_project(), state.poses()
        pivot = (pu, pv) if pu is not None and pv is not None else None
        chosen = _plane(poses, PlaneBody(tilt=tilt, azimuth=azimuth, dist=dist, pivot=pivot))
        frames = state.preview_frames()
        idx = render.select_frames(project, poses, aperture=aperture, max_frames=PREVIEW_FRAMES, log=lambda *_: None)
        (img,) = render.render_planes(frames.__getitem__, poses, [chosen], indices=idx, transfer=project.transfer())
        return _jpeg(img)

    @app.get("/api/render/{name:path}")
    def render_file(name: str):
        project = state.need_project()
        path = (project.renders_dir / name).resolve()
        if not path.is_relative_to(project.renders_dir.resolve()) or not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, headers={"Cache-Control": "no-store"})

    return app


def serve(initial: str | None = None, port: int = 8549, open_browser: bool = True) -> None:
    import uvicorn

    url = f"http://127.0.0.1:{port}"
    print(f"sa gui → {url}")
    if open_browser:
        threading.Timer(0.8, webbrowser.open, [url]).start()
    uvicorn.run(create_app(initial), host="127.0.0.1", port=port, log_level="warning")
