"""Make the regenerated sprite/chair sheets compositable.

The regenerated character atlases and the chair strip ship as opaque RGB PNGs
with a solid near-white background; the office background is opaque black. To
layer characters + chairs over the office we must key out only the *background*
white (the flat exterior + the gaps between grid cells) while preserving white
that belongs to the characters themselves (shirts, collars, hair highlights).

We do that with connected-component labelling: any near-white region that
touches the image border is background and becomes transparent; enclosed white
stays. Originals are backed up once to ``<name>.opaque.png`` so the keying is
idempotent and re-runnable after the user regenerates art.

Run:  python scripts/prepare_sprites.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

REPO_ROOT = Path(__file__).resolve().parents[1]
PIXEL_DIR = REPO_ROOT / "public" / "pixel"

SHEETS = [
    "bald-glasses",
    "bald-round-glasses",
    "balding-square-glasses",
    "black-hair-businessman",
    "gray-mustache-businessman",
    "white-beard-businessman",
    "white-hair-glasses",
]

SHEET_COLS, SHEET_ROWS = 6, 3
CHAIR_COLS = 8
# A pixel is "background-ish white" when every channel is bright and the colour
# is close to neutral grey (keeps coloured art, catches the anti-aliased fringe).
WHITE_MIN = 205
NEUTRAL_SPREAD = 28


def _source(path: Path) -> Image.Image:
    """Return the opaque source, backing it up once so re-runs stay idempotent."""

    backup = path.with_suffix(".opaque.png")
    if backup.exists():
        return Image.open(backup).convert("RGB")
    if path.exists():
        Image.open(path).convert("RGB").save(backup)
        return Image.open(backup).convert("RGB")
    raise FileNotFoundError(path)


def _key_white_background(img: Image.Image) -> Image.Image:
    rgb = np.asarray(img, dtype=np.int16)
    mx = rgb.max(axis=2)
    mn = rgb.min(axis=2)
    whiteish = (mn >= WHITE_MIN) & ((mx - mn) <= NEUTRAL_SPREAD)

    # Label 4-connected white regions; anything touching the border is backdrop.
    labels, n = ndimage.label(whiteish, structure=[[0, 1, 0], [1, 1, 1], [0, 1, 0]])
    if n == 0:
        alpha = np.full(whiteish.shape, 255, dtype=np.uint8)
    else:
        border = set(labels[0, :]) | set(labels[-1, :])
        border |= set(labels[:, 0]) | set(labels[:, -1])
        border.discard(0)
        background = np.isin(labels, list(border))
        alpha = np.where(background, 0, 255).astype(np.uint8)

    out = np.dstack([np.asarray(img, dtype=np.uint8), alpha])
    return Image.fromarray(out, mode="RGBA")


def _cell_bbox(alpha: np.ndarray, c: int, r: int, cols: int, rows: int) -> str:
    h, w = alpha.shape
    cw, ch = w / cols, h / rows
    x0, x1 = int(c * cw), int((c + 1) * cw)
    y0, y1 = int(r * ch), int((r + 1) * ch)
    sub = alpha[y0:y1, x0:x1]
    ys, xs = np.where(sub > 40)
    if len(xs) == 0:
        return "empty"
    cx = (xs.min() + xs.max()) / 2 / (x1 - x0)
    return (
        f"x[{xs.min()},{xs.max()}] w={xs.max()-xs.min()} "
        f"y[{ys.min()},{ys.max()}] feetFrac={ys.max()/(y1-y0):.2f} cxFrac={cx:.2f}"
    )


def process_sheet(name: str) -> None:
    path = PIXEL_DIR / name / "atlas.png"
    keyed = _key_white_background(_source(path))
    keyed.save(path)
    alpha = np.asarray(keyed)[:, :, 3]
    print(f"[atlas] {name}")
    for r in range(SHEET_ROWS):
        row = " | ".join(
            _cell_bbox(alpha, c, r, SHEET_COLS, SHEET_ROWS) for c in range(SHEET_COLS)
        )
        print(f"  row{r}: {row}")


def process_chairs() -> None:
    path = PIXEL_DIR / "chairs1.png"
    keyed = _key_white_background(_source(path))
    keyed.save(path)
    alpha = np.asarray(keyed)[:, :, 3]
    print("[chairs] chairs1.png")
    row = " | ".join(_cell_bbox(alpha, c, 0, CHAIR_COLS, 1) for c in range(CHAIR_COLS))
    print(f"  {row}")


def main() -> None:
    for name in SHEETS:
        process_sheet(name)
    process_chairs()
    print("done")


if __name__ == "__main__":
    main()
