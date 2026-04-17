from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _env_path(name: str, default: str) -> Path:
    return Path(os.getenv(name, default)).expanduser().resolve()


@dataclass(frozen=True)
class Settings:
    api_prefix: str
    project_name: str
    dataset_iceclass_dir: Path
    dataset_composite_dir: Path
    storage_dir: Path
    sqlite_path: Path
    model_checkpoint_path: Path
    model_device: str
    model_input_size: int
    preview_max_width: int
    route_grid_size: int
    cors_origins: list[str]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    storage_dir = _env_path("VIZARD_STORAGE_DIR", str(Path(__file__).resolve().parents[2] / "storage"))
    storage_dir.mkdir(parents=True, exist_ok=True)

    sqlite_path = _env_path("VIZARD_SQLITE_PATH", str(storage_dir / "metadata.db"))
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    checkpoint = _env_path("VIZARD_MODEL_CKPT", str(Path(__file__).resolve().parents[1] / "checkpoints" / "mvp_unet.pt"))

    default_ice = r"C:\Users\maksi\Downloads\vizard_iceclass\Dataset_2025_IceClass"
    default_comp = r"C:\Users\maksi\Downloads\vizard_composite\Dataset_2025_composite"

    cors_default = "http://localhost:8080,http://127.0.0.1:8080,http://localhost:5173,http://127.0.0.1:5173"
    cors_origins = [x.strip() for x in os.getenv("VIZARD_CORS_ORIGINS", cors_default).split(",") if x.strip()]

    return Settings(
        api_prefix="/api/v1",
        project_name="Vizard Arctic API",
        dataset_iceclass_dir=_env_path("VIZARD_ICECLASS_DIR", default_ice),
        dataset_composite_dir=_env_path("VIZARD_COMPOSITE_DIR", default_comp),
        storage_dir=storage_dir,
        sqlite_path=sqlite_path,
        model_checkpoint_path=checkpoint,
        model_device=os.getenv("VIZARD_MODEL_DEVICE", "cuda"),
        model_input_size=int(os.getenv("VIZARD_MODEL_INPUT_SIZE", "512")),
        preview_max_width=int(os.getenv("VIZARD_PREVIEW_MAX_WIDTH", "2048")),
        route_grid_size=int(os.getenv("VIZARD_ROUTE_GRID_SIZE", "512")),
        cors_origins=cors_origins,
    )
