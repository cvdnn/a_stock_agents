# A-Stock Agents 核心规范、指南、架构与规则知识库 (Guidelines Center)

欢迎查阅 **A-Stock Agents** 核心研发标准知识库。本项目所有的**工程规范 (Specifications)**、**实践指南 (Guides)**、**系统架构 (Architecture)** 与 **量化业务规则 (Rules)** 统一在此集中归档与治理，作为全系统研发与演进的单一真理来源 (Single Source of Truth, SSOT)。

> 💡 **架构职责划分**：
> - **`docs/guidelines/`（本目录）**：专注于**定义与规范本身**，包含完整的架构设计、交互标准、数学模型公式、代码契约与操作规范。
> - **[`docs/specs/`](../specs/README.md)**：专注于**落地实施与执行进度追踪**，包含各阶段任务清单、实施矩阵、验证证据与交付里程碑。

---

## 一、 知识体系分类矩阵导航 (Taxonomy Matrix)

### 1. 工程与交互规范 (Specifications)
| 规范名称 | 物理路径 | 对应实施看板 | 核心内容概述 |
|:---|:---|:---:|:---|
| **项目工程结构与智能体工作区架构规范** | [`project-structure-specification.md`](project-structure-specification.md) | [`SPEC-ENG-001`](../specs/engineering/eng-project-structure-and-workspace.md) | 零全局污染原则、单一真理来源 (SSOT)、跨平台 CLI 门面、用户私有数据物理隔离 (`output/`) |
| **A2UI 组件库拆解与模块化注册发现机制规范** | [`a2ui-component-registry-specification.md`](a2ui-component-registry-specification.md) | [`SPEC-A2UI-002`](../specs/a2ui/a2ui-component-registry-specification.md) | 领域组件包规范 (`@a2ui/pack-astock`)、未决缓冲队列时序解耦、命名空间隔离与自省清单 |

### 2. 研发与设计指南 (Guides & Governance)
| 指南名称 | 物理路径 | 关联看板/规范 | 核心内容概述 |
|:---|:---|:---:|:---|
| **Web UI 界面设计与交互指南** | [`ui-design-guide.md`](ui-design-guide.md) | [`SPEC-UI-001`](../specs/ui/ui-design-and-interaction-specification.md) | 浅色金融风格、红涨绿跌、双模动态视口（40/60 投研助手 vs 业务主工作区）、卡片微边框 |
| **算法审查与全生命周期治理指南** | [`algorithm-governance.md`](algorithm-governance.md) | [`SPEC-ALGO-001`](../specs/algorithm/algo-lifecycle-and-governance-specification.md) | 44 项量化算法全景清单、AlgoRegistry 2.0 统一纳管抽象、ALCM 四道质量门禁 |
| **代码审查标准与工程红线清单** | [`code-review.md`](code-review.md) | - | 严禁全局目录污染、禁止生硬竖条、路径解耦等 10 项严苛审查标准 |
| **回归测试架构与规约指南** | [`testing-guide.md`](testing-guide.md) | - | 10 大核心领域测试套件、TDD 契约、即测即删原则与持续集成基线 |
| **架构命名规范与设计范式指南** | [`naming-conventions.md`](naming-conventions.md) | - | 消除版本号侵入、模型演进四大设计范式、废弃退役协议与文档双语命名规范 |

### 3. 系统核心架构设计 (Architecture)
| 架构设计名称 | 物理路径 | 对应实施看板 | 核心内容概述 |
|:---|:---|:---:|:---|
| **独立 Web AIChatUI 与 Skill 治理系统架构** | [`web-aichat-architecture.md`](web-aichat-architecture.md) | [`SPEC-ARCH-001`](../specs/architecture/arch-web-aichat-and-skill-governance.md) | 脱离第三方宿主的独立 Web 交互中枢、FastAPI 服务网关、17 项技能治理控制平面与多端部署 |
| **大模型双轨接入与多场景角色分配架构** | [`llm-provider-architecture.md`](llm-provider-architecture.md) | [`SPEC-ARCH-002`](../specs/architecture/arch-llm-provider-and-role-allocation.md) | 物理接入轨 (Providers) 与逻辑角色轨 (Roles) 双轨解耦、网络延迟探测与防 CORS 代理 |
| **Token 链路安全网关与审计 Agent 架构** | [`token-security-architecture.md`](token-security-architecture.md) | [`SPEC-ARCH-003`](../specs/architecture/arch-token-security-gateway.md) | 控制平面与执行平面物理分离、请求上行脱敏、响应下行过滤、不可篡改指纹审计日志 |
| **Agent2UI (A2UI) 前端渲染引擎框架架构** | [`a2ui-framework-architecture.md`](a2ui-framework-architecture.md) | [`SPEC-A2UI-001`](../specs/a2ui/a2ui-framework-engine-specification.md) | 静态 WebApp Shell 容器硬锁定、1:1 骨架预占位 (CLS=0)、五阶段渐进式水合流水线 |

### 4. 量化业务与实战规则 (Rules)
| 规则名称 | 物理路径 | 对应实施看板 | 核心内容概述 |
|:---|:---|:---:|:---|
| **A股最低保本卖出价量化精算与进位规则** | [`breakeven-calculation-rules.md`](breakeven-calculation-rules.md) | [`SPEC-BIZ-002`](../specs/business/biz-breakeven-price-calculation-rules.md) | 全摩擦税费公式精算、理论值向上精确进位至 0.01 元分位 (`math.ceil`) 绝对保本铁律 |
| **券商佣金及市场交易费率配置化规则** | [`broker-commission-rules.md`](broker-commission-rules.md) | [`SPEC-BIZ-001`](../specs/business/biz-broker-commission-configurable-design.md) | 全局 `config.yaml` 费率中心、万2.5及保底5元动态化、CLI 管理与未配置友好提醒 |
| **实战交易反应动作与量化风控执行规则** | [`trading-execution-rules.md`](trading-execution-rules.md) | [`SPEC-BIZ-003`](../specs/business/biz-trading-execution-and-risk-control.md) | 阿尔法选股与贝塔执行解耦、实战交易三原则、六大交易反应动作、T0/T1/T2 三级风控止损 |

---

## 二、 统一命名与演进范式

归档于 `docs/guidelines/` 的文档严格遵循统一的命名范式：
```text
{domain_slug}-{category_suffix}.md
```
- **`category_suffix`**：
  - `-specification.md`：工程技术规格、结构与接口标准；
  - `-guide.md` / `-governance.md`：开发、交互与治理指引；
  - `-architecture.md`：系统拓扑与核心子系统架构设计；
  - `-rules.md`：量化数学公式、交易纪律与业务硬约束。
- **不可变性与单一真理来源**：物理文件名禁止版本化侵入，持续演进保持最新。
