from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from ml.benchmark import run_benchmark


def main() -> None:
    root = ROOT
    ckpt = root / "backend" / "checkpoints" / "mvp_unet.pt"
    out = run_benchmark(
        ice_dir=Path(r"C:\Users\maksi\Downloads\vizard_iceclass\Dataset_2025_IceClass"),
        comp_dir=Path(r"C:\Users\maksi\Downloads\vizard_composite\Dataset_2025_composite"),
        palette_path=root / "configs" / "ice_palette.json",
        history_steps=2,
        checkpoint=ckpt if ckpt.exists() else None,
        yolo_pred_dir=None,
        max_scenes=8,
        seed=42,
        crop_size=512,
        output_json=root / "storage" / "reports" / "benchmark_quick.json",
        output_md=root / "storage" / "reports" / "benchmark_quick.md",
        yolo_summary_json=None,
    )

    top = out["ranking_by_masked_miou"][0] if out["ranking_by_masked_miou"] else None
    payload = {
        "winner": top,
        "gates": out["gates"],
        "available_methods": list(out["methods"].keys()),
    }
    print(json.dumps(payload, ensure_ascii=False))
    print(f"saved={root / 'storage' / 'reports' / 'benchmark_quick.json'}")


if __name__ == "__main__":
    main()
