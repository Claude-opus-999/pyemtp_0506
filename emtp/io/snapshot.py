"""Save/restore solver state — snapshot serialization, hashing, and metadata."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import numpy as np


# -- Metadata schema -----------------------------------------------------

@dataclass
class SnapshotMetadata:
    """Immutable metadata written alongside a solver snapshot."""

    schema_version: str
    solver_version: str = "0.2.0"
    case_name: str = ""
    time: float = 0.0
    step_index: int = 0
    dt: float = 0.0
    finish_time: float = 0.0
    config_hash: str = ""
    topology_hash: str = ""
    created_at: str = ""
    notes: str = ""


# -- Hashing -------------------------------------------------------------

def stable_json_hash(obj) -> str:
    """Return a deterministic SHA-256 hex digest for a JSON-serializable *obj*."""
    raw = json.dumps(obj, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def compute_config_hash(config) -> str:
    """Compute config hash from a :class:`CaseConfig` or compatible dict."""
    if hasattr(config, "__dataclass_fields__"):
        from dataclasses import asdict
        return stable_json_hash(asdict(config))
    return stable_json_hash(config)


def compute_topology_hash(solver) -> str:
    """Return a hash that changes only when circuit topology changes.

    Covers branch names/types/nodes, line names, and VS names.
    """
    topology = {
        "branches": sorted(
            (
                b.name,
                str(b.element_type),
                b.node_from,
                b.node_to,
            )
            for b in solver.branches.values()
            if hasattr(b, "name")
        ),
        "lines": sorted(
            name for name in getattr(solver, "transmission_lines", {})
        ),
        "transformers": sorted(
            name for name in getattr(solver, "transformers", {})
        ),
        "voltage_sources": sorted(
            vs.name for vs in getattr(solver, "voltage_sources", {}).values()
        ),
    }
    return stable_json_hash(topology)


# -- Serializer ----------------------------------------------------------

def save_snapshot(
    solver, path, *, config=None, notes: str = "", solver_version: str = "0.2.0",
) -> None:
    """Save the current solver state to *path*.

    Creates the directory if it does not exist and writes::

        metadata.json   — SnapshotMetadata
        branches.json   — per-branch dynamic state
        arrays.npz      — optional large arrays (last solution, etc.)
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)

    # -- metadata ------------------------------------------------------------
    config_hash = ""
    if config is not None:
        config_hash = compute_config_hash(config)

    topology_hash = compute_topology_hash(solver)

    meta = SnapshotMetadata(
        schema_version="0.1.0",
        solver_version=solver_version,
        case_name=getattr(config, "case_name", "") if config else "",
        time=solver.time,
        step_index=solver.step_count,
        dt=solver.dt,
        finish_time=solver.finish_time,
        config_hash=config_hash,
        topology_hash=topology_hash,
        created_at=datetime.now(timezone.utc).isoformat(),
        notes=notes,
    )

    with (path / "metadata.json").open("w", encoding="utf-8") as f:
        json.dump(_dataclass_to_dict(meta), f, indent=2, ensure_ascii=False)

    # -- branches ------------------------------------------------------------
    branches_data = []
    for br in solver.branches.values():
        branches_data.append({
            "name": br.name,
            "current": float(br.current),
            "voltage": float(br.voltage),
            "current_prev": float(br.current_prev),
            "voltage_prev": float(br.voltage_prev),
            "Geq": float(br.Geq),
            "Ihist": float(br.Ihist),
            "Rp": float(getattr(br, "Rp", 0.0)),
            "Geq_damping": float(getattr(br, "Geq_damping", 0.0)),
            "is_closed": bool(getattr(br, "is_closed", False)),
            "value": float(br.value),
        })

    with (path / "branches.json").open("w", encoding="utf-8") as f:
        json.dump(branches_data, f, indent=2, ensure_ascii=False)

    # -- arrays --------------------------------------------------------------
    arrays = {}
    np.savez_compressed(path / "arrays.npz", **arrays)

    # -- line states ---------------------------------------------------------
    _save_line_states(solver, path)

    # -- LPM states ----------------------------------------------------------
    _save_lpm_states(solver, path)


