"""MNA assembly and kernel — builds the augmented MNA system and manages the G-matrix lifecycle.

MNAAssembler was extracted from EMTPSolver._build_MNA_matrix and
_build_MNA_rhs.  MNAKernel owns the G-matrix lifecycle, dirty detection,
and sparse linear solve dispatch.

PR-4b: _assemble_matrix_impl contains the actual G-matrix assembly logic
(formerly solver._build_MNA_matrix).  Solver methods are now thin wrappers.
"""

from __future__ import annotations

from typing import Dict, List, Optional, TYPE_CHECKING

import numpy as np
import scipy.sparse as sp

from emtp.circuit.nodes import NodeIndexer
from emtp.circuit.elements import VoltageSource
from emtp.engine.stamping import COOStamper, StampingEngine

if TYPE_CHECKING:
    import numpy as np
    import scipy.sparse as sp


class MNAAssembler:
    """Build the (n+m)x(n+m) MNA augmented system.

    Parameters
    ----------
    stamping_engine:
        The engine that manages COO-stamping lifecycle and LU caching.
    indexer:
        Compact node-indexer (must be frozen before assembly).
    """

    def __init__(self, stamping_engine: StampingEngine, indexer: NodeIndexer):
        self._eng = stamping_engine
        self._indexer = indexer

    # -- G-matrix ------------------------------------------------------------

    def begin_G(self, m_vs: int) -> COOStamper:
        return self._eng.begin_G(self._indexer.n, m_vs)

    def finish_G(self, stamper: COOStamper) -> sp.csc_matrix:
        return self._eng.finish_G(stamper)

    def stamp_devices_G(
        self, stamper: COOStamper, devices: List,
    ) -> None:
        self._eng.stamp_devices_G(stamper, devices)

    def stamp_multiport_G(
        self, stamper: COOStamper, multiport_devices: List,
    ) -> None:
        for dev in multiport_devices:
            if dev.contributes_G:
                dev.stamp_G(stamper, self._indexer)

    def stamp_vs_G(
        self, stamper: COOStamper, vs_list: List[VoltageSource],
    ) -> None:
        self._eng.stamp_vs_G(stamper, vs_list)

    # -- RHS vector ----------------------------------------------------------

    def new_rhs(self, size: int) -> np.ndarray:
        return self._eng.ensure_rhs_buf(size)

    def stamp_devices_rhs(
        self, rhs: np.ndarray, devices: List, t: float,
    ) -> None:
        for dev in devices:
            dev.stamp_rhs(rhs, self._indexer, t)

    def stamp_multiport_rhs(
        self, rhs: np.ndarray, multiport_devices: List, t: float,
    ) -> None:
        for dev in multiport_devices:
            dev.stamp_rhs(rhs, self._indexer, t)

    def stamp_current_sources_rhs(
        self,
        rhs: np.ndarray,
        current_sources: Dict,
        t: float,
    ) -> None:
        for source in current_sources.values():
            I_s = source.current_at(t)
            cf = self._indexer.to_compact(source.node_from)
            ct = self._indexer.to_compact(source.node_to)
            if cf >= 0:
                rhs[cf] -= I_s
            if ct >= 0:
                rhs[ct] += I_s

    def stamp_vs_rhs(
        self,
        rhs: np.ndarray,
        vs_list: List[VoltageSource],
        t: float,
    ) -> None:
        n = self._indexer.n
        for k, vs in enumerate(vs_list):
            rhs[n + k] = vs.voltage_at(t)

    def solve(
        self,
        MNA: sp.csc_matrix,
        rhs: np.ndarray,
        vs_list: List[VoltageSource],
    ) -> np.ndarray:
        return self._eng.solve(MNA, rhs, vs_list or [])


# -- MNA Kernel (G-matrix lifecycle + LU solve) --------------------------

