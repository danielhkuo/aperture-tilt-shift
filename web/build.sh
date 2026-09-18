#!/bin/sh
# Static site for Vercel: the GUI page (single source of truth lives in the
# Python package) plus every exported scene bundle under web/scenes/.
set -e
cd "$(dirname "$0")"
rm -rf dist && mkdir -p dist/scenes
cp ../src/sa/gui/index.html dist/index.html
python3 - <<'PY'
import json, pathlib, shutil
out = pathlib.Path("dist/scenes"); index = []
for scene in sorted(pathlib.Path("scenes").glob("*/scene.json")):
    shutil.copytree(scene.parent, out / scene.parent.name)
    index.append({"path": f"scenes/{scene.parent.name}", "title": json.loads(scene.read_text())["title"]})
(out / "index.json").write_text(json.dumps(index))
print(f"{len(index)} scene(s) → web/dist")
PY
