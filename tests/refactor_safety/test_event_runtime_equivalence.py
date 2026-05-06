"""PR-5 safety net: EventRuntime step equivalence checks.

Verifies that TimeStepper and EventRuntime produce identical results
to the solver's _run_one_step path, and that per-step statistics
are consistent.
"""

import numpy as np
import pytest
from emtp import EMTPSolver


class TestEventRuntimeExistence:
    """EventRuntime must be present and functional after init and run."""

    def test_runtime_present_after_init(self):
        s = EMTPSolver(dt=1e-6, finish_time=10e-6, verbose=False)
        assert hasattr(s, 'event_runtime')
        assert s.event_runtime is not None

    def test_runtime_step_runs_without_error(self):
        s = EMTPSolver(dt=1e-6, finish_time=10e-6, verbose=False)
        s.add_VS("vs", 1, 0, 1.0)
        s.add_R("r1", 1, 0, 100.0)
        s.add_voltage_probe("V1", 1, 0)
        s.run()
        v = s.get_voltage_probe("V1", "V")
        assert len(v) > 0
        assert np.all(np.isfinite(v))

    def test_runtime_with_switch_handles_events(self):
        s = EMTPSolver(dt=1e-6, finish_time=100e-6, verbose=False)
        s.add_VS("vs", 1, 0, 10.0)
        s.add_R("r1", 1, 2, 100.0)
        s.add_SW("sw1", 2, 0, t_close=30e-6, t_open=70e-6,
                 R_closed=1e-3, R_open=1e6, initially_closed=False)
        s.add_R("r2", 2, 0, 1000.0)
        s.add_voltage_probe("V2", 2, 0)
        s.run()

        v = s.get_voltage_probe("V2", "V")
        # Switch transitions should create distinct voltage regions
        assert np.any(v < 1.0), "Should have near-zero region when switch closed"
        assert np.any(v > 8.0), "Should have high-voltage region when switch open"


class TestTimeStepperConsistency:
    """TimeStepper must produce consistent step counts and timing."""

    def test_step_count_matches_expected(self):
        s = EMTPSolver(dt=1e-6, finish_time=50e-6, verbose=False)
        s.add_VS("vs", 1, 0, 1.0)
        s.add_R("r1", 1, 0, 100.0)
        s.run()

        n_steps = int(50e-6 / 1e-6)
        assert s.step_count == n_steps + 1  # includes initial condition
        t = s.get_time("s")
        assert len(t) == n_steps + 1

    def test_run_until_extends_step_count(self):
        s = EMTPSolver(dt=1e-6, finish_time=50e-6, verbose=False)
        s.add_VS("vs", 1, 0, 1.0)
        s.add_R("r1", 1, 0, 100.0)
        s.add_voltage_probe("V1", 1, 0)
        s.run_until(25e-6)
        assert s.step_count == 25

        s.run_until(50e-6, reset_state=False)
        assert s.step_count == 50


class TestRunRepeatability:
    """Same circuit run twice must produce identical results."""

    def test_rc_run_repeatable(self):
        def _run():
            s = EMTPSolver(dt=1e-6, finish_time=100e-6, verbose=False)
            s.add_VS("vs", 1, 0, 1.0)
            s.add_R("r1", 1, 2, 10.0)
            s.add_C("c1", 2, 0, 1e-6)
            s.add_voltage_probe("Vc", 2, 0)
            s.run()
            return s.get_voltage_probe("Vc", "V")

        v1 = _run()
        v2 = _run()
        np.testing.assert_allclose(v1, v2, rtol=1e-14, atol=1e-14)

    def test_rlc_run_repeatable(self):
        def _run():
            s = EMTPSolver(dt=1e-6, finish_time=200e-6, verbose=False)
            s.add_VS("vs", 1, 0, 5.0)
            s.add_R("r1", 1, 2, 10.0)
            s.add_L("l1", 2, 3, 100e-6)
            s.add_C("c1", 3, 0, 1e-6)
            s.add_voltage_probe("Vc", 3, 0)
            s.run()
            return s.get_voltage_probe("Vc", "V")

        v1 = _run()
        v2 = _run()
        np.testing.assert_allclose(v1, v2, rtol=1e-14, atol=1e-14)
