# A-Stock 行情数据 · 本地同步与安全隔离规范 (Market Data Sync & Isolation Specification)

> **文档类别**：工程技术与系统架构规范 (Specification)  
> **单一真理来源 (SSOT)**：`scripts/core/data/sync_engine.py` & `scripts/core/workspace.py`  
> **实施进度看板**：[`SPEC-DATA-001`](../../specs/data/market-data-sync-implementation-plan.md)  
> **所属文档簇**：`A-Stock 行情数据`（中枢：[`market-data-api-specification.md`](./market-data-api-specification.md)，`SPEC-DATA-001`）
> **关联控制面**：[`SPEC-UI-003`](../../specs/ui/market-data-sync-control-console-plan.md)（[行情数据同步控制台交互规范](../ui/market-data-sync-control-console-specification.md)）

---

## 一、 架构定位与设计哲学

为保障全系统技术指标计算一致性、防止多用户并发拉取触发外部 API 频控，并严格遵循项目“零全局污染”与数据安全原则，本地数据同步机制确立以下核心架构哲学：

```mermaid
graph TD
    subgraph "公共数据基础设施 (local/ 保护目录)"
        Store[(A-Stock 公共时序数据库<br>astock_data.db)]
        Cache[(高速前复权 JSON 镜像<br>cache/data_layer/)]
    end

    subgraph "权限与访问控制 (POSIX 700)"
        Owner["系统运行进程 Owner<br>(唯一可读写)"]
        Others["同机其他系统用户<br>(0o000 物理阻断)"]
    end

    subgraph "消费端业务应用"
        User1["研究员 A (只读)"]
        User2["交易员 B (只读)"]
        Cron["盘后定时同步 (写权限)"]
        Indicators["本地指标引擎 (<5ms)"]
    end

    Owner --> Store
    Owner --> Cache
    Others -. 权限拒绝 .-> Store

    Cron -->|增量落盘| Store
    Store --> Cache
    Store --> Indicators
    User1 --> Indicators
    User2 --> Indicators
```

1. **公共市场数据共享原则**：行情快照、日K线与大盘指数属于公共基础设施，全系统所有用户、角色与 Agent 统一共享同一份时序底座，杜绝重复下载与数据分裂；
2. **私有资产物理隔离原则**：用户个人的持仓档案、自选股列表、交易流水与研究报告严格隔离于 `output/` 个人交付区，不与公共时序数据混合；
3. **数据安全防泄漏原则**：公共基础设施统一归集于根目录 `local/`，采用操作系统级 POSIX 权限阻断，并在版本控制与发布打包中 100% 排除。

---

## 二、 同步调度与时钟驱动策略

A 股交易具有严格的周期时序性，数据同步引擎依时钟状态机运转：

### 1. 交易日时钟状态机
- **盘前阶段 (00:00 - 09:15)**：静默期。禁止任何无意义的外网日线轮询；允许执行本地时序断点检测；
- **盘中阶段 (09:15 - 15:00)**：实时盯盘期。**严禁执行全量日 K 线同步**；仅允许以“动态内存 Bar”记录当前分时状态，不覆盖已定盘的离线历史日K；
- **盘后清算期 (15:05 - 15:30)**：交易所清算期。数据源处于大宗交易与盘后定价结算状态；
- **定盘归档期 (15:35 之后)**：**主同步窗口**。交易所日 K 与复权因子正式定盘，触发增量同步任务，落盘固化当日数据；
- **非交易日 (周末/节假日)**：跳过日线增量同步，仅按需执行“历史完整性深度审计与坏账修补”。

### 2. 标的池优先级调度 (Tiered Universe)
- **P0 核心持仓 (`holdings`)**：最高优先级，保留 250 交易日深度，每日 15:35 优先完成；
- **P1 重点自选/关注 (`watchlist/focus`)**：高优先级，保留 120 交易日深度，每日 15:40 完成；
- **P2 大盘指数 (`indices`)**：上证指数、深证成指、创业板指、科创50、沪深300；
- **P3 全市场标的 (`universe`)**：交易日默认 `16:00` 执行全市场增量同步，同时允许控制台按市场或代码选择手动同步；采用默认并发度 8、批大小 600 进行流控。

