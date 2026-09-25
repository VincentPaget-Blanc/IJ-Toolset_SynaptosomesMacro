#!/usr/bin/env python3
"""Build a neutralized classifier-training corpus from manually reviewed analyses.

Run without arguments to open the desktop GUI. Command-line use remains available:

    python build_redacted_training_corpus.py INPUT [INPUT ...] --output-dir OUTPUT

Inputs may be whole-analysis ZIP files or parent folders. Folder inputs are scanned
recursively for both whole-analysis ZIPs and loose Gallery/RoiSet/Results triplets.
The output contains only neutral Archive_### / Acquisition_### identifiers.

Classifier-relevant information is preserved:
  * Gallery TIFF payload bytes (pixel data/source TIFF payload)
  * ImageJ ROI binary payload bytes (including manual green/red state)
  * Results.csv numeric rows/values

No original-to-redacted name lookup table is written.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


@dataclass
class RawAcquisition:
    gallery_bytes: bytes
    roiset_bytes: bytes
    results_bytes: bytes
    source_locator: str


@dataclass
class SourceGroup:
    acquisitions: List[RawAcquisition]
    source_locator: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _zip_bytes(entries: Sequence[Tuple[str, bytes]]) -> bytes:
    """Create a deterministic ZIP containing the supplied entries."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, payload in entries:
            info = zipfile.ZipInfo(name)
            # Fixed metadata prevents source timestamps/paths from leaking and makes
            # repeated builds deterministic for identical inputs.
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            z.writestr(info, payload)
    return out.getvalue()


def _triplets_from_outer_zip(path: Path) -> List[RawAcquisition]:
    out: List[RawAcquisition] = []
    try:
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if not n.startswith("__MACOSX/")]
            gallery_names = sorted(n for n in names if n.endswith("___Gallery.zip"))
            for gallery_name in gallery_names:
                base = gallery_name[: -len("___Gallery.zip")]
                roi_name = base + "___RoiSet.zip"
                result_name = base + "___Results.csv"
                if roi_name not in names or result_name not in names:
                    continue
                out.append(
                    RawAcquisition(
                        gallery_bytes=z.read(gallery_name),
                        roiset_bytes=z.read(roi_name),
                        results_bytes=z.read(result_name),
                        source_locator=f"{path}:{base}",
                    )
                )
    except zipfile.BadZipFile:
        return []
    return out


def _loose_triplets_grouped(root: Path) -> List[SourceGroup]:
    grouped: Dict[Path, List[RawAcquisition]] = {}
    for gallery in sorted(root.rglob("*___Gallery.zip")):
        if "__MACOSX" in gallery.parts:
            continue
        base = str(gallery)[: -len("___Gallery.zip")]
        roiset = Path(base + "___RoiSet.zip")
        results = Path(base + "___Results.csv")
        if not (roiset.exists() and results.exists()):
            continue
        parent = gallery.parent
        grouped.setdefault(parent, []).append(
            RawAcquisition(
                gallery_bytes=gallery.read_bytes(),
                roiset_bytes=roiset.read_bytes(),
                results_bytes=results.read_bytes(),
                source_locator=base,
            )
        )
    return [SourceGroup(acquisitions=v, source_locator=str(k)) for k, v in sorted(grouped.items(), key=lambda kv: str(kv[0]))]


def acquisition_fingerprint(acq: RawAcquisition) -> str:
    h = hashlib.sha256()
    for payload in (acq.gallery_bytes, acq.roiset_bytes, acq.results_bytes):
        h.update(len(payload).to_bytes(8, "big"))
        h.update(payload)
    return h.hexdigest()