def _save_line_states(solver, path) -> None:
    """Save per-line dynamic state.

    Lines with a ``get_state_dict`` method (e.g. BergeronLine) export
    full dynamic state including delay buffers.  Other lines fall back
    to saving I_hist only, with ``snapshot_support: partial``.
    """
    line_states = {}
    support_info: dict = {}

    for name, line in solver.transmission_lines.items():
        if hasattr(line, "get_state_dict"):
            line_states[name] = line.get_state_dict()
            support_info[name] = "full"
        else:
            state: dict = {"snapshot_support": "partial"}
            if hasattr(line, "I_hist_k"):
                state["I_hist_k"] = _to_jsonable(line.I_hist_k)
            if hasattr(line, "I_hist_m"):
                state["I_hist_m"] = _to_jsonable(line.I_hist_m)
            line_states[name] = state
            support_info[name] = "partial"

    if line_states:
        with (path / "lines.json").open("w", encoding="utf-8") as f:
            json.dump(line_states, f, indent=2, ensure_ascii=False)

    # snapshot support metadata — detect dynamically
    support_meta = _detect_snapshot_support(solver)
    with (path / "snapshot_support.json").open("w", encoding="utf-8") as f:
        json.dump(support_meta, f, indent=2, ensure_ascii=False)


def _detect_snapshot_support(solver) -> dict:
    """Determine snapshot support level for each model category."""
    support = {
        "branch": "partial",
        "lpm": "partial",
        "umec": "partial",
        "ulm": "unsupported",
        "bergeron": "unsupported",
    }

    lines = getattr(solver, "transmission_lines", {})
    if lines:
        all_full = all(
            hasattr(line, "get_state_dict") and hasattr(line, "set_state_dict")
            for line in lines.values()
        )
        support["bergeron"] = "full" if all_full else "partial"

    return support


def _to_jsonable(value):
    """Convert a numeric or array value to a JSON-serializable form."""
    if isinstance(value, (int, float)):
        return value
    arr = np.asarray(value)
    if arr.ndim == 0:
        return float(arr)
    return arr.tolist()


def _save_lpm_states(solver, path) -> None:
    """Save LPM insulator states."""
    lpm_data = {}
    for name, lpm in getattr(solver, "_lpm_elements", {}).items():
        lpm_data[name] = {
            "is_flashed_over": bool(getattr(lpm, "is_flashed_over", False)),
            "R_current": float(getattr(lpm, "R_current", 1e9)),
            "G_current": float(getattr(lpm, "G_current", 1e-9)),
        }
        if hasattr(lpm, "leader_length"):
            lpm_data[name]["leader_length"] = float(lpm.leader_length)

    if lpm_data:
        with (path / "lpm.json").open("w", encoding="utf-8") as f:
            json.dump(lpm_data, f, indent=2, ensure_ascii=False)


def _dataclass_to_dict(obj) -> dict:
    """Convert a dataclass instance to a plain dict."""
    if hasattr(obj, "__dataclass_fields__"):
        return {f: _dataclass_to_dict(getattr(obj, f)) for f in obj.__dataclass_fields__}
    return obj


# -- Restore -------------------------------------------------------------

