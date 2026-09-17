"""Stage 1: video → PNG frames (ffmpeg)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from sa.project import Project


def probe(video: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams", "-of", "json", str(video)],
        check=True, capture_output=True, text=True,
    ).stdout
    return json.loads(out)["streams"][0]


def ingest(video: Path | str, root: Path | str | None = None, every: int = 8, log: Callable[[str], None] = print) -> Project:
    """Create (or refresh) a project from ``video``, keeping every Nth frame."""
    video = Path(video).expanduser().resolve()
    if not video.is_file():
        raise FileNotFoundError(video)
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found — brew install ffmpeg")
    project = Project(root or Path.cwd() / video.stem)
    project.root.mkdir(parents=True, exist_ok=True)

    link = project.root / f"video{video.suffix}"
    if link.resolve() != video:
        link.unlink(missing_ok=True)
        os.symlink(video, link)

    stream = probe(video)
    transfer = "hlg" if stream.get("color_transfer") == "arib-std-b67" else "srgb"
    if transfer == "hlg":
        log("HDR (HLG) video: averaging with the HLG curve. Colours will look flat on SDR viewers; "
            "shooting with HDR Video off is the better fix.")

    shutil.rmtree(project.frames_dir, ignore_errors=True)
    project.frames_dir.mkdir()
    subprocess.run(
        ["ffmpeg", "-v", "error", "-stats", "-i", str(video), "-vf", f"select=not(mod(n\\,{every}))",
         "-fps_mode", "vfr", "-pix_fmt", "rgb24", str(project.frames_dir / "%04d.png")],
        check=True,
    )
    count = len(project.frame_paths())
    if count == 0:
        raise RuntimeError("ffmpeg produced no frames")
    project.meta_path.write_text(json.dumps({"source": str(video), "every": every, "transfer": transfer,
                                             "fps": stream.get("r_frame_rate"), "frames": count}, indent=2))
    project.log_run("ingest", source=str(video), every=every, frames=count, transfer=transfer)
    log(f"{count} frames → {project.frames_dir}")
    if not 40 <= count <= 200:
        log(f"note: 60–150 frames is the sweet spot; adjust --every (now {every})")
    return project
