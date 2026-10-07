from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_production_sources_have_no_fabricated_runtime_patterns() -> None:
    server = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "scripts/server").rglob("*.py")
        if path.name != "mock_provider.py"
    )
    api_js = (ROOT / "web/js/api.js").read_text(encoding="utf-8")
    app_js = (ROOT / "web/js/app.js").read_text(encoding="utf-8")
    components = (ROOT / "web/js/components/astock.js").read_text(encoding="utf-8")

    server_forbidden = (
        '"status": "simulated"',
        '"status": "active"',
        '"rolling_ic": 0.065',
        '"bull_bear_ratio": "52% 多头 vs 48% 空头"',
        '"total_returns": 0.185',
        "1000000.0",
    )
    for literal in server_forbidden:
        assert literal not in server

    browser = "\n".join((api_js, app_js, components))
    browser_forbidden = (
        "fallbackTypewriter",
        "Fallback Mock",
        "3426.56",
        "3,426.56",
        "1.28万亿",
        "1.28 万亿",
        "¥454.24万",
        "¥328.56万",
        "¥125.68万",
        "+36.78%",
        "夏普比率 1.84",
        "交易胜率 68.5%",
        "78分 · 亢温贪婪",
        "毫秒级28ms延迟监控",
        "持仓组合综合健康度 88分",
        "Mock 200",
    )
    for literal in browser_forbidden:
        assert literal not in browser

    assert not re.search(r"currentPrice\s*:\s*\d", app_js)
    assert not re.search(r"localStorage\.(?:setItem|getItem)\(['\"]astock_llm_providers", app_js)
    assert "model = 'mock'" not in api_js
    assert "'mock'," not in app_js


def test_datafeed_fallback_panel_is_probe_driven_not_static() -> None:
    """设置弹窗「行情数据源降级」面板必须由真实探测端点驱动。

    历史缺陷：面板静态写死「● 运行中 (延迟 85ms)」「备用就绪」，并宣称存在
    Baostock / DuckDB 两级链路——三者均与 data_bridge 真实降级链不符，属伪造运行态。
    现口径：延迟一律来自 GET /api/market_data/ping，未测速前只显示「○ 未检测」。
    """
    index_html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    parts = index_html.split('id="sec-datafeed"', 1)
    assert len(parts) == 2, "设置弹窗缺少行情数据源降级面板 (sec-datafeed)"
    # 截取本面板内容：到下一个 settings-sec 之前
    panel = parts[1].split('<div class="settings-sec"', 1)[0]

    assert not re.search(r"延迟\s*\d+\s*ms", panel), "面板不得静态写死延迟数值"
    for literal in ("备用就绪", "Baostock", "DuckDB", "status-online"):
        assert literal not in panel, f"面板残留伪造运行态字面量: {literal}"

    # 四个探测槽位与 app.js runDatasyncPing 的取数 ID 必须一一对应
    for slot in ("pingL1", "pingL2", "pingL3", "pingLocal"):
        assert f'id="{slot}"' in panel, f"缺少探测槽位 {slot}"
    assert "runDatasyncPing(this)" in panel, "面板未接入真实测速入口"
    assert "/api/market_data/ping" in panel, "面板未声明延迟数据来源"
    assert "未检测" in panel, "初始态必须如实为未检测"

    # 展示顺序必须与 data_bridge 真实降级链一致：腾讯 → 新浪 → 东财 → 本地库
    order = [panel.index(marker) for marker in ("Tencent", "Sina", "Eastmoney", "本地 SQLite")]
    assert order == sorted(order), "降级链路展示顺序与真实取数链不一致"


