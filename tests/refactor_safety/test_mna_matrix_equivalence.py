"""PR-4 safety net: MNA matrix invariance and solution validity."""

import numpy as np
import pytest
from emtp import EMTPSolver


class TestMNAMatrixInvariance:
    """Topology changes must produce different G matrices."""

    def test_repeated_build_without_change_same_shape(self):
        s = EMTPSolver(dt=1e-6, finish_time=10e-6, verbose=False)
        s.add_VS("vs", 1, 0, 10.0)
        s.add_R("r1", 1, 2, 100.0)
        s.add_C("c1", 2, 0, 1e-6)

        s._build_MNA_matrix()
        G1_shape = s._stamping.cached_MNA.shape

        s._stamping.mark_dirty()
        s._build_MNA_matrix()
        assert s._stamping.cached_MNA.shape == G1_shape

    def test_matrix_grows_with_new_node(self):
        s = EMTPSolver(dt=1e-6, finish_time=10e-6, verbose=False)
        s.add_VS("vs", 1, 0, 10.0)
        s.add_R("r1", 1, 0, 100.0)

        s._build_MNA_matrix()
        shape1 = s._stamping.cached_MNA.shape

        # Add element using a NEW node → matrix grows
        s.add_R("r2", 1, 2, 50.0)   # node 2 is new
        s._stamping.mark_dirty()
        s._build_MNA_matrix()
        shape2 = s._stamping.cached_MNA.shape

        assert shape2[0] > shape1[0]

    def test_matrix_shape_matches_topology(self):
        s = EMTPSolver(dt=1e-6, finish_time=10e-6, verbose=False)
        s.add_VS("vs", 1, 0, 10.0)
        s.add_R("r1", 1, 0, 100.0)

        s._build_MNA_matrix()
        G = s._stamping.cached_MNA
        expected_n = s._indexer.n + len(s.voltage_sources)
        assert G.shape == (expected_n, expected_n)


class TestMNACacheTracking:
    """G matrix rebuild counts must be tracked during run()."""

    def test_cache_hit_during_run(self):
        s = EMTPSolver(dt=1e-6, finish_time=10e-6, verbose=False)
        s.add_VS("vs", 1, 0, 5.0)
        s.add_R("r1", 1, 0, 100.0)
        s.add_voltage_probe("V1", 1, 0)
        s.run()

        stats = s.get_solver_statistics()
        assert stats["G_rebuilds"] >= 1
        assert stats["G_cache_hits"] > 0

    def test_rebuilds_increase_with_switch(self):
        s = EMTPSolver(dt=1e-6, finish_time=100e-6, verbose=False)
        s.add_VS("vs", 1, 0, 10.0)
        s.add_R("r1", 1, 2, 100.0)
        s.add_SW("sw1", 2, 0, t_close=30e-6, t_open=70e-6,
                 R_closed=1e-3, R_open=1e6, initially_closed=False)
        s.add_R("r2", 2, 0, 1000.0)
        s.add_voltage_probe("V2", 2, 0)
        s.run()

        stats = s.get_solver_statistics()
        assert stats["G_rebuilds"] >= 3  # init + close + open


class TestMNASolutionValidity:
    """MNA solutions must obey Kirchhoff's laws."""

    def test_voltage_divider_solution(self):
        s = EMTPSolver(dt=1e-6, finish_time=10e-6, verbose=False)
        s.add_VS("vs", 1, 0, 10.0)
        s.add_R("r1", 1, 2, 10.0)
        s.add_R("r2", 2, 0, 10.0)

        s._pre_sample_sources(11)
        s._build_MNA_matrix()
        rhs = s._build_MNA_rhs()
        MNA = s._stamping.cached_MNA
        V = s._solve_mna(MNA, rhs)
        v2 = V[s._indexer.to_compact(2)]

        assert abs(v2 - 5.0) < 1e-9

    def test_solution_with_open_switch(self):
        s = EMTPSolver(dt=1e-6, finish_time=10e-6, verbose=False)
        s.add_VS("vs", 1, 0, 10.0)
        s.add_R("r1", 1, 2, 100.0)
        s.add_SW("sw1", 2, 0, t_close=1e-6, t_open=1e-3,
                 R_closed=1e-3, R_open=1e6, initially_closed=False)
        s.add_R("r2", 2, 0, 1e6)

        s._pre_sample_sources(11)
        s._build_MNA_matrix()
        rhs = s._build_MNA_rhs()
        MNA = s._stamping.cached_MNA
        V = s._solve_mna(MNA, rhs)
        v2_open = V[s._indexer.to_compact(2)]

        assert abs(v2_open - 10.0) < 0.01

        # Close switch
        sw = s.branches["sw1"]
        sw.is_closed = True
        sw.Geq = 1.0 / 1e-3
        s._stamping.mark_dirty()
        s._build_MNA_matrix()
        MNA = s._stamping.cached_MNA
        V = s._solve_mna(MNA, rhs)
        v2_closed = V[s._indexer.to_compact(2)]

        assert abs(v2_closed) < 0.01
