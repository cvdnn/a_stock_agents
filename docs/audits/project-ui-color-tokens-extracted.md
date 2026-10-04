# 项目工程 UI 设计配色提取

> 用途：沉淀 A-Stock Agents 当前工程中已经落地的 UI 配色与语义 Token，作为审计、设计联调和新页面复用依据。
> 主要来源：[`web/css/style.css`](../../web/css/style.css)、[`ui-design-guide.md`](../guidelines/ui/ui-design-guide.md)、[`market-data-sync-control-console-specification.md`](../guidelines/ui/market-data-sync-control-console-specification.md)。

## 1. 配色基调

项目当前采用浅色金融商务风格，整体以冷白画布、白色卡片、品牌蓝强调和 A 股红涨绿跌语义色构成。主工作台应优先复用 `web/css/style.css` 的 `:root` 变量，而不是直接复制局部硬编码色值。

## 2. 主站核心 Token

| 语义 | Token / 用途 | 颜色值 | 来源 |
|---|---|---:|---|
| 画布背景 | `--bg-canvas` | `#F6F8FC` | `style.css` |
| 卡片背景 | `--bg-card` | `#FFFFFF` | `style.css` |
| Hover 背景 | `--bg-hover` | `#F4F7FC` | `style.css` |
| Active 背景 | `--bg-active` | `#EBF3FF` | `style.css` |
| 标签底色 | `--bg-tag` | `#F2F5FA` | `style.css` |
| 品牌主色 | `--primary` | `#1677FF` | `style.css` / `ui-design-guide` |
| 品牌深蓝 | `--primary-hover` | `#0958D9` | `style.css` |
| 主色浅底 | `--primary-light` | `#E6F4FF` | `style.css` |
| 主色边框 | `--primary-border` | `#91CAFF` | `style.css` |
| 焦点边框 | `--border-focus` | `#1677FF` | `style.css` |
| 主标题文字 | `--text-title` | `#1D2129` | `style.css` |
| 正文文字 | `--text-body` | `#4E5969` | `style.css` |
| 次级文字 | `--text-muted` | `#86909C` | `style.css` |
| 弱提示文字 | `--text-subtle` | `#C9CDD4` | `style.css` |
| 卡片边框 | `--border-card` | `#EBF0F5` | `style.css` |
| 轻边框 | `--border-light` | `#F0F2F5` | `style.css` |

## 3. A 股语义色

| 语义 | Token / 用途 | 颜色值 | 说明 |
|---|---|---:|---|
| 上涨 / 盈利 / 做多 | `--color-up` | `#F5222D` | 严格遵守 A 股红涨 |
| 上涨深色 | `--color-up-dark` | `#CF1322` | 强调数值或深态 |
| 上涨浅底 | `--color-up-bg` | `#FFF1F0` | Tag / Badge / 风险提示底色 |
| 上涨边框 | `--color-up-border` | `#FFA39E` | 上涨态边框 |
| 下跌 / 规避 / 回撤 | `--color-down` | `#52C41A` | 严格遵守 A 股绿跌 |
| 下跌深色 | `--color-down-dark` | `#389E0D` | 强调数值或深态 |
| 下跌浅底 | `--color-down-bg` | `#F6FFED` | Tag / Badge / 状态底色 |
| 下跌边框 | `--color-down-border` | `#B7EB8F` | 下跌态边框 |
| 警告橙 | `--color-warn` | `#FA8C16` | 预警、停牌、次级提醒 |
| 警告浅底 | `--color-warn-bg` | `#FFF7E6` | 橙色弱提示容器 |

## 4. 交互标签扩展色

这些颜色主要出现在 @ 操作符、股池胶囊徽章和功能标签中。

