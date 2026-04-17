from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


def to_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def from_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    return json.loads(raw)


def params_hash(scene_id: str, history_steps: int, model_mode: str, aoi_bbox: list[float] | None) -> str:
    payload = {
        "scene_id": scene_id,
        "history_steps": history_steps,
        "model_mode": model_mode,
        "aoi_bbox": aoi_bbox,
    }
    digest = hashlib.sha256(to_json(payload).encode("utf-8")).hexdigest()
    return digest[:20]
