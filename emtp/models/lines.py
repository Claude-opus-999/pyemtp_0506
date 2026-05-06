"""Transmission-line models — Bergeron (constant-parameter) and ULM (frequency-dependent)."""

import numpy as np

from emtp.models.multiport import MultiPortDevice


# -- Bergeron line device -------------------------------------------------

class BergeronLineDevice:
    """MultiPortDevice adapter for a lossless constant-parameter Bergeron line.

    The underlying Bergeron model treats each end as a port referenced to
    ground.  For a single-phase line::

        ports = ((node_k, 0), (node_m, 0))

    The equivalent conductance ``G_eq = 1 / Zc`` is stamped on the diagonal
    at both ends, and the history currents ``I_hist_k`` / ``I_hist_m`` are
    injected into the RHS according to the transmission-line convention
    documented in ``DIRECTION_CONVENTIONS.md``.
    """

    def __init__(self, name: str, impl, node_k: int, node_m: int):
        self.name = name
        self.impl = impl          # BergeronLine (transmission_line_emtp_v2)
        self._node_k = node_k
        self._node_m = node_m
        self._vk: float = 0.0
        self._vm: float = 0.0

    # -- MultiPortDevice port topology ----------------------------------------

    @property
    def ports(self):
        return ((self._node_k, 0), (self._node_m, 0))

    @property
    def contributes_G(self) -> bool:
        return True

    @property
    def is_dynamic(self) -> bool:
        return True

    def register_nodes(self, indexer) -> None:
        indexer.register(self._node_k)
        indexer.register(self._node_m)

    # -- MNA stamping ---------------------------------------------------------

    def stamp_G(self, stamper, indexer) -> None:
        G_eq = float(self.impl.G_eq)
        ck = indexer.to_compact(self._node_k)
        cm = indexer.to_compact(self._node_m)
        stamper.add(ck, ck, G_eq)
        stamper.add(cm, cm, G_eq)

    def stamp_rhs(self, rhs, indexer, t: float) -> None:
        ck = indexer.to_compact(self._node_k)
        cm = indexer.to_compact(self._node_m)
        rhs[ck] -= float(self.impl.I_hist_k)
        rhs[cm] -= float(self.impl.I_hist_m)

    # -- post-solve update ----------------------------------------------------

    def update_after_solve(self, V, indexer, t: float) -> None:
        ck = indexer.to_compact(self._node_k)
        cm = indexer.to_compact(self._node_m)
        self._vk = float(V[ck])
        self._vm = float(V[cm])

    def update_history(self, V, indexer, dt: float) -> None:
        self.impl.update_state(self._vk, self._vm)
        self.impl.update_history_sources()

    def check_rebuild_required(self, V, indexer, t: float) -> bool:
        return False

    def reset_state(self) -> None:
        self._vk = 0.0
        self._vm = 0.0


# -- ULM line device ------------------------------------------------------

class ULMLineDevice:
    """MultiPortDevice adapter for a frequency-dependent ULM transmission line.

    Each conductor is a port referenced to ground::

        ports = ((node_k[0], 0), (node_k[1], 0), ..., (node_m[0], 0), ...)

    For single-phase lines the two ports are ``(node_k, 0)`` and ``(node_m, 0)``.
    """

    def __init__(self, name: str, impl, nodes_k, nodes_m):
        self.name = name
        self.impl = impl       # ULMLine (ulm_transmission_line_PARA)
        self._nodes_k = list(nodes_k)
        self._nodes_m = list(nodes_m)
        self._nc = len(self._nodes_k)

    # -- port topology --------------------------------------------------------

    @property
    def ports(self):
        return tuple((nk, 0) for nk in self._nodes_k) + \
               tuple((nm, 0) for nm in self._nodes_m)

    @property
    def contributes_G(self) -> bool:
        return True

    @property
    def is_dynamic(self) -> bool:
        return True

    def register_nodes(self, indexer) -> None:
        for n in self._nodes_k + self._nodes_m:
            if n > 0:
                indexer.register(n)

    # -- MNA stamping ---------------------------------------------------------

    def stamp_G(self, stamper, indexer) -> None:
        nc = self._nc
        G_eq = self.impl.G_eq

        # Build full (2*nc × 2*nc) conductance matrix from G_eq
        if isinstance(G_eq, np.ndarray):
            if G_eq.ndim == 2:
                G_mat = G_eq
            elif G_eq.ndim == 1:
                G_mat = np.diag(G_eq)
            else:
                G_mat = np.eye(nc) * float(G_eq)
        else:
            G_mat = np.eye(nc) * float(G_eq)

        if G_mat.shape != (nc, nc):
            raise ValueError(
                f"ULMLineDevice {self.name}: G_eq shape {G_mat.shape} "
                f"mismatch with nc={nc}"
            )

        # Stamp k-k block
        for i in range(nc):
            nk_i = self._nodes_k[i]
            if nk_i <= 0:
                continue
            ci = indexer.to_compact(nk_i)
            for j in range(nc):
                nk_j = self._nodes_k[j]
                if nk_j > 0:
                    cj = indexer.to_compact(nk_j)
                    stamper.add(ci, cj, G_mat[i, j])

        # Stamp m-m block
        for i in range(nc):
            nm_i = self._nodes_m[i]
            if nm_i <= 0:
                continue
            ci = indexer.to_compact(nm_i)
            for j in range(nc):
                nm_j = self._nodes_m[j]
                if nm_j > 0:
                    cj = indexer.to_compact(nm_j)
                    stamper.add(ci, cj, G_mat[i, j])

    def stamp_rhs(self, rhs, indexer, t: float) -> None:
        I_hk = np.atleast_1d(self.impl.I_hist_k)
        I_hm = np.atleast_1d(self.impl.I_hist_m)

        for i in range(self._nc):
            nk = self._nodes_k[i]
            nm = self._nodes_m[i]
            if nk > 0:
                rhs[indexer.to_compact(nk)] -= float(I_hk[i % len(I_hk)])
            if nm > 0:
                rhs[indexer.to_compact(nm)] -= float(I_hm[i % len(I_hm)])

    # -- post-solve -----------------------------------------------------------

    def update_after_solve(self, V, indexer, t: float) -> None:
        # Read port voltages from solution
        self._vk = np.array([
            V[indexer.to_compact(n)] if n > 0 else 0.0
            for n in self._nodes_k
        ])
        self._vm = np.array([
            V[indexer.to_compact(n)] if n > 0 else 0.0
            for n in self._nodes_m
        ])

    def update_history(self, V, indexer, dt: float) -> None:
        # Use full_step (combined update + history) if state is fresh from solve
        self.impl.update_state(self._vk, self._vm)
        self.impl.update_history_sources()

    def check_rebuild_required(self, V, indexer, t: float) -> bool:
        return False

    def reset_state(self) -> None:
        self._vk = np.zeros(self._nc)
        self._vm = np.zeros(self._nc)


# -- Optional Layer-0 re-exports ------------------------------------------

try:
    from transmission_line_emtp_v2 import (
        BergeronLine,
        TransmissionLineInterface,
        TransmissionLineFactory,
        DelayBuffer,
    )
except ImportError:
    BergeronLine = None
    TransmissionLineInterface = None
    TransmissionLineFactory = None
    DelayBuffer = None

try:
    from ulm_transmission_line_PARA import (
        FitULMData,
        FitULMReader,
        ULMLine,
        ULMModel,
        ULMBatchPack,
    )
except ImportError:
    FitULMData = None
    FitULMReader = None
    ULMLine = None
    ULMModel = None
    ULMBatchPack = None