### 3. P3 全市场同步与资源仲裁

1. **自动任务**：仅在交易日按有效设置中的固定时间触发，默认 `16:00`；自动任务只允许增量模式，非交易日直接跳过；
2. **手动任务**：允许选择全市场、沪市、深市、北交所或指定代码，支持增量同步、完整性审计与缺漏修复；全量重构属于高负载操作，必须由控制面展示影响范围并二次确认；
3. **互斥约束**：同一时刻最多运行一个 P3 任务，存在冲突活动任务时拒绝重复提交；
4. **优先级约束**：P0/P1 高于 P3，P3 不得抢占持仓与自选同步任务；P3 的局部失败不得改变已完成的 P0/P1 结果；
5. **批处理约束**：默认批大小 600、并发度 8；具体有效值由服务端白名单校验后的设置决定。

---

## 三、 数据完整性稽核与自愈算法

系统内置 `TradeCalendar` 交易日历工具与断点探测器，算法流程如下：

### 1. 交易日历基准对齐
1. 过滤周末（周六/周日）与法定节假日；
2. 提取基准指数（`sh000001`）实际发生开市的交易日集合 $D_{ref}$ 作为真值标准。

### 2. 缺漏（Gap）与坏点探测算法
对于目标标的 $S$，其本地时序范围为 $[T_{min}, T_{max}]$，本地日期集合为 $D_S$：
1. **期望交易日集合**：$D_{expected} = \{ d \in D_{ref} \mid T_{min} \le d \le T_{max} \}$；
2. **缺漏切片检测**：$Gaps = D_{expected} \setminus D_S$；
3. **坏点检测**：遍历记录，检查收盘价 $Close \le 0$ 或开高低收存在空值/零值的记录。
4. **状态评级**：
   - 若 $Gaps = \emptyset$ 且无坏点 $\to$ `🟢 healthy`（数据健康完整）；
   - 若 $|Gaps| > 0$ 或存在坏点 $\to$ `🔴 degraded`（存在断点缺漏）。

### 3. 靶向自愈与重构 (Auto-Repair)
对评级为 `degraded` 的标的，自动激活靶向重取流程，拉取覆盖断点区间的完整前复权切片，通过 SQLite `ON CONFLICT DO UPDATE` 机制实施原子合并与缝合。

---

## 四、 本地存储与多用户安全隔离规范

### 1. 存储架构设计
存储介质选用 Python 标准库内置的嵌入式 SQLite（零外部依赖），主文件位于 `local/market_data/astock_data.db`。

#### 核心数据表 Schema 规范
```sql
-- 1. 核心日K线表
CREATE TABLE IF NOT EXISTS daily_kline (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL NOT NULL,
    close REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    volume REAL NOT NULL,
    amount REAL DEFAULT 0.0,
    turnover_pct REAL DEFAULT 0.0,
    pe REAL DEFAULT 0.0,
    pb REAL DEFAULT 0.0,
    PRIMARY KEY (symbol, date)
);
CREATE INDEX IF NOT EXISTS idx_kline_symbol_date ON daily_kline (symbol, date);
CREATE INDEX IF NOT EXISTS idx_kline_date ON daily_kline (date);

-- 2. 同步元数据水位线表
CREATE TABLE IF NOT EXISTS sync_meta (
    symbol TEXT PRIMARY KEY,
    last_sync_date TEXT,
    row_count INTEGER DEFAULT 0,
    min_date TEXT,
    max_date TEXT,
    integrity_status TEXT DEFAULT 'unknown',
    updated_at TEXT
);
```

