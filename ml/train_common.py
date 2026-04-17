from __future__ import annotations

import argparse
import json
import random
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

from app.palette import load_palette
from app.scene_index import SceneIndex
from ml.dataset import SceneTemporalDataset, collate_scene_samples
from ml.metrics import evaluate_segmentation
from ml.model import TemporalUNet


@dataclass
class TrainConfig:
    ice_dir: Path
    comp_dir: Path
    palette_path: Path
    output_checkpoint: Path
    output_metrics_json: Path
    history_steps: int
    crop_size: int
    batch_size: int
    epochs: int
    lr: float
    subset_size: int
    seed: int
    val_ratio: float
    gap_loss_weight: float
    focal_gamma: float
    base_channels: int
    train_workers: int
    grad_accum: int
    synthetic_gap_prob: float
    norm: str


def parse_common_args(default_subset: int, default_epochs: int) -> TrainConfig:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ice-dir", type=Path, default=Path(r"C:\Users\maksi\Downloads\vizard_iceclass\Dataset_2025_IceClass"))
    parser.add_argument("--comp-dir", type=Path, default=Path(r"C:\Users\maksi\Downloads\vizard_composite\Dataset_2025_composite"))
    parser.add_argument("--palette", type=Path, default=ROOT / "configs" / "ice_palette.json")
    parser.add_argument("--output", type=Path, default=ROOT / "backend" / "checkpoints" / "mvp_unet.pt")
    parser.add_argument("--output-metrics", type=Path, default=ROOT / "storage" / "reports" / "train_metrics.json")
    parser.add_argument("--history-steps", type=int, default=1)
    parser.add_argument("--crop-size", type=int, default=256)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--epochs", type=int, default=default_epochs)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--subset-size", type=int, default=default_subset)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--val-ratio", type=float, default=0.15)
    parser.add_argument("--gap-loss-weight", type=float, default=4.0)
    parser.add_argument("--focal-gamma", type=float, default=2.0)
    parser.add_argument("--base-channels", type=int, default=16)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--synthetic-gap-prob", type=float, default=0.65)
    parser.add_argument("--norm", type=str, choices=["batch", "group"], default="group")
    args = parser.parse_args()

    return TrainConfig(
        ice_dir=args.ice_dir,
        comp_dir=args.comp_dir,
        palette_path=args.palette,
        output_checkpoint=args.output,
        output_metrics_json=args.output_metrics,
        history_steps=args.history_steps,
        crop_size=args.crop_size,
        batch_size=args.batch_size,
        epochs=args.epochs,
        lr=args.lr,
        subset_size=args.subset_size,
        seed=args.seed,
        val_ratio=float(np.clip(args.val_ratio, 0.05, 0.4)),
        gap_loss_weight=float(max(0.0, args.gap_loss_weight)),
        focal_gamma=float(max(0.0, args.focal_gamma)),
        base_channels=int(max(16, args.base_channels)),
        train_workers=max(0, int(args.workers)),
        grad_accum=max(1, int(args.grad_accum)),
        synthetic_gap_prob=float(np.clip(args.synthetic_gap_prob, 0.0, 1.0)),
        norm=str(args.norm),
    )


def _aux_gap_ratio(comp_path: Path) -> float:
    aux = comp_path.with_suffix(comp_path.suffix + ".aux.xml")
    if not aux.exists():
        return 0.35
    try:
        root = ET.fromstring(aux.read_text(encoding="utf-8"))
        for mdi in root.findall(".//MDI"):
            if mdi.attrib.get("key") == "STATISTICS_VALID_PERCENT" and mdi.text:
                valid = float(mdi.text)
                return float(np.clip(1.0 - valid / 100.0, 0.0, 1.0))
    except Exception:  # noqa: BLE001
        return 0.35
    return 0.35


