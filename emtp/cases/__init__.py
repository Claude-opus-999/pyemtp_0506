"""Cases — JSON config schema, loading, validation, solver building, and case running."""

from .defaults import (
    DEFAULT_SIMULATION, SUPPORTED_ELEMENTS, SUPPORTED_SOURCES, SUPPORTED_PROBES,
)
from .schema import CaseConfig, SimulationOptions
from .loader import load_case_config
from .validator import validate_case_config
from .element_builder import add_element_to_solver
from .source_builder import add_source_to_solver
from .probe_builder import add_probe_to_solver
from .builder import build_solver_from_config
from .runner import run_case

__all__ = [
    "DEFAULT_SIMULATION", "SUPPORTED_ELEMENTS", "SUPPORTED_SOURCES", "SUPPORTED_PROBES",
    "CaseConfig", "SimulationOptions",
    "load_case_config", "validate_case_config",
    "add_element_to_solver", "add_source_to_solver", "add_probe_to_solver",
    "build_solver_from_config",
    "run_case",
]