def discover_source_groups(inputs: Sequence[Path]) -> Tuple[List[SourceGroup], int]:
    """Recursively discover outer archives and loose triplets; deduplicate acquisitions."""
    groups: List[SourceGroup] = []

    for inp in inputs:
        inp = inp.expanduser().resolve()
        if inp.is_file():
            if inp.suffix.lower() != ".zip":
                raise ValueError(f"Input file is not a ZIP archive: {inp}")
            acquisitions = _triplets_from_outer_zip(inp)
            if acquisitions:
                groups.append(SourceGroup(acquisitions=acquisitions, source_locator=str(inp)))
            continue
        if not inp.is_dir():
            raise FileNotFoundError(inp)

        # Whole-analysis ZIPs may live at any nesting depth. Gallery.zip/RoiSet.zip
        # files themselves are harmless here because they do not contain triplets.
        for zpath in sorted(inp.rglob("*.zip")):
            if "__MACOSX" in zpath.parts:
                continue
            acquisitions = _triplets_from_outer_zip(zpath)
            if acquisitions:
                groups.append(SourceGroup(acquisitions=acquisitions, source_locator=str(zpath)))

        # Also accept already-extracted analysis folders.
        groups.extend(_loose_triplets_grouped(inp))

    if not groups:
        raise RuntimeError(
            "No complete ___Gallery.zip / ___RoiSet.zip / ___Results.csv training triplets were found."
        )

    seen: set[str] = set()
    duplicates = 0
    deduped_groups: List[SourceGroup] = []
    for group in groups:
        keep: List[RawAcquisition] = []
        for acq in group.acquisitions:
            fp = acquisition_fingerprint(acq)
            if fp in seen:
                duplicates += 1
                continue
            seen.add(fp)
            keep.append(acq)
        if keep:
            deduped_groups.append(SourceGroup(keep, group.source_locator))

    if not deduped_groups:
        raise RuntimeError("Only duplicate training acquisitions were discovered.")
    return deduped_groups, duplicates


def _extract_single_tiff(gallery_zip: bytes) -> Tuple[bytes, str]:
    with zipfile.ZipFile(io.BytesIO(gallery_zip)) as z:
        names = [
            n for n in z.namelist()
            if n.lower().endswith((".tif", ".tiff")) and not n.startswith("__MACOSX/")
        ]
        if len(names) != 1:
            raise ValueError(f"Expected exactly one TIFF in Gallery.zip; found {len(names)}")
        return z.read(names[0]), Path(names[0]).suffix.lower()


def redact_gallery(gallery_zip: bytes, acquisition_id: str) -> Tuple[bytes, str]:
    tiff_payload, suffix = _extract_single_tiff(gallery_zip)
    neutral_suffix = ".tiff" if suffix == ".tiff" else ".tif"
    redacted = _zip_bytes([(f"{acquisition_id}___Gallery{neutral_suffix}", tiff_payload)])
    return redacted, sha256_bytes(tiff_payload)


def _roi_numeric_index(name: str, fallback: int) -> int:
    m = re.search(r"(\d+)(?=\.roi$)", os.path.basename(name), flags=re.IGNORECASE)
    return int(m.group(1)) if m else fallback


def redact_roiset(roiset_zip: bytes) -> Tuple[bytes, List[str]]:
    with zipfile.ZipFile(io.BytesIO(roiset_zip)) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".roi") and not n.startswith("__MACOSX/")]
        if not names:
            raise ValueError("RoiSet.zip contains no .roi files")
        ordered = sorted(enumerate(names, 1), key=lambda pair: _roi_numeric_index(pair[1], pair[0]))
        entries: List[Tuple[str, bytes]] = []
        payload_hashes: List[str] = []
        for fallback, original_name in ordered:
            payload = z.read(original_name)
            roi_index = _roi_numeric_index(original_name, fallback)
            entries.append((f"ROI_{roi_index:04d}.roi", payload))
            payload_hashes.append(sha256_bytes(payload))
    return _zip_bytes(entries), payload_hashes


def _line_ending(first_line: bytes) -> bytes:
    if first_line.endswith(b"\r\n"):
        return b"\r\n"
    if first_line.endswith(b"\n"):
        return b"\n"
    if first_line.endswith(b"\r"):
        return b"\r"
    return b"\n"


def _is_numeric_cell(value: str) -> bool:
    value = value.strip()
    if not value:
        return True
    try:
        float(value)
        return True
    except ValueError:
        return False