| 类别 | 文字 | 背景 | 边框 | 主要出处 |
|---|---:|---:|---:|---|
| 股票标签 | `#0958D9` | `#E6F4FF` | `#91CAFF` | `ui-design-guide` |
| 自选 / 持仓橙标签 | `#D46B08` | `#FFF7E6` | `#FFD591` | `ui-design-guide` |
| 引用标签 | `#135200` | `#F6FFED` | `#B7EB8F` | `ui-design-guide` |
| 技能标签 | `#D4380D` | `#FFF2E8` | `#FFBB96` | `ui-design-guide` |
| 算法标签 | `#531DAB` | `#F9F0FF` | `#D3ADF7` | `ui-design-guide` |
| 关注股徽章 | `#722ED1` | `#F9F0FF` | `#D3ADF7` | `ui-design-guide` |
| 自选股徽章 | `#1677FF` | `#EDF5FF` | `#ADC6FF` | `ui-design-guide` |

## 5. 数据同步页面可直接复用的配色

结合数据同步控制台规范，推荐直接复用以下映射：

| 页面元素 | 推荐颜色 |
|---|---|
| 页面画布 | `#F8FAFD` 或 `var(--bg-canvas)` |
| 顶部标题栏 | `#FFFFFF` + `1px solid var(--border-card)` |
| 普通卡片 | `#FFFFFF` |
| 次级卡片 / 区块底 | `#FAFCFE` |
| 激活导航项 | `var(--primary)` + 白字 |
| 成功 / 正常 | `#52C41A` |
| 警告 / 停牌 / 待关注 | `#FA8C16` |
| 异常 / 缺漏 / 失败 | `#F5222D` |
| 信息 / 链接 / 焦点 | `#1677FF` |

## 6. 当前存在的配色漂移

### 6.1 背景色轻微漂移
- 工程根 Token：`--bg-canvas: #F6F8FC`
- 设计文档与多处页面说明：`#F8FAFD`

这两个值都属于冷白浅背景，视觉差异不大，但后续若要统一设计系统，建议选一个作为唯一画布背景标准。

### 6.2 文档/报告场景独立色板

报告导出 HTML 和部分 Markdown 转 HTML 场景使用了独立色板：

| 语义 | 颜色值 |
|---|---:|
| 报告背景 | `#f4f5f7` |
| 报告边框 | `#d8dce3` |
| 报告主文字 | `#1a1d24` |
| 报告次文字 | `#5a6070` |
| 报告上涨 | `#d0312d` |
| 报告下跌 | `#219653` |
| 报告蓝强调 | `#2563eb` |

该组颜色适合单文件交付文档，不建议直接覆盖主工作台的品牌蓝和市场语义色。

## 7. 建议的后续动作

1. 以 `web/css/style.css` 为主源，整理一版统一命名的设计 Token。
2. 清理页面中散落的硬编码色值，优先替换为 `:root` 变量。
3. 明确主工作台与报告导出两套色板的边界，避免组件互相串色。
4. 数据同步页新增组件时，优先使用本文件第 5 节推荐映射，不再定义第三套状态色。

## 8. 关键引用

- [`style.css:L5-L44`](file:///Users/handy/workon/a_stock_agents/web/css/style.css#L5-L44)
- [`ui-design-guide.md:L16-L30`](file:///Users/handy/workon/a_stock_agents/docs/guidelines/ui/ui-design-guide.md#L16-L30)
- [`ui-design-guide.md:L119-L127`](file:///Users/handy/workon/a_stock_agents/docs/guidelines/ui/ui-design-guide.md#L119-L127)
- [`ui-design-guide.md:L236-L240`](file:///Users/handy/workon/a_stock_agents/docs/guidelines/ui/ui-design-guide.md#L236-L240)
- [`market-data-sync-control-console-specification.md:L21-L34`](file:///Users/handy/workon/a_stock_agents/docs/guidelines/ui/market-data-sync-control-console-specification.md#L21-L34)
- [`web/js/app.js:L6132-L6145`](file:///Users/handy/workon/a_stock_agents/web/js/app.js#L6132-L6145)
