# PyEMTP — Python Electromagnetic Transients Program

基于 Python 的电磁暂态（EMTP）仿真求解器。使用修正节点分析法（MNA）进行电路求解，集成多相传输线、非线性元件、UMEC 变压器和绝缘子闪络模型。

**当前版本**: `v0.5.0` · **测试**: 445 passed, 3 skipped · **Python**: 3.12+ · **依赖**: numpy, scipy

---

## 快速开始

### 方式一：程序化 API

```python
from emtp import EMTPSolver

solver = EMTPSolver(dt=1e-6, finish_time=100e-6)
solver.add_VS("Vs", 1, 0, 10.0)          # 10V 电压源
solver.add_R("R1", 1, 0, 100.0)           # 100Ω 电阻
solver.add_voltage_probe("V1", 1, 0)       # 节点 1 电压探针
solver.run()

t = solver.get_time("us")
v = solver.get_voltage_probe("V1", "V")
print(f"V1 = {v[-1]:.2f}V")
```

### 方式二：JSON 配置驱动

```python
from emtp.cases import run_case

result = run_case("cases/templates/rc_step.json")
print(result.metrics)
# {'total_steps': 101, 'G_rebuilds': 1, 'G_cache_hits': 100,
#  'probe_V_cap_peak_V': 0.999, ...}
```

### JSON 配置示例

```json
{
  "case_name": "rc_step",
  "simulation": { "dt": 1e-6, "finish_time": 100e-6 },
  "elements": [
    { "kind": "resistor", "name": "R1", "node_from": 1, "node_to": 2, "R": 10.0 },
    { "kind": "capacitor", "name": "C1", "node_from": 2, "node_to": 0, "C": 1e-6 }
  ],
  "sources": [
    { "kind": "voltage", "name": "VS1", "node_pos": 1, "node_neg": 0, "voltage": 1.0 }
  ],
  "probes": [
    { "kind": "voltage", "name": "V_cap", "node_pos": 2, "node_neg": 0 }
  ]
}
```

---

## Snapshot / Resume（分段运行）

```python
from emtp.cases import run_case, load_case_config, build_solver_from_config

config = load_case_config("cases/templates/rc_step.json")

# 运行到中点并保存 snapshot
solver = build_solver_from_config(config)
solver.run_until(50e-6)
solver.save_snapshot("snapshots/midpoint", config=config)

# 从 snapshot 继续运行
solver2 = build_solver_from_config(config)
solver2.load_snapshot("snapshots/midpoint")
solver2.run_until(100e-6, reset_state=False)
```

---

## 结果导出

```python
from emtp.io import export_waveforms_npz, export_metrics_json, read_waveform_chunk

# 导出波形 (stride=10 降采样)
export_waveforms_npz(result.waveforms, "runs/job_001", stride=10)

# 导出指标
export_metrics_json(result.metrics, "runs/job_001")

# 分块读取（前端友好）
chunk = read_waveform_chunk("runs/job_001", "V_cap", start=100, count=50)
# {'signal': 'V_cap', 'start': 100, 'count': 50, 'time': [...], 'values': [...]}
```

### SQLite 运行历史

```python
from emtp.io import ResultDatabase

db = ResultDatabase("runs/history.sqlite")
db.insert_run("job_001", "rc_step", "done", "runs/job_001")
db.insert_metrics("job_001", result.metrics)
db.list_recent_runs(10)
```

---

## 支持的元件

| 类别 | 元件 | API |
|------|------|-----|
| 无源 | 电阻 R | `add_R(name, nf, nt, R)` |
| | 电感 L | `add_L(name, nf, nt, L)` |
| | 电容 C | `add_C(name, nf, nt, C)` |
| | 串联 RL | `add_series_RL(name, nf, nt, R, L)` |
| | 开关 | `add_SW(name, nf, nt, t_close, t_open)` |
| 电源 | 电流源 | `add_IS(name, nf, nt, func)` |
| | 电压源 | `add_VS(name, pos, neg, func)` |
| | 雷电电流源 | `add_lightning_IS(...)` |
| | 双指数源 | `add_standard_double_exponential_current_source(...)` |
| 线路 | Bergeron | `add_bergeron_line(name, nk, nm, Zc, tau)` |
| | ULM (外部文件) | `add_ULM_line(name, nodes_send, nodes_recv, length, fitulm_path=...)` |
| | ULM (LCP自动生成) | `add_ULM_line(name, nodes_send, nodes_recv, generate_fitulm=True, lcp_spec=...)` |
| 变压器 | UMEC | `add_UMEC_transformer(name, data)` |
| 非线性 | MOA 避雷器 | `add_MOA_from_file(name, nf, nt, file)` |
| | LPM 闪络 | `add_insulator_LPM(name, nf, nt, gap_length)` |

---

## 架构总览

