"""RHSEngine — builds the MNA right-hand-side vector each time step.

PR-3: Now owns RHS buffer, plan compilation, source pre-sampling,
and plan invalidation.  The build logic still delegates to solver
for now; full extraction is PR-3b.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

import numpy as np

from emtp.circuit.elements import RHSPlan, ElementType

if TYPE_CHECKING:
    from emtp.circuit.nodes import NodeIndexer
    from emtp.circuit.model import CircuitModel


class RHSEngine:
    """Right-hand-side assembler for MNA transient simulation.

    Owns:
    - RHS buffer management (reuse across steps)
    - RHSPlan compilation and fast-path application
    - Source pre-sampling buffers
    - Plan dirty tracking and invalidation

    Parameters
    ----------
    solver: EMTPSolver
        The owning solver.  Delegate reference; will be replaced
        with explicit circuit + indexer + options in PR-3b.
    """

    def __init__(self, solver):
        self._solver = solver
        self._rhs_buf: Optional[np.ndarray] = None
        self._plan: Optional[RHSPlan] = None
        self._plan_dirty: bool = True
        self._current_source_samples: Dict[str, np.ndarray] = {}
        self._voltage_source_samples: Dict[str, np.ndarray] = {}

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def build(self) -> "np.ndarray":
        """Return the MNA right-hand-side vector for the current time step."""
        return self._solver._build_MNA_rhs()

    def build_fast(self) -> "np.ndarray":
        """Return the RHS via precompiled RHSPlan (fast path)."""
        return self._solver._build_rhs_fast()

    # -----------------------------------------------------------------
    # Plan management
    # -----------------------------------------------------------------

    @property
    def plan(self) -> Optional[RHSPlan]:
        return self._plan

    @plan.setter
    def plan(self, value: Optional[RHSPlan]) -> None:
        self._plan = value

    @property
    def plan_dirty(self) -> bool:
        return self._plan_dirty

    def invalidate_plan(self) -> None:
        """Mark the compiled RHS plan as dirty (topology changed)."""
        self._plan_dirty = True

    def compile_plan(self, circuit: "CircuitModel", indexer: "NodeIndexer") -> RHSPlan:
        """Pre-compile topological index arrays for fast RHS assembly.

        Builds flat arrays of node indices for reactive branches,
        current sources, and transformer ports so the per-step RHS
        construction avoids iterating Python device objects.
        """
        plan = RHSPlan()

        # ---- reactive branch history sources ----
        dyn_names = []
        dyn_nf = []
        dyn_nt = []
        dyn_types = []
        for name, branch in circuit.branches.items():
            et = branch.element_type
            if et in (ElementType.INDUCTOR, ElementType.CAPACITOR,
                       ElementType.SERIES_RL, ElementType.NONLINEAR_RESISTOR):
                dyn_names.append(name)
                dyn_nf.append(indexer.to_compact(branch.node_from))
                dyn_nt.append(indexer.to_compact(branch.node_to))
                if et == ElementType.NONLINEAR_RESISTOR:
                    dyn_types.append("NR")
                elif et == ElementType.SERIES_RL:
                    dyn_types.append("SRL")
                else:
                    dyn_types.append("LC")

        plan.dyn_branch_names = dyn_names
        plan.dyn_branch_nf_idx = np.array(dyn_nf, dtype=int)
        plan.dyn_branch_nt_idx = np.array(dyn_nt, dtype=int)
        plan.dyn_branch_type = dyn_types

        # ---- current sources ----
        is_names = []
        is_nf = []
        is_nt = []
        for name, source in circuit.current_sources.items():
            is_names.append(name)
            is_nf.append(indexer.to_compact(source.node_from))
            is_nt.append(indexer.to_compact(source.node_to))

        plan.isource_names = is_names
        plan.isource_nf_idx = np.array(is_nf, dtype=int)
        plan.isource_nt_idx = np.array(is_nt, dtype=int)

        # ---- transformer ports ----
        for name, xfmr in circuit.transformers.items():
            plan.xfmr_names.append(name)
            port_nodes = xfmr.get_port_nodes()
            nf_arr = np.array([indexer.to_compact(nf) for nf, _ in port_nodes],
                              dtype=int)
            nt_arr = np.array([indexer.to_compact(nt) for _, nt in port_nodes],
                              dtype=int)
            plan.xfmr_port_nf_idx.append(nf_arr)
            plan.xfmr_port_nt_idx.append(nt_arr)

        self._plan = plan
        self._plan_dirty = False
        return plan

    # -----------------------------------------------------------------
    # Source pre-sampling
    # -----------------------------------------------------------------

    def pre_sample_sources(self, n_steps: int, dt: float,
                           current_sources: Dict[str, Any],
                           voltage_sources: Dict[str, Any]) -> None:
        """Pre-sample all independent source waveforms into flat arrays.

        Parameters
        ----------
        n_steps:
            Number of simulation time steps.
        dt:
            Time step size.
        current_sources:
            Dict of current source objects with ``current_at(t)`` method.
        voltage_sources:
            Dict of voltage source objects with ``voltage_at(t)`` method.
        """
        self._current_source_samples.clear()
        self._voltage_source_samples.clear()

        n_samples = n_steps + 1
        t = np.arange(n_samples) * dt

        for name, source in current_sources.items():
            self._current_source_samples[name] = np.array(
                [source.current_at(ti) for ti in t], dtype=np.float64,
            )

        for name, vs in voltage_sources.items():
            self._voltage_source_samples[name] = np.array(
                [vs.voltage_at(ti) for ti in t], dtype=np.float64,
            )

    # -----------------------------------------------------------------
    # Buffer management
    # -----------------------------------------------------------------

    @property
    def rhs_buf(self) -> Optional[np.ndarray]:
        return self._rhs_buf

    def ensure_rhs_buf(self, size: int) -> np.ndarray:
        """Return a zeroed RHS buffer of at least *size* elements."""
        if self._rhs_buf is None or self._rhs_buf.shape[0] != size:
            self._rhs_buf = np.zeros(size, dtype=np.float64)
        else:
            self._rhs_buf.fill(0.0)
        return self._rhs_buf

    @property
    def current_source_samples(self) -> Dict[str, np.ndarray]:
        return self._current_source_samples

    @property
    def voltage_source_samples(self) -> Dict[str, np.ndarray]:
        return self._voltage_source_samples