class MNAKernel:
    """Sparse MNA matrix lifecycle manager.

    Owns:
    - Matrix dirty detection and rebuild scheduling
    - G-matrix assembly (via _assemble_matrix_impl)
    - LU factorization and linear solve (via StampingEngine)
    - Rebuild reason tracking for diagnostics

    Parameters
    ----------
    solver: EMTPSolver
        The owning solver.  Complex internal state (line nodes, vs_list,
        _mna_size) is still accessed through this reference.
    """

    def __init__(self, solver):
        self._solver = solver
        self._dirty_reasons: list[str] = []

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def ensure_matrix(self) -> "sp.csc_matrix":
        """Return the current MNA matrix, rebuilding if needed."""
        s = self._solver
        eng = s._stamping
        if eng.G_dirty or eng.cached_MNA is None:
            self._assemble_matrix_impl()
            s._cached_MNA = eng.cached_MNA
            s._stats['G_rebuilds'] = s._stats.get('G_rebuilds', 0) + 1
            self._dirty_reasons.clear()
        else:
            s._cached_MNA = eng.cached_MNA
            s._stats['G_cache_hits'] = s._stats.get('G_cache_hits', 0) + 1
        return s._cached_MNA

    def solve(self, MNA: "sp.csc_matrix", rhs: "np.ndarray") -> "np.ndarray":
        """Solve MNA x = rhs via StampingEngine (LU factorization)."""
        s = self._solver
        return s._stamping.solve(MNA, rhs, s._vs_list or [])

    # -----------------------------------------------------------------
    # G-matrix assembly (formerly solver._build_MNA_matrix)
    # -----------------------------------------------------------------

    def _assemble_matrix_impl(self) -> None:
        """Build the augmented MNA sparse matrix (CSC format).

        Delegates device stamping to StampingEngine; inserts transmission
        line and transformer contributions between begin/finish.
        Side-effect: updates solver._vs_list, _vs_index_map, _mna_size.
        """
        s = self._solver
        n = s._indexer.n
        if n == 0:
            raise ValueError("Circuit has no nodes")

        if s._vs_list is None:
            s._vs_list = list(s.voltage_sources.values())
            s._vs_index_map = {
                vs.name: idx for idx, vs in enumerate(s._vs_list)
            }

        m = len(s._vs_list)
        s._mna_size = n + m

        eng = s._stamping
        stamper = eng.begin_G(n, m)

        # 1. branch devices
        eng.stamp_devices_G(stamper, s._devices)

        # 2. transmission lines
        for line in s.transmission_lines.values():
            nk_list, nm_list = s._get_line_nodes(line)
            nc = len(nk_list)
            G_line = line.G_eq

            if not isinstance(G_line, np.ndarray):
                G_line = np.eye(nc) * G_line
            elif G_line.ndim == 1:
                G_line = np.diag(G_line)
            elif G_line.shape != (nc, nc):
                if G_line.shape[0] >= nc and G_line.shape[1] >= nc:
                    G_line = G_line[:nc, :nc]
                else:
                    G_line = np.eye(nc) * G_line[0, 0]

            for i, node_row in enumerate(nk_list):
                if node_row <= 0:
                    continue
                cr = s._indexer.to_compact(node_row)
                for j, node_col in enumerate(nk_list):
                    if node_col > 0:
                        stamper.add(cr, s._indexer.to_compact(node_col), G_line[i, j])
            for i, node_row in enumerate(nm_list):
                if node_row <= 0:
                    continue
                cr = s._indexer.to_compact(node_row)
                for j, node_col in enumerate(nm_list):
                    if node_col > 0:
                        stamper.add(cr, s._indexer.to_compact(node_col), G_line[i, j])

        # 3. UMEC transformers
        for xfmr in s.transformers.values():
            G_tf, _ = xfmr.get_norton_equivalent()
            port_nodes = xfmr.get_port_nodes()
            mp = len(port_nodes)
            for i in range(mp):
                nf_i, nt_i = port_nodes[i]
                cf_i = s._indexer.to_compact(nf_i)
                ct_i = s._indexer.to_compact(nt_i)
                for j in range(mp):
                    nf_j, nt_j = port_nodes[j]
                    cf_j = s._indexer.to_compact(nf_j)
                    ct_j = s._indexer.to_compact(nt_j)
                    g = G_tf[i, j]
                    if cf_i >= 0 and cf_j >= 0:
                        stamper.add(cf_i, cf_j, g)
                    if ct_i >= 0 and ct_j >= 0:
                        stamper.add(ct_i, ct_j, g)
                    if cf_i >= 0 and ct_j >= 0:
                        stamper.add(cf_i, ct_j, -g)
                    if ct_i >= 0 and cf_j >= 0:
                        stamper.add(ct_i, cf_j, -g)

        # 4. voltage sources
        eng.stamp_vs_G(stamper, s._vs_list)

        eng.finish_G(stamper)

    # -----------------------------------------------------------------
    # Dirty detection
    # -----------------------------------------------------------------

    @property
    def is_dirty(self) -> bool:
        """True when the G matrix needs to be rebuilt."""
        return self._solver._stamping._G_dirty

    @property
    def cached_matrix(self):
        """The most recently assembled MNA matrix (or None)."""
        return self._solver._stamping._cached_MNA

    def mark_dirty(self, reason: str = "") -> None:
        """Force a matrix rebuild on the next ensure_matrix() call."""
        self._solver._stamping.mark_dirty()
        if reason:
            self._dirty_reasons.append(reason)

    @property
    def dirty_reasons(self) -> list[str]:
        """Reasons for the most recent dirty events (diagnostics)."""
        return list(self._dirty_reasons)

    # -----------------------------------------------------------------
    # Statistics
    # -----------------------------------------------------------------

    @property
    def rebuild_count(self) -> int:
        return self._solver._stats.get('G_rebuilds', 0)

    @property
    def cache_hit_count(self) -> int:
        return self._solver._stats.get('G_cache_hits', 0)
