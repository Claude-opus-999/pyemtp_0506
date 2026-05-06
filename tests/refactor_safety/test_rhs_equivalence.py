"""PR-3 safety net: RHS plan behavior and consistency checks.

Verifies that RHSPlan compilation works correctly and RHS vectors
are consistent through the public run() API.
"""

import numpy as np
import pytest
from emtp import EMTPSolver


class TestRHSPlanBasics:
    """RHS plan must compile at run time and produce correct results."""

    def test_plan_compiles_during_run(self):
        s = EMTPSolver(dt=1e-6, finish_time=10e-6, verbose=False,
                       use_rhs_plan=True)
        s.add_VS("vs", 1, 0, 5.0)
        s.add_R("r1", 1, 0, 100.0)
        s.add_voltage_probe("V1", 1, 0)
        s.run()

        assert s._rhs_plan is not None
        assert not s._rhs_plan_dirty

    def test_plan_recompiles_after_topology_change(self):
        s = EMTPSolver(dt=1e-6, finish_time=10e-6, verbose=False,
                       use_rhs_plan=True)
        s.add_VS("vs", 1, 0, 5.0)
        s.add_R("r1", 1, 0, 100.0)
        s.add_voltage_probe("V1", 1, 0)
        s.run()

        assert not s._rhs_plan_dirty

        # Adding a new branch must invalidate the plan
        s.add_R("r2", 1, 0, 50.0)
        assert s._rhs_plan_dirty


class TestRHSConsistency:
    """Same circuit with and without RHS plan must match."""

    def test_run_with_and_without_rhs_plan_equal(self):
        def _run(use_plan):
            s = EMTPSolver(dt=1e-6, finish_time=10e-6, verbose=False,
                           use_rhs_plan=use_plan)
            s.add_VS("vs", 1, 0, 10.0)
            s.add_R("r1", 1, 2, 10.0)
            s.add_R("r2", 2, 0, 10.0)
            s.add_voltage_probe("Vmid", 2, 0)
            s.run()
            return s.get_voltage_probe("Vmid", "V")

        v_plan = _run(True)
        v_no_plan = _run(False)

        np.testing.assert_allclose(v_plan, v_no_plan, rtol=1e-12, atol=1e-12)

    def test_run_with_sources_and_rhs_plan(self):
        s = EMTPSolver(dt=1e-6, finish_time=10e-6, verbose=False,
                       use_rhs_plan=True)
        s.add_VS("vs", 1, 0, 10.0)
        s.add_IS("is1", 2, 0, lambda t: 1.0)
        s.add_R("r1", 1, 2, 10.0)
        s.add_R("r2", 2, 0, 100.0)
        s.add_voltage_probe("V1", 1, 0)
        s.add_voltage_probe("V2", 2, 0)
        s.run()

        v1 = s.get_voltage_probe("V1", "V")
        v2 = s.get_voltage_probe("V2", "V")
        assert np.all(np.isfinite(v1))
        assert np.all(np.isfinite(v2))
        assert np.allclose(v1, 10.0)