def redact_results(results_bytes: bytes) -> Tuple[bytes, str, int]:
    """Redact column names while preserving every data row byte-for-byte."""
    lines = results_bytes.splitlines(keepends=True)
    if not lines:
        raise ValueError("Results.csv is empty")

    encoding = "utf-8-sig" if results_bytes.startswith(b"\xef\xbb\xbf") else "utf-8"
    header_text = lines[0].decode(encoding).rstrip("\r\n")
    header = next(csv.reader([header_text]))
    if not header:
        raise ValueError("Results.csv has an empty header")

    label_indices = [i for i, h in enumerate(header) if h.strip().lower() == "label"]
    if len(label_indices) != 1:
        raise ValueError("Results.csv must contain exactly one 'Label' column")
    label_index = label_indices[0]

    # Training Results are expected to be numeric. Refuse to package unexpected
    # text rather than risk copying an identifier into the distributed corpus.
    for row_number, raw_line in enumerate(lines[1:], start=2):
        text = raw_line.decode("utf-8").rstrip("\r\n")
        if not text.strip():
            continue
        row = next(csv.reader([text]))
        for cell in row:
            if not _is_numeric_cell(cell):
                raise ValueError(
                    f"Results.csv row {row_number} contains non-numeric text {cell!r}; "
                    "redaction stopped to avoid leaking an identifier."
                )

    neutral_header: List[str] = []
    channel_number = 0
    for i, _name in enumerate(header):
        if i == label_index:
            neutral_header.append("Label")
        else:
            channel_number += 1
            neutral_header.append(f"Channel_{channel_number}")

    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="")
    writer.writerow(neutral_header)
    encoded_header = buf.getvalue().encode("utf-8") + _line_ending(lines[0])
    body = b"".join(lines[1:])
    redacted = encoded_header + body
    return redacted, sha256_bytes(body), channel_number


def archive_sha256s(directory: Path) -> List[Tuple[str, str]]:
    return [(p.name, sha256_bytes(p.read_bytes())) for p in sorted(directory.glob("Archive_*.zip"))]


