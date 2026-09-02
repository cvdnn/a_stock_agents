"""
aStocks 数据源注册表 — 继承 TACN DataSourceCode 设计哲学

轻量化枚举 + 数据类注册表，不依赖 TACN/TradingAgents 项目代码。
每个数据源有: code, layer, speed, markets, features, zero_dep, status.

用法:
    from data_source_registry import list_by_layer, list_available, get_source
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class DataSourceInfo:
    """数据源信息 — 轻量化版 TACN DataSourceInfo (仅A股)"""
    code: str
    name: str
    layer: str                      # L1/L2/L3/L4
    speed: str                      # 预期速度
    markets: List[str]              # 支持市场: A股, 指数
    features: List[str]             # 功能列表
    zero_dep: bool                  # 是否零依赖
    status: str = "active"          # active / deprecated
    requires_venv: bool = False     # 是否需要 venv Python
    requires_api_key: bool = False  # 是否需要 API Key


# ─── A股数据源 ──────────────────────────────────

DATA_SOURCES: Dict[str, DataSourceInfo] = {
    # L1: 零依赖层
    "tencent_qt": DataSourceInfo(
        code="tencent_qt",
        name="腾讯实时行情",
        layer="L1",
        speed="~0.1s",
        markets=["A股", "指数", "港股"],
        features=["实时行情", "PE", "换手率", "市值", "涨跌幅", "内外盘", "批量12只"],
        zero_dep=True,
    ),
    "tencent_kline": DataSourceInfo(
        code="tencent_kline",
        name="腾讯日K线",
        layer="L1",
        speed="~0.5s",
        markets=["A股"],
        features=["日K线", "前复权", "开高低收量"],
        zero_dep=True,
    ),
    # L2: a-share-data 脚本
    "sina_scripts": DataSourceInfo(
        code="sina_scripts",
        name="新浪财经脚本",
        layer="L2",
        speed="~3-5s",
        markets=["A股"],
        features=["行情", "K线", "板块排行", "行业分类", "技术指标"],
        zero_dep=False,
        requires_venv=False,
    ),
    # L3: proxy-patch (需积分)
    "proxy_patch": DataSourceInfo(
        code="proxy_patch",
        name="东财代理补丁",
        layer="L3",
        speed="~0.4-2s",
        markets=["A股"],
        features=["CYQ筹码分布", "资金流向", "个股事件", "A+H列表", "股东人数"],
        zero_dep=False,
        requires_venv=True,
    ),
    # ─── L4: efinance ─────────────────────────
    "efinance": DataSourceInfo(
        code="efinance",
        name="efinance 基本面",
        layer="L4",
        speed="~0.2s",
        markets=["A股"],
        features=["基本面", "PE动态", "PB", "ROE", "营收", "净利润"],
        zero_dep=False,
        requires_venv=False,
    ),
}


# ─── 查询辅助函数 ─────────────────────────────

def list_by_layer(layer: str) -> List[DataSourceInfo]:
    """按层级列出数据源"""
    return [ds for ds in DATA_SOURCES.values() if ds.layer == layer]


def list_by_market(market: str) -> List[DataSourceInfo]:
    """按市场列出数据源"""
    return [ds for ds in DATA_SOURCES.values() if market in ds.markets]


def list_available() -> List[DataSourceInfo]:
    """列出所有可用的 (active) 数据源"""
    return [ds for ds in DATA_SOURCES.values() if ds.status == "active"]


def list_zero_dep() -> List[DataSourceInfo]:
    """列出零依赖数据源"""
    return [ds for ds in DATA_SOURCES.values() if ds.zero_dep and ds.status == "active"]


def get_source(code: str) -> Optional[DataSourceInfo]:
    """按code获取数据源"""
    return DATA_SOURCES.get(code)


# ─── 降级链配置 ──────────────────────────────

FALLBACK_CHAIN = {
    "realtime_quote": ["tencent_qt", "sina_scripts", "proxy_patch", "efinance"],
    "kline": ["tencent_kline", "sina_scripts"],
    "technical": ["tencent_kline", "sina_scripts"],
    "fundamentals": ["tencent_qt", "efinance", "proxy_patch"],
    "cyq": ["proxy_patch"],
    "fund_flow": ["proxy_patch", "sina_scripts"],
}


def get_fallback(order_name: str) -> List[str]:
    """获取指定功能的降级链"""
    return FALLBACK_CHAIN.get(order_name, [])


# ─── 统计信息 ──────────────────────────────

def summary() -> Dict:
    """数据源总览 (仅A股)"""
    active = list_available()
    return {
        "total_sources": len(DATA_SOURCES),
        "active": len(active),
        "zero_dep": len(list_zero_dep()),
        "layers": {
            layer: len(list_by_layer(layer))
            for layer in ["L1", "L2", "L3", "L4"]
        },
        "source_codes": [ds.code for ds in active],
    }


if __name__ == "__main__":
    import json
    print(json.dumps(summary(), ensure_ascii=False, indent=2))
    print()
    print("=== Active Data Sources ===")
    for ds in list_available():
        print(f"  {ds.layer} {ds.code:<20} {ds.speed:<10} {ds.markets}")
