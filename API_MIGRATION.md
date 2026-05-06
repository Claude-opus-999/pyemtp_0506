# API Migration Guide

v0.5.0 已完成目录重组：16 碎片目录 → 6 强边界目录。v0.4.0 旧路径已全部删除。

---

## 唯一入口

| 用途 | v0.4.0 (旧) | v0.5.0 (当前) |
|------|-----------|-------------|
| 求解器 | `from emtp import EMTPSolver` | **不变** |
| 高层管线 | `from emtp.case_runner import run_case` | `from emtp.cases import run_case` |
| 节点管理 | `from emtp import NodeBook, NodeIndexer` | **不变** |
| 类型 | `from emtp.types import Branch, ...` | `from emtp.circuit.elements import Branch, ...` |
| 电路容器 | `from emtp.circuit import CircuitModel` | `from emtp.circuit.model import CircuitModel` |
| 校验 | `from emtp.validation import ...` | `from emtp.circuit.validation import ...` |
| 注册中心 | `from emtp.registry import SimulationRegistry` | `from emtp.circuit import SimulationRegistry` |
| 探针 | `from emtp.probes import ProbeManager` | `from emtp.circuit.probes import ProbeManager` |

---

## v0.4.0 → v0.5.0 完整导入路径变更

### circuit/ (拓扑描述)

| v0.4.0 路径 | v0.5.0 路径 |
|---|---|
| `from emtp.nodes import ...` | `from emtp.circuit.nodes import ...` |
| `from emtp.types import ...` | `from emtp.circuit.elements import ...` |
| `from emtp.circuit import ...` | `from emtp.circuit.model import ...` |
| `from emtp.validation import ...` | `from emtp.circuit.validation import ...` |
| `from emtp.registry import ...` | `from emtp.circuit.registry import ...` |
| `from emtp.registry.records import ...` | `from emtp.circuit.registry_records import ...` |
| `from emtp.probes import ...` | `from emtp.circuit.probes import ...` |

### engine/ (求解引擎)

| v0.4.0 路径 | v0.5.0 路径 |
|---|---|
| `from emtp.sparse_solver import ...` | `from emtp.engine.linear import ...` |
| `from emtp.stamping import ...` | `from emtp.engine.stamping import ...` |
| `from emtp.assembly.mna import ...` | `from emtp.engine.mna import ...` |
| `from emtp.kernel import ...` | `from emtp.engine.mna import ...` |
| `from emtp.rhs import ...` | `from emtp.engine.rhs import ...` |
| `from emtp.runtime import ...` | `from emtp.engine.state import ...` |
| `from emtp.runtime.resolve import ...` | `from emtp.engine.nonlinear import ...` |
| `from emtp.runtime.stepper import ...` | `from emtp.engine.simulation import ...` |
| `from emtp.runtime.event_runtime import ...` | `from emtp.engine.simulation import ...` |

### models/ (物理模型)

| v0.4.0 路径 | v0.5.0 路径 |
|---|---|
| `from emtp.devices import ...` | `from emtp.models import ...` |
| `from emtp.devices.base import ...` | `from emtp.models.base import ...` |
| `from emtp.devices.multiport import ...` | `from emtp.models.multiport import ...` |
| `from emtp.devices.resistor import ...` | `from emtp.models.lumped import ...` |
| `from emtp.devices.inductor import ...` | `from emtp.models.lumped import ...` |
| `from emtp.devices.capacitor import ...` | `from emtp.models.lumped import ...` |
| `from emtp.devices.series_rl import ...` | `from emtp.models.lumped import ...` |
| `from emtp.devices.switch import ...` | `from emtp.models.switches import ...` |
| `from emtp.devices.nonlinear import ...` | `from emtp.models.nonlinear import ...` |
| `from emtp.devices.lpm import ...` | `from emtp.models.nonlinear import ...` |
| `from emtp.lines.bergeron import ...` | `from emtp.models.lines import ...` |
| `from emtp.lines.ulm import ...` | `from emtp.models.lines import ...` |
| `from emtp.lines.fitulm_resolver import ...` | `from emtp.models.fitulm import ...` |
| `from emtp.transformers.umec import ...` | `from emtp.models.transformers import ...` |
| `from emtp.sources import ...` | `from emtp.models.sources import ...` |
| `from emtp.nonlinear import ...` | `from emtp.models.nonlinear import ...` |