> 规划数据集表（`stock_basic` / `minute_kline` / `dividend_event` / `index_member` / `financial_report` / `capital_snapshot` / `industry_class`）见本文 §5.2，仅在满足 §5.3 接入准入后允许迁移创建；准入前控制台覆盖表保持"未接入"占位。

### 2. `local/` 目录安全加固规范
```
local/                              # POSIX权限: 700 (drwx------)
├── README.md                       # 安全声明与拓扑文档 (权限: 600)
├── market_data/                    # 公共行情时序数据 (权限: 700)
│   └── astock_data.db              # SQLite 时序库 (权限: 600)
├── cache/                          # 高速计算缓存 (权限: 700)
│   └── data_layer/                 # 日K JSON 镜像 (权限: 600)
└── server/                         # 服务端用户与会话数据 (权限: 700)
    └── chats.db                    # 账号、角色、会话数据库 (权限: 600)
```

#### 安全三防机制
1. **POSIX 权限物理阻断**：
   - 目录设为 `0o700`，数据文件设为 `0o600`；
   - 系统中其他非 root 用户无法查看目录列表、无法读取数据库内容，防止密码哈希或量化数据泄漏；
   - `scripts/core/workspace.py` 与 `scripts/core/config.py` 启动时自动执行 `enforce_secure_permissions()` 加固。
2. **Git 版本控制完全忽略**：
   - `.gitignore` 与 `.dockerignore` 显式写入 `local/`，杜绝本地时序库与用户账户入库。
3. **打包发布自动化排除**：
   - 打包脚本 `scripts/tools/pack.py` 的 `EXCLUDE_DIRS` 强制排除 `"local"`。

---

## 五、 数据集登记册与接入规划 (Dataset Registry & Rollout)

控制台"数据覆盖与更新状态"表以本登记册为**唯一设计依据**，8 个展示行与 D1–D8 一一对应。未登记的数据集不得出现在覆盖表；已登记但未接入的数据集必须以"未接入（规划：…）"与"未检测"占位呈现，严禁伪造水位（与 SPEC-UI-003 §7.2 一致）。

**归属注记原则**：随日线管线内嵌的产物（P2 指数 K 线、pe/pb/turnover_pct 估值字段、前复权 JSON 镜像）一律归属 D2，不在其他数据集行重复声明接入状态；各行的"接入状态"仅以其**主存储形态**是否具备真实水位为准。

**字段规避原则**：经依赖声明、技能实测文档与已安装版本函数/docstring 三重证据核验，无法确认外部接口渠道的字段（**退市日期、指数成分历史进出日期、行业变更历史区间**）一律**不入 Schema、不设同步与稽核项**；如未来业务确需变更类信息，必须先按 §5.3 准入条件 5 完成接口确认，再回本登记册重新登记。

### 1. 登记册总览

