# Release 分发架构与通用生态发布指南 (Release Distribution & Universal Skills Guide)

- **归属规范**：[`docs/guidelines/engineering/skill-suite-portability-specification.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/guidelines/engineering/skill-suite-portability-specification.md) §8.1、§8.4
- **审查评估**：[`docs/audits/2026-10-16-skill-structure-review.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/audits/2026-10-16-skill-structure-review.md) §5.4、H2
- **执行清单**：[`docs/specs/engineering/delivery-execution-roadmap.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/delivery-execution-roadmap.md) `P2-04`

---

## 1. 核心架构与生态兼容背景

在开发工作区中，本工程遵循严格的工程隔离规范：
- 开发源码仅位于 `skill_bundle/skills/` 与 `skill_bundle/runtime/core/`；
- 工作区不建立任何软链接污染本地目录；
- 禁止直接将开发源码注册为宿主生产技能。

为了满足跨宿主、跨平台的生产级安装以及社区开源生态的即插即用诉求，本项目通过构建工具派生标准的 **Release 产物与分发树 (Release Distribution Tree)**：
1. **多宿主原生兼容**：支持 Codex、Hermes Desktop、WorkBuddy 及 Universal 目录（`~/.agents/skills`）；
2. **通用开源 Skills 生态打通**：通过标准化的 `skills/` 根目录布局，无缝支持通用生态一行命令接入：
   ```bash
   npx skills add cvdnn/a-stock-agents -g
   ```
3. **锚点技能架构 (Anchor Skill)**：在构建期将公共 `runtime/`、`assets/` 与 `references/` 收敛注入到总入口 `skills/a-stock-agents/` 中，其余 19 项专业技能通过转发壳与三级寻址（自定位 ➔ 兄弟定位 ➔ 收据定位）稳定执行。

---

## 2. 标准 Release 分发目录规范 (Canonical Layout)

通过 `tools/packaging/publish_release.py` 或 `tools/packaging/common.py` 构建出的标准 Release 根结构如下：

```text
<Release 归档根 / Release 分支根>/
├── .codex-plugin/
│   └── plugin.json                    ← Codex 插件清单（支持 Codex 插件市场一层发现）
├── skills/                            ← 标准技能集合根（支持 npx skills add 直接扫描）
│   ├── a-stock-agents/                ←【锚点技能】：总入口 + 包含完整 runtime 量化引擎
│   │   ├── SKILL.md
│   │   ├── bundle.json                (distribution: release, anchor: true)
│   │   ├── runtime/                   (core 引擎与 CLI 统一启动器)
│   │   ├── assets/ & references/      (公共配置模板与说明)
│   │   └── requirements*.txt
│   ├── astock-data-feed/              ←【专业技能】：标准文档 + 轻量转发壳
│   │   ├── SKILL.md
│   │   ├── scripts/
│   │   └── requirements.txt
│   └── …（共 19 个专业量化技能）
├── install.ps1                        ←【Windows 双模态安装内核】
├── install.sh                         ←【POSIX 双模态安装内核 (0o755)】
├── INSTALL.json                       ←【平台元数据与版本契约声明】
├── requirements.txt                   ←【基础依赖声明】
├── requirements-full.txt              ←【全量量化依赖（含 akshare/MyTT/efinance，派生自 pyproject.toml）】
├── LICENSE                            ←【开源许可证】
├── README.md                          ←【发版使用说明】
└── SHA256SUMS                         ←【全文件哈希校验账本】
```

---

## 3. 三大安装与接入通道全景对照

| 安装通道 | 执行命令 | 目标受众与场景 | 依赖管理机制 | 引擎寻址机制 |
| :--- | :--- | :--- | :--- | :--- |
| **模态一：AI 协同安装** | 复制标准 AI Copilot Bootstrap Prompt 发给 AI | 普通用户在 AIChat 中通过 5 阶段卡片交互引导安装 | 自动在数据根创建独立 `.venv`，隔离无污染 | 自动建立宿主链接，收据与兄弟双寻址 |
| **模态二：终端命令行手动安装** | `.\install.ps1` (Win) 或 `./install.sh` (POSIX) | 开发者与系统运维，支持 TUI 交互式导轨与 CLI 参数化 | 自动探测或新建隔离 `.venv` | 自动配置宿主路径并生成 `install.json` 收据 |
| **通道三：通用 Skills CLI** | `npx skills add cvdnn/a-stock-agents -g` | 熟悉 Node.js / Universal 生态的 AI Agent 用户 | 依赖宿主已有的全局 Python 环境或首启自检 | 依赖兄弟定位（`../a-stock-agents/bundle.json`） |

---

## 4. 通用生态接入实战与验证

### 4.1 全局一键安装
```bash
# 全局安装全部 20 个技能入口（包含 1 锚点总入口 + 19 专业技能）
npx skills add cvdnn/a-stock-agents -g
```

### 4.2 指定安装单个技能
```bash
# 仅安装总入口锚点技能
npx skills add cvdnn/a-stock-agents --skill a-stock-agents -g

# 安装单个专业技能（建议同时安装 a-stock-agents 锚点）
npx skills add cvdnn/a-stock-agents --skill astock-data-feed -g
```

### 4.3 兄弟寻址容错验证
当 `npx skills add` 将技能拉取到 `~/.agents/skills/` 目录后：
1. `skills/a-stock-agents` 拥有完整 `runtime/core`；
2. 其他专业技能（如 `skills/astock-screener-5a`）被触发时，其内部转发壳检测到平级兄弟目录存在 `../a-stock-agents/bundle.json`，自动透传执行；
3. 若未安装锚点技能，系统将 fail-closed 抛出标准结构化异常：`ANCHOR_SKILL_MISSING`，明确指导用户安装总入口。

---

## 5. 发布工具使用方法

### 5.1 导出标准分发目录
```bash
# 默认导出到 output/packages/a_stock_agents_v3_release_dist
python tools/packaging/publish_release.py

# 导出到指定目录并输出结构化 JSON
python tools/packaging/publish_release.py --export-dir output/dist --json
```

### 5.2 模拟验证（Dry-run）
```bash
python tools/packaging/publish_release.py --dry-run --json
```

### 5.3 同步 Release 孤立分支
```bash
python tools/packaging/publish_release.py --sync-branch release --json
```
