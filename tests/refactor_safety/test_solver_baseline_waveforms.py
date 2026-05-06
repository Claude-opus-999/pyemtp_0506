"""PR-0 safety net: solver baseline waveform invariants.

Each test case verifies key scalar invariants (final value, peak,
monotonicity, etc.) that must survive any refactoring of the solver
internals.  No large golden files — just physics-based assertions.
"""

import numpy as np
import pytest
from emtp import EMTPSolver


# =========================================================================
# RC step response
# =========================================================================

class TestRCStepBaseline:
    @pytest.fixture
    def result(self):
        s = EMTPSolver(dt=1e-6, finish_time=100e-6, verbose=False)
        s.add_VS("vs", 1, 0, 1.0)
        s.add_R("r1", 1, 2, 10.0)
        s.add_C("c1", 2, 0, 1e-6)
        s.add_voltage_probe("Vc", 2, 0)
        s.run()
        return s

    def test_vc_ends_near_one(self, result):
        v = result.get_voltage_probe("Vc", "V")
        assert abs(v[-1] - 1.0) < 0.05

    def test_vc_monotonic_increasing(self, result):
        v = result.get_voltage_probe("Vc", "V")
        assert np.all(np.diff(v) >= -1e-15)

    def test_time_constant_behavior(self, result):
        """After one tau (R*C = 10us), Vc ≈ 0.632."""
        v = result.get_voltage_probe("Vc", "V")
        tau_idx = int(10e-6 / result.dt)
        if tau_idx < len(v):
            assert 0.55 < v[tau_idx] < 0.72

    def test_G_rebuilds_correct(self, result):
        assert result._stats.get("G_rebuilds", 0) == 1


# =========================================================================
# RL step response
# =========================================================================

class TestRLStepBaseline:
    @pytest.fixture
    def result(self):
        s = EMTPSolver(dt=1e-6, finish_time=100e-6, verbose=False)
        s.add_VS("vs", 1, 0, 1.0)
        s.add_R("r1", 1, 2, 10.0)
        s.add_L("l1", 2, 0, 1e-3)
        s.add_branch_current_probe("IL", "l1")
        s.run()
        return s

    def test_il_ends_positive(self, result):
        i = result.get_branch_current_probe("IL", "A")
        # L/R = 100us tau; after 100us, i ≈ 0.632 * (V/R) = 0.0632
        assert i[-1] > 0.05

    def test_il_monotonic_increasing(self, result):
        i = result.get_branch_current_probe("IL", "A")
        assert np.all(np.diff(i) >= -1e-15)


# =========================================================================
# RLC damped oscillation
# =========================================================================

class TestRLCDampedBaseline:
    @pytest.fixture
    def result(self):
        s = EMTPSolver(dt=1e-6, finish_time=200e-6, verbose=False)
        s.add_VS("vs", 1, 0, 5.0)
        s.add_R("r1", 1, 2, 10.0)
        s.add_L("l1", 2, 3, 100e-6)
        s.add_C("c1", 3, 0, 1e-6)
        s.add_voltage_probe("Vc", 3, 0)
        s.run()
        return s

    def test_vc_ends_near_dc_value(self, result):
        v = result.get_voltage_probe("Vc", "V")
        assert abs(v[-1] - 5.0) < 0.1

    def test_energy_finite(self, result):
        v = result.get_voltage_probe("Vc", "V")
        assert np.all(np.isfinite(v))


# =========================================================================
# Switch open/close
# =========================================================================

class TestSwitchBaseline:
    @pytest.fixture
    def result(self):
        s = EMTPSolver(dt=1e-6, finish_time=100e-6, verbose=False)
        s.add_VS("vs", 1, 0, 10.0)
        s.add_R("r1", 1, 2, 100.0)
        s.add_SW("sw1", 2, 0, t_close=30e-6, t_open=70e-6,
                 R_closed=1e-3, R_open=1e6, initially_closed=False)
        s.add_R("r2", 2, 0, 1000.0)
        s.add_voltage_probe("V2", 2, 0)
        s.run()
        return s

    def test_voltage_low_when_closed(self, result):
        v = result.get_voltage_probe("V2", "V")
        idx_closed = int(50e-6 / result.dt)
        assert abs(v[idx_closed]) < 2.0, f"v_closed={v[idx_closed]}"

    def test_voltage_high_when_open(self, result):
        v = result.get_voltage_probe("V2", "V")
        idx_open_end = int(25e-6 / result.dt)
        avg = np.mean(v[:idx_open_end])
        assert avg > 8.0

    def test_G_rebuilds_on_switch_events(self, result):
        assert result._stats.get("G_rebuilds", 0) >= 3


