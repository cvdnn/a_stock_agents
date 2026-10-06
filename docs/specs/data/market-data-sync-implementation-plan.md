# SPEC-DATA-001: 本地行情数据同步机制实施计划与验收看板 (market-data-sync-implementation-plan)

> **规范编号**：`SPEC-DATA-001`  
> **实施状态**：✅ **正式基线 (Production Baseline, M1–M4 100% 交付)** · ✅ **M5 交付（漏斗数据依赖，2026-10-06 两批完成）**  
> **关联权威规范 (SSOT)**：  
> - [`market-data-api-specification.md`](../../guidelines/data/market-data-api-specification.md)（A-Stock 行情数据 · 接口与全周期技术指标规范）  
> - [`market-data-sync-specification.md`](../../guidelines/data/market-data-sync-specification.md)（A-Stock 行情数据 · 本地同步与安全隔离规范）
> **关联控制面看板**：[`SPEC-UI-003`](../ui/market-data-sync-control-console-plan.md)

---

## 一、 实施背景与目标

针对项目中行情数据多源获取（腾讯/新浪/东财）的 API 调用瓶颈、防止多用户或高频 Agent 重复拉取触发外部反爬封禁，并为本地技术指标分析提供**毫秒级（<5ms）离线数据底座**，本项目规划并实施了本地数据同步机制。

### 核心交付目标
1. **统一数据时序存储**：基于 SQLite 建立本地公共嵌入式主库，支持复合主键去重与多周期检索；
2. **多模式同步能力**：支持当日收盘快速同步、时间区间回溯、增量追加与全量重构；
3. **数据完整性自愈**：实现交易日历对齐、断点缺漏日探测与一键定向回补；
4. **安全与权限防泄漏**：设立独立 `local/` 目录，通过 POSIX 700/600 权限物理阻断同机其他用户访问，且在 Git 和打包发布中 100% 隔离。

---

## 二、 任务实施与执行矩阵 (Implementation Matrix)

> 本表使用 M1–M4 表示实施里程碑；同步标的优先级 P0–P3 仅用于数据调度，二者不得混用。

