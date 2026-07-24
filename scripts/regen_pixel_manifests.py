"""Regenerate public/pixel manifests to describe the real 6x3 sprite grid.

The runtime (frontend/office/js/app.js) reads the atlas directly via the 6x3
grid constants and does not consume these files; they are descriptive metadata
only. This keeps that metadata truthful after the atlases were regenerated as a
single 6-column x 3-row sheet (row 0 front, row 1 back, row 2 side-facing-left;
columns 0-3 walk cycle, columns 4-5 idle).
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

PIX = Path(__file__).resolve().parent.parent / "public" / "pixel"
COLS, ROWS = 6, 3
ROW_ROLE = {0: "front", 1: "back", 2: "side_left"}
WALK_COLS = [0, 1, 2, 3]
IDLE_COLS = [4, 5]


def col_role(c: int) -> str:
    return "walk" if c in WALK_COLS else "idle"


def build_manifest(name: str, w: int, h: int) -> dict:
    cw, ch = w / COLS, h / ROWS
    frames = []
    for r in range(ROWS):
        for c in range(COLS):
            frames.append({
                "index": r * COLS + c,
                "row": r,
                "col": c,
                "facing": ROW_ROLE[r],
                "role": col_role(c),
                "x": round(c * cw),
                "y": round(r * ch),
                "width": round(cw),
                "height": round(ch),
            })
    return {
        "name": name,
        "atlas": {
            "file": "atlas.png",
            "columns": COLS,
            "rows": ROWS,
            "width": w,
            "height": h,
            "cell_width": round(cw, 3),
            "cell_height": round(ch, 3),
        },
        "layout": {
            "rows": ROW_ROLE,
            "walk_columns": WALK_COLS,
            "idle_columns": IDLE_COLS,
        },
        "frame_count": COLS * ROWS,
        "frames": frames,
    }


def main() -> None:
    sheets = []
    for d in sorted(p for p in PIX.iterdir() if p.is_dir()):
        atlas = d / "atlas.png"
        if not atlas.exists():
            continue
        w, h = Image.open(atlas).size
        manifest = build_manifest(d.name, w, h)
        (d / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        sheets.append({
            "name": d.name,
            "manifest": f"{d.name}/manifest.json",
            "atlas": f"{d.name}/atlas.png",
            "columns": COLS,
            "rows": ROWS,
            "frame_count": COLS * ROWS,
        })
    index = {
        "format": "AlphaOS pixel sprite atlas v2 (6x3 grid)",
        "grid": {"columns": COLS, "rows": ROWS},
        "layout": {"rows": ROW_ROLE, "walk_columns": WALK_COLS, "idle_columns": IDLE_COLS},
        "sheets": sheets,
    }
    (PIX / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print(f"regenerated {len(sheets)} manifests + index.json")


if __name__ == "__main__":
    main()
