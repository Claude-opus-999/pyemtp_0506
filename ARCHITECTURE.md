# PyEMTP 架构文档

版本 `v0.5.0` · 2026-05-06 · **445 passed, 3 skipped**

---

## 目录

1. [整体分层架构](#整体分层架构)
2. [根目录文件清单](#根目录文件清单)
3. [Layer 0: 外部物理库](#layer-0-外部物理库)
4. [Layer 1: 核心求解器 — emtp/ 包](#layer-1-核心求解器-emtp-包)
5. [Layer 2: LCP 线路常数计算](#layer-2-lcp-线路常数计算)
6. [数据流](#数据流)
7. [测试体系](#测试体系)
8. [版本历程](#版本历程)
9. [已知技术债](#已知技术债)

---

## 整体分层架构

```
┌──────────────────────────────────────────────────────────────┐
│  Public API                                                   │
│  emtp/__init__.py  +  emtp/solver.py                          │
│  from emtp import EMTPSolver                                  │
├──────────────────────────────────────────────────────────────┤
│  cases/                                                       │
│  JSON schema、配置加载、配置校验、solver builder、run_case      │
├──────────────────────────────────────────────────────────────┤
│  circuit/                                                     │
│  CircuitModel、NodeIndexer、Element records、Registry、Probes   │
│  负责：电路拓扑是什么                                          │
├──────────────────────────────────────────────────────────────┤
│  engine/                                                      │
│  SimulationEngine、RuntimeState、MNA、RHS、Nonlinear、LU Solver │
│  负责：怎么一步步求解                                          │
├──────────────────────────────────────────────────────────────┤
│  models/                                                      │
│  R/L/C、source、switch、MOA、LPM、Bergeron、ULM、UMEC            │
│  负责：元件物理模型怎么算                                      │
├──────────────────────────────────────────────────────────────┤
│  io/                                                          │
│  ResultStore、ResultBundle、export、snapshot、SQLite、run_id    │
│  负责：结果怎么保存、导出、恢复                                │
├──────────────────────────────────────────────────────────────┤
│  Layer 0: 外部物理库 (顶层 .py 文件)                            │
│  transmission_line_emtp_v2.py   ulm_transmission_line_PARA.py  │
│  nonlinear_models_pscad.py      umec_transformer.py            │
│  atp_lightning_current_generator_simplified.py                 │
├──────────────────────────────────────────────────────────────┤
│  Layer 2: LCP / pylcp — 线路常数计算、fitULM 生成、缓存          │
└──────────────────────────────────────────────────────────────┘
```

**依赖方向**: cases → solver → circuit/engine/models/io → Layer 0（单向，绝不反向）

---

## 根目录文件清单

```
pyemtp_v0.2/
├── README.md                                     # 项目文档
├── CLAUDE.md                                     # Claude Code 行为指南
├── ARCHITECTURE.md                               # 架构文档（本文件）
├── API_MIGRATION.md                              # 旧→新 API 迁移说明
├── DIRECTION_CONVENTIONS.md                      # 符号/单位/stamping 约定
├── .gitignore
│
├── atp_lightning_current_generator_simplified.py  # Layer 0: 雷电电流源 (1058 行)
├── transmission_line_emtp_v2.py                   # Layer 0: Bergeron 传输线 (381 行)
├── ulm_transmission_line_PARA.py                  # Layer 0: ULM 频变传输线 (2540 行)
├── nonlinear_models_pscad.py                      # Layer 0: MOA/LPM 非线性 (765 行)
├── umec_transformer.py                            # Layer 0: UMEC 变压器 (766 行)
│
├── LCP/                                           # Layer 2: 线路常数物理引擎 (12 .py)
├── pylcp/                                         # Layer 2: LCP Python 包装层 (10 .py)
├── emtp/                                          # 主求解器包 (45 .py) ← v0.5.0 收敛到 6 强边界目录
├── tests/                                         # 测试套件 (52 .py, 445 passed)
└── cases/templates/                               # JSON 工况模板 (4 个)
```

---

## v0.5.0: 目录重组 — 16 目录 → 6 强边界目录

v0.5.0 把 v0.4.0 的 16 个碎片化一级子目录收敛为 6 个强边界目录：

```
v0.4.0 (旧)                                v0.5.0 (新)
──────────────────────────────────────     ──────────────────────────────
emtp/registry/      emtp/probes/          emtp/circuit/   (circuit 是什么)
emtp/nodes.py       emtp/types.py               nodes.py, elements.py,
emtp/circuit.py     emtp/validation.py        model.py, validation.py,
                                              registry.py, registry_records.py,
                                              probes.py

emtp/assembly/      emtp/kernel/           emtp/engine/    (怎么求解)
emtp/rhs/           emtp/runtime/                linear.py, stamping.py,
emtp/stamping.py    emtp/sparse_solver.py        mna.py, rhs.py, state.py,
                                                 nonlinear.py, simulation.py

emtp/devices/       emtp/lines/            emtp/models/    (元件怎么算)
emtp/transformers/  emtp/sources/                base.py, multiport.py,
emtp/nonlinear/                                 lumped.py, switches.py,
                                                nonlinear.py, sources.py,
                                                lines.py, fitulm.py,
                                                transformers.py

emtp/config/        emtp/builders/         emtp/cases/     (工况怎么进来)
emtp/case_runner.py                               defaults.py, schema.py,
                                                loader.py, validator.py,
                                                element_builder.py,
                                                source_builder.py,
                                                probe_builder.py,
                                                builder.py, runner.py

emtp/results/       emtp/export/           emtp/io/        (结果怎么出去)
emtp/snapshot/      emtp/result_bundle.py         results.py, result_bundle.py,
emtp/result_db.py   emtp/run_id.py              database.py, run_id.py,
                                                export.py, snapshot.py

emtp/utils/   (预留)
emtp/solver.py  (用户门面)
```

### 关键合并

| 合并 | 旧文件 | 新文件 |
|------|--------|--------|
| R/L/C/SeriesRL | `devices/{resistor,inductor,capacitor,series_rl}.py` | `models/lumped.py` |
| 非线性 + LPM + PSCAD 导出 | `devices/{nonlinear,lpm}.py` + `nonlinear/__init__.py` | `models/nonlinear.py` |
| Bergeron + ULM + Layer 0 导出 | `lines/{bergeron,ulm}.py` + `lines/__init__.py` | `models/lines.py` |
| MNAAssembler + MNAKernel | `assembly/mna.py` + `kernel/mna_kernel.py` | `engine/mna.py` |
| TimeStepper + EventRuntime | `runtime/{stepper,event_runtime}.py` | `engine/simulation.py` |
| 3 export 文件 | `export/{csv,metrics,waveform}_exporter.py` | `io/export.py` |
| 4 snapshot 文件 + scale helpers | `snapshot/{hashing,restore,schema,serializer}.py` + `results/__init__.py` | `io/snapshot.py` + `io/results.py` |

---

## v0.3.1–v0.3.2 已删除的旧内容

| 文件/目录 | 删除原因 |
|-----------|---------|
| `emtp_solver_v3.py` | 旧入口垫片 — 22 个引用文件已全部迁移到 `from emtp import EMTPSolver` |
| `emtp_components_series_rl_only.py` | 旧类型垫片 — solver.py 三层 try/except 导入链已清理 |
| `emtp_plotting.py` | 死代码 — 全项目无任何 import 引用 |
| `test_lasted/` | 旧测试 — 6 个遗留脚本，与 tests/ 功能重叠 |
| `validation/` | 空框架 — cases/golden_results 子目录均空，仅 4 个工具脚本 |
| `EMTP_SOLVER_ARCHITECTURE.md` | 旧文档 — 大量引用已删除的 emtp_solver_v3.py |
| `P3_P4_P5_IMPLEMENTATION_REPORT.md` | 历史报告 — 描述旧→新架构迁移，已无参考价值 |

---

## Layer 0: 外部物理库

五个大型自包含模块。仅依赖 numpy/scipy/numba/stdlib，相互无交叉依赖，不依赖 `emtp/` 包内任何模块。由 `emtp/models/` 通过 try/except + `None` 回退模式按需导入。

| 文件 | 行数 | 用途 | 核心导出 |
|------|------|------|---------|
| `transmission_line_emtp_v2.py` | 381 | 无损 Bergeron 恒参数传输线 | `BergeronLine`, `DelayBuffer`, `TransmissionLineInterface` |
| `ulm_transmission_line_PARA.py` | 2540 | ULM 频变传输线 + Numba JIT | `FitULMData`, `FitULMReader`, `ULMModel`, `ULMLine`, `ULMBatchPack` |
| `nonlinear_models_pscad.py` | 765 | PSCAD 分段 MOA + CIGRE LPM 闪络 | `SegmentedMOAResistor`, `InsulatorFlashoverLPM`, `SegmentedSolverHelper` |
| `umec_transformer.py` | 766 | UMEC 三相变压器（含饱和） | `UMECTransformer`, `UMECTransformerData` |
| `atp_lightning_current_generator_simplified.py` | 1058 | ATP 兼容雷电电流源（双指数 + Heidler） | `TWOEXPFCurrentSource`, `HEIDLERFCurrentSource`, `LightningWaveform` |

---

## Layer 1: 核心求解器 — emtp/ 包

`EMTPSolver` 是 MNA 瞬态仿真的用户门面类。

```python
from emtp import EMTPSolver
# 或
from emtp.cases import run_case
```

### 实际目录结构（v0.5.0）

```
emtp/
├── __init__.py              # 惰性导出 EMTPSolver（__getattr__）
├── solver.py                # ★ 用户门面 (~3670 行) — 对象装配 + public API
│
├── circuit/                 # 电路拓扑是什么
│   ├── nodes.py             #   NodeIndexer (紧凑映射) + NodeBook (命名节点)
│   ├── elements.py          #   Branch, ElementType, VoltageSource, CurrentSource, RHSPlan
│   ├── model.py             #   CircuitModel dataclass — 独立于求解器的电路拓扑容器
│   ├── validation.py        #   拓扑/参数/内存校验 → ValidationReport
│   ├── registry.py          #   SimulationRegistry — 统一对象注册中心 (shadow mode)
│   ├── registry_records.py  #   ElementRecord, SourceRecord, MultiPortRecord
│   └── probes.py            #   ProbeManager — 探针注册/采样
│
├── engine/                  # 怎么一步步求解
│   ├── linear.py            #   SparseLinearSolver — SuperLU 封装 + _sparse_factorize
│   ├── stamping.py          #   COOStamper + StampingEngine — MNA 装配生命周期
│   ├── mna.py               #   MNAAssembler + MNAKernel — G 矩阵构建/LU 求解
│   ├── rhs.py               #   RHSEngine — RHS 构建/预采样/RHSPlan
│   ├── state.py             #   DynamicDeviceRuntime — 开关事件/分支V-I更新/历史推进
│   ├── nonlinear.py         #   ResolveManager + ResolveEvent — MOA/LPM/UMEC 重解
│   └── simulation.py        #   TimeStepper + EventRuntime — 每步编排
│
├── models/                  # 元件物理模型怎么算
│   ├── base.py              #   Device Protocol — 二端元件抽象接口
│   ├── multiport.py         #   MultiPortDevice Protocol — 多端口元件接口
│   ├── lumped.py            #   R/L/C/SeriesRL 集总元件
│   ├── switches.py          #   SwitchDevice — 定时开/关
│   ├── nonlinear.py         #   NonlinearResistorDevice + LPMFlashoverDevice + PSCAD 导出
│   ├── sources.py           #   雷电电流源 (Layer 0 try/except 导入)
│   ├── lines.py             #   BergeronLineDevice + ULMLineDevice + Layer 0 导出
│   ├── fitulm.py            #   FitULMSpec + FitULMResolver
│   └── transformers.py      #   UMECTransformerDevice + UMEC Layer 0 导出
│
├── cases/                   # 工况怎么进来
│   ├── schema.py            #   CaseConfig + SimulationOptions
│   ├── loader.py            #   load_case_config()
│   ├── validator.py         #   validate_case_config()
│   ├── defaults.py          #   SUPPORTED_ELEMENTS/SOURCES/PROBES + DEFAULT_SIMULATION
│   ├── element_builder.py   #   add_element_to_solver()
│   ├── source_builder.py    #   add_source_to_solver()
│   ├── probe_builder.py     #   add_probe_to_solver()
│   ├── builder.py           #   build_solver_from_config()
│   └── runner.py            #   run_case() — 全流程入口
│
├── io/                      # 结果怎么出去
│   ├── results.py           #   ResultStore + scale/voltage/current 工具函数
│   ├── result_bundle.py     #   ResultBundle dataclass
│   ├── database.py          #   ResultDatabase — SQLite 运行历史
│   ├── run_id.py            #   make_run_id() — 时戳+UUID
│   ├── export.py            #   NPZ/CSV/JSON 导出 (3 in 1)
│   └── snapshot.py          #   快照 save/restore/hash (4 in 1)
│
└── utils/                   # 通用工具（预留）
```

### 关键关系

- `solver.py` 单向导入 engine/circuit/models/io 子包，models/ 负责隔离 Layer 0
- `emtp/__init__.py` 惰性导出 `EMTPSolver`（避免 `__init__` 阶段触发 solver 内所有 Layer 0 导入）
- engine 层模块（kernel/rhs/runtime）当前部分仍是 thin wrapper，后续 PR 逐步将内部逻辑迁入
- models/ 是所有 Layer 0 物理库的唯一导入入口，solver 不直接 import Layer 0

---

## v0.4.0 子模块 → v0.5.0 路径对照（已废弃名称）

| v0.4.0 路径 (旧) | v0.5.0 路径 (当前) | 说明 |
|---|---|---|
| `emtp/registry/simulation_registry.py` | `emtp/circuit/registry.py` | 迁入 circuit |
| `emtp/registry/records.py` | `emtp/circuit/registry_records.py` | 迁入 circuit |
| `emtp/probes/probe_manager.py` | `emtp/circuit/probes.py` | 迁入 circuit |
| `emtp/nodes.py` | `emtp/circuit/nodes.py` | 迁入 circuit |
| `emtp/types.py` | `emtp/circuit/elements.py` | 迁入 circuit |
| `emtp/circuit.py` | `emtp/circuit/model.py` | 迁入 circuit |
| `emtp/validation.py` | `emtp/circuit/validation.py` | 迁入 circuit |
| `emtp/assembly/mna.py` | `emtp/engine/mna.py` | 迁入 engine (与 kernel 合并) |
| `emtp/kernel/mna_kernel.py` | `emtp/engine/mna.py` | 迁入 engine (与 assembly 合并) |
| `emtp/rhs/rhs_engine.py` | `emtp/engine/rhs.py` | 迁入 engine |
| `emtp/runtime/__init__.py` | `emtp/engine/state.py` | 迁入 engine |
| `emtp/runtime/resolve.py` | `emtp/engine/nonlinear.py` | 迁入 engine |
| `emtp/runtime/stepper.py` | `emtp/engine/simulation.py` | 迁入 engine |
| `emtp/runtime/event_runtime.py` | `emtp/engine/simulation.py` | 迁入 engine (与 stepper 合并) |
| `emtp/stamping.py` | `emtp/engine/stamping.py` | 迁入 engine |
| `emtp/sparse_solver.py` | `emtp/engine/linear.py` | 迁入 engine |
| `emtp/devices/*` | `emtp/models/*` | 迁入 models |
| `emtp/lines/*` | `emtp/models/lines.py` + `fitulm.py` | 迁入 models |
| `emtp/transformers/umec.py` | `emtp/models/transformers.py` | 迁入 models |
| `emtp/sources/__init__.py` | `emtp/models/sources.py` | 迁入 models |
| `emtp/nonlinear/__init__.py` | `emtp/models/nonlinear.py` | 迁入 models |
| `emtp/config/*` | `emtp/cases/*` | 迁入 cases |
| `emtp/builders/*` | `emtp/cases/*` | 迁入 cases |
| `emtp/case_runner.py` | `emtp/cases/runner.py` | 迁入 cases |
| `emtp/results/store.py` | `emtp/io/results.py` | 迁入 io |
| `emtp/results/__init__.py` (helpers) | `emtp/io/results.py` | 迁入 io |
| `emtp/export/*` | `emtp/io/export.py` | 迁入 io (3 in 1) |
| `emtp/snapshot/*` | `emtp/io/snapshot.py` | 迁入 io (4 in 1) |
| `emtp/result_bundle.py` | `emtp/io/result_bundle.py` | 迁入 io |
| `emtp/result_db.py` | `emtp/io/database.py` | 迁入 io |
| `emtp/run_id.py` | `emtp/io/run_id.py` | 迁入 io |

---

## Layer 2: LCP 线路常数计算

v0.3.2 新增。分两层：`LCP/` 是物理引擎（底层算法），`pylcp/` 是 Python 包装层（面向 EMTP 集成）。

### LCP/ — 线路常数物理引擎 (12 .py)

```
LCP/
├── __init__.py                           # 包入口
├── cable_model.py                        # 电缆 Z/Y (Ametani 1980)
├── ulm_atp_zy_deri_semlyen.py            # 架空线 Z/Y (Deri-Semlyen)
├── vectfit3.py                           # Vector Fitting v1.3.1 引擎
├── vf_core.py                            # VF 适配层 → VectorFitResult
├── vector_fitting_v411_independent.py    # ULM 完整拟合 v4.11
└── test/                                 # 案例/验证脚本
    ├── pscad_reader.py                   # PSCAD 输出文件读取器
    ├── ulm_ohl_calculation_deri_semlyen.py  # 架空线完整案例
    ├── ulm_three_core_cable_v2 (1).py    # 三芯管型电缆案例
    ├── ulm_cable_calculation.py          # 多回铠装电缆案例
    └── test0304.py                       # 架空线 PSCAD 对比
```

**模块依赖链**:

```
vectfit3.py          ← VF 底层引擎，无 LCP 内依赖
  ↑
vf_core.py           ← VF 适配层，导入 .vectfit3
  ↑
vector_fitting_v411_independent.py  ← ULM 完整拟合 + fitULM 读写，导入 .vf_core
```

### pylcp/ — LCP Python 包装层 (10 .py)

```
pylcp/
├── __init__.py              # 统一导出
├── specs.py                 # LCPLineType 枚举 + LCPFitULMSpec dataclass
├── exceptions.py            # LCPError / LCPInputError / LCPFittingError / ...
├── validation.py            # validate_frequency_vector() / validate_zy_matrices()
├── cache.py                 # compute_cache_key() / get_cache_path()
├── lcp_fitulm_generator.py  # LCPFitULMGenerator — Z/Y → VF → fitULM 全链路
└── generation/
    ├── __init__.py
    ├── ohl_deri_semlyen.py          # 架空线 Z/Y
    ├── pipe_type_cable.py           # 管型电缆 Z/Y (兼容 2D/3D P_matrix)
    └── multi_armored_cable.py       # 多回铠装电缆 Z/Y (块对角 Y 组装)
```

### ULM 线路接入 — 两条路径

**路径 A：外部 fitULM 文件**（已有文件，直接读取）

```python
solver.add_ULM_line(
    name="line1",
    nodes_send=[1, 2, 3], nodes_recv=[101, 102, 103],
    length=5000.0,
    generate_fitulm=False,
    fitulm_path="models/cable14.fitULM",
)
```

**路径 B：LCP 自动生成**（从几何参数生成 fitULM）

```python
from pylcp import LCPLineType, LCPFitULMSpec

lcp_spec = LCPFitULMSpec(
    line_type=LCPLineType.OHL_DERI_SEMLYEN,
    name="ohl_line", length=20000.0,
    freq=np.logspace(0, 5, 201),
    geometry_config=line_geometry,
)

solver.add_ULM_line(
    name="ohl_line",
    nodes_send=[1, 2], nodes_recv=[101, 102],
    generate_fitulm=True,
    lcp_spec=lcp_spec,
)
```

---

## 数据流

### run_case() 全链路

```
run_case("cases/templates/rc_step.json")
  │
  ├─ 1. load_case_config()          cases/loader.py
  │     ├─ JSON → CaseConfig        cases/schema.py
  │     └─ validate_case_config()   cases/validator.py
  │
  ├─ 2. build_solver_from_config()  cases/builder.py
  │     ├─ add_element_to_solver()  cases/element_builder.py
  │     ├─ add_source_to_solver()   cases/source_builder.py
  │     └─ add_probe_to_solver()    cases/probe_builder.py
  │
  ├─ 3. solver.run()                solver.py
  │     ├─ DynamicDeviceRuntime     engine/state.py
  │     ├─ ResolveManager           engine/nonlinear.py
  │     ├─ TimeStepper              engine/simulation.py
  │     ├─ MNAAssembler / MNAKernel engine/mna.py
  │     ├─ SparseLinearSolver       engine/linear.py
  │     └─ ResultStore              io/results.py
  │
  ├─ 4. _collect_metrics()          cases/runner.py
  ├─ 5. _collect_waveforms()        cases/runner.py
  │
  ├─ 6. export_waveforms_npz()      io/export.py
  ├─ 7. export_metrics_json()       io/export.py
  ├─ 8. [可选] export_waveforms_csv() io/export.py
  │
  └─ 9. ResultDatabase.insert_*()   io/database.py
```

### 时间步内部流程

```
TimeStepper.run()                       engine/simulation.py
  └─ for step in range(n_steps):
       └─ EventRuntime.step()
            ├─ pre_step_events()        engine/state.py (switch/LPM)
            ├─ RHSEngine.build()        engine/rhs.py
            ├─ MNAKernel.ensure_matrix() engine/mna.py
            ├─ MNAKernel.solve()        engine/mna.py
            ├─ ResolveManager.solve()   engine/nonlinear.py (MOA/UMEC/LPM)
            ├─ DynamicDeviceRuntime     engine/state.py (branch V/I)
            ├─ ProbeManager.record()    circuit/probes.py
            └─ DynamicDeviceRuntime     engine/state.py (history advance)
```

---

## 测试体系

```
445 passed, 3 skipped
```

```
tests/
├── test_basic_mna.py               # MNA 基本装配
├── test_trapezoidal_rlc.py         # 梯形法 RLC
├── test_switches.py                # 开关元件
├── test_nodes.py                   # 节点管理
│   ...
│
├── test_case_config.py             # 配置加载/验证
├── test_snapshot.py                # 快照保存/恢复
├── test_export_and_db.py           # 导出 + 数据库
├── test_product_kernel_loop.py     # run_case → export → db 闭环
├── test_solver_regression.py       # 求解器回归 (56 tests)
│
├── test_baseline_lcp_emtp.py       # LCP 模块可达性 + fitULM API + 语法检查
├── test_pr1_fitulm_resolver.py     # FitULMResolver + add_ULM_line 全接口
│
├── pylcp_tests/                    # LCP 集成测试
│   ├── test_pr2_generation.py       # Z/Y 生成 + P_matrix 2D/3D + Y 块对角
│   ├── test_pr3_generator.py        # LCPFitULMGenerator 管线
│   ├── test_cache.py                # 内容 hash 缓存 + 版本字段 + cache_dir 传播
│   └── test_pr67_integration.py     # 缓存复用 + E2E 求解器仿真
│
├── validation/                      # P5 物理验证
│   ├── test_p5_basic_physics.py
│   ├── test_p5_bergeron_reflection.py
│   ├── test_p5_lpm_validation.py
│   ├── test_p5_moa_validation.py
│   ├── test_p5_umec_validation.py
│   ├── test_p5_ulm_validation.py
│   └── test_p5_tower_validation.py
│
└── refactor_safety/                # v0.4.0+ 重构安全网 (136 tests)
    ├── test_public_api_contract.py  # 78 方法 + 属性存在 + 8 调用模式
    ├── test_import_boundaries.py    # Layer 隔离 / solver→Layer0 禁止 (xfail)
    ├── test_waveform_regression.py  # RC/RL/开关/Bergeron 标量不变量
    ├── test_registry_consistency.py # 双写一致性/版本号/去重
    ├── test_probe_manager.py        # 注册/索引/采样/向后兼容
    ├── test_rhs_engine.py           # RHS 构建/预采样等效
    ├── test_mna_kernel.py           # G 重建/LU 求解/dirty 检测
    ├── test_event_runtime.py        # 步进编排/开关事件
    └── test_element_builder_ulm.py  # Builder ulm_line 集成
```

---

## 版本历程

| 版本 | Commit | 关键变更 |
|------|--------|---------|
| v0.1 | `75f307e` | P3/P4/P5 模块化：Device 协议、emtp 包、物理验证 |
| v0.2.0 | `d439b80` | Solver 迁移：emtp/solver.py canonical、MultiPortDevice、ResolveManager |
| v0.2.1 | `f42404b` | PR-10~17：ResultStore、Multiport registry、Bergeron/ULM/UMEC adapter |
| v0.2.2 | `cf8b7dc` | PR-18~19：TimeStepper 主循环、CircuitModel 容器 |
| v0.3.0 | `6d77ab8` | Case/Config 层、Snapshot/Resume、降采样导出、SQLite |
| v0.3.1 | `52b87f8` | Bugfix: run_id 字符串路径；PR1: 删除旧 API 垫片 |
| v0.3.1 | `a487e0f` | Cleanup: 删除死代码/旧测试/空框架 (-10,771 行) |
| v0.3.2 | `866e210` | **LCP 集成**: fitULM 自动生成, solver.add_ULM_line(), pylcp 包 |
| v0.3.2 | `200d879`→`56f3d43` | **P0 修复 x6**: 语法检查 / verify 不吞异常 / hash 缓存 / length 一致性 / P_matrix 2D-3D / Y 块对角 |
| v0.3.3 | `19acfa0`→`735cfdf` | **严格验收 x2**: cache key 版本字段 + cache_dir 传播 / length 默认 None 语义 |
| v0.4.0 | `8278832`→`07ac052` | **重构 PR0–PR7**: 安全网 (136 tests) + registry/probes/rhs/kernel/event_runtime 子模块 + element_builder ulm_line |
| v0.5.0 | `55a1e79` | **目录重组**: 16 碎片目录 → 6 强边界目录 (circuit/engine/models/cases/io/utils)；关键文件合并 (lumped, lines, nonlinear, mna, simulation, export, snapshot)；所有 import 路径更新 |

---

## 已知技术债（v0.5.0 后）

Thin wrapper 层 (RHSEngine/MNAKernel/EventRuntime/SimulationRegistry) 已建立框架，每个子模块有了自己的家。后续深度重构方向：

| # | 问题 | 状态 |
|---|------|------|
| 1 | `SimulationRegistry` 从 shadow mode 升级为唯一真相源 | 框架已建，双写进行中 |
| 2 | `RHSEngine` 内部化 source_sampler / RHSPlan 编译 | wrapper 已建，内部仍委托 solver |
| 3 | `MNAKernel` 接管 layout / topology signature / 诊断 | wrapper 已建，内部仍委托 solver |
| 4 | `EventRuntime` 三步接口（pre_step / post_solve_check / commit_step） | wrapper 已建，设备接口待统一 |
| 5 | `solver.py` 不再直接 import Layer 0 物理模型 | 仍在 solver.py 中（xfail 标记） |
| 6 | solver.py 瘦身：逐步迁出 MNA/RHS/timestep 逻辑 | 待 PR-3~PR-7 |

---

## 架构红线（后续修改强制遵守）

1. `solver.py` 不直接 import Layer 0 物理模型
2. `solver.py` 不直接构造 G/RHS
3. 新增物理模型不修改 `solver.py`，只新增 Device/MultiPortDevice adapter 和 builder
4. models/ 是 Layer 0 物理库的唯一导入入口
5. engine/ 不依赖 cases/（求解不依赖 JSON 配置）
6. circuit/ 不依赖 engine/（拓扑描述不依赖求解算法）
