"""Verify canonical import paths and single-implementation guarantees.

After the v0.5.0 reorg:
- ``emtp/circuit/`` owns nodes, elements, model, registry, probes.
- ``emtp/engine/`` owns stamping, MNA, RHS, nonlinear, linear, simulation.
- ``emtp/models/`` owns all physical element implementations.
- ``emtp/cases/`` owns JSON config loading, validation, solver building.
- ``emtp/io/`` owns results, export, snapshot, database.
- ``EMTPSolver`` is served from ``emtp/solver.py``.
"""

import os

import pytest


class TestCircuitPackage:
    def test_imports_as_package(self):
        import emtp.circuit
        path = emtp.circuit.__file__.replace("\\", "/")
        assert path.endswith("emtp/circuit/__init__.py"), f"got {path}"

    def test_node_indexer_from_package(self):
        from emtp.circuit.nodes import NodeIndexer
        assert NodeIndexer.__module__ == "emtp.circuit.nodes"


class TestEnginePackage:
    def test_imports_as_package(self):
        import emtp.engine
        path = emtp.engine.__file__.replace("\\", "/")
        assert path.endswith("emtp/engine/__init__.py"), f"got {path}"

    def test_dynamic_runtime_from_package(self):
        from emtp.engine.state import DynamicDeviceRuntime
        assert DynamicDeviceRuntime.__module__ == "emtp.engine.state"

    def test_resolve_manager_from_package(self):
        from emtp.engine.nonlinear import ResolveManager
        assert ResolveManager.__module__ == "emtp.engine.nonlinear"


class TestResultsModule:
    def test_result_store_from_package(self):
        from emtp.io.results import ResultStore
        assert ResultStore.__module__ == "emtp.io.results"


class TestSingleImplementations:
    def test_dynamic_runtime_single_source(self):
        """DynamicDeviceRuntime must have exactly one class definition."""
        import glob
        import emtp
        pkg_root = os.path.dirname(emtp.__file__)
        project_root = os.path.dirname(pkg_root)

        matches = []
        for pyfile in glob.glob(os.path.join(project_root, "**", "*.py"), recursive=True):
            if "__pycache__" in pyfile or "tests" + os.sep in pyfile:
                continue
            with open(pyfile, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "class DynamicDeviceRuntime" in line:
                        matches.append(pyfile)
                        break

        canonical = [f for f in matches
                     if f.replace("\\", "/").endswith("emtp/engine/state.py")]
        assert len(canonical) == 1, f"canonical not found in {matches}"
        others = [f for f in matches
                  if not f.replace("\\", "/").endswith("emtp/engine/state.py")]
        assert len(others) == 0, f"stale definitions in {others}"

    def test_emtp_solver_from_canonical_source(self):
        from emtp import EMTPSolver as A
        from emtp.solver import EMTPSolver as B
        assert A is B

    def test_no_stale_top_level_py_files(self):
        """Old top-level module files must not exist next to new packages."""
        import emtp
        pkg_dir = os.path.dirname(emtp.__file__)
        stale = ["runtime.py", "results.py", "types.py", "nodes.py", "circuit.py",
                 "stamping.py", "sparse_solver.py", "validation.py",
                 "result_bundle.py", "result_db.py", "run_id.py", "case_runner.py"]
        for name in stale:
            path = os.path.join(pkg_dir, name)
            assert not os.path.isfile(path), f"{path} still exists"