| 阶段 | 任务模块 | 具体改造内容与物理文件 | 状态 | 验收证据与交付成果 |
|:---:|:---|:---|:---:|:---|
| **M1** | **存储引擎建设** | 新建 `MarketDataStore`，支持 WAL 并发读写与索引优化<br>• [`scripts/core/data/sync_engine.py`](../../../scripts/core/data/sync_engine.py) | ✅ 完成 | 建立 `daily_kline` 与 `sync_meta` 表，支持 Upsert |
| **M1** | **日历与完整性算法** | 实现 `TradeCalendar` 节假日过滤与基准指数差集算法<br>• [`scripts/core/data/sync_engine.py`](../../../scripts/core/data/sync_engine.py) | ✅ 完成 | 精准识别交易日断点与坏点，输出健康报告 |
| **M1** | **同步调度核心** | 实现 `DataSyncEngine`，支持 `--today/--start/--mode` 等调度<br>• [`scripts/core/data/sync_engine.py`](../../../scripts/core/data/sync_engine.py) | ✅ 完成 | 增量模式重复执行 0.0s 跳过，全量 250 日K 仅需 0.27s |
| **M2** | **`local/` 目录与权限** | 建立 `local/` 独立目录，实施 0o700 / 0o600 POSIX 物理权限加固<br>• [`scripts/core/workspace.py`](../../../scripts/core/workspace.py)<br>• [`scripts/core/config.py`](../../../scripts/core/config.py) | ✅ 完成 | 仅 Owner 可读写，同机其他用户彻底阻断访问 |
| **M2** | **数据服务平滑迁移** | 将 `chats.db` 与 `astock_data.db` 迁入 `local/` 并做自动兼容<br>• [`scripts/server/config.py`](../../../scripts/server/config.py) | ✅ 完成 | 迁移成功，旧目录安全清理，服务端配置无缝切至 `local/` |
| **M2** | **CLI 门面与分发** | 接入 `astock data sync`，支持终端彩色报告与 `--json`<br>• [`scripts/core/cli.py`](../../../scripts/core/cli.py)<br>• [`scripts/core/commands/data_cmds.py`](../../../scripts/core/commands/data_cmds.py) | ✅ 完成 | 命令行参数完备，交互体验与文档契约一致 |
| **M2** | **离线指标分析打通** | 优化 `DataBridge.get_kline_robust()`，优先命中本地数据库<br>• [`scripts/core/data/data_bridge.py`](../../../scripts/core/data/data_bridge.py) | ✅ 完成 | `astock data tech` 无需外网请求即可秒级计算指标 |
| **M3** | **防泄漏与打包隔离** | 在版本控制与发布打包中彻底排除 `local/`<br>• [`.gitignore`](../../../.gitignore)<br>• [`.dockerignore`](../../../.dockerignore)<br>• [`scripts/tools/pack.py`](../../../scripts/tools/pack.py) | ✅ 完成 | Git 追踪纯净，打包工具排除 `local/` |
| **M3** | **自动化测试验证** | 编写单元测试并运行全套回归套件<br>• [`tests/test_data_sync.py`](../../../tests/core/test_data_sync.py)<br>• [`verify.py`](../../../verify.py) | ✅ 完成 | 单元测试 16/16 通过，核心测试全部通过 |
| **M4** | **批量并发加速** | 引入 ThreadPoolExecutor 支持 --workers 多线程并发与保序<br>• [`scripts/core/data/sync_engine.py`](../../../scripts/core/data/sync_engine.py)<br>• [`scripts/core/commands/data_cmds.py`](../../../scripts/core/commands/data_cmds.py) | ✅ 完成 | 批量同步吞吐量倍增，SQLite WAL 模式并发安全 |
| **M4** | **停牌与假阳性消解** | 区分合法停牌与真实断点，在 sync_meta 登记停牌切片避免误报<br>• [`scripts/core/data/sync_engine.py`](../../../scripts/core/data/sync_engine.py) | ✅ 完成 | 消除停牌股与次新股误报，校验列新增“停牌数” |
| **M4** | **常驻自动化定时守护** | 新建 DataSyncDaemon，依据 15:35 / 15:40 时钟状态机自动定盘同步<br>• [`scripts/core/data/sync_daemon.py`](../../../scripts/core/data/sync_daemon.py)<br>• [`scripts/core/cli.py`](../../../scripts/core/cli.py) | ✅ 完成 | 支持 CLI 独立守护与单次检测，日志沉淀至 log/ |
| **M4** | **交易日历动态真值延伸** | 支持超出已知年份时从本地基准指数历史时序动态推导真值<br>• [`scripts/core/data/sync_engine.py`](../../../scripts/core/data/sync_engine.py) | ✅ 完成 | 摆脱静态硬编码年份限制，实现日历自愈 |
| **M5** | **登记册扩项 D9–D12** | D9 快照 / D11 Tick+五档 / D12 竞价运行捕获切片（`intraday_archiver.py`，落 `local/cache/intraday/`，盘后 seal 写 §5.5 水位）；D10 资金流**精算档+代理兜底双档**（渠道 2026-10-06 实测核验通过，覆盖表探测已扩展，`astock dataset --key capital_flow`）；控制台登记册 12 行占位<br>• [`scripts/core/data/intraday_archiver.py`](../../../scripts/core/data/intraday_archiver.py)<br>• [`scripts/core/data/dataset_sync.py`](../../../scripts/core/data/dataset_sync.py)<br>• [`scripts/server/services/data_sync_overview.py`](../../../scripts/server/services/data_sync_overview.py) | ✅ 完成 | D10 已接入（精算档 finalized 水位为 `main_fund_inflow` 启用前提，W-07）；D12 东财盘前渠道非交易日实测失败，维持快照切片归档口径，交易日复测后再定建表 |
| **M5** | **候选池门槛字段随日线定盘** | 流通市值/股本前置到 15:35 批次（裁定 W-02），`DATASET_WINDOWS.valuation` 由 16:30 前移，幂等 REPLACE<br>• [`scripts/core/data/dataset_sync.py`](../../../scripts/core/data/dataset_sync.py) | ✅ 完成 | 解除与 `post_close` 硬门槛的时序冲突（W-01 判据切换为水位门控） |
| **M5** | **`UniverseWatermark` 契约实现** | `write_universe_watermark` / `get_universe_watermark` / `check_post_close_ready`（复用 `dataset_audit.detail` JSON，state 列单点换算保持控制台兼容）；D2 定盘水位 `sync_daily_kline_watermark` 挂 15:45 窗口；CLI `astock dataset --watermark`<br>• [`scripts/core/data/dataset_sync.py`](../../../scripts/core/data/dataset_sync.py) | ✅ 完成 | 消费方为选股侧数据装配（`finalized_local`）；覆盖率主口径 = 有值标的数 ÷ 候选池标的数；degraded 仅观察运行 |
| **M5** | **分钟线双通道** | 盘中前向采集归档（`intraday_archiver` m1 切片，ts 水位去重、append-only）+ 盘后回补深度校验（W-04：`_expected_min_date` 按 1m 30/5m 90/15·30·60m 180 交易日回数，深度不足判 degraded，不出假水位）<br>• [`scripts/core/data/intraday_archiver.py`](../../../scripts/core/data/intraday_archiver.py)<br>• [`scripts/core/data/dataset_sync.py`](../../../scripts/core/data/dataset_sync.py) | ✅ 完成 | 回归用例：`test_minute_kline_depth_guard_marks_shallow_history` |
| **M5** | **五档与 Tick 解析统一** | T-09 落地：`tencent_fields.parse_order_book` 权威解析（parts[9-28]，缺档不入列、整体缺失或卖盘为 0 → None）；DataBridge 快照与归档器切片透传 `order_book`；Tick 采集并入归档器（direction B/S/M 源侧口径显式落切片）<br>• [`scripts/core/data/tencent_fields.py`](../../../scripts/core/data/tencent_fields.py) | ✅ 完成 | 真实数据实测通过（`astock data quote` 直出五档）；回归用例 `test_tencent_fields_order_book_t09`；ERS B2 委买卖比可计算 |
| **M5** | **`stock_basic` 字段核验** | 三列渠道核验完成（2026-10-06 实测 akshare 1.18.94）：`stock_info_sh_name_code` 列仅 代码/简称/全称/上市日期，**源无 ST/上市状态列** → 按 W-03 终局维持派生口径（name 词表 + 代码前缀/调用入口），不建列 | ✅ 完成 | 核验证据已登记规范 §5.1 D1 行渠道列；无代码改动 |
| **M5** | **流通市值单位口径统一（高危）** | 按裁定 W-09 在入库时一次性 `× 1e8` 并以 `source=tencent_snapshot_derived_yuan` 标记换算口径<br>• [`scripts/core/data/dataset_sync.py`](../../../scripts/core/data/dataset_sync.py) | ✅ 完成 | 回归用例：`test_capital_snapshot_persisted_in_yuan`；旧批次（source 无 `_yuan` 后缀且值为亿）须删除重同步 |
| **M5** | **缺失值禁止置零** | 按裁定 W-10：`get_fundamentals()` 缺失返回 `None` + `blocking_fields`；D7/D10 分母改为请求标的数，0/缺失标的跳过入库并计入 watermark missing<br>• [`scripts/core/data/data_bridge.py`](../../../scripts/core/data/data_bridge.py)<br>• [`scripts/core/data/dataset_sync.py`](../../../scripts/core/data/dataset_sync.py) | ✅ 完成 | 回归用例：`test_fundamentals_missing_fields_return_none_not_zero` / `test_capital_missing_market_cap_counts_as_missing` |