def test_workbench_panes_have_no_fabricated_fallback_data() -> None:
    """工作台各面板不得保留任何本地伪造兜底数据或凭空合成的走势。

    历史缺陷（均已清除，本用例防止复现）：
    - app.js `MarketFallbackData`：写死四大指数 3426.56 等、78 分情绪、板块/概念/榜单/快讯；
    - app.js `WatchlistFallbackData`：写死茅台/宁德等自选档案、资金流、新闻与 AI 结论；
    - app.js `ReturnsFallbackData`：写死 28.56% 收益、2.36 夏普、68.23% 胜率与 50 点走势；
    - app.js `generateKlines`：随机游走合成 K 线，冒充真实行情绘入画布；
    - app.js `initDashboardCharts` / `loadDashboardData`：目标 DOM id 已全部不存在，
      属死代码却仍在启动时白发 5 个后端请求并写死 454.24 总资产与 78 分表盘；
    - `switchTrendPeriod` 对伪造数组乘 0.3/0.5/0.8 系数"生成"多周期曲线。
    """
    app_js = (ROOT / "web/js/app.js").read_text(encoding="utf-8")
    for dead in (
        "MarketFallbackData", "WatchlistFallbackData", "ReturnsFallbackData",
        "generateKlines", "initDashboardCharts", "loadDashboardData",
        "defaultSpark", "askAboutReturnReport",
    ):
        assert dead not in app_js, f"app.js 残留伪造数据载体: {dead}"

    # 必须保留真实的不可用态渲染入口，避免"删掉兜底却不补空态"造成骨架屏永久闪烁
    for honest in ("renderReturnsUnavailable", "renderWatchHeroUnavailable",
                   "markMarketIndicesUnavailable", "markMarketKlineUnavailable"):
        assert honest in app_js, f"缺少如实空态渲染函数: {honest}"


def test_index_html_has_no_static_fabricated_market_values() -> None:
    """index.html 静态层不得预置任何具体行情数值、标的身分或投研结论。

    静态值只在"接口尚未返回"时可见，一旦写死具体数字就会在接口失败时永久挂盘，
    等同于伪造。合规写法是 `--` 或 skeleton 占位（同文件情绪卡即为范本）。
    """
    index_html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    forbidden = (
        "3,426.56", "3410.32", "3398.76", "3376.21",   # 上证指数与 MA 图例
        "18.72%", "6.34%", "2.87%", "0.63%",           # 收益构成图例
        "超越了92%的投资者", "最大回撤8.72%",              # 收益报告结论
        "近30家机构调研", "10派5元", "解禁股数1.25亿股",     # 个股事件时间轴
        ">宁德时代<", ">CATL<", ">300750<",              # 自选 Hero 预置标的身分
        ">融资融券<", ">MSCI<",                          # 自选 Hero 预置标签
    )
    for literal in forbidden:
        assert literal not in index_html, f"index.html 残留静态伪造值: {literal}"

    # 自选 Hero 标签容器必须为空：标的标签（深股通/融资融券/MSCI）只能由接口按选中标的下发。
    # 注意不能直接禁 "深股通" 字面量——北向资金页签的合法 UI 文案也含该词。
    hero_tags = index_html.split('id="watchHeroTags"', 1)
    assert len(hero_tags) == 2, "缺少自选 Hero 标签容器 watchHeroTags"
    assert hero_tags[1].lstrip().startswith("></div>"), "watchHeroTags 不得预置任何标的标签"

    # 无真实数据源的静态列表必须直接给出如实空态，而不是永久 skeleton 假加载条。
    # （mktNewsList 由 loadMarketData 无条件写入空态文案，不在此静态断言范围内）
    for placeholder_id in ("watchEventsTimeline", "watchNewsList", "retReportList"):
        block = index_html.split(f'id="{placeholder_id}"', 1)
        assert len(block) == 2, f"缺少容器 {placeholder_id}"
        assert "datasync-detail-placeholder" in block[1][:600], f"{placeholder_id} 未给出如实空态"


def test_unconnected_market_endpoints_fail_closed_in_source() -> None:
    """情绪/榜单/收益归因三个端点必须 fail-closed，不得谎称来自某个"引擎"。

    断言用 `"source": "<engine>"` 的赋值形态匹配，避免误伤文档字符串中
    对历史缺陷的说明性引用。
    """
    source = (ROOT / "scripts/server/api/market_data.py").read_text(encoding="utf-8")
    for capability in ("market.sentiment", "market.ranks", "portfolio.analysis"):
        assert f'_unavailable("{capability}")' in source, f"{capability} 未 fail-closed"
    for lie in ('"source": "market_sentiment_engine"',
                '"source": "market_ranks_engine"',
                '"source": "quant_engine"'):
        assert lie not in source, f"残留虚构数据源标注: {lie}"


def test_mock_provider_is_guarded_by_explicit_test_mode() -> None:
    factory = (ROOT / "scripts/server/llm/factory.py").read_text(encoding="utf-8")
    assert 'server_settings.runtime_mode != "test"' in factory
    assert "return MockLLMProvider" in factory
    assert factory.index('server_settings.runtime_mode != "test"') < factory.index("return MockLLMProvider")
