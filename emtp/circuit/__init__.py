"""Circuit model — topology description: nodes, elements, registry, validation, probes."""

from .nodes import NodeBook, NodeIndexer
from .elements import (
    Branch, ElementType, VoltageSource, CurrentSource, LineData,
    ValidationIssue, ValidationReport, RHSPlan,
)
from .model import CircuitModel
from .validation import (
    finalize_validation, check_floating_components, estimate_result_memory_bytes,
)
from .registry import SimulationRegistry
from .registry_records import ElementRecord, SourceRecord, MultiPortRecord
from .probes import ProbeManager, ProbeSpec

__all__ = [
    "NodeBook", "NodeIndexer",
    "Branch", "ElementType", "VoltageSource", "CurrentSource", "LineData",
    "ValidationIssue", "ValidationReport", "RHSPlan",
    "CircuitModel",
    "finalize_validation", "check_floating_components", "estimate_result_memory_bytes",
    "SimulationRegistry",
    "ElementRecord", "SourceRecord", "MultiPortRecord",
    "ProbeManager", "ProbeSpec",
]
