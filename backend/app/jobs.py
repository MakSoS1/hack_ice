from __future__ import annotations

import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .db import MetadataDB
from .palette import IceClassPalette
from .reconstruction import run_reconstruction
from .scene_index import SceneIndex
from .utils import params_hash


class JobManager:
    def __init__(
        self,
        *,
        db: MetadataDB,
        scene_index: SceneIndex,
        palette: IceClassPalette,
        storage_dir: Path,
        preview_max_width: int,
        route_grid_size: int,
        workers: int = 2,
    ):
        self.db = db
        self.scene_index = scene_index
        self.palette = palette
        self.storage_dir = storage_dir
        self.preview_max_width = preview_max_width
        self.route_grid_size = route_grid_size
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="recon")

    def submit_reconstruction(self, job_id: str, *, scene_id: str, history_steps: int, model_mode: str, aoi_bbox: list[float] | None) -> None:
        self.executor.submit(
            self._run_reconstruction_job,
            job_id,
            scene_id,
            history_steps,
            model_mode,
            aoi_bbox,
        )

    def _run_reconstruction_job(self, job_id: str, scene_id: str, history_steps: int, model_mode: str, aoi_bbox: list[float] | None) -> None:
        try:
            self.db.update_job(job_id, status="running", progress=0.05)

            phash = params_hash(scene_id, history_steps, model_mode, aoi_bbox)
            cached = self.db.get_cached_layer(scene_id, phash)
            if cached:
                self.db.update_job(job_id, status="completed", progress=1.0, layer_id=cached["id"])
                return

            self.db.update_job(job_id, progress=0.12)

            artifacts = run_reconstruction(
                scene_index=self.scene_index,
                palette=self.palette,
                storage_dir=self.storage_dir,
                scene_id=scene_id,
                history_steps=history_steps,
                model_mode=model_mode,
                preview_max_width=self.preview_max_width,
                route_grid_size=self.route_grid_size,
            )

            self.db.update_job(job_id, progress=0.95)
            self.db.upsert_layer(
                layer_id=artifacts.layer_id,
                scene_id=scene_id,
                params_hash=phash,
                path=str(artifacts.layer_dir),
                bounds=artifacts.bounds,
                summary=artifacts.summary,
            )

            self.db.update_job(job_id, status="completed", progress=1.0, layer_id=artifacts.layer_id)
        except Exception as exc:  # noqa: BLE001
            message = f"{type(exc).__name__}: {exc}"
            trace = traceback.format_exc(limit=4)
            self.db.update_job(job_id, status="failed", error=f"{message}\n{trace}")