| # | 数据集（覆盖表行） | 主存储形态（现状） | 规划扩展 | 同步调度窗口 | 完整性稽核口径 | 外部接口渠道（已确认） | 接入状态 |
|:--|:--|:--|:--|:--|:--|:--|:--|
| D1 | 基础资料与交易日历 | `TradeCalendar` 规则日历（2024–2027）+ sh000001 真值延伸 | `stock_basic` 表（名称/市场/上市日期；**退市日期不入库**） | 规则内置；基础资料盘后 15:35 日增核对 | 规则区间与真值交易日对齐；基础资料按已登记标的名称/上市日期覆盖率 | 交易所官方列表 `stock_info_sh/sz/bj_name_code` + `stock_individual_info_em`；日历真值 akshare(sina) | 已接入（规则日历）；基础资料未接入 |
| D2 | 日线行情 | `daily_kline` + `sync_meta`（含 P2 指数符号、pe/pb/turnover_pct 字段、前复权镜像） | P3 全市场水位聚合展示 | P0 15:35 / P1 15:40 / P2 盘后 / P3 16:00 增量 | 本文 §3 缺漏（Gap）与坏点探测 | 腾讯/新浪/雪球/东财 4 级降级 K 线 | 已接入 |
| D3 | 分钟K线 | 无（盘中仅动态内存 Bar，不落盘） | `minute_kline` 表 | 盘后归档期按需回补；保留深度 1m 30 天 / 5m 90 天 / 15·30·60m 180 天滚动 | 每交易日每周期期望 Bar 数 = 交易分钟数 ÷ 周期分钟数，缺段记 gap | 腾讯 mkline m1–m60 + `stock_zh_a_hist_min_em`（技能实测 ✅） | 未接入 |
| D4 | 复权因子与分红 | 无独立表（前复权镜像归属 D2 管线产物） | 独立复权因子表 + `dividend_event` 表 | 复权因子随 D2 于 15:35 定盘落盘；分红事件按除权除息日 15:50 增量 | 复权切片连续性随 D2 稽核；分红按交易所公告除权事件覆盖率 | 新浪 `stock_zh_a_daily(adjust="qfq-factor")` 因子序列；`stock_history_dividend` / `stock_dividend_cninfo` 分红 | 未接入 |
| D5 | 指数与成分股 | 指数行情归属 D2（P2 五条指数同表同步） | `index_member` 最新成分快照表（含权重；**历史进出不入库**） | 成分每日 16:10 最新批次快照 | 指数行情随 D2 稽核；成分按最新批次覆盖率与权重非空率 | 中证官方 `index_stock_cons_weight_csindex`（仅最新成分+权重） | 未接入 |
| D6 | 财务报表与指标 | 无 | `financial_report` 表 | 按披露时间每日 16:20 增量，按报告期回补 | 报告期序列完整（一季报/半年报/三季报/年报）；披露时效待巨潮渠道接入 | `stock_financial_analysis_indicator` + 三表 `_by_report_em`（技能实测 ✅）；披露日渠道预留（巨潮 `stock_report_disclosure`，本期 `disclose_date` 留空） | 未接入 |
| D7 | 估值与股本 | pe/pb/turnover_pct 内嵌 D2 字段 | `capital_snapshot` 表（总股本/流通股本/市值） | 估值随 D2；股本快照盘后 16:30 全市场快照 | 估值随 D2 稽核；股本按字段非空率与日期连续性 | 腾讯 L1 批量快照 PE/PB/市值；股本 = 市值 ÷ 现价 推导（全市场批量） | 未接入 |
| D8 | 行业分类 | 无（仅在线板块/行业接口能力） | `industry_class` 当前分类快照表（**变更历史不入库**） | 每日 16:40 最新分类快照 | 最新批次分类覆盖率（已登记标的） | 东财 `stock_board_industry_name_em`/`cons_em` + `stock_individual_info_em` 行业字段 + 新浪板块 | 未接入 |

### 2. 规划表 Schema (SQLite)

规划表仅在满足 §5.3 接入准入后由 `MarketDataStore` 迁移创建，创建前不得在覆盖表声明接入：

