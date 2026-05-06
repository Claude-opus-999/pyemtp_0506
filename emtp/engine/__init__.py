"""Engine — MNA assembly, stamping, RHS construction, nonlinear resolve, LU solve, and simulation loop."""

from .linear import SparseLinearSolver, _sparse_factorize, _SPARSE_SOLVER_NAME
from .stamping import COOStamper, StampingEngine
from .mna import MNAAssembler, MNAKernel
from .rhs import RHSEngine
from .state import DynamicDeviceRuntime
from .nonlinear import ResolveManager, ResolveEvent
from .simulation import TimeStepper, EventRuntime

__all__ = [
    "SparseLinearSolver", "_sparse_factorize", "_SPARSE_SOLVER_NAME",
    "COOStamper", "StampingEngine",
    "MNAAssembler", "MNAKernel",
    "RHSEngine",
    "DynamicDeviceRuntime",
    "ResolveManager", "ResolveEvent",
    "TimeStepper", "EventRuntime",
]
