from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class SegmentationMetrics:
    masked_accuracy: float
    masked_macro_f1: float
    masked_miou: float
    masked_edge_f1: float
    coverage_before: float
    coverage_after: float
    recovered_ratio: float
    confidence_brier: float
    confidence_ece: float


def _safe_div(a: float, b: float) -> float:
    if b <= 0:
        return 0.0
    return float(a / b)


def _to_indices(arr: np.ndarray, class_ids: np.ndarray) -> np.ndarray:
    lookup = {int(cid): i for i, cid in enumerate(class_ids.tolist())}
    out = np.full(arr.shape, -1, dtype=np.int32)
    unique_vals = np.unique(arr)
    for v in unique_vals:
        if int(v) in lookup:
            out[arr == v] = lookup[int(v)]
    return out


def _confusion_matrix(y_true_idx: np.ndarray, y_pred_idx: np.ndarray, valid_mask: np.ndarray, k: int) -> np.ndarray:
    yt = y_true_idx[valid_mask]
    yp = y_pred_idx[valid_mask]
    ok = (yt >= 0) & (yp >= 0)
    yt = yt[ok]
    yp = yp[ok]
    cm = np.zeros((k, k), dtype=np.int64)
    if yt.size == 0:
        return cm
    np.add.at(cm, (yt, yp), 1)
    return cm


def _macro_f1_iou_from_cm(cm: np.ndarray) -> tuple[float, float]:
    k = cm.shape[0]
    f1s: list[float] = []
    ious: list[float] = []
    for i in range(k):
        tp = float(cm[i, i])
        fp = float(np.sum(cm[:, i]) - tp)
        fn = float(np.sum(cm[i, :]) - tp)
        support = float(np.sum(cm[i, :]))
        if support <= 0:
            continue
        prec = _safe_div(tp, tp + fp)
        rec = _safe_div(tp, tp + fn)
        f1 = _safe_div(2.0 * prec * rec, prec + rec)
        iou = _safe_div(tp, tp + fp + fn)
        f1s.append(f1)
        ious.append(iou)
    return (float(np.mean(f1s)) if f1s else 0.0, float(np.mean(ious)) if ious else 0.0)


def _edge_mask(classes: np.ndarray) -> np.ndarray:
    cls_u8 = classes.astype(np.uint8)
    kernel = np.ones((3, 3), dtype=np.uint8)
    dil = cv2.dilate(cls_u8, kernel, iterations=1)
    ero = cv2.erode(cls_u8, kernel, iterations=1)
    edge = (dil != ero).astype(np.uint8)
    return edge.astype(bool)


def _binary_f1(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    tp = float(np.sum((y_true == 1) & (y_pred == 1)))
    fp = float(np.sum((y_true == 0) & (y_pred == 1)))
    fn = float(np.sum((y_true == 1) & (y_pred == 0)))
    p = _safe_div(tp, tp + fp)
    r = _safe_div(tp, tp + fn)
    return _safe_div(2.0 * p * r, p + r)


def _confidence_scores(correct: np.ndarray, conf: np.ndarray, bins: int = 10) -> tuple[float, float]:
    if correct.size == 0:
        return 0.0, 0.0

    correct_f = correct.astype(np.float32)
    conf_f = conf.astype(np.float32)
    brier = float(np.mean((conf_f - correct_f) ** 2))

    ece = 0.0
    n = float(correct_f.size)
    edges = np.linspace(0.0, 1.0, bins + 1)
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        if i == bins - 1:
            m = (conf_f >= lo) & (conf_f <= hi)
        else:
            m = (conf_f >= lo) & (conf_f < hi)
        if not np.any(m):
            continue
        acc = float(np.mean(correct_f[m]))
        cavg = float(np.mean(conf_f[m]))
        ece += (float(np.sum(m)) / n) * abs(acc - cavg)
    return brier, float(ece)


def evaluate_segmentation(
    *,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    gap_mask: np.ndarray,
    class_ids: np.ndarray,
    confidence: np.ndarray | None = None,
) -> SegmentationMetrics:
    if y_true.shape != y_pred.shape:
        raise ValueError("y_true and y_pred must have the same shape")
    if y_true.shape != gap_mask.shape:
        raise ValueError("gap_mask must match class map shape")

    masked = gap_mask.astype(bool)
    observed = ~masked

    y_true_idx = _to_indices(y_true, class_ids)
    y_pred_idx = _to_indices(y_pred, class_ids)
    cm = _confusion_matrix(y_true_idx, y_pred_idx, masked, k=len(class_ids))

    total_masked = float(np.sum(masked))
    total_observed = float(np.sum(observed))
    masked_correct = float(np.sum((y_true == y_pred) & masked))
    masked_acc = _safe_div(masked_correct, total_masked)
    macro_f1, miou = _macro_f1_iou_from_cm(cm)

    edge = _edge_mask(y_true)
    edge_masked = edge & masked
    if np.any(edge_masked):
        edge_true = y_true[edge_masked]
        edge_pred = y_pred[edge_masked]
        edge_f1 = float(np.mean(edge_true == edge_pred))
    else:
        edge_f1 = 0.0

    coverage_before = _safe_div(total_observed, total_observed + total_masked)
    coverage_after = 1.0
    recovered_ratio = _safe_div(masked_correct, total_masked)

    if confidence is None:
        confidence = np.where(masked, 0.5, 1.0).astype(np.float32)
    conf_masked = confidence[masked].astype(np.float32)
    corr_masked = (y_true[masked] == y_pred[masked]).astype(np.float32)
    brier, ece = _confidence_scores(corr_masked, conf_masked)

    return SegmentationMetrics(
        masked_accuracy=float(masked_acc),
        masked_macro_f1=float(macro_f1),
        masked_miou=float(miou),
        masked_edge_f1=float(edge_f1),
        coverage_before=float(coverage_before),
        coverage_after=float(coverage_after),
        recovered_ratio=float(recovered_ratio),
        confidence_brier=float(brier),
        confidence_ece=float(ece),
    )
