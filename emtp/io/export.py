"""Export waveforms to NPZ, CSV, and metrics to JSON."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np


# -- NPZ export ----------------------------------------------------------

def export_waveforms_npz(
    waveforms: Dict[str, object],
    result_dir: str | Path,
    *,
    stride: int = 1,
    signal_specs: Optional[dict] = None,
    flatten: bool = False,
) -> Path:
    """Write waveforms to ``waveforms.npz`` and ``waveform_metadata.json``.

    Parameters
    ----------
    waveforms:
        Dict mapping signal name → ndarray or list.
    result_dir:
        Output directory (created if needed).
    stride:
        Downsampling factor.  ``stride=10`` keeps every 10th sample.
    signal_specs:
        Optional ``{name: {kind, unit}}`` hints derived from config probes.
    flatten:
        When ``True``, ravel multi-dimensional signals (legacy behaviour).
        When ``False``, raise ``ValueError`` for ndim > 2 signals.

    Returns
    -------
    Path
        Path to the NPZ file.
    """
    result_dir = Path(result_dir)
    result_dir.mkdir(parents=True, exist_ok=True)

    specs = signal_specs or {}
    arrays = {}
    metadata: dict = {"signals": [], "stride": stride}

    for name, values in waveforms.items():
        arr = np.asarray(values)
        original_shape = list(arr.shape)

        # -- downsample along last axis (time) --------------------------------
        if arr.ndim == 1:
            arr_ds = arr[::stride]
        elif arr.ndim == 2:
            arr_ds = arr[..., ::stride]
        else:
            if flatten:
                arr_ds = arr.ravel()[::stride]
            else:
                raise ValueError(
                    f"Waveform {name!r} has unsupported shape {arr.shape}; "
                    "pass flatten=True or export components separately."
                )

        arrays[name] = arr_ds

        spec = specs.get(name, {})
        metadata["signals"].append({
            "name": name,
            "kind": spec.get("kind", _infer_signal_kind(name)),
            "unit": spec.get("unit", _infer_signal_unit(name)),
            "length": int(arr_ds.shape[-1]) if arr_ds.ndim >= 1 else 0,
            "shape": list(arr_ds.shape),
            "original_shape": original_shape,
            "flattened": bool(flatten and arr.ndim > 1),
            "min": float(np.nanmin(arr_ds)) if arr_ds.size else 0.0,
            "max": float(np.nanmax(arr_ds)) if arr_ds.size else 0.0,
            "peak_abs": float(np.nanmax(np.abs(arr_ds))) if arr_ds.size else 0.0,
        })

    np.savez_compressed(result_dir / "waveforms.npz", **arrays)

    with (result_dir / "waveform_metadata.json").open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    return result_dir / "waveforms.npz"


def collect_waveform_metadata(result_dir: str | Path) -> dict:
    """Read waveform_metadata.json from *result_dir*."""
    with (Path(result_dir) / "waveform_metadata.json").open(encoding="utf-8") as f:
        return json.load(f)


def read_waveform_chunk(
    result_dir: str | Path,
    signal: str,
    start: int = 0,
    count: int = 1000,
) -> dict:
    """Read a chunk of a waveform signal from an NPZ result directory.

    Slices along the last axis (time) for both 1-D and 2-D arrays.
    Returns ``{"signal", "start", "count", "time", "values", "shape"}``.
    """
    if start < 0:
        raise ValueError("start must be >= 0")
    if count <= 0:
        raise ValueError("count must be > 0")

    result_dir = Path(result_dir)
    npz_path = result_dir / "waveforms.npz"

    with np.load(npz_path) as data:
        if "time_s" not in data:
            raise KeyError("waveforms.npz does not contain 'time_s'")
        if signal not in data:
            raise KeyError(f"Signal {signal!r} not found in waveforms.npz")

        time_full = data["time_s"]
        values_full = data[signal]

        end = min(start + count, time_full.shape[0])
        time = time_full[start:end]

        if values_full.ndim == 1:
            values = values_full[start:end]
        elif values_full.ndim == 2:
            values = values_full[..., start:end]
        else:
            raise ValueError(
                f"Signal {signal!r} has unsupported ndim={values_full.ndim}"
            )

    return {
        "signal": signal,
        "start": start,
        "count": int(time.shape[-1]),
        "time": time.tolist(),
        "values": values.tolist(),
        "shape": list(values.shape),
    }


# -- Signal kind / unit inference ----------------------------------------

def _infer_signal_kind(name: str) -> str:
    lower = name.lower()
    if lower in {"time", "time_s", "t"}:
        return "time"
    if lower.startswith("v_") or "voltage" in lower:
        return "voltage"
    if lower.startswith("i_") or "current" in lower:
        return "current"
    if "leader" in lower:
        return "leader_length"
    return "other"


def _infer_signal_unit(name: str) -> str:
    lower = name.lower()
    if lower in {"time", "time_s"}:
        return "s"
    if lower.endswith("_kv"):
        return "kV"
    if lower.endswith("_v"):
        return "V"
    if lower.endswith("_ka"):
        return "kA"
    if lower.endswith("_a"):
        return "A"
    if lower.endswith("_mm"):
        return "mm"
    return ""


# -- CSV export ----------------------------------------------------------

def export_waveforms_csv(
    waveforms: dict,
    result_dir: str | Path,
    *,
    filename: str = "probes.csv",
    stride: int = 1,
) -> Path:
    """Write 1-D waveform signals to a CSV file.

    The first column is ``time_s``; subsequent columns are every other
    1-D signal in *waveforms*.
    """
    result_dir = Path(result_dir)
    result_dir.mkdir(parents=True, exist_ok=True)

    if "time_s" not in waveforms:
        raise ValueError("waveforms must contain 'time_s' for CSV export")

    time = np.asarray(waveforms["time_s"])[::stride]

    # Collect 1-D signal names (exclude time)
    one_d_names = []
    for n, v in waveforms.items():
        if n == "time_s":
            continue
        arr = np.asarray(v)
        if arr.ndim == 1:
            one_d_names.append(n)

    path = result_dir / filename
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["time_s"] + one_d_names)

        for idx in range(len(time)):
            row = [time[idx]]
            for n in one_d_names:
                vals = np.asarray(waveforms[n])[::stride]
                row.append(vals[idx] if idx < len(vals) else "")
            writer.writerow(row)

    return path


# -- JSON metrics export -------------------------------------------------

def export_metrics_json(
    metrics: Dict[str, Any],
    result_dir: str | Path,
    *,
    filename: str = "metrics.json",
) -> Path:
    """Write a metrics dict to *result_dir / filename*.

    Non-JSON-serializable values are converted to strings.
    """
    result_dir = Path(result_dir)
    result_dir.mkdir(parents=True, exist_ok=True)

    safe: Dict[str, Any] = {}
    for k, v in metrics.items():
        try:
            json.dumps(v)
            safe[k] = v
        except (TypeError, ValueError):
            safe[k] = str(v)

    path = result_dir / filename
    with path.open("w", encoding="utf-8") as f:
        json.dump(safe, f, indent=2, ensure_ascii=False)
    return path