def build_redacted_corpus(inputs: Sequence[Path], output_dir: Path, overwrite: bool = False) -> dict:
    output_dir = output_dir.expanduser().resolve()
    archive_dir = output_dir / "redacted_archives"
    if archive_dir.exists() and any(archive_dir.iterdir()) and not overwrite:
        raise FileExistsError(
            f"Output already contains files: {archive_dir}\n"
            "Choose a new output folder or use --overwrite."
        )
    archive_dir.mkdir(parents=True, exist_ok=True)
    if overwrite:
        for old in archive_dir.glob("Archive_*.zip"):
            old.unlink()

    groups, duplicate_count = discover_source_groups(inputs)
    manifest_rows: List[dict] = []
    acquisition_counter = 0
    gallery_verified = 0
    rois_verified = 0
    results_verified = 0

    for archive_number, group in enumerate(groups, start=1):
        archive_id = f"Archive_{archive_number:03d}"
        outer_entries: List[Tuple[str, bytes]] = []

        for acq in group.acquisitions:
            acquisition_counter += 1
            acquisition_id = f"Acquisition_{acquisition_counter:03d}"

            red_gallery, original_tiff_hash = redact_gallery(acq.gallery_bytes, acquisition_id)
            red_roiset, original_roi_hashes = redact_roiset(acq.roiset_bytes)
            red_results, original_body_hash, channel_count = redact_results(acq.results_bytes)

            # Byte/payload preservation audits.
            red_tiff, _ = _extract_single_tiff(red_gallery)
            if sha256_bytes(red_tiff) != original_tiff_hash:
                raise AssertionError("Gallery TIFF payload changed during redaction")
            gallery_verified += 1

            with zipfile.ZipFile(io.BytesIO(red_roiset)) as rz:
                red_roi_hashes = [sha256_bytes(rz.read(n)) for n in sorted(rz.namelist()) if n.lower().endswith(".roi")]
            if sorted(red_roi_hashes) != sorted(original_roi_hashes):
                raise AssertionError("ROI binary payload changed during redaction")
            rois_verified += len(original_roi_hashes)

            red_lines = red_results.splitlines(keepends=True)
            if sha256_bytes(b"".join(red_lines[1:])) != original_body_hash:
                raise AssertionError("Results.csv data rows changed during redaction")
            results_verified += 1

            outer_entries.extend(
                [
                    (f"{acquisition_id}___Gallery.zip", red_gallery),
                    (f"{acquisition_id}___RoiSet.zip", red_roiset),
                    (f"{acquisition_id}___Results.csv", red_results),
                ]
            )
            manifest_rows.append(
                {
                    "archive_id": archive_id,
                    "acquisition_id": acquisition_id,
                    "roi_count": len(original_roi_hashes),
                    "channel_columns": channel_count,
                    "gallery_tiff_sha256": original_tiff_hash,
                    "results_body_sha256": original_body_hash,
                    "acquisition_fingerprint_sha256": acquisition_fingerprint(acq),
                }
            )

        (archive_dir / f"{archive_id}.zip").write_bytes(_zip_bytes(outer_entries))

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "redaction_manifest.csv"
    fieldnames = [
        "archive_id",
        "acquisition_id",
        "roi_count",
        "channel_columns",
        "gallery_tiff_sha256",
        "results_body_sha256",
        "acquisition_fingerprint_sha256",
    ]
    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(manifest_rows)

    checksums = archive_sha256s(archive_dir)
    (output_dir / "SHA256SUMS.txt").write_text(
        "".join(f"{digest}  redacted_archives/{name}\n" for name, digest in checksums),
        encoding="utf-8",
    )

    audit = {
        "archives": len(groups),
        "acquisitions": acquisition_counter,
        "duplicate_acquisitions_skipped": duplicate_count,
        "gallery_tiff_payloads_verified_identical": gallery_verified,
        "roi_binary_payloads_verified_identical": rois_verified,
        "results_numeric_bodies_verified_identical": results_verified,
        "identifier_mapping_written": False,
        "output_archive_names": [name for name, _ in checksums],
    }
    (output_dir / "redaction_audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    return audit


def launch_gui() -> None:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except Exception as exc:
        raise RuntimeError(
            "The GUI requires Python's tkinter module. Use the command-line interface if tkinter is unavailable."
        ) from exc

    root = tk.Tk()
    root.title("Redacted Training Corpus Builder")
    root.minsize(760, 500)

    inputs: List[Path] = []
    output_var = tk.StringVar(value=str(Path.cwd() / "redacted_training_corpus"))
    overwrite_var = tk.BooleanVar(value=False)
    status_var = tk.StringVar(value="Choose a parent folder or one or more whole-analysis ZIP files.")

    outer = ttk.Frame(root, padding=14)
    outer.pack(fill="both", expand=True)
    outer.columnconfigure(0, weight=1)
    outer.rowconfigure(2, weight=1)

    ttk.Label(outer, text="Manual-analysis inputs", font=("TkDefaultFont", 11, "bold")).grid(row=0, column=0, sticky="w")
    ttk.Label(
        outer,
        text="Folders are searched recursively for complete Gallery / RoiSet / Results training triplets.",
    ).grid(row=1, column=0, sticky="w", pady=(2, 6))

    list_frame = ttk.Frame(outer)
    list_frame.grid(row=2, column=0, sticky="nsew")
    list_frame.columnconfigure(0, weight=1)
    list_frame.rowconfigure(0, weight=1)
    input_list = tk.Listbox(list_frame, height=8, exportselection=False)
    input_list.grid(row=0, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(list_frame, orient="vertical", command=input_list.yview)
    scroll.grid(row=0, column=1, sticky="ns")
    input_list.configure(yscrollcommand=scroll.set)

    def refresh() -> None:
        input_list.delete(0, "end")
        for p in inputs:
            input_list.insert("end", str(p))

    def add_folder() -> None:
        chosen = filedialog.askdirectory(title="Choose parent folder containing manual analyses")
        if chosen:
            p = Path(chosen)
            if p not in inputs:
                inputs.append(p)
                refresh()
            if output_var.get().endswith("redacted_training_corpus"):
                output_var.set(str(p / "redacted_training_corpus"))

    def add_zips() -> None:
        chosen = filedialog.askopenfilenames(
            title="Choose whole-analysis ZIP files",
            filetypes=[("ZIP archives", "*.zip"), ("All files", "*")],
        )
        for name in chosen:
            p = Path(name)
            if p not in inputs:
                inputs.append(p)
        refresh()

    def remove_selected() -> None:
        for index in reversed(input_list.curselection()):
            del inputs[index]
        refresh()

    buttons = ttk.Frame(outer)
    buttons.grid(row=3, column=0, sticky="w", pady=(6, 12))
    ttk.Button(buttons, text="Add folder…", command=add_folder).pack(side="left")
    ttk.Button(buttons, text="Add ZIP(s)…", command=add_zips).pack(side="left", padx=(6, 0))
    ttk.Button(buttons, text="Remove selected", command=remove_selected).pack(side="left", padx=(6, 0))

    settings = ttk.LabelFrame(outer, text="Output", padding=10)
    settings.grid(row=4, column=0, sticky="ew")
    settings.columnconfigure(1, weight=1)
    ttk.Label(settings, text="Output folder").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
    ttk.Entry(settings, textvariable=output_var).grid(row=0, column=1, sticky="ew", pady=4)

    def choose_output() -> None:
        chosen = filedialog.askdirectory(title="Choose output folder")
        if chosen:
            output_var.set(chosen)

    ttk.Button(settings, text="Browse…", command=choose_output).grid(row=0, column=2, padx=(8, 0), pady=4)
    ttk.Checkbutton(settings, text="Overwrite existing redacted Archive_*.zip files", variable=overwrite_var).grid(
        row=1, column=0, columnspan=3, sticky="w", pady=(6, 2)
    )
    ttk.Label(
        settings,
        text="No original-to-redacted name mapping is written. Unexpected non-numeric Results text stops the build.",
    ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(2, 4))

    progress = ttk.Progressbar(outer, mode="indeterminate")
    progress.grid(row=5, column=0, sticky="ew", pady=(14, 6))
    ttk.Label(outer, textvariable=status_var, wraplength=720).grid(row=6, column=0, sticky="w")
    run_button = ttk.Button(outer, text="Build redacted corpus")
    run_button.grid(row=7, column=0, sticky="e", pady=(12, 0))

    def finish_success(audit: dict, outdir: Path) -> None:
        progress.stop()
        run_button.configure(state="normal")
        status_var.set(
            f"Complete — {audit['archives']} archives, {audit['acquisitions']} acquisitions, "
            f"{audit['roi_binary_payloads_verified_identical']} ROI payloads verified."
        )
        messagebox.showinfo(
            "Corpus build complete",
            "Redacted training corpus built successfully.\n\n"
            f"Output: {outdir}\n"
            f"Archives: {audit['archives']}\n"
            f"Acquisitions: {audit['acquisitions']}\n"
            f"ROI payloads verified: {audit['roi_binary_payloads_verified_identical']}\n"
            f"Duplicate acquisitions skipped: {audit['duplicate_acquisitions_skipped']}",
        )

    def finish_error(exc: BaseException) -> None:
        progress.stop()
        run_button.configure(state="normal")
        status_var.set("Failed. See the error message for details.")
        messagebox.showerror("Corpus build failed", f"{type(exc).__name__}: {exc}")

    def start_run() -> None:
        if not inputs:
            messagebox.showwarning("No input", "Add at least one parent folder or ZIP archive.")
            return
        out_text = output_var.get().strip()
        if not out_text:
            messagebox.showwarning("No output folder", "Choose an output folder.")
            return
        outdir = Path(out_text)
        selected_inputs = list(inputs)
        overwrite = bool(overwrite_var.get())
        run_button.configure(state="disabled")
        progress.start(12)
        status_var.set("Scanning recursively, redacting identifiers, and verifying preserved training payloads…")

        def worker() -> None:
            try:
                audit = build_redacted_corpus(selected_inputs, outdir, overwrite=overwrite)
            except BaseException as exc:
                root.after(0, lambda e=exc: finish_error(e))
                return
            root.after(0, lambda a=audit, o=outdir: finish_success(a, o))

        threading.Thread(target=worker, daemon=True).start()

    run_button.configure(command=start_run)
    root.mainloop()


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("inputs", nargs="+", type=Path, help="Whole-analysis ZIP(s) or parent folder(s) to scan recursively")
    ap.add_argument("--output-dir", type=Path, required=True, help="Destination for the redacted corpus")
    ap.add_argument("--overwrite", action="store_true", help="Replace existing redacted Archive_*.zip outputs")
    return ap.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    effective_argv = list(sys.argv[1:] if argv is None else argv)
    if not effective_argv:
        launch_gui()
        return
    args = parse_args(effective_argv)
    audit = build_redacted_corpus(args.inputs, args.output_dir, overwrite=args.overwrite)
    print(f"archives={audit['archives']}")
    print(f"acquisitions={audit['acquisitions']}")
    print(f"duplicates_skipped={audit['duplicate_acquisitions_skipped']}")
    print(f"gallery_tiff_payloads_verified={audit['gallery_tiff_payloads_verified_identical']}")
    print(f"roi_binary_payloads_verified={audit['roi_binary_payloads_verified_identical']}")
    print(f"results_bodies_verified={audit['results_numeric_bodies_verified_identical']}")


if __name__ == "__main__":
    main()
