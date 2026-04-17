from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

import numpy as np
import tifffile

SCENE_TIME_FMT = "%Y%m%dT%H%M%S"


def normalize_scene_id(filename: str) -> str:
    name = Path(filename).name
    if name.lower().endswith(".tif"):
        name = name[:-4]
    name = name.replace(".SAFE", "")
    for suffix in ("_fix_IceClass", "_composite_IceClass", "_IceClass", "_composite"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name


@dataclass(frozen=True)
class SceneNameParts:
    mission: str
    acquisition_mode: str
    product_type: str
    level_polarization: str
    sensing_start: datetime
    sensing_stop: datetime
    absolute_orbit: str
    datatake_id: str
    product_uid: str


_MISSION_RE = re.compile(r"^S1[A-Z]$")
_ACQ_MODE_RE = re.compile(r"^[A-Z]{2}$")
_PRODUCT_RE = re.compile(r"^[A-Z]{4}$")
_LEVEL_POL_RE = re.compile(r"^\d[A-Z]{3}$")
_ORBIT_RE = re.compile(r"^\d{6}$")
_HEX6_RE = re.compile(r"^[0-9A-Fa-f]{6}$")
_HEX4_RE = re.compile(r"^[0-9A-Fa-f]{4}$")


def parse_scene_name(scene_id: str) -> SceneNameParts:
    """Parse Sentinel-1 scene id according to ESA naming blocks.

    Expected normalized format:
      MMM_BB_TTTT_XXXX_YYYYMMDDThhmmss_YYYYMMDDThhmmss_OOOOOO_DDDDDD_CCCC
    """

    parts = scene_id.split("_")
    if len(parts) < 9:
        raise ValueError(f"Unexpected scene format: {scene_id}")

    mission, mode, product, level_pol = parts[0], parts[1], parts[2], parts[3]
    start_raw, stop_raw = parts[4], parts[5]
    orbit, datatake, uid = parts[6], parts[7], parts[8]

    if not _MISSION_RE.match(mission):
        raise ValueError(f"Invalid mission block in scene_id={scene_id}")
    if not _ACQ_MODE_RE.match(mode):
        raise ValueError(f"Invalid acquisition mode block in scene_id={scene_id}")
    if not _PRODUCT_RE.match(product):
        raise ValueError(f"Invalid product block in scene_id={scene_id}")
    if not _LEVEL_POL_RE.match(level_pol):
        raise ValueError(f"Invalid level/polarization block in scene_id={scene_id}")
    if not _ORBIT_RE.match(orbit):
        raise ValueError(f"Invalid orbit block in scene_id={scene_id}")
    if not _HEX6_RE.match(datatake):
        raise ValueError(f"Invalid datatake block in scene_id={scene_id}")
    if not _HEX4_RE.match(uid):
        raise ValueError(f"Invalid product UID block in scene_id={scene_id}")

    start = datetime.strptime(start_raw, SCENE_TIME_FMT).replace(tzinfo=UTC)
    stop = datetime.strptime(stop_raw, SCENE_TIME_FMT).replace(tzinfo=UTC)

    return SceneNameParts(
        mission=mission,
        acquisition_mode=mode,
        product_type=product,
        level_polarization=level_pol,
        sensing_start=start,
        sensing_stop=stop,
        absolute_orbit=orbit,
        datatake_id=datatake.upper(),
        product_uid=uid.upper(),
    )


def parse_scene_timestamps(scene_id: str) -> tuple[datetime, datetime]:
    parsed = parse_scene_name(scene_id)
    return parsed.sensing_start, parsed.sensing_stop


@dataclass(frozen=True)
class SceneRecord:
    scene_id: str
    acquisition_start: datetime
    acquisition_end: datetime
    iceclass_path: Path
    composite_path: Path


@dataclass(frozen=True)
class GeoInfo:
    bounds: list[float]  # [lon_min, lat_min, lon_max, lat_max]
    coordinates: list[list[float]]
    shape_hw: tuple[int, int]


class SceneIndex:
    def __init__(self, iceclass_dir: Path, composite_dir: Path):
        self.iceclass_dir = iceclass_dir
        self.composite_dir = composite_dir

        self._records: dict[str, SceneRecord] = {}
        self._ordered_ids: list[str] = []
        self._geo_cache: dict[str, GeoInfo] = {}

        self._build_index()

    @property
    def total(self) -> int:
        return len(self._ordered_ids)

    def list_scene_ids(self) -> list[str]:
        return list(self._ordered_ids)

    def list_records(self) -> list[SceneRecord]:
        return [self._records[sid] for sid in self._ordered_ids]

    def get(self, scene_id: str) -> SceneRecord:
        try:
            return self._records[scene_id]
        except KeyError as exc:
            raise KeyError(f"Unknown scene_id={scene_id}") from exc

    def get_history(self, scene_id: str, steps: int) -> list[SceneRecord]:
        if scene_id not in self._records:
            raise KeyError(f"Unknown scene_id={scene_id}")
        idx = self._ordered_ids.index(scene_id)
        left = max(0, idx - steps)
        history_ids = self._ordered_ids[left:idx]
        history_ids.reverse()  # nearest first
        return [self._records[sid] for sid in history_ids]

    def get_geo_info(self, scene_id: str) -> GeoInfo:
        if scene_id in self._geo_cache:
            return self._geo_cache[scene_id]

        rec = self.get(scene_id)
        with tifffile.TiffFile(rec.composite_path) as tf:
            series = tf.series[0]
            h, w = int(series.shape[0]), int(series.shape[1])
            tags = tf.pages[0].tags
            scale = tags[33550].value if 33550 in tags else (1.0, 1.0, 0.0)
            tie = tags[33922].value if 33922 in tags else (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        pixel_w = float(scale[0])
        pixel_h = float(scale[1])
        lon_min = float(tie[3])
        lat_max = float(tie[4])
        lon_max = lon_min + pixel_w * w
        lat_min = lat_max - pixel_h * h

        bounds = [lon_min, lat_min, lon_max, lat_max]
        coordinates = [
            [lon_min, lat_max],
            [lon_max, lat_max],
            [lon_max, lat_min],
            [lon_min, lat_min],
        ]
        out = GeoInfo(bounds=bounds, coordinates=coordinates, shape_hw=(h, w))
        self._geo_cache[scene_id] = out
        return out

    def read_gap_mask(self, scene_id: str) -> np.ndarray:
        rec = self.get(scene_id)
        comp = tifffile.imread(rec.composite_path)
        if comp.ndim != 3:
            raise ValueError(f"Unexpected composite shape for {scene_id}: {comp.shape}")
        gap = np.all(comp == 0, axis=-1)
        return gap.astype(np.uint8)

    def _build_index(self) -> None:
        ice_files = {normalize_scene_id(p.name): p for p in sorted(self.iceclass_dir.glob("*.tif"))}
        comp_files = {normalize_scene_id(p.name): p for p in sorted(self.composite_dir.glob("*.tif"))}

        scene_ids = sorted(set(ice_files) & set(comp_files))

        records: list[SceneRecord] = []
        for sid in scene_ids:
            start, end = parse_scene_timestamps(sid)
            records.append(
                SceneRecord(
                    scene_id=sid,
                    acquisition_start=start,
                    acquisition_end=end,
                    iceclass_path=ice_files[sid],
                    composite_path=comp_files[sid],
                )
            )

        records.sort(key=lambda x: x.acquisition_start)
        self._records = {r.scene_id: r for r in records}
        self._ordered_ids = [r.scene_id for r in records]


_SCENE_ID_RE = re.compile(
    r"^S1[A-Z]_[A-Z]{2}_[A-Z]{4}_\d[A-Z]{3}_\d{8}T\d{6}_\d{8}T\d{6}_\d{6}_[0-9A-Fa-f]{6}_[0-9A-Fa-f]{4}$"
)


def is_scene_filename(name: str) -> bool:
    return bool(_SCENE_ID_RE.match(normalize_scene_id(name)))


def filter_scene_files(paths: Iterable[Path]) -> list[Path]:
    return [p for p in paths if p.suffix.lower() == ".tif" and is_scene_filename(p.name)]
