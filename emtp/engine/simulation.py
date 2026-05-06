"""Simulation time-stepping — main loop and per-step event orchestration.

PR-5b: The actual time-step body (formerly solver._run_one_step) now
lives in EventRuntime._step_impl.  Solver._run_one_step is a thin wrapper.
"""

from __future__ import annotations

import time as _perf_time
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np


class TimeStepper:
    """Orchestrate the time-step loop.

    The stepper owns the loop structure and timing instrumentation;
    per-step physics is delegated to :class:`EventRuntime`.
    """

    def run(self, solver: Any, n_steps: int, timing: dict) -> None:
        """Execute the main time-stepping loop over *n_steps* steps."""
        _t = _perf_time.perf_counter
        runtime = solver.event_runtime

        for step_idx in range(n_steps):
            runtime.step(step_idx, n_steps, _t)

        # Post-loop: export ULM batch state back to per-line models.
        ulm_batch = getattr(solver, '_ulm_batch', None)
        if ulm_batch is not None and hasattr(ulm_batch, 'export_model_state_to_lines'):
            ulm_batch.export_model_state_to_lines()


# -- Event runtime (per-step physics orchestration) -----------------------

class EventRuntime:
    """Per-time-step event-driven simulation loop.

    Owns:
    - The actual time-step body (_step_impl) — formerly solver._run_one_step
    - Pre-step switch/event detection
    - Core solve dispatch (linear / segmented / resolve)
    - Post-solve branch V/I update
    - Probe recording
    - History advance

    Parameters
    ----------
    solver: EMTPSolver
        The owning solver.  Complex internal state is still accessed
        through this reference until explicit deps are wired.
    """

    def __init__(self, solver):
        self._solver = solver
        self._steps_executed: int = 0
        self._event_count: int = 0

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def step(self, step_idx: int, n_steps: int, perf_counter) -> None:
        """Execute one full time step."""
        self._step_impl(step_idx, n_steps, perf_counter)
        self._steps_executed += 1

    # -----------------------------------------------------------------
    # Time-step body (formerly solver._run_one_step)
    # -----------------------------------------------------------------

    def _step_impl(self, step_idx: int, n_steps: int, _t) -> None:
        s = self._solver
        s.time = step_idx * s.dt

        # 1. switch events
        t0 = _t()
        if s._runtime.step_pre_solve(
            s.time, s._devices, set(s._lpm_elements),
        ):
            s.mark_topology_changed("switch event")
        t1 = _t()
        s._timing['switch_update'] += t1 - t0

        # 2. core solve
        V = s._solve_step()
        t2 = _t()
        s._timing['solve_step_total'] += t2 - t1

        # 3. branch V/I update (MUST precede probes)
        s._runtime.step_post_solve_V_I(
            V, s._devices, s._indexer,
            step_idx, n_steps,
            bool(getattr(s, 'record_branch_history', False)),
            s._branch_v_bufs, s._branch_i_bufs,
        )
        t3 = _t()
        s._timing['branch_update'] += t3 - t2

        # 4. probe / time / voltage recording
        s._record_probes(step_idx, V)
        s._time_array_buf[step_idx] = s.time
        if s._voltage_buf is not None:
            s._voltage_buf[:, step_idx] = V

        s._update_source_history()

        if s.record_source_history:
            for name, vs in s.voltage_sources.items():
                vs.current_history.append(vs.current)
                if name in s._vs_current_bufs:
                    s._vs_current_bufs[name][step_idx] = vs.current

        t_probe = _t()
        s._timing['probe_store'] += t_probe - t3

        # 5. transmission lines
        s._update_lines_combined(V)
        t4 = _t()
        s._timing['line_combined_update'] += t4 - t_probe

        # 6. branch reactive history (after probes, after lines)
        s._runtime.step_post_solve_history(s._devices)

        # 7. transformer history
        s._update_transformer_history(V)
        t5 = _t()
        s._timing['transformer_history'] += t5 - t4

        s._timing['data_store'] += _t() - t5

        s.step_count += 1
        s._stats['total_steps'] += 1

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