> **扩展边界**：P3 全市场交易日定时增量同步、Web 手动范围选择与相关设置/API 属于控制面扩展，由 `SPEC-UI-003` 跟踪；不计入本看板当前"正式基线"完成度。**M5 由选股漏斗示例 1 的数据依赖反向牵引产生**（登记册 D9–D12 与冲突裁定 W-01～W-10 见权威规范 §5.1/§5.4）。两批交付汇总：**第 1 批（2026-10-06）** W-09 单位口径、W-10 缺失禁置零、D7 门槛字段前置 15:35、D10 代理档管线、§5.5 水位契约与 CLI、D9/D11/D12 运行捕获归档器、控制台 12 行登记册；**第 2 批（2026-10-06）** T-09 五档解析（`parse_order_book` 权威实现+透传，真实数据实测）、D3 回补深度校验（W-04 防假水位）、D10 精算档 `eastmoney_exact`（渠道实测核验 120 交易日日频、覆盖表探测翻正）、D1 三列核验终局（维持派生口径）。**唯一遗留**：D12 东财盘前渠道交易日复测（不影响快照切片归档通道）。M1–M4 的"正式基线 100% 交付"结论不受 M5 影响。

---

## 三、 CLI 交互命令对照表

| 业务场景 | 推荐命令 | 预期效果 |
|:---|:---|:---|
| **默认增量同步** | `./bin/astock data sync --code 600519` | 若本地为最新则 0 次网络调用跳过；否则增量拉取缺失切片 |
| **全量基准重构** | `./bin/astock data sync --code 600519 --mode full --days 250` | 全量更新近 250 交易日前复权 K 线，耗时 ~0.27s |
| **区间范围回溯** | `./bin/astock data sync --code 000001 --start 2026-06-01 --end 2026-09-18` | 精确同步指定历史日期范围 |
| **当日快照落盘** | `./bin/astock data sync --codes 600519,000001 --today` | 盘后快速落盘当日最终成交与价格快照 |
| **批量大盘指数** | `./bin/astock data sync --indices --mode incremental` | 批量同步上证/深证/创业板/科创50/沪深300 |
| **完整性校验** | `./bin/astock data sync --code 600519 --check` | 检查本地数据是否存在断点、缺失交易日或坏点 |
| **缺漏自愈修复** | `./bin/astock data sync --code 600519 --repair` | 定向回补缺失切片，恢复数据健康完整状态 |
| **离线技术分析** | `./bin/astock data tech 600519` | 秒级就地计算 MA/MACD/KDJ/BOLL/二次金叉/缺口 |
| **多线程并发同步** | `./bin/astock data sync --codes 600519,000001,300750 -w 4` | 4 线程并发加速拉取，大幅提升批量吞吐量 |
| **定时守护单次检测** | `./bin/astock data daemon --once` | 检查当前时钟是否进入盘后定盘窗口并执行到期同步 |
| **启动常驻同步守护** | `./bin/astock data daemon --interval 60 -w 4` | 常驻后台，15:35 自动同步持仓，15:40 自动同步自选 |
| **数据集单跑（资金流）** | `./bin/astock dataset --key capital_flow --json` | D10 精算档(eastmoney_exact)+代理兜底双档，15:35 批次；水印 finalized 仅当全部标的取得精算档（W-07） |
| **盘中前向采集归档** | `./bin/astock data intraday --codes 600519,000001 --watch` | D9/D3/D11/D12 切片落 `local/cache/intraday/`，收盘自动封存并写 §5.5 水位 |
| **水位门控查询** | `./bin/astock dataset --watermark --json` | 输出各数据集 §5.5 水位与 post_close 就绪判定（D1/D2/D7） |