### cases/ (工况管线)

| v0.4.0 路径 | v0.5.0 路径 |
|---|---|
| `from emtp.config import ...` | `from emtp.cases import ...` |
| `from emtp.builders import ...` | `from emtp.cases import ...` |
| `from emtp.case_runner import ...` | `from emtp.cases.runner import ...` |

### io/ (结果)

| v0.4.0 路径 | v0.5.0 路径 |
|---|---|
| `from emtp.results import ...` | `from emtp.io.results import ...` |
| `from emtp.results.store import ...` | `from emtp.io.results import ...` |
| `from emtp.export import ...` | `from emtp.io.export import ...` |
| `from emtp.snapshot import ...` | `from emtp.io.snapshot import ...` |
| `from emtp.result_bundle import ...` | `from emtp.io.result_bundle import ...` |
| `from emtp.result_db import ...` | `from emtp.io.database import ...` |
| `from emtp.run_id import ...` | `from emtp.io.run_id import ...` |

---

## Solver Methods

| Old method | Recommended alias | Notes |
|-----------|------------------|-------|
| `add_IS(...)` | `add_current_source(...)` | Same behavior |
| `add_VS(...)` | `add_voltage_source(...)` | Same behavior |
| `add_insulator_LPM(...)` | `add_lpm_flashover_insulator(...)` | Clearer name; adds unit docs |
| `add_lightning_IS(...)` | `add_lightning_current_source(...)` | Same behavior |
| `add_standard_twoexpf_IS(...)` | `add_standard_double_exponential_current_source(...)` | Same behavior |

---

## UMEC Factory Functions

| Old function | New function | Returns |
|-------------|-------------|---------|
| `create_umec_transformer_3ph_bank(...)` | `create_umec_transformer_3ph_bank_data(...)` | `UMECTransformerData` |
| _(new)_ | `create_umec_transformer_3ph_bank_instance(dt=..., ...)` | `UMECTransformer` |

The old function `create_umec_transformer_3ph_bank()` returns `UMECTransformerData`, not a transformer instance. The name was misleading. Use `create_umec_transformer_3ph_bank_data()` for clarity.

---

## Direction & Unit Conventions

See [DIRECTION_CONVENTIONS.md](DIRECTION_CONVENTIONS.md) for the full specification of:

- Branch voltage/current direction
- Norton equivalent RHS stamping
- Independent current source direction
- Transmission line port conventions
- UMEC port conventions
- LPM insulator voltage convention
- Per-step operation order
- Supported output units

---

## 模块状态

| 模块 | 状态 |
|--------|--------|
| `emtp_solver_v3.py` | ❌ 已删除（v0.3.1） |
| `emtp_components_series_rl_only.py` | ❌ 已删除（v0.3.1） |
| `emtp_plotting.py` | ❌ 已删除 — 死代码，无引用 |
| v0.4.0 旧子目录 (16 个) | ❌ 已删除（v0.5.0）→ 收敛为 6 目录 |
| `transmission_line_emtp_v2.py` | ✅ 活跃 — Bergeron 模型 |
| `ulm_transmission_line_PARA.py` | ✅ 活跃 — ULM 模型 |
| `umec_transformer.py` | ✅ 活跃 — UMEC 模型 |
| `nonlinear_models_pscad.py` | ✅ 活跃 — 非线性模型 |
| `atp_lightning_current_generator_simplified.py` | ✅ 活跃 — 雷电电流源 |
