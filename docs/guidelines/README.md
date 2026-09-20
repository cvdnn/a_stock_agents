# A-Stock Agents 核心规范、指南、架构与规则知识库 (Guidelines Center)

欢迎查阅 **A-Stock Agents** 核心研发标准知识库。本项目所有的**工程规范 (Specifications)**、**实践指南 (Guides)**、**系统架构 (Architecture)** 与 **量化业务规则 (Rules)** 统一在此按 7 大领域子目录集中归档与治理，作为全系统研发与演进的单一真理来源 (Single Source of Truth, SSOT)。

> 💡 **架构职责划分**：
> - **`docs/guidelines/`（本目录）**：专注于**定义与规范本身**，包含完整的架构设计、交互标准、数学模型公式、代码契约与操作规范。
> - **[`docs/specs/`](../specs/README.md)**：专注于**落地实施与执行进度追踪**，包含各阶段任务清单、实施矩阵、验证证据与交付里程碑。

---

## 一、 7 大领域分层知识矩阵导航 (Domain Taxonomy Matrix)

本知识库与 [`docs/specs/`](../specs/README.md) 实施看板保持 7 大领域完全对应与对称治理：

```text
docs/guidelines/
├── a2ui/         # A2UI 前端渲染引擎与组件体系规范
├── algorithm/    # 算法资产与全生命周期治理规范
├── architecture/ # 系统核心架构设计规范
├── business/     # 量化业务规则与风控执行标准
├── data/         # 行情数据源与同步存储规范
├── engineering/  # 工程结构、代码审查、安全加固与测试规范
└── ui/           # 前端界面设计、交互与模块化重构指南
```

---

### 1. A2UI 框架与组件规范 (`a2ui/`)
| 规范名称 | 类别 | 物理路径 | 对应实施看板 | 核心内容概述 |
|:---|:---:|:---|:---:|:---|
| **Agent2UI (A2UI) 前端渲染引擎框架架构** | 架构 | [`a2ui/a2ui-framework-architecture.md`](a2ui/a2ui-framework-architecture.md) | [`SPEC-A2UI-001`](../specs/a2ui/a2ui-framework-engine-specification.md) | 静态 WebApp Shell 容器硬锁定、1:1 骨架预占位 (CLS=0)、五阶段渐进式水合流水线 |
| **A2UI 组件库拆解与模块化注册发现机制规范** | 规范 | [`a2ui/a2ui-component-registry-specification.md`](a2ui/a2ui-component-registry-specification.md) | [`SPEC-A2UI-002`](../specs/a2ui/a2ui-component-registry-specification.md) | 领域组件包规范 (`@a2ui/pack-astock`)、未决缓冲队列时序解耦、命名空间隔离与自省清单 |

### 2. 算法模型与生命周期治理 (`algorithm/`)
| 规范名称 | 类别 | 物理路径 | 对应实施看板 | 核心内容概述 |
|:---|:---:|:---|:---:|:---|
| **算法审查与全生命周期治理指南** | 治理 | [`algorithm/algorithm-governance.md`](algorithm/algorithm-governance.md) | [`SPEC-ALGO-001`](../specs/algorithm/algo-lifecycle-and-governance-specification.md)<br>[`SPEC-ALGO-ISS-001`](../specs/algorithm/configurable-funnel-feature-build-spec.md) | 44 项量化算法全景清单、AlgoRegistry 2.0 统一纳管抽象、ALCM 四道质量门禁、漏斗选股系统设计 |

### 3. 系统核心架构设计 (`architecture/`)
| 规范名称 | 类别 | 物理路径 | 对应实施看板 | 核心内容概述 |
|:---|:---:|:---|:---:|:---|
| **独立 Web AIChatUI 与 Skill 治理系统架构** | 架构 | [`architecture/web-aichat-architecture.md`](architecture/web-aichat-architecture.md) | [`SPEC-ARCH-001`](../specs/architecture/arch-web-aichat-and-skill-governance.md) | 脱离第三方宿主的独立 Web 交互中枢、FastAPI 服务网关、18 项技能治理控制平面与多端部署 |
| **大模型双轨接入与多场景角色分配架构** | 架构 | [`architecture/llm-provider-architecture.md`](architecture/llm-provider-architecture.md) | [`SPEC-ARCH-002`](../specs/architecture/arch-llm-provider-and-role-allocation.md) | 物理接入轨 (Providers) 与逻辑角色轨 (Roles) 双轨解耦、网络延迟探测与防 CORS 代理 |
| **Token 链路安全网关与审计 Agent 架构** | 架构 | [`architecture/token-security-architecture.md`](architecture/token-security-architecture.md) | [`SPEC-ARCH-003`](../specs/architecture/arch-token-security-gateway.md) | 控制平面与执行平面物理分离、请求上行脱敏、响应下行过滤、不可篡改指纹审计日志 |

### 4. 量化业务与实战规则 (`business/`)
| 规范名称 | 类别 | 物理路径 | 对应实施看板 | 核心内容概述 |
|:---|:---:|:---|:---:|:---|
| **券商佣金及市场交易费率配置化规则** | 规则 | [`business/broker-commission-rules.md`](business/broker-commission-rules.md) | [`SPEC-BIZ-001`](../specs/business/biz-broker-commission-configurable-design.md) | 全局 `config.yaml` 费率中心、万2.5及保底5元动态化、CLI 管理与未配置友好提醒 |
| **A股最低保本卖出价量化精算与进位规则** | 规则 | [`business/breakeven-calculation-rules.md`](business/breakeven-calculation-rules.md) | [`SPEC-BIZ-002`](../specs/business/biz-breakeven-price-calculation-rules.md) | 全摩擦税费公式精算、理论值向上精确进位至 0.01 元分位 (`math.ceil`) 绝对保本铁律 |
| **实战交易反应动作与量化风控执行规则** | 规则 | [`business/trading-execution-rules.md`](business/trading-execution-rules.md) | [`SPEC-BIZ-003`](../specs/business/biz-trading-execution-and-risk-control.md) | 阿尔法选股与贝塔执行解耦、实战交易三原则、六大交易反应动作、T0/T1/T2 三级风控止损 |