def stratified_scene_subset(scene_index: SceneIndex, subset_size: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    records = scene_index.list_records()
    if subset_size >= len(records):
        return [r.scene_id for r in records]

    buckets: dict[tuple[int, str], list[str]] = {}
    for r in records:
        g = _aux_gap_ratio(r.composite_path)
        if g < 0.20:
            gb = "lt20"
        elif g < 0.35:
            gb = "20_35"
        elif g < 0.50:
            gb = "35_50"
        else:
            gb = "ge50"
        key = (r.acquisition_start.month, gb)
        buckets.setdefault(key, []).append(r.scene_id)

    keys = sorted(buckets)
    counts = np.array([len(buckets[k]) for k in keys], dtype=np.float64)
    weights = counts / max(1.0, np.sum(counts))
    quota = np.floor(weights * subset_size).astype(int)
    short = subset_size - int(np.sum(quota))
    for i in np.argsort(-weights)[:short]:
        quota[i] += 1

    chosen: list[str] = []
    for q, key in zip(quota, keys, strict=True):
        group = list(buckets[key])
        rng.shuffle(group)
        chosen.extend(group[: min(len(group), int(q))])

    if len(chosen) < subset_size:
        remaining = [r.scene_id for r in records if r.scene_id not in set(chosen)]
        rng.shuffle(remaining)
        chosen.extend(remaining[: subset_size - len(chosen)])

    rng.shuffle(chosen)
    return chosen[:subset_size]


def time_aware_split(scene_index: SceneIndex, scene_ids: list[str], val_ratio: float) -> tuple[list[str], list[str]]:
    ordered = sorted(scene_ids, key=lambda sid: scene_index.get(sid).acquisition_start)
    cut = int(round(len(ordered) * (1.0 - val_ratio)))
    cut = max(1, min(len(ordered) - 1, cut))
    train_ids = ordered[:cut]
    val_ids = ordered[cut:]
    return train_ids, val_ids


def focal_ce_loss(logits: torch.Tensor, target: torch.Tensor, gamma: float) -> torch.Tensor:
    ce = F.cross_entropy(logits, target, reduction="none")
    if gamma <= 0:
        return ce
    pt = torch.exp(-ce)
    focal = ((1.0 - pt) ** gamma) * ce
    return focal


def masked_multiclass_dice_loss(logits: torch.Tensor, target: torch.Tensor, gap_mask: torch.Tensor, eps: float = 1e-6) -> torch.Tensor:
    num_classes = logits.shape[1]
    probs = F.softmax(logits, dim=1)
    one_hot = F.one_hot(target, num_classes=num_classes).permute(0, 3, 1, 2).float()

    # Focus Dice mostly on reconstructed areas; if absent, fallback to full image.
    m = (gap_mask > 0.5).unsqueeze(1).float()
    if float(torch.sum(m)) < 1.0:
        m = torch.ones_like(m)

    inter = torch.sum(probs * one_hot * m, dim=(0, 2, 3))
    denom = torch.sum((probs + one_hot) * m, dim=(0, 2, 3))
    dice = (2.0 * inter + eps) / (denom + eps)
    return 1.0 - torch.mean(dice)


def _batch_metrics(
    *,
    y_true_idx: np.ndarray,
    y_pred_idx: np.ndarray,
    gap: np.ndarray,
    conf: np.ndarray,
    palette_ids: np.ndarray,
) -> dict[str, float]:
    y_true_ids = palette_ids[y_true_idx]
    y_pred_ids = palette_ids[y_pred_idx]
    met = evaluate_segmentation(
        y_true=y_true_ids,
        y_pred=y_pred_ids,
        gap_mask=gap.astype(np.uint8),
        class_ids=palette_ids.astype(np.uint8),
        confidence=conf.astype(np.float32),
    )
    return {
        "masked_accuracy": met.masked_accuracy,
        "masked_macro_f1": met.masked_macro_f1,
        "masked_miou": met.masked_miou,
        "masked_edge_f1": met.masked_edge_f1,
        "confidence_brier": met.confidence_brier,
        "confidence_ece": met.confidence_ece,
    }


def evaluate(
    model: TemporalUNet,
    loader: DataLoader,
    device: torch.device,
    *,
    gap_loss_weight: float,
    focal_gamma: float,
    palette_ids: np.ndarray,
) -> tuple[float, dict[str, float]]:
    model.eval()
    losses: list[float] = []
    metrics_acc: dict[str, list[float]] = {
        "masked_accuracy": [],
        "masked_macro_f1": [],
        "masked_miou": [],
        "masked_edge_f1": [],
        "confidence_brier": [],
        "confidence_ece": [],
    }

    with torch.no_grad():
        for batch in loader:
            x = batch.x.to(device)
            y = batch.y.to(device)
            gap = batch.gap_mask.to(device)
            conf_t = batch.confidence_target.to(device)

            logits, conf_p = model(x)
            focal = focal_ce_loss(logits, y, gamma=focal_gamma)
            weighted = focal * (1.0 + gap_loss_weight * gap)
            loss_cls = torch.mean(weighted)
            loss_dice = masked_multiclass_dice_loss(logits, y, gap)
            conf_w = 1.0 + 2.0 * gap.unsqueeze(1)
            loss_conf = torch.mean(F.binary_cross_entropy(conf_p, conf_t, reduction="none") * conf_w)
            loss = loss_cls + 0.45 * loss_dice + 0.25 * loss_conf
            losses.append(float(loss.item()))

            pred = torch.argmax(logits, dim=1).detach().cpu().numpy().astype(np.int64)
            gt = y.detach().cpu().numpy().astype(np.int64)
            gap_np = gap.detach().cpu().numpy().astype(np.uint8)
            conf_np = conf_p.detach().cpu().numpy().astype(np.float32)[:, 0]

            for i in range(pred.shape[0]):
                m = _batch_metrics(
                    y_true_idx=gt[i],
                    y_pred_idx=pred[i],
                    gap=gap_np[i],
                    conf=conf_np[i],
                    palette_ids=palette_ids,
                )
                for k, v in m.items():
                    metrics_acc[k].append(float(v))

    agg = {k: (float(np.mean(v)) if v else 0.0) for k, v in metrics_acc.items()}
    return (float(np.mean(losses)) if losses else 0.0, agg)


def train_model(cfg: TrainConfig) -> None:
    torch.manual_seed(cfg.seed)
    np.random.seed(cfg.seed)
    random.seed(cfg.seed)

    scene_index = SceneIndex(cfg.ice_dir, cfg.comp_dir)
    palette = load_palette(cfg.palette_path)

    subset = stratified_scene_subset(scene_index, cfg.subset_size, cfg.seed)
    train_ids, val_ids = time_aware_split(scene_index, subset, cfg.val_ratio)

    train_ds = SceneTemporalDataset(
        scene_index=scene_index,
        palette=palette,
        scene_ids=train_ids,
        history_steps=cfg.history_steps,
        crop_size=cfg.crop_size,
        random_crop=True,
        gap_focus_prob=0.85,
        augment=True,
        seed=cfg.seed,
        synthetic_gap_prob=cfg.synthetic_gap_prob,
    )
    val_ds = SceneTemporalDataset(
        scene_index=scene_index,
        palette=palette,
        scene_ids=val_ids,
        history_steps=cfg.history_steps,
        crop_size=cfg.crop_size,
        random_crop=False,
        gap_focus_prob=0.0,
        augment=False,
        seed=cfg.seed + 7,
        synthetic_gap_prob=1.0,
    )

    train_loader = DataLoader(
        train_ds,
        batch_size=cfg.batch_size,
        shuffle=True,
        num_workers=cfg.train_workers,
        pin_memory=True,
        collate_fn=collate_scene_samples,
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=cfg.batch_size,
        shuffle=False,
        num_workers=cfg.train_workers,
        pin_memory=True,
        collate_fn=collate_scene_samples,
    )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    in_channels = cfg.history_steps + 4  # current + histories + observed mask + month sin/cos
    model = TemporalUNet(
        in_channels=in_channels,
        num_classes=len(palette.class_ids),
        base_channels=cfg.base_channels,
        norm=cfg.norm,
    ).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=1e-4)
    scaler = torch.amp.GradScaler(device="cuda", enabled=device.type == "cuda")

    best_key = -1.0
    history: list[dict] = []
    cfg.output_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    cfg.output_metrics_json.parent.mkdir(parents=True, exist_ok=True)

    patience = 4
    stale = 0

    for epoch in range(cfg.epochs):
        model.train()
        train_losses: list[float] = []
        opt.zero_grad(set_to_none=True)
        for step, batch in enumerate(train_loader):
            x = batch.x.to(device, non_blocking=True)
            y = batch.y.to(device, non_blocking=True)
            gap = batch.gap_mask.to(device, non_blocking=True)
            conf_t = batch.confidence_target.to(device, non_blocking=True)

            with torch.autocast(device_type=device.type, enabled=device.type == "cuda"):
                logits, conf_p = model(x)
                focal = focal_ce_loss(logits, y, gamma=cfg.focal_gamma)
                weighted = focal * (1.0 + cfg.gap_loss_weight * gap)
                loss_cls = torch.mean(weighted)
                loss_dice = masked_multiclass_dice_loss(logits, y, gap)
            conf_w = 1.0 + 2.0 * gap.unsqueeze(1)
            loss_conf = torch.mean(F.binary_cross_entropy(conf_p.float(), conf_t.float(), reduction="none") * conf_w.float())
            loss = loss_cls + 0.45 * loss_dice + 0.25 * loss_conf

            scaler.scale(loss / float(cfg.grad_accum)).backward()
            if (step + 1) % cfg.grad_accum == 0 or (step + 1) == len(train_loader):
                scaler.step(opt)
                scaler.update()
                opt.zero_grad(set_to_none=True)
            train_losses.append(float(loss.item()))

        val_loss, val_metrics = evaluate(
            model,
            val_loader,
            device,
            gap_loss_weight=cfg.gap_loss_weight,
            focal_gamma=cfg.focal_gamma,
            palette_ids=palette.class_ids,
        )
        train_loss = float(np.mean(train_losses)) if train_losses else 0.0

        epoch_row = {
            "epoch": epoch + 1,
            "train_loss": train_loss,
            "val_loss": val_loss,
            **val_metrics,
        }
        history.append(epoch_row)

        print(
            f"epoch={epoch+1}/{cfg.epochs} "
            f"train_loss={train_loss:.4f} val_loss={val_loss:.4f} "
            f"masked_miou={val_metrics['masked_miou']:.4f} "
            f"masked_macro_f1={val_metrics['masked_macro_f1']:.4f} "
            f"masked_edge_f1={val_metrics['masked_edge_f1']:.4f}"
        )

        key = 0.7 * val_metrics["masked_miou"] + 0.3 * val_metrics["masked_macro_f1"]
        if key > best_key:
            best_key = key
            stale = 0
            torch.save(
                {
                    "model_state": model.state_dict(),
                    "history_steps": cfg.history_steps,
                    "num_classes": len(palette.class_ids),
                    "crop_size": cfg.crop_size,
                    "palette_ids": palette.class_ids.tolist(),
                    "in_channels": in_channels,
                    "base_channels": cfg.base_channels,
                    "norm": cfg.norm,
                    "best_key": best_key,
                    "best_metrics": val_metrics,
                    "train_config": {
                        "subset_size": cfg.subset_size,
                        "val_ratio": cfg.val_ratio,
                        "gap_loss_weight": cfg.gap_loss_weight,
                        "focal_gamma": cfg.focal_gamma,
                        "seed": cfg.seed,
                        "grad_accum": cfg.grad_accum,
                        "synthetic_gap_prob": cfg.synthetic_gap_prob,
                    },
                },
                cfg.output_checkpoint,
            )
        else:
            stale += 1
            if stale >= patience:
                print(f"early_stop=true reason=patience_{patience}")
                break

        cfg.output_metrics_json.write_text(
            json.dumps(
                {
                    "config": {
                        "history_steps": cfg.history_steps,
                        "crop_size": cfg.crop_size,
                        "batch_size": cfg.batch_size,
                        "epochs": cfg.epochs,
                        "lr": cfg.lr,
                        "subset_size": cfg.subset_size,
                        "seed": cfg.seed,
                        "grad_accum": cfg.grad_accum,
                        "synthetic_gap_prob": cfg.synthetic_gap_prob,
                        "norm": cfg.norm,
                    },
                    "train_size": len(train_ids),
                    "val_size": len(val_ids),
                    "history": history,
                    "best_key": best_key,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
