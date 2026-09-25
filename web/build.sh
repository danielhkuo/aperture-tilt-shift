#!/bin/sh
# Static site for Vercel: the GUI page (single source of truth lives in the
# Python package), the site assets, and every exported scene under web/scenes/.
set -e
cd "$(dirname "$0")"
rm -rf dist && mkdir -p dist/scenes
cp ../src/sa/gui/index.html dist/index.html
cp favicon.png favicon-32.png apple-touch-icon.png icon-512.png og.jpg dist/
python3 - <<'PY'
import json, pathlib, shutil
out = pathlib.Path("dist/scenes"); scenes = []
for path in pathlib.Path("scenes").glob("*/scene.json"):
    meta = json.loads(path.read_text())
    scenes.append((meta.get("order", 99), path.parent.name, meta["title"]))
index = []
for _, name, title in sorted(scenes):
    shutil.copytree(f"scenes/{name}", out / name)
    index.append({"path": f"scenes/{name}", "title": title})
(out / "index.json").write_text(json.dumps(index))
print(f"{len(index)} scene(s) → web/dist")
PY
