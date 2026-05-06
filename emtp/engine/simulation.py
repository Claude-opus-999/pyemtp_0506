"""Simulation time-stepping — extracted main loop and per-step event orchestration for EMTPSolver."""

from __future__ import annotations

import time as _perf_time
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np


class TimeStepper:
    """Orchestrate the time-step loop.

    The stepper owns the loop structure and timing instrumentation;
    per-step physics is delegated to the solver via ``_run_one_step``.
    """

    def run(self, solver: Any, n_steps: int, timing: dict) -> None:
        """Execute the main time-stepping loop over *n_steps* steps.

        Parameters
        ----------
        solver:
            The EMTPSolver instance (duck-typed — must provide
            ``_run_one_step`` and timing-friendly attributes).
        n_steps:
            Number of time steps.
        timing:
            Mutable timing dict updated with per-phase wall-clock deltas.
        """
        _t = _perf_time.perf_counter

        for step_idx in range(n_steps):
            solver._run_one_step(step_idx, n_steps, _t)

        # Post-loop: export ULM batch state back to per-line models.
        ulm_batch = getattr(solver, '_ulm_batch', None)
        if ulm_batch is not None and hasattr(ulm_batch, 'export_model_state_to_lines'):
            ulm_batch.export_model_state_to_lines()


# -- Event runtime (per-step physics orchestration) -----------------------

class EventRuntime:
    """Per-time-step event-driven simulation loop.

    Owns:
    - Pre-step switch/event detection
    - Core solve dispatch (linear / segmented / resolve)
    - Post-solve branch V/I update
    - Probe recording
    - History advance

    Parameters
    ----------
    solver: EMTPSolver
        The owning solver.  Delegate reference; will be replaced
        with explicit registry/kernel/rhs/probe dependencies.
    """

    def __init__(self, solver):
        self._solver = solver
        self._steps_executed: int = 0
        self._event_count: int = 0

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def step(self, step_idx: int, n_steps: int, perf_counter) -> None:
        """Execute one full time step — delegates to solver._run_one_step."""
        self._solver._run_one_step(step_idx, n_steps, perf_counter)
        self._steps_executed += 1

    # -----------------------------------------------------------------
    # Sub-step accessors
    # -----------------------------------------------------------------

    def pre_step_switches(self) -> bool:
        """Check timed switch events; return True if topology changed."""
        s = self._solver
        changed = s._runtime.step_pre_solve(
            s.time, s._devices, set(s._lpm_elements),
        )
        if changed:
            self._event_count += 1
        return changed

    def post_solve_update(self, V: "np.ndarray", step_idx: int, n_steps: int) -> None:
        """Update branch voltages and currents from solution."""
        s = self._solver
        s._runtime.step_post_solve_V_I(
            V, s._devices, s._indexer,
            step_idx, n_steps,
            bool(getattr(s, 'record_branch_history', False)),
            s._branch_v_bufs, s._branch_i_bufs,
        )

    def advance_history(self, step_idx: int) -> None:
        """Advance device, line, and transformer histories."""
        s = self._solver
        s._runtime.step_post_solve_advance(
            s.time, s.dt, step_idx,
            s._devices, set(s._lpm_elements),
            getattr(s, '_line_devices', {}),
            s.transformers,
        )

    # -----------------------------------------------------------------
    # Diagnostics
    # -----------------------------------------------------------------

    @property
    def steps_executed(self) -> int:
        return self._steps_executed

    @property
    def event_count(self) -> int:
        return self._event_count

    def reset_counters(self) -> None:
        self._steps_executed = 0
        self._event_count = 0
