"""SimulationRegistry — single entry point for all simulation object state.

Now driving MNA invalidation: topology_version and numeric_version
are the authoritative dirty signals for MNAKernel and RHSEngine.
"""

from __future__ import annotations

from typing import Any, Iterator

from .registry_records import ElementRecord, SourceRecord, MultiPortRecord


class SimulationRegistry:
    """Owns the identity and topology of every circuit object.

    Terminology:
    - *element*: a two-terminal branch (R, L, C, switch, series RL, MOA, LPM)
    - *source*: an independent current or voltage source
    - *multiport*: a multi-terminal device (Bergeron, ULM, UMEC)

    Version counters increment monotonically when state changes so
    downstream modules (MNAKernel, RHSEngine) can detect when cached
    plans or factorizations are stale.
    """

    def __init__(self, node_book, node_indexer):
        self.node_book = node_book
        self.node_indexer = node_indexer

        # -- registry storage ----------------------------------------------
        self._elements: dict[str, ElementRecord] = {}
        self._sources: dict[str, SourceRecord] = {}
        self._multiports: dict[str, MultiPortRecord] = {}
        self._devices: dict[str, object] = {}  # Device/MultiPortDevice instances

        # -- version counters ----------------------------------------------
        self._topology_version: int = 0   # node count, voltage source count, etc.
        self._numeric_version: int = 0    # conductance values, segment switches

        # -- convenience lookups (populated on finalise) -------------------
        self._vs_list: list | None = None
        self._node_set: set = set()

    # -----------------------------------------------------------------
    # Properties
    # -----------------------------------------------------------------

    @property
    def topology_version(self) -> int:
        return self._topology_version

    @property
    def numeric_version(self) -> int:
        return self._numeric_version

    @property
    def elements(self) -> dict[str, ElementRecord]:
        return dict(self._elements)

    @property
    def sources(self) -> dict[str, SourceRecord]:
        return dict(self._sources)

    @property
    def multiports(self) -> dict[str, MultiPortRecord]:
        return dict(self._multiports)

    @property
    def devices(self) -> dict[str, object]:
        return dict(self._devices)

    def element_names(self) -> list[str]:
        return list(self._elements)

    def source_names(self) -> list[str]:
        return list(self._sources)

    def multiport_names(self) -> list[str]:
        return list(self._multiports)

    # -----------------------------------------------------------------
    # Iterator / accessor API — for engine modules to enumerate circuit
    # -----------------------------------------------------------------

    def iter_element_records(self) -> Iterator[ElementRecord]:
        return iter(self._elements.values())

    def iter_source_records(self) -> Iterator[SourceRecord]:
        return iter(self._sources.values())

    def iter_multiport_records(self) -> Iterator[MultiPortRecord]:
        return iter(self._multiports.values())

    def iter_devices(self) -> Iterator[object]:
        return iter(self._devices.values())

    def get_device(self, name: str) -> object:
        """Return a registered device by name (raises KeyError if missing)."""
        return self._devices[name]

    def has_name(self, name: str) -> bool:
        """True if *name* is registered in any category."""
        return name in self._elements or name in self._sources or name in self._multiports

    # -----------------------------------------------------------------
    # Registration — sole entry point for add_* methods
    # -----------------------------------------------------------------

    def register_element(self, record: ElementRecord) -> None:
        self._ensure_unique(record.name)
        self._elements[record.name] = record
        if record.device is not None:
            self._devices[record.name] = record.device
        for n in record.nodes:
            if n > 0:
                self._node_set.add(n)
        self._topology_version += 1

    def register_source(self, record: SourceRecord) -> None:
        self._ensure_unique(record.name)
        self._sources[record.name] = record
        if record.kind == "voltage":
            self._topology_version += 1
        else:
            self._numeric_version += 1
        for n in record.nodes:
            if n > 0:
                self._node_set.add(n)

    def register_multiport(self, record: MultiPortRecord) -> None:
        self._ensure_unique(record.name)
        self._multiports[record.name] = record
        self._devices[record.name] = record.device
        for n in record.terminals:
            if n > 0:
                self._node_set.add(n)
        self._topology_version += 1

    # -----------------------------------------------------------------
    # Dirty markers
    # -----------------------------------------------------------------

    def mark_topology_dirty(self) -> None:
        self._topology_version += 1

    def mark_numeric_dirty(self) -> None:
        self._numeric_version += 1

    def touch(self) -> None:
        """Convenience: bump both counters (used when in doubt)."""
        self._topology_version += 1
        self._numeric_version += 1

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    def _ensure_unique(self, name: str) -> None:
        if self.has_name(name):
            raise ValueError(f"Duplicate device name: {name!r}")
