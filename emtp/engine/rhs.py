"""RHSEngine — builds the MNA right-hand-side vector each time step.

PR-3b: The actual RHS building logic now lives here.  Solver methods
_build_MNA_rhs and _build_rhs_fast are thin delegation wrappers.
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
    - The actual slow-path and fast-path RHS assembly logic

    Parameters
    ----------
    solver: EMTPSolver
        The owning solver.  Complex internal state (ULM batch, line inject
        maps) is still accessed through this reference.
    """

    def __init__(self, solver):
        self._solver = solver
        self._rhs_buf: Optional[np.ndarray] = None
        self._plan: Optional[RHSPlan] = None
        self._plan_dirty: bool = True
        self._current_source_samples: Dict[str, np.ndarray] = {}
        self._voltage_source_samples: Dict[str, np.ndarray] = {}

    # -----------------------------------------------------------------
    # Public API — called once per time step
    # -----------------------------------------------------------------

    def build(self) -> np.ndarray:
        """Return the MNA RHS vector (slow path — iterates device objects)."""
        return self._build_slow_impl()

    def build_fast(self) -> np.ndarray:
        """Return the MNA RHS vector (fast path — uses precompiled RHSPlan)."""
        return self._build_fast_impl()

    # -----------------------------------------------------------------
    # Slow-path RHS assembly (formerly solver._build_MNA_rhs)
    # -----------------------------------------------------------------

    def _build_slow_impl(self) -> np.ndarray:
        s = self._solver
        n = s._indexer.n
        m = len(s._vs_list) if s._vs_list else 0
        N = n + m

        rhs = self._rhs_buf
        if rhs is None or rhs.shape[0] != N:
            rhs = np.zeros(N, dtype=np.float64)
            self._rhs_buf = rhs
        else:
            rhs.fill(0.0)

        # ---- 1. branch history sources ----
        for dev in s._devices:
            dev.stamp_rhs(rhs, s._indexer, s.time)

        # ---- 1b. MultiPortDevice history sources ----
        s._stamp_multiport_rhs(rhs, s.time)

        # ---- 2. current sources ----
        if s.pre_sample_sources and self._current_source_samples:
            step_idx = int(round(s.time / s.dt))
            for source in s.current_sources.values():
                I_s = float(self._current_source_samples[source.name][step_idx])
                cf = s._indexer.to_compact(source.node_from)
                ct = s._indexer.to_compact(source.node_to)
                if cf >= 0:
                    rhs[cf] -= I_s
                if ct >= 0:
                    rhs[ct] += I_s
        else:
            for source in s.current_sources.values():
                I_s = source.current_at(s.time)
                cf = s._indexer.to_compact(source.node_from)
                ct = s._indexer.to_compact(source.node_to)
                if cf >= 0:
                    rhs[cf] -= I_s
                if ct >= 0:
                    rhs[ct] += I_s

        # ---- 3. transmission line history sources ----
        batch = getattr(s, '_ulm_batch', None)
        if batch is not None and s._ulm_batch_k_nodes_v is not None:
            if s._ulm_batch_k_nodes_v.size:
                np.add.at(
                    rhs, s._ulm_batch_k_nodes_v,
                    -batch.I_hist_k_batch[
                        s._ulm_batch_k_rows_v, s._ulm_batch_k_slots_v,
                    ],
                )
            if s._ulm_batch_m_nodes_v.size:
                np.add.at(
                    rhs, s._ulm_batch_m_nodes_v,
                    -batch.I_hist_m_batch[
                        s._ulm_batch_m_rows_v, s._ulm_batch_m_slots_v,
                    ],
                )
            line_iter = getattr(s, '_line_inject_maps_nonbatch', [])
        else:
            line_iter = getattr(s, '_line_inject_maps', [])

        for line, k_idx, m_idx, nc, _is_multi, _has_full in line_iter:
            I_hist_k, I_hist_m = s._get_line_history_sources(line)
            arr = np.asarray(I_hist_k)
            if arr.ndim == 0:
                if nc == 1 and k_idx[0] >= 0:
                    rhs[k_idx[0]] -= float(np.real(arr))
            else:
                vals = arr.real.ravel()
                limit = min(nc, len(k_idx), len(vals))
                for i in range(limit):
                    if k_idx[i] >= 0:
                        rhs[k_idx[i]] -= float(vals[i])
            arr = np.asarray(I_hist_m)
            if arr.ndim == 0:
                if nc == 1 and m_idx[0] >= 0:
                    rhs[m_idx[0]] -= float(np.real(arr))
            else:
                vals = arr.real.ravel()
                limit = min(nc, len(m_idx), len(vals))
                for i in range(limit):
                    if m_idx[i] >= 0:
                        rhs[m_idx[i]] -= float(vals[i])

        # ---- 4. UMEC transformer history sources ----
        for xfmr in s.transformers.values():
            _, I_hist_tf = xfmr.get_norton_equivalent()
            port_nodes = xfmr.get_port_nodes()
            for i, (nf_i, nt_i) in enumerate(port_nodes):
                cf_i = s._indexer.to_compact(nf_i)
                ct_i = s._indexer.to_compact(nt_i)
                if cf_i >= 0:
                    rhs[cf_i] -= I_hist_tf[i]
                if ct_i >= 0:
                    rhs[ct_i] += I_hist_tf[i]

        # ---- 5. voltage source excitation E ----
        if s._vs_list:
            if s.pre_sample_sources and self._voltage_source_samples:
                step_idx = int(round(s.time / s.dt))
                for k, vs in enumerate(s._vs_list):
                    rhs[n + k] = float(
                        self._voltage_source_samples[vs.name][step_idx]
                    )
            else:
                for k, vs in enumerate(s._vs_list):
                    rhs[n + k] = vs.voltage_at(s.time)

        return rhs

    # -----------------------------------------------------------------
    # Fast-path RHS assembly (formerly solver._build_rhs_fast)
    # -----------------------------------------------------------------

    def _build_fast_impl(self) -> np.ndarray:
        s = self._solver
        plan = self._plan
        n = s._indexer.n
        m = len(s._vs_list) if s._vs_list else 0
        N = n + m

        rhs = self._rhs_buf
        if rhs is None or rhs.shape[0] != N:
            rhs = np.zeros(N, dtype=np.float64)
            self._rhs_buf = rhs
        else:
            rhs.fill(0.0)

        # ---- 1. branch history sources (flat index arrays) ----
        n_dyn = len(plan.dyn_branch_names)
        for k in range(n_dyn):
            br = s.branches[plan.dyn_branch_names[k]]
            if plan.dyn_branch_type[k] == "NR":
                i_eq = getattr(br, 'Ihist', 0.0)
            else:
                i_eq = br.Ihist
            if i_eq == 0.0:
                continue
            nf_idx = plan.dyn_branch_nf_idx[k]
            nt_idx = plan.dyn_branch_nt_idx[k]
            if nf_idx >= 0:
                rhs[nf_idx] -= i_eq
            if nt_idx >= 0:
                rhs[nt_idx] += i_eq

        # ---- 2. current sources ----
        if s.pre_sample_sources and self._current_source_samples:
            step_idx = int(round(s.time / s.dt))
            n_is = len(plan.isource_names)
            for k in range(n_is):
                I_s = float(
                    self._current_source_samples[plan.isource_names[k]][step_idx]
                )
                if I_s == 0.0:
                    continue
                nf_idx = plan.isource_nf_idx[k]
                nt_idx = plan.isource_nt_idx[k]
                if nf_idx >= 0:
                    rhs[nf_idx] -= I_s
                if nt_idx >= 0:
                    rhs[nt_idx] += I_s
        else:
            n_is = len(plan.isource_names)
            for k in range(n_is):
                source = s.current_sources[plan.isource_names[k]]
                I_s = source.current_at(s.time)
                if I_s == 0.0:
                    continue
                nf_idx = plan.isource_nf_idx[k]
                nt_idx = plan.isource_nt_idx[k]
                if nf_idx >= 0:
                    rhs[nf_idx] -= I_s
                if nt_idx >= 0:
                    rhs[nt_idx] += I_s

        # ---- 3. transmission line history sources ----
        batch = getattr(s, '_ulm_batch', None)
        if batch is not None and s._ulm_batch_k_nodes_v is not None:
            if s._ulm_batch_k_nodes_v.size:
                np.add.at(
                    rhs, s._ulm_batch_k_nodes_v,
                    -batch.I_hist_k_batch[
                        s._ulm_batch_k_rows_v, s._ulm_batch_k_slots_v,
                    ],
                )
            if s._ulm_batch_m_nodes_v.size:
                np.add.at(
                    rhs, s._ulm_batch_m_nodes_v,
                    -batch.I_hist_m_batch[
                        s._ulm_batch_m_rows_v, s._ulm_batch_m_slots_v,
                    ],
                )
            line_iter = getattr(s, '_line_inject_maps_nonbatch', [])
        else:
            line_iter = getattr(s, '_line_inject_maps', [])

        for line, k_idx, m_idx, nc, _is_multi, _has_full in line_iter:
            I_hist_k, I_hist_m = s._get_line_history_sources(line)
            arr = np.asarray(I_hist_k)
            if arr.ndim == 0:
                if nc == 1 and k_idx[0] >= 0:
                    rhs[k_idx[0]] -= float(np.real(arr))
            else:
                vals = arr.real.ravel()
                limit = min(nc, len(k_idx), len(vals))
                for i in range(limit):
                    if k_idx[i] >= 0:
                        rhs[k_idx[i]] -= float(vals[i])
            arr = np.asarray(I_hist_m)
            if arr.ndim == 0:
                if nc == 1 and m_idx[0] >= 0:
                    rhs[m_idx[0]] -= float(np.real(arr))
            else:
                vals = arr.real.ravel()
                limit = min(nc, len(m_idx), len(vals))
                for i in range(limit):
                    if m_idx[i] >= 0:
                        rhs[m_idx[i]] -= float(vals[i])

        # ---- 4. UMEC transformer history sources (flat index arrays) ----
        for x_idx, name in enumerate(plan.xfmr_names):
            xfmr = s.transformers[name]
            _, I_hist_tf = xfmr.get_norton_equivalent()
            nf_arr = plan.xfmr_port_nf_idx[x_idx]
            nt_arr = plan.xfmr_port_nt_idx[x_idx]
            for i in range(len(nf_arr)):
                if nf_arr[i] >= 0:
                    rhs[nf_arr[i]] -= I_hist_tf[i]
                if nt_arr[i] >= 0:
                    rhs[nt_arr[i]] += I_hist_tf[i]

        # ---- 5. voltage source excitation E ----
        if s._vs_list:
            if s.pre_sample_sources and self._voltage_source_samples:
                step_idx = int(round(s.time / s.dt))
                for k, vs in enumerate(s._vs_list):
                    rhs[n + k] = float(
                        self._voltage_source_samples[vs.name][step_idx]
                    )
            else:
                for k, vs in enumerate(s._vs_list):
                    rhs[n + k] = vs.voltage_at(s.time)

        return rhs

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
        """Pre-compile topological index arrays for fast RHS assembly."""
        plan = RHSPlan()

        # reactive branch history sources
        dyn_names, dyn_nf, dyn_nt, dyn_types = [], [], [], []
        for name, branch in circuit.branches.items():
            et = branch.element_type
            if et in (ElementType.INDUCTOR, ElementType.CAPACITOR,
                       ElementType.SERIES_RL, ElementType.NONLINEAR_RESISTOR):
                dyn_names.append(name)
                dyn_nf.append(indexer.to_compact(branch.node_from))
                dyn_nt.append(indexer.to_compact(branch.node_to))
                dyn_types.append(
                    "NR" if et == ElementType.NONLINEAR_RESISTOR else
                    "SRL" if et == ElementType.SERIES_RL else "LC"
                )

        plan.dyn_branch_names = dyn_names
        plan.dyn_branch_nf_idx = np.array(dyn_nf, dtype=int)
        plan.dyn_branch_nt_idx = np.array(dyn_nt, dtype=int)
        plan.dyn_branch_type = dyn_types

        # current sources
        is_names, is_nf, is_nt = [], [], []
        for name, source in circuit.current_sources.items():
            is_names.append(name)
            is_nf.append(indexer.to_compact(source.node_from))
            is_nt.append(indexer.to_compact(source.node_to))
        plan.isource_names = is_names
        plan.isource_nf_idx = np.array(is_nf, dtype=int)
        plan.isource_nt_idx = np.array(is_nt, dtype=int)

        # transformer ports
        for name, xfmr in circuit.transformers.items():
            plan.xfmr_names.append(name)
            port_nodes = xfmr.get_port_nodes()
            plan.xfmr_port_nf_idx.append(
                np.array([indexer.to_compact(nf) for nf, _ in port_nodes], dtype=int))
            plan.xfmr_port_nt_idx.append(
                np.array([indexer.to_compact(nt) for _, nt in port_nodes], dtype=int))

        self._plan = plan
        self._plan_dirty = False
        return plan

    # -----------------------------------------------------------------
    # Source pre-sampling
    # -----------------------------------------------------------------

    def pre_sample_sources(self, n_steps: int, dt: float,
                           current_sources: Dict[str, Any],
                           voltage_sources: Dict[str, Any]) -> None:
        """Pre-sample all independent source waveforms into flat arrays."""
        self._current_source_samples.clear()
        self._voltage_source_samples.clear()
        n_samples = n_steps + 1
        t = np.arange(n_samples) * dt
        for name, source in current_sources.items():
            self._current_source_samples[name] = np.array(
                [source.current_at(ti) for ti in t], dtype=np.float64)
        for name, vs in voltage_sources.items():
            self._voltage_source_samples[name] = np.array(
                [vs.voltage_at(ti) for ti in t], dtype=np.float64)

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