---

## 四、 验收测试与回归验证证据

### 1. 增量与防重性能实测
- **全量同步测试**：`astock data sync --code 600519 --mode full --days 250`
  - 结果：拉取 251 根日 K 线，耗时 **0.27s**，成功落盘；
- **增量防重测试**：再次执行 `astock data sync --code 600519 --mode incremental`
  - 结果：状态为 `up_to_date`，本次拉取 0 根，耗时 **0.0s**，零网络冗余开销。

### 2. 人为断点注入与自动自愈实测
1. **注入故障**：在本地数据库中手动删除 `2026-06-15` 与 `2026-06-16` 两个交易日；
2. **运行校验**：
   ```
   === 行情数据完整性校验报告 (共 1 只标的) ===
   代码         状态       在库条数     时间范围                    缺漏数      坏点数     
   ---------------------------------------------------------------------------
   sh600519   🔴 degraded 249      2025-09-08 ~ 2026-09-18 2        0       
      └─ 缺漏日期切片: 2026-06-15, 2026-06-16
   ```
3. **执行自愈**：运行 `astock data sync --code 600519 --repair`
   ```
   === 缺漏数据修复回补报告 (共 1 只标的) ===
   ✅ [sh600519] 修复成功 (已对齐完整)
   ```
4. **状态复查**：重新 `--check`，状态重置为 `🟢 healthy`，缺漏数归 0。

### 3. 系统级回归测试证据
- **专有单元测试**：`tests/test_data_sync.py` 执行耗时 0.37s，**3/3 测试通过 (OK)**；
- **全平台自动化自检**：运行 `.venv/bin/python verify.py`，全量 11 项核心领域测试 **11/11 项全部通过 (ALL SYSTEMS GO)**。