```
emtp/
├── solver.py               EMTPSolver 用户门面
│
├── circuit/                电路拓扑是什么
│   ├── nodes.py            NodeIndexer / NodeBook
│   ├── elements.py         Branch / VoltageSource / ElementType / ...
│   ├── model.py            CircuitModel 数据容器
│   ├── validation.py       电路校验
│   ├── registry.py         SimulationRegistry 统一对象注册
│   ├── registry_records.py ElementRecord / SourceRecord / MultiPortRecord
│   └── probes.py           ProbeManager 探针管理
│
├── engine/                 怎么一步步求解
│   ├── linear.py           SparseLinearSolver (SuperLU)
│   ├── stamping.py         COOStamper / StampingEngine
│   ├── mna.py              MNAAssembler + MNAKernel
│   ├── rhs.py              RHSEngine RHS 构建
│   ├── state.py            DynamicDeviceRuntime 每步状态管理
│   ├── nonlinear.py        ResolveManager + ResolveEvent
│   └── simulation.py       TimeStepper + EventRuntime
│
├── models/                 元件物理模型怎么算
│   ├── base.py             Device Protocol
│   ├── multiport.py        MultiPortDevice Protocol
│   ├── lumped.py           R / L / C / SeriesRL
│   ├── switches.py         Switch 开关
│   ├── nonlinear.py        MOA + LPM + PSCAD 导出
│   ├── sources.py          雷电电流源
│   ├── lines.py            Bergeron + ULM + Layer 0 导出
│   ├── fitulm.py           FitULMSpec + FitULMResolver
│   └── transformers.py     UMEC 变压器
│
├── cases/                  工况怎么进来
│   ├── schema.py           CaseConfig / SimulationOptions
│   ├── loader.py           load_case_config()
│   ├── validator.py        validate_case_config()
│   ├── defaults.py         SUPPORTED_ELEMENTS / SOURCES / PROBES
│   ├── element_builder.py  元件构建
│   ├── source_builder.py   电源构建
│   ├── probe_builder.py    探针构建
│   ├── builder.py          build_solver_from_config()
│   └── runner.py           run_case() 全流程入口
│
├── io/                     结果怎么出去
│   ├── results.py          ResultStore + scale 工具函数
│   ├── result_bundle.py    ResultBundle 输出容器
│   ├── database.py         ResultDatabase SQLite 历史
│   ├── run_id.py           make_run_id()
│   ├── export.py           NPZ / CSV / JSON 导出
│   └── snapshot.py         状态快照 save / restore / hash
│
└── utils/                  通用工具（预留）
```

### v0.4.0 → v0.5.0 导入路径变更

| 旧路径 (v0.4.0) | 新路径 (v0.5.0) |
|---|---|
| `from emtp.config import ...` | `from emtp.cases import ...` |
| `from emtp.builders import ...` | `from emtp.cases import ...` |
| `from emtp.case_runner import ...` | `from emtp.cases import ...` |
| `from emtp.export import ...` | `from emtp.io import ...` |
| `from emtp.result_db import ...` | `from emtp.io import ...` |
| `from emtp.snapshot import ...` | `from emtp.io import ...` |
| `from emtp.devices import ...` | `from emtp.models import ...` |
| `from emtp.lines import ...` | `from emtp.models import ...` |
| `from emtp.transformers import ...` | `from emtp.models import ...` |
| `from emtp.registry import ...` | `from emtp.circuit import ...` |
| `from emtp.probes import ...` | `from emtp.circuit import ...` |
| `from emtp.types import ...` | `from emtp.circuit.elements import ...` |
| `from emtp.nodes import ...` | `from emtp.circuit.nodes import ...` |
| `from emtp.stamping import ...` | `from emtp.engine.stamping import ...` |
| `from emtp.rhs import ...` | `from emtp.engine.rhs import ...` |
| `from emtp.kernel import ...` | `from emtp.engine.mna import ...` |
| `from emtp.runtime import ...` | `from emtp.engine.state import ...` |

---

## MNA 修正节点分析

求解器构建 (n+m)×(n+m) 增广系统：

```
    ┌       ┐ ┌     ┐   ┌   ┐
    │ G   B │ │  v  │   │ I │
    │       │ │     │ = │   │
    │ C   D │ │ i_s │   │ E │
    └       ┘ └     ┘   └   ┘
```

- **G** (n×n): 节点导纳矩阵（梯形法 Norton 等效电导）
- **B/C** (n×m): 电压源关联矩阵
- **v**: 节点电压 · **i_s**: 电压源电流

矩阵以 `scipy.sparse.csc_matrix` 存储，SuperLU 稀疏 LU 分解缓存复用。

---

## 导入约定

```python
# 唯一入口
from emtp import EMTPSolver

# Identity 保证
from emtp import EMTPSolver as A
from emtp.solver import EMTPSolver as B
assert A is B  # True
```

---

## 配置选项