# =========================================================================
# Voltage source + resistor (simple circuit)
# =========================================================================

class TestVoltageDividerBaseline:
    @pytest.fixture
    def result(self):
        s = EMTPSolver(dt=1e-6, finish_time=10e-6, verbose=False)
        s.add_VS("vs", 1, 0, 10.0)
        s.add_R("r1", 1, 2, 10.0)
        s.add_R("r2", 2, 0, 10.0)
        s.add_voltage_probe("Vmid", 2, 0)
        s.run()
        return s

    def test_midpoint_voltage_half(self, result):
        v = result.get_voltage_probe("Vmid", "V")
        assert np.allclose(v, 5.0, rtol=1e-6)


# =========================================================================
# Current source + resistor
# =========================================================================

class TestCurrentSourceBaseline:
    @pytest.fixture
    def result(self):
        s = EMTPSolver(dt=1e-6, finish_time=10e-6, verbose=False)
        s.add_IS("is1", 1, 0, lambda t: 2.0)
        s.add_R("r1", 1, 0, 50.0)
        s.add_voltage_probe("V1", 1, 0)
        s.run()
        return s

    def test_voltage_magnitude_matches_ohms_law(self, result):
        v = result.get_voltage_probe("V1", "V")
        # I*R = 2*50 = 100V; check magnitude
        assert np.allclose(np.abs(v), 100.0, rtol=1e-6)


# =========================================================================
# Bergeron transmission line smoke test
# =========================================================================

class TestBergeronSmokeBaseline:
    @pytest.fixture
    def result(self):
        try:
            from transmission_line_emtp_v2 import BergeronLine
        except ImportError:
            pytest.skip("transmission_line_emtp_v2 not available")
        s = EMTPSolver(dt=1e-6, finish_time=100e-6, verbose=False)
        s.add_VS("vs", 1, 0, 1.0)
        s.add_R("rs", 1, 0, 50.0)
        s.add_bergeron_line("line1", node_k=1, node_m=2, Zc=50.0, tau=10e-6)
        s.add_R("rload", 2, 0, 50.0)
        s.add_voltage_probe("Vload", 2, 0)
        s.run()
        return s

    def test_produces_finite_output(self, result):
        v = result.get_voltage_probe("Vload", "V")
        assert len(v) > 0
        assert np.all(np.isfinite(v))

    def test_line_info_present(self, result):
        info = result.get_line_info("line1")
        assert isinstance(info, dict)
        assert len(info) > 0


# =========================================================================
# Probe shape and count invariants
# =========================================================================

class TestProbeInvariants:
    def test_probe_lengths_match_step_count(self):
        s = EMTPSolver(dt=1e-6, finish_time=100e-6, verbose=False)
        s.add_VS("vs", 1, 0, 1.0)
        s.add_R("r1", 1, 0, 100.0)
        s.add_voltage_probe("V1", 1, 0)
        s.add_branch_current_probe("IR", "r1")
        s.run()

        v = s.get_voltage_probe("V1", "V")
        i = s.get_branch_current_probe("IR", "A")
        expected_len = int(100e-6 / 1e-6) + 1

        assert len(v) == expected_len
        assert len(i) == expected_len

    def test_time_array_correct(self):
        s = EMTPSolver(dt=1e-6, finish_time=50e-6, verbose=False)
        s.add_VS("vs", 1, 0, 1.0)
        s.add_R("r1", 1, 0, 100.0)
        s.run()

        t = s.get_time("s")
        assert t[0] == 0.0
        assert abs(t[-1] - 50e-6) < 1e-15
        assert len(t) == 51
