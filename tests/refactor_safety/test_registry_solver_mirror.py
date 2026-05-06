"""PR-2 safety net: solver containers are circuit model aliases."""

import pytest
from emtp import EMTPSolver


class TestSolverCircuitAlias:
    """solver.branches, _devices, etc. must be the SAME objects as circuit's."""

    def test_branches_is_circuit_branches(self):
        s = EMTPSolver(dt=1e-6, finish_time=10e-6, verbose=False)
        assert s.branches is s.circuit.branches

    def test_devices_is_circuit_devices(self):
        s = EMTPSolver(dt=1e-6, finish_time=10e-6, verbose=False)
        assert s._devices is s.circuit.devices

    def test_current_sources_is_circuit_current_sources(self):
        s = EMTPSolver(dt=1e-6, finish_time=10e-6, verbose=False)
        assert s.current_sources is s.circuit.current_sources

    def test_voltage_sources_is_circuit_voltage_sources(self):
        s = EMTPSolver(dt=1e-6, finish_time=10e-6, verbose=False)
        assert s.voltage_sources is s.circuit.voltage_sources

    def test_transmission_lines_is_circuit_transmission_lines(self):
        s = EMTPSolver(dt=1e-6, finish_time=10e-6, verbose=False)
        assert s.transmission_lines is s.circuit.transmission_lines

    def test_transformers_is_circuit_transformers(self):
        s = EMTPSolver(dt=1e-6, finish_time=10e-6, verbose=False)
        assert s.transformers is s.circuit.transformers


class TestCircuitAfterAdd:
    """After add_* calls, circuit must contain the same data as solver."""

    def test_add_R_appears_in_circuit(self):
        s = EMTPSolver(dt=1e-6, finish_time=10e-6, verbose=False)
        s.add_R("r1", 1, 0, 100.0)
        assert "r1" in s.circuit.branches
        assert len(s.circuit.devices) == 1
        assert len(s._devices) == 1
        assert s._devices is s.circuit.devices

    def test_add_multiple_elements_in_circuit(self):
        s = EMTPSolver(dt=1e-6, finish_time=10e-6, verbose=False)
        s.add_VS("vs", 1, 0, 10.0)
        s.add_R("r1", 1, 2, 100.0)
        s.add_C("c1", 2, 0, 1e-6)

        assert len(s.circuit.branches) == 2  # R + C (VS is not a branch)
        assert len(s.circuit.voltage_sources) == 1
        assert len(s.circuit.devices) == 2

        # verify identity is maintained
        assert s.circuit.branches is s.branches
        assert s.circuit.devices is s._devices

    def test_registry_has_element_after_add(self):
        s = EMTPSolver(dt=1e-6, finish_time=10e-6, verbose=False)
        s.add_R("r1", 1, 0, 100.0)
        assert "r1" in s.registry.elements
        assert s.registry.elements["r1"].name == "r1"

    def test_registry_version_bumps(self):
        s = EMTPSolver(dt=1e-6, finish_time=10e-6, verbose=False)
        v0 = s.registry.topology_version
        s.add_R("r1", 1, 0, 100.0)
        assert s.registry.topology_version > v0