```sql
-- D1 基础资料（退市日期无外部接口渠道，按字段规避原则不入库）
CREATE TABLE IF NOT EXISTS stock_basic (
    symbol TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    market TEXT NOT NULL,              -- sh / sz / bj
    list_date TEXT,
    updated_at TEXT
);

-- D3 分钟K线
CREATE TABLE IF NOT EXISTS minute_kline (
    symbol TEXT NOT NULL,
    freq TEXT NOT NULL,                -- 1m / 5m / 15m / 30m / 60m
    ts TEXT NOT NULL,                  -- Bar 结束时间 YYYY-MM-DD HH:MM
    open REAL NOT NULL, close REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL,
    volume REAL DEFAULT 0.0, amount REAL DEFAULT 0.0,
    PRIMARY KEY (symbol, freq, ts)
);
CREATE INDEX IF NOT EXISTS idx_minute_symbol_freq_ts ON minute_kline (symbol, freq, ts);

-- D4 复权因子（新浪 qfq-factor 直取序列）
CREATE TABLE IF NOT EXISTS adjust_factor (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    factor REAL NOT NULL,
    updated_at TEXT,
    PRIMARY KEY (symbol, date)
);

-- D4 分红事件
CREATE TABLE IF NOT EXISTS dividend_event (
    symbol TEXT NOT NULL,
    ex_date TEXT NOT NULL,             -- 除权除息日
    dividend_per_share REAL DEFAULT 0.0,
    bonus_ratio REAL DEFAULT 0.0,
    allot_ratio REAL DEFAULT 0.0,
    source TEXT,
    updated_at TEXT,
    PRIMARY KEY (symbol, ex_date)
);

-- D5 指数成分（仅最新批次快照；历史进出日期无外部接口渠道，按字段规避原则不入库）
CREATE TABLE IF NOT EXISTS index_member (
    index_code TEXT NOT NULL,
    symbol TEXT NOT NULL,
    weight REAL,
    batch_date TEXT NOT NULL,          -- 快照批次日期
    PRIMARY KEY (index_code, symbol, batch_date)
);

-- D6 财务报表
CREATE TABLE IF NOT EXISTS financial_report (
    symbol TEXT NOT NULL,
    report_date TEXT NOT NULL,         -- 报告期 YYYY-03-31 / 06-30 / 09-30 / 12-31
    disclose_date TEXT,
    revenue REAL, net_profit REAL, roe REAL, gross_margin REAL,
    source TEXT,
    updated_at TEXT,
    PRIMARY KEY (symbol, report_date)
);

-- D7 股本快照
CREATE TABLE IF NOT EXISTS capital_snapshot (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    total_shares REAL, float_shares REAL,
    total_market_cap REAL, float_market_cap REAL,
    source TEXT,
    PRIMARY KEY (symbol, date)
);

-- D8 行业分类（仅当前分类快照；变更历史区间无外部接口渠道，按字段规避原则不入库）
CREATE TABLE IF NOT EXISTS industry_class (
    symbol TEXT NOT NULL,
    industry_code TEXT NOT NULL,
    industry_name TEXT NOT NULL,
    batch_date TEXT NOT NULL,          -- 快照批次日期
    PRIMARY KEY (symbol, batch_date)
);

-- 稽核快照（覆盖表"完整性/状态"列的数据源；每次同步批次写入一条）
CREATE TABLE IF NOT EXISTS dataset_audit (
    dataset_key TEXT NOT NULL,
    batch_date TEXT NOT NULL,
    covered INTEGER, total INTEGER, missing INTEGER,
    state TEXT, detail TEXT,
    updated_at TEXT,
    PRIMARY KEY (dataset_key, batch_date)
);
```

### 3. 接入准入 (Definition of Connected)

数据集由"未接入"切换为"已接入"必须同时满足：

1. 对应表 Schema 已纳入 SSOT `scripts/core/data/sync_engine.py` 的迁移创建流程；
2. 增量同步任务与 §5.1 调度窗口已实现，并复用本文 §2 的任务互斥与 P0/P1 优先仲裁；
3. §5.1 完整性稽核口径已实现，并接入控制台覆盖表的"完整性/状态"列；
4. 本地读取失败时返回显式不可用状态，不得回退演示值或静默置零；
5. 字段级渠道确认完成：每个入库字段具备"依赖声明 + 技能实测文档 + 已安装版本函数/docstring"三重证据（见 §5.1 外部接口渠道列）；东财源字段接入前须通过列名校验（见技能 `data-source-traps`）；无法通过确认的字段按字段规避原则删除，不得保留占位列。

准入完成前，覆盖表对应行保持"未接入（规划：…）"与"未检测"占位；准入完成后，该行覆盖范围、数据截至/批次与完整性列改由真实水位与真实审计结果驱动。