### 5. 行情数据与存储规范 (`data/`)
| 规范名称 | 类别 | 物理路径 | 对应实施看板 | 核心内容概述 |
|:---|:---:|:---|:---:|:---|
| **A-Stock 行情数据接口与全周期技术指标规范** | 规范 | [`data/market-data-api-specification.md`](data/market-data-api-specification.md) | [`SPEC-DATA-001`](../specs/data/market-data-sync-implementation-plan.md) | 4级降级数据源规范、实时快照与全周期K线协议字典、本地闭环技术指标计算标准、调用量级容量模型 |
| **A-Stock 本地行情数据同步与安全隔离规范** | 规范 | [`data/market-data-sync-specification.md`](data/market-data-sync-specification.md) | [`SPEC-DATA-001`](../specs/data/market-data-sync-implementation-plan.md) | 交易日时钟驱动策略、完整性Gap探测自愈算法、SQLite嵌入式存储设计、`local/` 700权限物理阻断规范 |

### 6. 工程质量与安全规范 (`engineering/`)
| 规范名称 | 类别 | 物理路径 | 对应实施看板 | 核心内容概述 |
|:---|:---:|:---|:---:|:---|
| **项目工程结构与智能体工作区架构规范** | 规范 | [`engineering/project-structure-specification.md`](engineering/project-structure-specification.md) | [`SPEC-ENG-001`](../specs/engineering/eng-project-structure-and-workspace.md) | 零全局污染原则、单一真理来源 (SSOT)、跨平台 CLI 门面、用户私有数据物理隔离 (`output/`) |
| **架构命名规范与设计范式指南** | 指南 | [`engineering/naming-conventions.md`](engineering/naming-conventions.md) | [`SPEC-ENG-001`](../specs/engineering/eng-project-structure-and-workspace.md) | 消除版本号侵入、模型演进四大设计范式、废弃退役协议、文档体系领域分类标准 (SSOT) |
| **代码审查标准与工程红线清单** | 指南 | [`engineering/code-review.md`](engineering/code-review.md) | [`eng-remediation-acceptance.md`](../specs/engineering/eng-remediation-acceptance.md) | 当前可检查的真实性、安全、分层与证据规则；历史结论由指南链接至审查归档与整改验收台账 |
| **系统安全与加固开发实战指南** | 指南 | [`engineering/security-hardening-guide.md`](engineering/security-hardening-guide.md) | [`security-remediation-plan.md`](../audits/2026-09-14-security-remediation-execution-plan.md)<br>[`eng-remediation-plan.md`](../specs/engineering/eng-remediation-plan.md) | 8项漏洞场景与防御规约手册、物理沙箱隔离、iframe严格降权、无内联事件委托、物理DNS防SSRF |
| **回归测试架构与规约指南** | 指南 | [`engineering/testing-guide.md`](engineering/testing-guide.md) | [`eng-runtime-and-test-plan.md`](../specs/engineering/eng-runtime-and-test-remediation-plan.md) | 10 大核心领域测试套件、TDD 契约、即测即删原则与持续集成基线 |

### 7. UI 与前端重构指南 (`ui/`)
| 规范名称 | 类别 | 物理路径 | 对应实施看板 | 核心内容概述 |
|:---|:---:|:---|:---:|:---|
| **Web UI 界面设计与交互指南** | 指南 | [`ui/ui-design-guide.md`](ui/ui-design-guide.md) | [`SPEC-UI-001`](../specs/ui/ui-design-and-interaction-specification.md) | 浅色金融风格、红涨绿跌、双模动态视口（40/60 投研助手 vs 业务主工作区）、卡片微边框 |
| **前端架构重构与开发指南：app.js 源码拆分与模块化规范** | 指南 | [`ui/app-js-modularization-guide.md`](ui/app-js-modularization-guide.md) | [`chat-presentation-plan.md`](../specs/ui/chat-response-presentation-plan.md) | 9340行巨石单体解耦为22个领域驱动模块、零构建工具依赖、100%兼容215处HTML内联事件与后续开发规范 |

---

## 二、 统一命名与演进范式

归档于 `docs/guidelines/` 各领域子目录的文档严格遵循统一的命名范式：
```text
docs/guidelines/{domain}/{domain_slug}-{category_suffix}.md
```
- **`domain`**：7 大业务与工程领域（`a2ui/`, `algorithm/`, `architecture/`, `business/`, `data/`, `engineering/`, `ui/`）
- **`category_suffix`**：
  - `-specification.md`：工程技术规格、结构与接口标准；
  - `-guide.md` / `-governance.md`：开发、交互与治理指引；
  - `-architecture.md`：系统拓扑与核心子系统架构设计；
  - `-rules.md`：量化数学公式、交易纪律与业务硬约束。
- **不可变性与单一真理来源**：物理文件名禁止版本化与时间戳侵入，持续演进保持最新。
