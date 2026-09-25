#!/usr/bin/env python3
"""Rebuild and audit the SynaptosomesMacro AutoROI logistic classifier.

This script supports two feature geometries:

1. historical_classifier (default)
   Reproduces the feature extraction used to fit the deployed Version 13b
   coefficients. The central 24 px circle is represented by pixel-centre geometry
   and the local background is the mathematical annulus from radius 12 to 23 px.
   Background SD uses the sample standard deviation (ddof=1).

2. imagej_runtime
   Reconstructs Fiji/ImageJ's current `Make Band...` geometry more literally from
   the ROI mask and byte-rounded Euclidean distance map. This mode is intended for
   parity auditing and future model-development work; it is not the historical fit
   definition.

Historical model fitting is intentionally reproducible:
  StandardScaler -> LogisticRegression(
      C=1.0,
      class_weight='balanced',
      solver='lbfgs',
      tol=1e-4,
      max_iter=100
  )
The fitted standardized coefficients are transformed back to the original feature
units for direct insertion into the ImageJ macro.

The historical fit uses all manually labelled ROIs. Hard-invalid status is still
computed and exported for audit because Version 13b rejects such ROIs before the
score is applied at runtime.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import re
import struct
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import tifffile
from scipy.ndimage import distance_transform_edt
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

GREEN = 0xFF00FF00
RED = 0xFFFF0000
FIXED_MODEL = np.array([-1.4169522, -0.4050303, 42.6003835], dtype=float)


@dataclass
class AcquisitionSource:
    archive_id: str
    acquisition_id: str
    gallery_bytes: bytes
    roiset_bytes: bytes
    results_bytes: bytes
    source_locator: str


def _numeric_roi_index(name: str) -> int:
    base = os.path.basename(name)
    m = re.search(r"(?:Detection|ROI)_(\d+)", base, flags=re.IGNORECASE)
    if not m:
        raise ValueError(f"Cannot determine ROI index from {name!r}")
    return int(m.group(1))


def parse_roi_set(roiset_bytes: bytes) -> List[dict]:
    rows: List[dict] = []
    with zipfile.ZipFile(io.BytesIO(roiset_bytes)) as rz:
        names = [n for n in rz.namelist() if n.lower().endswith(".roi") and not n.startswith("__MACOSX/")]
        names.sort(key=_numeric_roi_index)
        for name in names:
            b = rz.read(name)
            if len(b) < 44 or b[:4] != b"Iout":
                raise ValueError(f"Unsupported ImageJ ROI payload: {name}")
            rows.append(
                {
                    "roi_index": _numeric_roi_index(name),
                    "top": struct.unpack(">H", b[8:10])[0],
                    "left": struct.unpack(">H", b[10:12])[0],
                    "bottom": struct.unpack(">H", b[12:14])[0],
                    "right": struct.unpack(">H", b[14:16])[0],
                    "stroke": struct.unpack(">I", b[40:44])[0],
                }
            )
    return rows


def read_gallery(gallery_zip_bytes: bytes) -> np.ndarray:
    with zipfile.ZipFile(io.BytesIO(gallery_zip_bytes)) as gz:
        names = [n for n in gz.namelist() if n.lower().endswith((".tif", ".tiff")) and not n.startswith("__MACOSX/")]
        if len(names) != 1:
            raise ValueError(f"Expected exactly one TIFF in Gallery.zip, found {len(names)}")
        arr = tifffile.imread(io.BytesIO(gz.read(names[0])))
    if arr.ndim == 2:
        arr = arr[np.newaxis, ...]
    if arr.ndim != 3:
        raise ValueError(f"Expected gallery as CxYxX or YxX, got shape {arr.shape}")
    return np.asarray(arr)


def parse_kept_labels(results_bytes: bytes) -> set[int]:
    df = pd.read_csv(io.BytesIO(results_bytes))
    if "Label" not in df.columns:
        raise ValueError("Results.csv has no 'Label' column")
    return set(pd.to_numeric(df["Label"], errors="coerce").dropna().astype(int).tolist())


def _triplets_from_outer_zip(path: Path, archive_id: str) -> List[AcquisitionSource]:
    out: List[AcquisitionSource] = []
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if not n.startswith("__MACOSX/")]
        galleries = sorted(n for n in names if n.endswith("___Gallery.zip"))
        for g in galleries:
            base = g[: -len("___Gallery.zip")]
            r = base + "___RoiSet.zip"
            s = base + "___Results.csv"
            if r not in names or s not in names:
                raise FileNotFoundError(f"Incomplete training triplet in {path}: {base}")
            acquisition_id = os.path.basename(base)
            out.append(
                AcquisitionSource(
                    archive_id=archive_id,
                    acquisition_id=acquisition_id,
                    gallery_bytes=z.read(g),
                    roiset_bytes=z.read(r),
                    results_bytes=z.read(s),
                    source_locator=f"{path.name}:{base}",
                )
            )
    return out


def _triplets_from_directory(path: Path, archive_id: str) -> List[AcquisitionSource]:
    out: List[AcquisitionSource] = []
    for g in sorted(path.rglob("*___Gallery.zip")):
        if "__MACOSX" in g.parts:
            continue
        base = str(g)[: -len("___Gallery.zip")]
        r = Path(base + "___RoiSet.zip")
        s = Path(base + "___Results.csv")
        if not r.exists() or not s.exists():
            raise FileNotFoundError(f"Incomplete training triplet: {base}")
        acquisition_id = Path(base).name
        out.append(
            AcquisitionSource(
                archive_id=archive_id,
                acquisition_id=acquisition_id,
                gallery_bytes=g.read_bytes(),
                roiset_bytes=r.read_bytes(),
                results_bytes=s.read_bytes(),
                source_locator=str(Path(base)),
            )
        )
    return out


def discover_sources(inputs: Sequence[Path]) -> List[AcquisitionSource]:
    sources: List[AcquisitionSource] = []
    archive_counter = 0
    for inp in inputs:
        if inp.is_dir():
            # Treat each immediate ZIP as a distinct archive. If there are none,
            # treat the directory itself as one archive and recurse for triplets.
            zips = sorted(p for p in inp.iterdir() if p.is_file() and p.suffix.lower() == ".zip")
            found_outer = False
            for z in zips:
                archive_counter += 1
                group = _triplets_from_outer_zip(z, f"Archive_{archive_counter:03d}")
                if group:
                    sources.extend(group)
                    found_outer = True
                else:
                    archive_counter -= 1
            if not found_outer:
                archive_counter += 1
                sources.extend(_triplets_from_directory(inp, f"Archive_{archive_counter:03d}"))
        elif inp.is_file() and inp.suffix.lower() == ".zip":
            archive_counter += 1
            sources.extend(_triplets_from_outer_zip(inp, f"Archive_{archive_counter:03d}"))
        else:
            raise FileNotFoundError(inp)
    if not sources:
        raise RuntimeError("No Gallery/RoiSet/Results training triplets were discovered")
    return sources


def _historical_masks(box_size: int, quant_size: int) -> Tuple[np.ndarray, np.ndarray]:
    yy, xx = np.mgrid[0:box_size, 0:box_size]
    cx = box_size / 2.0
    cy = box_size / 2.0
    r = np.sqrt((xx + 0.5 - cx) ** 2 + (yy + 0.5 - cy) ** 2)
    inner_radius = quant_size / 2.0
    outer_radius = box_size / 2.0 - 1.0
    center = r <= inner_radius
    band = (r > inner_radius) & (r <= outer_radius)
    return center, band


def _imagej_runtime_masks(box_size: int, quant_size: int) -> Tuple[np.ndarray, np.ndarray]:
    # The central OvalRoi raster is the same pixel-centre ellipse used above.
    center, _ = _historical_masks(box_size, quant_size)
    band_width = box_size / 2.0 - quant_size / 2.0 - 1.0
    if abs(band_width - round(band_width)) > 1e-9:
        raise ValueError("This parity implementation expects an integer Make Band width")
    n = int(round(band_width))
    # ImageJ Make Band creates a byte EDM outside the ROI and then selects 0..n.
    # Byte rounding means the equivalent float-distance cut is < n+0.5.
    distance = distance_transform_edt(~center)
    band = (~center) & (distance < (n + 0.5))
    return center, band


def _hard_invalid(tile: np.ndarray, center: np.ndarray, band: np.ndarray, include_edge_rule: bool = True) -> bool:
    center_values = tile[:, center]
    band_values = tile[:, band]
    if np.isnan(center_values).any() or np.isnan(band_values).any():
        return True
    if (center_values == 0).any() or (band_values == 0).any():
        return True
    if include_edge_rule:
        invalid = np.isnan(tile) | (tile == 0)
        if (
            np.all(invalid[:, 0, :])
            or np.all(invalid[:, -1, :])
            or np.all(invalid[:, :, 0])
            or np.all(invalid[:, :, -1])
        ):
            return True
    return False


def extract_rows(
    sources: Sequence[AcquisitionSource],
    geometry: str = "historical_classifier",
    quant_size: int = 24,
    include_edge_rule: bool = True,
) -> pd.DataFrame:
    records: List[dict] = []
    for source in sources:
        arr = read_gallery(source.gallery_bytes).astype(float, copy=False)
        rois = parse_roi_set(source.roiset_bytes)
        kept = parse_kept_labels(source.results_bytes)
        if not rois:
            continue
        widths = {r["right"] - r["left"] for r in rois}
        heights = {r["bottom"] - r["top"] for r in rois}
        if len(widths) != 1 or len(heights) != 1 or widths != heights:
            raise ValueError(f"Non-square/inconsistent detection ROI geometry in {source.source_locator}")
        box_size = next(iter(widths))
        if geometry == "historical_classifier":
            center_mask, band_mask = _historical_masks(box_size, quant_size)
        elif geometry == "imagej_runtime":
            center_mask, band_mask = _imagej_runtime_masks(box_size, quant_size)
        else:
            raise ValueError(f"Unknown geometry: {geometry}")

        # Hard-invalid_v13b is an audit of the deployed runtime gate, not a
        # property of the historical feature geometry used for coefficient fitting.
        runtime_center_mask, runtime_band_mask = _imagej_runtime_masks(box_size, quant_size)

        for roi in rois:
            y0, x0 = roi["top"], roi["left"]
            tile = arr[:, y0 : y0 + box_size, x0 : x0 + box_size]
            if tile.shape[1:] != (box_size, box_size):
                raise ValueError(f"ROI tile extends outside gallery in {source.source_locator}")

            hard_invalid = _hard_invalid(
                tile, runtime_center_mask, runtime_band_mask, include_edge_rule=include_edge_rule
            )
            channel_stats: List[Tuple[float, float, float, float, float]] = []
            for c in range(tile.shape[0]):
                center = tile[c][center_mask]
                background = tile[c][band_mask]
                center_mean = float(np.mean(center))
                background_mean = float(np.mean(background))
                # ImageJ standard deviation is the sample SD (n-1 denominator).
                background_sd = float(np.std(background, ddof=1))
                if background_sd > 0:
                    local_snr = (center_mean - background_mean) / background_sd
                elif center_mean > background_mean:
                    local_snr = 1e30
                else:
                    local_snr = 0.0
                if abs(background_mean) > 1e-12:
                    background_cv = background_sd / abs(background_mean)
                elif background_sd > 0:
                    background_cv = 1e30
                else:
                    background_cv = 0.0
                channel_stats.append((center_mean, background_mean, background_sd, local_snr, background_cv))

            max_local_snr = max(x[3] for x in channel_stats)
            mean_background_cv = float(np.mean([x[4] for x in channel_stats]))
            manual_label = 0 if roi["roi_index"] in kept else 1
            stroke_label = 0 if roi["stroke"] == GREEN else 1 if roi["stroke"] == RED else -1
            rec = {
                "archive_id": source.archive_id,
                "acquisition_id": source.acquisition_id,
                "roi_id": f"ROI_{roi['roi_index']:04d}",
                "roi_index": roi["roi_index"],
                "manual_label": manual_label,
                "manual_class": "discard" if manual_label else "keep",
                "hard_invalid_v13b": bool(hard_invalid),
                "box_size_px": box_size,
                "quant_size_px": quant_size,
                "channel_count": arr.shape[0],
                "maxLocalSNR": float(max_local_snr),
                "meanBackgroundCV": float(mean_background_cv),
            }
            if stroke_label >= 0:
                rec["roiset_status_label"] = stroke_label
                rec["results_roiset_label_agree"] = bool(stroke_label == manual_label)
            for c, (cm, bm, bs, snr, cv) in enumerate(channel_stats, 1):
                rec[f"centerMean_Channel_{c}"] = cm
                rec[f"backgroundMean_Channel_{c}"] = bm
                rec[f"backgroundSD_Channel_{c}"] = bs
                rec[f"localSNR_Channel_{c}"] = snr
                rec[f"backgroundCV_Channel_{c}"] = cv
            records.append(rec)
    return pd.DataFrame.from_records(records)


def fit_historical_model(rows: pd.DataFrame, exclude_hard_invalid: bool = False) -> dict:
    fit_rows = rows.loc[~rows["hard_invalid_v13b"]].copy() if exclude_hard_invalid else rows.copy()
    X = fit_rows[["maxLocalSNR", "meanBackgroundCV"]].to_numpy(dtype=float)
    y = fit_rows["manual_label"].to_numpy(dtype=int)
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    model = LogisticRegression(
        C=1.0,
        class_weight="balanced",
        solver="lbfgs",
        tol=1e-4,
        max_iter=100,
    )
    model.fit(Xs, y)
    scaled_coef = model.coef_[0]
    raw_coef = scaled_coef / scaler.scale_
    raw_intercept = model.intercept_[0] - np.sum(scaled_coef * scaler.mean_ / scaler.scale_)
    return {
        "rows": fit_rows,
        "scaler": scaler,
        "model": model,
        "coefficients": np.array([raw_intercept, raw_coef[0], raw_coef[1]], dtype=float),
        "scaled_intercept": float(model.intercept_[0]),
        "scaled_coefficients": scaled_coef.astype(float),
    }


def score_with_coefficients(rows: pd.DataFrame, coefficients: Sequence[float]) -> np.ndarray:
    b0, b1, b2 = [float(x) for x in coefficients]
    z = b0 + b1 * rows["maxLocalSNR"].to_numpy(float) + b2 * rows["meanBackgroundCV"].to_numpy(float)
    # numerically stable sigmoid
    out = np.empty_like(z)
    pos = z >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-z[pos]))
    ez = np.exp(z[~pos])
    out[~pos] = ez / (1.0 + ez)
    return out


def archive_holdout_validation(rows: pd.DataFrame, exclude_hard_invalid: bool = False) -> Tuple[pd.DataFrame, pd.DataFrame, float]:
    use = rows.loc[~rows["hard_invalid_v13b"]].copy() if exclude_hard_invalid else rows.copy()
    oof = pd.Series(np.nan, index=use.index, dtype=float)
    folds: List[dict] = []
    for archive in sorted(use["archive_id"].unique()):
        train = use[use["archive_id"] != archive]
        test = use[use["archive_id"] == archive]
        fit = fit_historical_model(train, exclude_hard_invalid=False)
        scaler: StandardScaler = fit["scaler"]
        model: LogisticRegression = fit["model"]
        Xtest = test[["maxLocalSNR", "meanBackgroundCV"]].to_numpy(float)
        p = model.predict_proba(scaler.transform(Xtest))[:, 1]
        oof.loc[test.index] = p
        auc = roc_auc_score(test["manual_label"], p) if test["manual_label"].nunique() == 2 else float("nan")
        folds.append(
            {
                "held_out_archive": archive,
                "n": len(test),
                "kept": int((test["manual_label"] == 0).sum()),
                "discarded": int((test["manual_label"] == 1).sum()),
                "roc_auc": auc,
            }
        )
    pooled_auc = roc_auc_score(use["manual_label"], oof.loc[use.index])
    predictions = use[["archive_id", "acquisition_id", "roi_id", "manual_label", "manual_class"]].copy()
    predictions["out_of_fold_discard_score"] = oof.loc[use.index].to_numpy()
    return pd.DataFrame(folds), predictions, float(pooled_auc)


def acquisition_summary(rows: pd.DataFrame) -> pd.DataFrame:
    return (
        rows.groupby(["archive_id", "acquisition_id"], sort=True)
        .agg(
            candidates=("roi_id", "size"),
            kept=("manual_label", lambda s: int((s == 0).sum())),
            discarded=("manual_label", lambda s: int((s == 1).sum())),
            hard_invalid_v13b=("hard_invalid_v13b", "sum"),
            median_maxLocalSNR=("maxLocalSNR", "median"),
            median_meanBackgroundCV=("meanBackgroundCV", "median"),
        )
        .reset_index()
    )


def write_outputs(
    rows: pd.DataFrame,
    outdir: Path,
    exclude_hard_invalid: bool = False,
    feature_geometry: str = "historical_classifier",
) -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    fit = fit_historical_model(rows, exclude_hard_invalid=exclude_hard_invalid)
    coef = fit["coefficients"]
    folds, oof, auc = archive_holdout_validation(rows, exclude_hard_invalid=exclude_hard_invalid)
    scores = score_with_coefficients(rows, coef)
    rows_out = rows.copy()
    rows_out["fitted_discard_score"] = scores
    rows_out.to_csv(outdir / "training_rows_audit.csv", index=False)
    fit["rows"].to_csv(outdir / "training_rows_used_for_fit.csv", index=False)
    acquisition_summary(rows).to_csv(outdir / "acquisition_summary.csv", index=False)
    folds.to_csv(outdir / "archive_holdout_validation.csv", index=False)
    oof.to_csv(outdir / "out_of_fold_predictions.csv", index=False)
    pd.DataFrame(
        [{
            "intercept": coef[0],
            "beta_maxLocalSNR": coef[1],
            "beta_meanBackgroundCV": coef[2],
            "scaled_intercept": fit["scaled_intercept"],
            "scaled_beta_maxLocalSNR": fit["scaled_coefficients"][0],
            "scaled_beta_meanBackgroundCV": fit["scaled_coefficients"][1],
            "scaler_mean_maxLocalSNR": fit["scaler"].mean_[0],
            "scaler_mean_meanBackgroundCV": fit["scaler"].mean_[1],
            "scaler_scale_maxLocalSNR": fit["scaler"].scale_[0],
            "scaler_scale_meanBackgroundCV": fit["scaler"].scale_[1],
            "archive_holdout_pooled_roc_auc": auc,
            "n_total": len(rows),
            "n_used_for_fit": len(fit["rows"]),
            "n_keep": int((rows["manual_label"] == 0).sum()),
            "n_discard": int((rows["manual_label"] == 1).sum()),
            "n_hard_invalid_v13b": int(rows["hard_invalid_v13b"].sum()),
        }]
    ).to_csv(outdir / "model_coefficients.csv", index=False)

    model_json = {
        "model": "logistic_regression",
        "fit_protocol": "historical_classifier_standardized_balanced_l2",
        "feature_geometry": feature_geometry,
        "hard_invalid_audit_geometry": "imagej_runtime",
        "features": ["maxLocalSNR", "meanBackgroundCV"],
        "coefficients_original_feature_units": {
            "intercept": float(coef[0]),
            "maxLocalSNR": float(coef[1]),
            "meanBackgroundCV": float(coef[2]),
        },
        "standardization": {
            "mean": fit["scaler"].mean_.tolist(),
            "scale": fit["scaler"].scale_.tolist(),
        },
        "logistic_regression": {
            "C": 1.0,
            "class_weight": "balanced",
            "solver": "lbfgs",
            "tol": 1e-4,
            "max_iter": 100,
        },
        "exclude_hard_invalid_from_fit": bool(exclude_hard_invalid),
        "archive_holdout_pooled_roc_auc": auc,
        "versions": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
    }
    try:
        import sklearn
        import scipy
        model_json["versions"]["scikit_learn"] = sklearn.__version__
        model_json["versions"]["scipy"] = scipy.__version__
        model_json["versions"]["tifffile"] = tifffile.__version__
    except Exception:
        pass
    (outdir / "model.json").write_text(json.dumps(model_json, indent=2) + "\n", encoding="utf-8")
    equation = (
        "z = " + f"{coef[0]:.10f}" + f" {coef[1]:+.10f}*maxLocalSNR" + f" {coef[2]:+.10f}*meanBackgroundCV\n"
        "discardScore = 1/(1+exp(-z))\n"
    )
    (outdir / "classifier_equation.txt").write_text(equation, encoding="utf-8")
    return {"coefficients": coef, "pooled_auc": auc, "fit_rows": len(fit["rows"])}


def run_retrainer(
    inputs: Sequence[Path],
    output_dir: Path,
    geometry: str = "historical_classifier",
    quant_size: int = 24,
    exclude_hard_invalid: bool = False,
) -> dict:
    """Run the existing retraining pipeline and return a compact summary."""
    sources = discover_sources(inputs)
    rows = extract_rows(sources, geometry=geometry, quant_size=quant_size, include_edge_rule=True)
    result = write_outputs(
        rows,
        output_dir,
        exclude_hard_invalid=exclude_hard_invalid,
        feature_geometry=geometry,
    )
    return {
        "rows": rows,
        "result": result,
        "archives": int(rows["archive_id"].nunique()),
        "acquisitions": int(rows["acquisition_id"].nunique()),
        "keep": int((rows.manual_label == 0).sum()),
        "discard": int((rows.manual_label == 1).sum()),
        "hard_invalid": int(rows.hard_invalid_v13b.sum()),
    }


def print_run_summary(summary: dict) -> None:
    rows = summary["rows"]
    result = summary["result"]
    print(f"archives={summary['archives']}")
    print(f"acquisitions={summary['acquisitions']}")
    print(f"rows={len(rows)} keep={summary['keep']} discard={summary['discard']}")
    print(f"hard_invalid_v13b={summary['hard_invalid']}")
    c = result["coefficients"]
    print(f"coefficients={c[0]:.10f},{c[1]:.10f},{c[2]:.10f}")
    print(f"archive_holdout_pooled_auc={result['pooled_auc']:.10f}")


def launch_gui() -> None:
    """Open a small desktop launcher when the script is run without CLI arguments."""
    try:
        import threading
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except Exception as exc:
        raise RuntimeError(
            "The GUI requires Python's tkinter module. Use the command-line interface "
            "if tkinter is unavailable."
        ) from exc

    root = tk.Tk()
    root.title("Synaptosome Classifier Retrainer — Version 13b")
    root.minsize(760, 520)

    inputs: List[Path] = []
    output_var = tk.StringVar(value=str(Path.cwd() / "classifier_retrain_output"))
    geometry_var = tk.StringVar(value="historical_classifier")
    quant_var = tk.StringVar(value="24")
    exclude_var = tk.BooleanVar(value=False)
    status_var = tk.StringVar(value="Choose one or more training archives or a parent folder.")

    outer = ttk.Frame(root, padding=14)
    outer.pack(fill="both", expand=True)
    outer.columnconfigure(0, weight=1)
    outer.rowconfigure(2, weight=1)

    ttk.Label(
        outer,
        text="Training inputs",
        font=("TkDefaultFont", 11, "bold"),
    ).grid(row=0, column=0, sticky="w")
    ttk.Label(
        outer,
        text="Add a parent folder to scan recursively, or add one or more analysis ZIP archives.",
    ).grid(row=1, column=0, sticky="w", pady=(2, 6))

    list_frame = ttk.Frame(outer)
    list_frame.grid(row=2, column=0, sticky="nsew")
    list_frame.columnconfigure(0, weight=1)
    list_frame.rowconfigure(0, weight=1)
    input_list = tk.Listbox(list_frame, height=8, exportselection=False)
    input_list.grid(row=0, column=0, sticky="nsew")
    sb = ttk.Scrollbar(list_frame, orient="vertical", command=input_list.yview)
    sb.grid(row=0, column=1, sticky="ns")
    input_list.configure(yscrollcommand=sb.set)

    buttons = ttk.Frame(outer)
    buttons.grid(row=3, column=0, sticky="w", pady=(6, 12))

    def refresh_inputs() -> None:
        input_list.delete(0, "end")
        for path in inputs:
            input_list.insert("end", str(path))

    def add_folder() -> None:
        chosen = filedialog.askdirectory(title="Choose training corpus folder")
        if chosen:
            path = Path(chosen)
            if path not in inputs:
                inputs.append(path)
                refresh_inputs()
            if output_var.get().endswith("classifier_retrain_output"):
                output_var.set(str(path / "classifier_retrain_output"))

    def add_archives() -> None:
        chosen = filedialog.askopenfilenames(
            title="Choose training archive ZIP files",
            filetypes=[("ZIP archives", "*.zip"), ("All files", "*")],
        )
        for name in chosen:
            path = Path(name)
            if path not in inputs:
                inputs.append(path)
        refresh_inputs()

    def remove_selected() -> None:
        selected = list(input_list.curselection())
        for index in reversed(selected):
            del inputs[index]
        refresh_inputs()

    ttk.Button(buttons, text="Add folder…", command=add_folder).pack(side="left")
    ttk.Button(buttons, text="Add ZIP(s)…", command=add_archives).pack(side="left", padx=(6, 0))
    ttk.Button(buttons, text="Remove selected", command=remove_selected).pack(side="left", padx=(6, 0))

    options = ttk.LabelFrame(outer, text="Retraining settings", padding=10)
    options.grid(row=4, column=0, sticky="ew")
    options.columnconfigure(1, weight=1)

    ttk.Label(options, text="Output folder").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
    output_entry = ttk.Entry(options, textvariable=output_var)
    output_entry.grid(row=0, column=1, sticky="ew", pady=4)

    def choose_output() -> None:
        chosen = filedialog.askdirectory(title="Choose output folder")
        if chosen:
            output_var.set(chosen)

    ttk.Button(options, text="Browse…", command=choose_output).grid(row=0, column=2, padx=(8, 0), pady=4)

    ttk.Label(options, text="Feature geometry").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
    geometry_box = ttk.Combobox(
        options,
        textvariable=geometry_var,
        values=("historical_classifier", "imagej_runtime"),
        state="readonly",
        width=24,
    )
    geometry_box.grid(row=1, column=1, sticky="w", pady=4)

    ttk.Label(options, text="Quantification size (px)").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
    ttk.Entry(options, textvariable=quant_var, width=10).grid(row=2, column=1, sticky="w", pady=4)

    ttk.Checkbutton(
        options,
        text="Exclude Version 13b hard-invalid ROIs from fitting (methodological alternative)",
        variable=exclude_var,
    ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 2))

    ttk.Label(
        options,
        text="Default historical mode reproduces the deployed Version 13b fitting definition.",
    ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(0, 4))

    progress = ttk.Progressbar(outer, mode="indeterminate")
    progress.grid(row=5, column=0, sticky="ew", pady=(14, 6))
    status = ttk.Label(outer, textvariable=status_var, wraplength=720)
    status.grid(row=6, column=0, sticky="w")

    run_button = ttk.Button(outer, text="Retrain classifier")
    run_button.grid(row=7, column=0, sticky="e", pady=(12, 0))

    def finish_success(summary: dict, outdir: Path) -> None:
        progress.stop()
        run_button.configure(state="normal")
        result = summary["result"]
        c = result["coefficients"]
        status_var.set(
            f"Complete — {summary['archives']} archives, {summary['acquisitions']} acquisitions, "
            f"{len(summary['rows'])} ROI decisions."
        )
        messagebox.showinfo(
            "Retraining complete",
            "Classifier retraining completed successfully.\n\n"
            f"Output: {outdir}\n"
            f"Rows: {len(summary['rows'])} "
            f"({summary['keep']} keep / {summary['discard']} discard)\n"
            f"Coefficients:\n"
            f"  intercept = {c[0]:.10f}\n"
            f"  maxLocalSNR = {c[1]:.10f}\n"
            f"  meanBackgroundCV = {c[2]:.10f}\n"
            f"Archive-held-out pooled ROC AUC = {result['pooled_auc']:.10f}",
        )

    def finish_error(exc: BaseException) -> None:
        progress.stop()
        run_button.configure(state="normal")
        status_var.set("Failed. See the error message for details.")
        messagebox.showerror("Retraining failed", f"{type(exc).__name__}: {exc}")

    def start_run() -> None:
        if not inputs:
            messagebox.showwarning("No input", "Add at least one parent folder or ZIP archive.")
            return
        try:
            quant_size = int(quant_var.get())
            if quant_size <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid quantification size", "Quantification size must be a positive integer.")
            return
        outdir = Path(output_var.get()).expanduser()
        if not str(outdir).strip():
            messagebox.showwarning("No output folder", "Choose an output folder.")
            return

        geometry = geometry_var.get()
        exclude_hard_invalid = bool(exclude_var.get())
        selected_inputs = list(inputs)
        run_button.configure(state="disabled")
        progress.start(12)
        status_var.set("Scanning inputs, extracting ROI features, fitting the model, and validating archives…")

        def worker() -> None:
            try:
                summary = run_retrainer(
                    selected_inputs,
                    outdir,
                    geometry=geometry,
                    quant_size=quant_size,
                    exclude_hard_invalid=exclude_hard_invalid,
                )
            except BaseException as exc:
                root.after(0, lambda e=exc: finish_error(e))
                return
            root.after(0, lambda s=summary, o=outdir: finish_success(s, o))

        threading.Thread(target=worker, daemon=True).start()

    run_button.configure(command=start_run)
    root.mainloop()


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("inputs", nargs="+", type=Path, help="Training archive ZIP(s) or a directory containing them")
    ap.add_argument("--output-dir", type=Path, default=Path("classifier_retrain_output"))
    ap.add_argument("--geometry", choices=["historical_classifier", "imagej_runtime"], default="historical_classifier")
    ap.add_argument("--quant-size", type=int, default=24)
    ap.add_argument("--exclude-hard-invalid", action="store_true", help="Methodological alternative; not the historical deployed fit")
    return ap.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    # A normal double-click, Spyder Run, or `%runfile script.py --wdir` reaches
    # the GUI. Any real script argument keeps the original command-line path.
    effective_argv = list(sys.argv[1:] if argv is None else argv)
    if not effective_argv:
        launch_gui()
        return

    args = parse_args(effective_argv)
    summary = run_retrainer(
        args.inputs,
        args.output_dir,
        geometry=args.geometry,
        quant_size=args.quant_size,
        exclude_hard_invalid=args.exclude_hard_invalid,
    )
    print_run_summary(summary)


if __name__ == "__main__":
    main()
