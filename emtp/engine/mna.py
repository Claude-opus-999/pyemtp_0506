"""MNA assembly and kernel — builds the augmented MNA system and manages the G-matrix lifecycle.

MNAAssembler was extracted from ``EMTPSolver._build_MNA_matrix`` and
``EMTPSolver._build_MNA_rhs``.  MNAKernel owns the G-matrix lifecycle,
dirty detection, and sparse linear solve dispatch.
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
    """Build the (n+m)×(n+m) MNA augmented system.

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
    - StampingEngine (COOStamper + G assembly)
    - LU factorization cache (SuperLU via scipy.sparse.linalg.splu)
    - Linear solve

    Parameters
    ----------
    solver: EMTPSolver
        The owning solver.  This reference is used as a facade until
        explicit dependencies (stamping_engine, stats) are wired in a
        later PR.
    """

    def __init__(self, solver):
        self._solver = solver
        self._dirty_reasons: list[str] = []

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def ensure_matrix(self) -> "sp.csc_matrix":
        """Return the current MNA matrix, rebuilding if needed.

        Side-effects:
        - Updates solver._stats['G_rebuilds'] / ['G_cache_hits']
        - Updates solver._cached_MNA
        """
        s = self._solver
        eng = s._stamping
        if eng.G_dirty or eng.cached_MNA is None:
            s._build_MNA_matrix()
            s._cached_MNA = eng.cached_MNA
            s._stats['G_rebuilds'] = s._stats.get('G_rebuilds', 0) + 1
            self._dirty_reasons.clear()
        else:
            s._cached_MNA = eng.cached_MNA
            s._stats['G_cache_hits'] = s._stats.get('G_cache_hits', 0) + 1
        return s._cached_MNA

    def solve(self, MNA: "sp.csc_matrix", rhs: "np.ndarray") -> "np.ndarray":
        """Solve MNA · x = rhs using the current LU factorization."""
        return self._solver._solve_mna(MNA, rhs)

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
    # Statistics (delegated to solver._stats for now)
    # -----------------------------------------------------------------

    @property
    def rebuild_count(self) -> int:
        return self._solver._stats.get('G_rebuilds', 0)

    @property
    def cache_hit_count(self) -> int:
        return self._solver._stats.get('G_cache_hits', 0)
