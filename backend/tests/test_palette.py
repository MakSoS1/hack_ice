from pathlib import Path

import numpy as np

from app.palette import load_palette


def _palette_path() -> Path:
    return Path(__file__).resolve().parents[2] / "configs" / "ice_palette.json"


def test_official_palette_shape_and_ids() -> None:
    p = load_palette(_palette_path())
    assert p.class_ids.tolist() == [0, 1, 2, 3, 4, 5, 6, 7]
    assert p.class_rgbs.shape == (8, 3)
    assert int(p.unknown_id) == 255


def test_unknown_color_does_not_snap_to_nearest_class() -> None:
    p = load_palette(_palette_path())
    # [0, 90, 250] is close to open water [0, 100, 255], but should remain unknown in strict mode.
    rgb = np.array(
        [
            [[0, 100, 255], [0, 90, 250]],
            [[1, 1, 1], [150, 150, 150]],
        ],
        dtype=np.uint8,
    )
    cls = p.rgb_to_class_ids(rgb)
    assert int(cls[0, 0]) == 1
    assert int(cls[0, 1]) == int(p.unknown_id)
    assert int(cls[1, 0]) == 0
    assert int(cls[1, 1]) == 6