def load_snapshot_into_solver(solver, path, *, strict: bool = True) -> None:
    """Restore dynamic state from *path* into an already-configured *solver*.

    The solver must already have the correct topology (branches, lines,
    transformers).  This function only restores dynamic state: branch
    currents/voltages, history sources, LPM state, line state, etc.

    Parameters
    ----------
    solver:
        Pre-configured :class:`EMTPSolver` with matching topology.
    path:
        Snapshot directory (contains metadata.json, branches.json, ...).
    strict:
        If ``True``, validate dt, topology_hash, and raise on
        unsupported snapshot support levels.
    """
    path = Path(path)

    meta = json.loads((path / "metadata.json").read_text(encoding="utf-8"))

    if strict:
        _check_snapshot_metadata(solver, meta)

    # -- branches -----------------------------------------------------------
    if (path / "branches.json").exists():
        branch_states = json.loads((path / "branches.json").read_text(encoding="utf-8"))
        by_name = {b.name: b for b in solver.branches.values()}

        for state in branch_states:
            name = state["name"]
            if name not in by_name:
                if strict:
                    raise ValueError(f"Snapshot branch {name!r} not found in solver")
                continue
            br = by_name[name]
            br.current = state.get("current", 0.0)
            br.voltage = state.get("voltage", 0.0)
            br.current_prev = state.get("current_prev", 0.0)
            br.voltage_prev = state.get("voltage_prev", 0.0)
            br.Geq = state.get("Geq", 0.0)
            br.Ihist = state.get("Ihist", 0.0)
            br.Rp = state.get("Rp", 0.0)
            br.Geq_damping = state.get("Geq_damping", 0.0)
            br.is_closed = state.get("is_closed", False)
            br.value = state.get("value", br.value)

    # -- line states --------------------------------------------------------
    if (path / "lines.json").exists():
        line_states = json.loads((path / "lines.json").read_text(encoding="utf-8"))
        for name, state in line_states.items():
            if name not in solver.transmission_lines:
                if strict:
                    raise ValueError(f"Snapshot line {name!r} not found in solver")
                continue

            line = solver.transmission_lines[name]

            if hasattr(line, "set_state_dict"):
                line.set_state_dict(state)
            else:
                if strict and state.get("snapshot_support") == "partial":
                    raise ValueError(
                        f"Line {name!r} only has partial snapshot support. "
                        "Re-run with strict=False to load partial state."
                    )
                if "I_hist_k" in state and hasattr(line, "I_hist_k"):
                    line.I_hist_k = state["I_hist_k"]
                if "I_hist_m" in state and hasattr(line, "I_hist_m"):
                    line.I_hist_m = state["I_hist_m"]

    # -- LPM states ---------------------------------------------------------
    if (path / "lpm.json").exists():
        lpm_data = json.loads((path / "lpm.json").read_text(encoding="utf-8"))
        for name, state in lpm_data.items():
            if name not in solver._lpm_elements:
                if strict:
                    raise ValueError(f"Snapshot LPM {name!r} not found in solver")
                continue
            lpm = solver._lpm_elements[name]
            if hasattr(lpm, "is_flashed_over"):
                lpm.is_flashed_over = state.get("is_flashed_over", False)
            if hasattr(lpm, "R_current"):
                lpm.R_current = state.get("R_current", 1e9)
            if hasattr(lpm, "G_current"):
                lpm.G_current = state.get("G_current", 1e-9)
            if hasattr(lpm, "leader_length") and "leader_length" in state:
                lpm.leader_length = state.get("leader_length", 0.0)

    # -- sync solver metadata -----------------------------------------------
    solver.time = meta.get("time", 0.0)
    solver.step_count = meta.get("step_index", 0)

    # Mark lines as compiled so compile_transmission_lines (called by
    # run_until) skips re-initialisation, preserving restored delay buffers.
    solver._lines_compiled = True

    # Ensure G_eq is set on restored Bergeron lines (normally done by
    # initialize(), which we must skip to avoid buffer wipe).
    for line in solver.transmission_lines.values():
        if hasattr(line, "Zc") and getattr(line, "G_eq", 0.0) == 0.0:
            line.G_eq = 1.0 / max(float(line.Zc), 1e-9)
            if hasattr(line, "G_eq_k"):
                line.G_eq_k = line.G_eq
            if hasattr(line, "G_eq_m"):
                line.G_eq_m = line.G_eq

    # Force MNA rebuild on next solve
    solver._reset_caches()
    solver.mark_topology_changed("snapshot restore")


def _check_snapshot_metadata(solver, meta: dict) -> None:
    """Validate snapshot dt and topology_hash against current solver state."""
    snap_dt = meta.get("dt")
    if snap_dt is not None and abs(snap_dt - solver.dt) > 1e-30:
        raise ValueError(
            f"Snapshot dt ({snap_dt}) does not match solver dt ({solver.dt})"
        )

    expected_hash = meta.get("topology_hash")
    if expected_hash:
        actual_hash = compute_topology_hash(solver)
        if actual_hash != expected_hash:
            raise ValueError(
                "Snapshot topology_hash does not match current solver topology. "
                f"Expected: {expected_hash[:16]}..., "
                f"Actual:   {actual_hash[:16]}..."
            )