```python
solver = EMTPSolver(
    dt=1e-6,                    # 时间步长 (s)
    finish_time=100e-6,         # 仿真结束时间 (s)
    verbose=True,               # 打印计时和统计

    record_all_node_voltages=False,  # 全节点电压（大型网络建议关闭）
    record_branch_history=True,
    record_source_history=True,
    record_line_history=True,

    pre_sample_sources=True,    # 预采样独立源
    use_rhs_plan=True,          # 预编译 RHS 拓扑

    ulm_batch_mode="auto",      # "auto" | "parallel" | "serial" | "off"
    allow_singular_regularization=False,

    # Multiport dispatch (experimental)
    use_multiport_lines=False,
    use_multiport_transformers=False,
)
```

---

## 测试

```bash
pytest tests/ -q --ignore=tests/test_tower_case_p1.py
# 445 passed, 3 skipped
```

| 分类 | 测试文件 | 覆盖 |
|------|---------|------|
| 基础 | `test_basic_mna`, `test_trapezoidal_rlc`, `test_switches`, `test_nodes` | MNA/RLC/SW |
| 物理验证 | `test_p5_basic_physics`, `test_p5_*` | RC/RL/Bergeron/ULM/UMEC/MOA/LPM |
| API 回归 | `test_solver_regression` (56 tests) | getter/probe/validate/pre_sample/rhs_plan |
| 协议 | `test_multiport_contract`, `test_bergeron_adapter`, `test_ulm_umec_adapters`, `test_multiport_registry` | Device/MultiPortDevice |
| 运行时 | `test_result_store`, `test_mna_assembler`, `test_circuit_model`, `test_import_canonical_paths` | ResultStore/MNA/Circuit/import |
| 配置层 | `test_case_config` (22 tests) | load/validate/build/run_case |
| 快照 | `test_snapshot` (6 tests) | save/load/run_until/resume equivalence |
| 导出 | `test_export_and_db` (18 tests) | NPZ/JSON/stride/chunk/SQLite |
| 闭环 | `test_product_kernel_loop` (26 tests) | run_case → export → db → snapshot safety |
| 修复验证 | `test_fixes_min_max_chunk_snapshot` (17 tests) | DB min/max, 2D chunk, Bergeron state_dict, resume equivalence |

---

## 依赖关系

```
emtp/solver.py
  ├── numpy, scipy.sparse           (数值计算)
  ├── emtp/circuit/                 (NodeIndexer, Branch, ElementType, CircuitModel, Registry, Probes)
  ├── emtp/engine/                  (MNAKernel, RHSEngine, DynamicDeviceRuntime, ResolveManager, TimeStepper, SparseLinearSolver)
  ├── emtp/models/                  (Device + MultiPortDevice Protocol, all element adapters)
  ├── emtp/io/                      (ResultStore, export, snapshot, database, run_id)
  │
  ├── [可选] transmission_line_emtp_v2.py       Bergeron 底层模型 (via models/lines.py)
  ├── [可选] ulm_transmission_line_PARA.py      ULM 底层模型 + batch (via models/lines.py)
  ├── [可选] umec_transformer.py                UMEC 底层模型 (via models/transformers.py)
  ├── [可选] nonlinear_models_pscad.py          MOA + LPM (via models/nonlinear.py)
  └── [可选] atp_lightning_current_generator.py 雷电电流源 (via models/sources.py)
```

---

## 版本历程

| 版本 | Commit | 关键变更 |
|------|--------|---------|
| v0.1 | `75f307e` | P3/P4/P5 模块化：Device 协议、emtp 包、物理验证 |
| v0.2.0 | `d439b80` | Solver 迁移：emtp/solver.py canonical、去重、MultiPortDevice、ResolveManager、ResultStore (131 tests) |
| v0.2.1 | `f42404b` | PR-10~17：ResultStore 接入、Multiport registry、Bergeron/ULM/UMEC adapter 注册、ResolveEvent、MNAAssembler (154 tests) |
| v0.2.2 | `cf8b7dc` | PR-18~19：TimeStepper 主循环、CircuitModel 容器 (159 tests) |
| v0.3.0 | `6d77ab8` | Case/Config 层、Snapshot/Resume、结果降采样导出、SQLite 数据库 (205 tests) |
| v0.3.1 | `52b87f8` | Bugfix: run_id 字符串路径生成；补测 (248 tests) |
| v0.3.2 | `866e210` | **LCP 集成**: fitULM 自动生成, solver.add_ULM_line(), pylcp 包 (289 tests) |
| v0.3.3 | `735cfdf` | **P0 修复 ×8**: verify/缓存/length/P_matrix/Y块对角 等 (309 tests) |
| v0.4.0 | `d05a9eb` | **PR0–PR7 重构**: registry/probes/rhs/kernel/event_runtime + 安全网 136 tests (445 tests) |
| v0.5.0 | `55a1e79` | **目录重组**: 16 碎片目录 → 6 强边界目录；import 路径全部更新 |

---

## 文档

- [API Migration Guide](API_MIGRATION.md) — v0.4.0 → v0.5.0 导入路径变更
- [Direction Conventions](DIRECTION_CONVENTIONS.md) — 符号、单位和 stamping 约定
- [Architecture](ARCHITECTURE.md) — 详细架构文档
