# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

PyEMTP is a Python electromagnetic transients simulation solver using Modified Nodal Analysis (MNA). It integrates multi-phase transmission lines, nonlinear components (MOA arresters, LPM flashover), UMEC transformers, and lightning current sources.

**Stack**: Python 3.12+, numpy, scipy (sparse SuperLU). Optional: numba (ULM batch).

## Commands

```bash
# Run all tests (skip slow tower case)
pytest tests/ -q --ignore=tests/test_tower_case_p1.py

# Run a single test file
pytest tests/test_pr1_fitulm_resolver.py -v

# Run LCP-specific tests
pytest tests/pylcp_tests/ -v
pytest tests/test_baseline_lcp_emtp.py -v

# Syntax check new/modified modules
python -m py_compile emtp/models/fitulm.py
python -m py_compile pylcp/*.py
python -m py_compile pylcp/generation/*.py
```

## Architecture (v0.5.0 — six strong-boundary directories)

```
emtp/
├── solver.py               EMTPSolver user-facing facade
│
├── circuit/                 What the circuit topology IS
│     nodes.py, elements.py, model.py, validation.py,
│     registry.py, registry_records.py, probes.py
│
├── engine/                  HOW each time step is solved
│     linear.py, stamping.py, mna.py, rhs.py,
│     state.py, nonlinear.py, simulation.py
│
├── models/                  HOW physical elements compute
│     base.py, multiport.py, lumped.py, switches.py,
│     nonlinear.py, sources.py, lines.py, fitulm.py, transformers.py
│
├── cases/                   HOW JSON configs enter
│     schema.py, loader.py, validator.py, defaults.py,
│     element_builder.py, source_builder.py, probe_builder.py,
│     builder.py, runner.py
│
├── io/                      HOW results get out
│     results.py, result_bundle.py, database.py, run_id.py,
│     export.py, snapshot.py
│
└── utils/                   Shared utilities (reserved)
```

### v0.4.0 → v0.5.0 import path changes

| Old (v0.4.0) | New (v0.5.0) |
|---|---|
| `emtp.types` | `emtp.circuit.elements` |
| `emtp.nodes` | `emtp.circuit.nodes` |
| `emtp.circuit` (module) | `emtp.circuit.model` |
| `emtp.validation` | `emtp.circuit.validation` |
| `emtp.registry` | `emtp.circuit.registry` |
| `emtp.probes` | `emtp.circuit.probes` |
| `emtp.sparse_solver` | `emtp.engine.linear` |
| `emtp.stamping` | `emtp.engine.stamping` |
| `emtp.assembly.mna` | `emtp.engine.mna` |
| `emtp.kernel` | `emtp.engine.mna` |
| `emtp.rhs` | `emtp.engine.rhs` |
| `emtp.runtime` | `emtp.engine.state` |
| `emtp.runtime.resolve` | `emtp.engine.nonlinear` |
| `emtp.runtime.stepper` / `emtp.runtime.event_runtime` | `emtp.engine.simulation` |
| `emtp.devices` | `emtp.models` |
| `emtp.lines.bergeron` / `emtp.lines.ulm` | `emtp.models.lines` |
| `emtp.lines.fitulm_resolver` | `emtp.models.fitulm` |
| `emtp.transformers.umec` | `emtp.models.transformers` |
| `emtp.config` | `emtp.cases` |
| `emtp.builders` | `emtp.cases` |
| `emtp.case_runner` | `emtp.cases.runner` |
| `emtp.results` | `emtp.io.results` |
| `emtp.export` | `emtp.io.export` |
| `emtp.snapshot` | `emtp.io.snapshot` |
| `emtp.result_db` | `emtp.io.database` |
| `emtp.result_bundle` | `emtp.io.result_bundle` |
| `emtp.run_id` | `emtp.io.run_id` |

**Two entry points**:
- `from emtp import EMTPSolver` — programmatic API (solver.py)
- `from emtp.cases import run_case` — JSON config-driven pipeline

**LCP integration** (v0.3.2+): `LCP/` contains line-constants physics (cable Z/Y, overhead line Z/Y, Vector Fitting engine). `pylcp/` wraps it for solver integration via `solver.add_ULM_line()` with two modes:
- External file: `generate_fitulm=False, fitulm_path="file.fitULM"`
- Auto-generation: `generate_fitulm=True, lcp_spec=LCPFitULMSpec(...)` — length defaults to `lcp_spec.length`

**Key files for ULM/LCP flow**: `emtp/models/fitulm.py` (FitULMSpec + FitULMResolver), `pylcp/lcp_fitulm_generator.py` (LCPFitULMGenerator), `pylcp/cache.py` (content-hash cache keys), `pylcp/generation/_soil.py` (shared soil params).

## MNA sign conventions

- Branch current positive direction: `node_from → node_to`
- Branch voltage: `V(node_from) - V(node_to)`
- Norton equivalent: `i = Geq · v + Ihist`
- RHS stamping: `rhs[pos] -= Ihist`, `rhs[neg] += Ihist`
- Current source injection: `rhs[pos] -= I`, `rhs[neg] += I`
- Ground node is 0 — never write to `rhs[0]` or matrix row/col for node 0

## Key patterns

- **Device protocol**: Every two-terminal element implements `stamp_G`, `stamp_rhs`, `update_branch_quantities`, `update_history`. Defined in `emtp/models/base.py`.
- **MultiPortDevice protocol**: Multi-port elements (Bergeron, ULM, UMEC) implement `stamp_G`, `stamp_rhs`, `update_from_solution`, `advance_history`, `get_resolve_event`. Defined in `emtp/models/multiport.py`.
- **Optional Layer 0 imports**: All Layer 0 libraries are imported with try/except, falling back to `None` stubs. This allows the solver to run without all physics libraries present.
- **fitULM verification**: `_verify_fitulm()` checks existence, non-empty, and runs `verify_fitULM_file()` if LCP is available. Only catches `ImportError` (LCP missing) — real errors propagate. Both external-file and LCP-generated paths go through this check.
- **Cache key**: `compute_cache_key()` in `pylcp/cache.py` hashes geometry, soil, frequency, VF config, and pylcp/LCP version fields. Path: `{cache_dir}/{name}_{hash}.fitULM`. Outer `FitULMSpec.cache_dir` always overrides `lcp_spec.cache_dir`.

## Behavioral guidelines

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```
