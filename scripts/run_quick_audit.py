from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from ml.data_audit import run_audit


def main() -> None:
    root = ROOT
    report = run_audit(
        ice_dir=Path(r"C:\Users\maksi\Downloads\vizard_iceclass\Dataset_2025_IceClass"),
        comp_dir=Path(r"C:\Users\maksi\Downloads\vizard_composite\Dataset_2025_composite"),
        palette_path=root / "configs" / "ice_palette.json",
        output_json=root / "storage" / "reports" / "data_audit_quick.json",
        output_md=root / "storage" / "reports" / "data_audit_quick.md",
        class_sample_scenes=0,
        class_stride=16,
        full_gap_pass=False,
        max_scenes=120,
    )
    out = {
        "paired_intersection": report["counts"]["paired_intersection"],
        "paired_evaluated": report["counts"]["paired_evaluated"],
        "invalid_scene_ids": report["filename_validation"]["invalid_scene_ids"],
        "mode_counts": report["filename_validation"]["mode_counts"],
        "product_counts": report["filename_validation"]["product_counts"],
        "gap_mean": report["gap_ratio"]["summary"]["mean"],
        "gap_p95": report["gap_ratio"]["summary"]["p95"],
        "delta_median_min": report["time_distribution"]["delta_minutes_median"],
    }
    print(json.dumps(out, ensure_ascii=False))
    print(f"saved={root / 'storage' / 'reports' / 'data_audit_quick.json'}")


if __name__ == "__main__":
    main()
