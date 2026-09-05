# -*- coding: utf-8 -*-
"""
动态宇宙与市场主线推断引擎 (Dynamic Universe & Leading Sector Engine)

遵循“市场信息有效性与时间时效性”量化原则:
1. 彻底避免在代码或配置中硬编码固定股票池作为选股推荐；
2. 根据实时市场信息（板块领涨度、成交量能集中度、资金流向、动量突破），自适应动态推断评估形成当日标的池与活跃板块；
3. 严格区分“离线基准测试对照库（Benchmark Only）”与“实盘动态推荐宇宙（Dynamic Universe）”。
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from core.config import (
        CONFIG_DIR,
        OUTPUT_POOLS_DIR,
        PROJECT_ROOT,
        get_logger,
        load_stock_pools,
        normalize_symbol,
    )
    from core.data.data_bridge import DataBridge
    from core.strategy.pool_schema import is_blocked
    logger = get_logger("core.strategy.dynamic_universe")
except ImportError:
    import logging
    logger = logging.getLogger("core.strategy.dynamic_universe")
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    CONFIG_DIR = PROJECT_ROOT / "config"
    OUTPUT_POOLS_DIR = PROJECT_ROOT / "output" / "pools"

    def normalize_symbol(code: str, with_prefix: bool = True) -> str:
        clean = re.sub(r'[^0-9]', '', str(code))
        return clean[-6:] if len(clean) >= 6 else clean

    def is_blocked(code: str, **kwargs) -> bool:
        c = normalize_symbol(code)
        return c.startswith(("688", "689", "30", "8", "4", "92"))


class DynamicUniverseEngine:
    """动态宇宙与市场主线推断引擎"""

    def __init__(self, bridge: Optional[DataBridge] = None):
        self.bridge = bridge or DataBridge()

    # ═══════════════════════════════════════════════════════════════════
    #  1. 市场主线与领涨行业动态推断
    # ═══════════════════════════════════════════════════════════════════

    def infer_leading_sectors(
        self,
        top_n: int = 5,
        min_change_pct: float = -2.0,
        sort_by: str = "change_pct",
    ) -> List[Dict[str, Any]]:
        """
        动态评估当前市场领涨主线与热点板块。

        Args:
            top_n: 获取的前 N 个行业/概念板块
            min_change_pct: 最低板块涨幅阈值
            sort_by: 排序依据 ('change_pct' 涨幅优先, 'amount' 成交额优先)

        Returns:
            List[Dict]: 领涨板块信息列表 [{'name': '半导体', 'change_pct': 2.5, 'count': 80, ...}]
        """
        summary_raw = self.bridge.get_board_summary(limit=max(top_n * 3, 30))
        if not summary_raw:
            logger.warning("未能获取实时板块概览数据，尝试从历史板块快照评估")
            return []

        board_items = summary_raw.get("data") if isinstance(summary_raw, dict) else summary_raw
        if not isinstance(board_items, list):
            return []

        parsed_sectors: List[Dict[str, Any]] = []
        for b in board_items:
            if not isinstance(b, dict):
                continue
            name = str(b.get("groupLabel") or b.get("boardName") or b.get("name") or "").strip()
            if not name or any(skip in name for skip in ["ST", "退市", "B股", "风险"]):
                continue

            try:
                chg = float(b.get("changePct", 0) or 0)
            except (ValueError, TypeError):
                chg = 0.0

            try:
                turnover = float(b.get("totalTurnoverYuan", 0) or 0) / 1e8  # 亿元
            except (ValueError, TypeError):
                turnover = 0.0

            count = int(b.get("count", 0) or 0)

            if chg >= min_change_pct:
                parsed_sectors.append({
                    "name": name,
                    "change_pct": round(chg, 2),
                    "turnover_yi": round(turnover, 2),
                    "stock_count": count,
                    "lead_stock": b.get("leadStockName", ""),
                })

        # 排序
        if sort_by == "amount":
            parsed_sectors.sort(key=lambda x: x["turnover_yi"], reverse=True)
        else:
            parsed_sectors.sort(key=lambda x: x["change_pct"], reverse=True)

        return parsed_sectors[:top_n]

    # ═══════════════════════════════════════════════════════════════════
    #  2. 全市场高流动性活跃标的动态提取
    # ═══════════════════════════════════════════════════════════════════

    def infer_active_stocks(
        self,
        sort_by: str = "amount_desc",
        top_n: int = 50,
        allow_all_boards: bool = False,
        allow_chinext: Optional[bool] = None,
        allow_star: Optional[bool] = None,
        allow_bse: Optional[bool] = None,
    ) -> List[str]:
        """
        动态提取当前全市场流动性最充沛、资金博弈最活跃的标的。

        Args:
            sort_by: 排序指标 ('amount_desc' 成交额TOP, 'turnover_rate_desc' 换手率TOP, 'change_pct_desc' 涨幅TOP)
            top_n: 目标候选数量
            allow_all_boards: 是否允许跨板块
        """
        quotes = self.bridge.get_active_market_quotes(sort_by=sort_by, top=top_n * 2)
        if not quotes:
            logger.warning("未能通过实时API拉取全市场行情列表")
            return []

        candidates: List[str] = []
        for q in quotes:
            code = normalize_symbol(q.get("code", ""), with_prefix=False)
            if not code or len(code) != 6:
                continue

            # 剔除停牌/零成交
            vol = float(q.get("volume", 0) or 0)
            price = float(q.get("price", 0) or 0)
            if vol <= 0 or price <= 0:
                continue

            # 遵从板块准入权限
            if is_blocked(
                code,
                allow_all=allow_all_boards,
                allow_chinext=allow_chinext,
                allow_star=allow_star,
                allow_bse=allow_bse,
            ):
                continue

            candidates.append(code)
            if len(candidates) >= top_n:
                break

        return candidates

    # ═══════════════════════════════════════════════════════════════════
    #  3. 本地动态关注/自选池发现
    # ═══════════════════════════════════════════════════════════════════

    def load_user_watchlist_stocks(self, allow_all_boards: bool = False) -> List[str]:
        """动态加载用户本地维护的自选池 (selected_pool.csv + watch_pool.csv)"""
        candidates = []
        seen = set()
        for fn in ["selected_pool.csv", "watch_pool.csv"]:
            p = OUTPUT_POOLS_DIR / fn
            if not p.exists():
                continue
            try:
                import csv
                with open(p, "r", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        c = normalize_symbol(row.get("code", ""), with_prefix=False)
                        if c and len(c) == 6 and c not in seen:
                            if not is_blocked(c, allow_all=allow_all_boards):
                                seen.add(c)
                                candidates.append(c)
            except Exception as e:
                logger.debug(f"读取自选池 {fn} 异常: {e}")
        return candidates

    # ═══════════════════════════════════════════════════════════════════
    #  4. 统一动态宇宙推断形成总入口
    # ═══════════════════════════════════════════════════════════════════

    def generate_dynamic_universe(
        self,
        mode: str = "hot_sectors",
        size: int = 30,
        allow_all_boards: bool = False,
        allow_chinext: Optional[bool] = None,
        allow_star: Optional[bool] = None,
        allow_bse: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        生成由当前市场状态和时间信息动态评估形成的候选宇宙。

        Args:
            mode: 推断模式:
                - 'hot_sectors': 领涨主线板块龙头驱动 (优先)
                - 'liquidity': 全市场大资金流动性驱动 (成交额TOP)
                - 'momentum': 短期动量与异动活跃驱动
                - 'watchlist': 本地动态自选关注池驱动
                - 'balanced': 混合综合推断 (领涨板块50% + 流动性50%)
            size: 目标股票池容量
            allow_all_boards: 是否放行全市场板块 (双创/北交所)

        Returns:
            Dict[str, Any]:
                - stocks: List[str] 动态生成的代码列表
                - mode: str 推断模式
                - rationale: str 推断依据与市场上下文
                - leading_sectors: List[Dict] 关联主线板块
                - generated_at: str 生成时间戳
                - is_fallback: bool 是否发生降级
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        selected_stocks: List[str] = []
        rationale: str = ""
        leading_sectors: List[Dict[str, Any]] = []
        is_fallback = False

        # 模式 1: 领涨主线板块龙头驱动
        if mode in ("hot_sectors", "balanced"):
            leading_sectors = self.infer_leading_sectors(top_n=5)
            if leading_sectors:
                sec_info_strs = [f"{s['name']}({s['change_pct']:+.2f}%)" for s in leading_sectors[:3]]
                rationale = f"基于实时市场领涨主线板块动态推断: {', '.join(sec_info_strs)}"
                
                # 从领涨板块中动态抓取活跃标的
                for sec in leading_sectors[:3]:
                    detail = self.bridge.get_board_detail(sec["name"], limit=15)
                    if not detail or not isinstance(detail, dict):
                        continue
                    raw_data = detail.get("data")
                    if isinstance(raw_data, dict):
                        items = raw_data.get("items", [])
                    elif isinstance(raw_data, list):
                        items = raw_data
                    else:
                        items = []

                    for item in items:
                        if isinstance(item, dict):
                            raw_code = item.get("code") or item.get("secid") or ""
                        else:
                            raw_code = str(item)
                        c = normalize_symbol(raw_code, with_prefix=False)
                        if c and len(c) == 6 and c not in selected_stocks:
                            if not is_blocked(c, allow_all=allow_all_boards, allow_chinext=allow_chinext, allow_star=allow_star, allow_bse=allow_bse):
                                selected_stocks.append(c)
                                if len(selected_stocks) >= size:
                                    break
                    if len(selected_stocks) >= size:
                        break

        # 模式 2: 全市场流动性与大资金驱动 (或作为主线模式不足时的补充)
        if mode in ("liquidity", "balanced") or len(selected_stocks) < 10:
            active_stocks = self.infer_active_stocks(
                sort_by="amount_desc",
                top_n=size * 2,
                allow_all_boards=allow_all_boards,
                allow_chinext=allow_chinext,
                allow_star=allow_star,
                allow_bse=allow_bse,
            )
            if active_stocks:
                if not rationale:
                    rationale = f"基于当前全市场大资金流动性与成交活跃度TOP标的动态推断形成"
                else:
                    rationale += f"；补充全市场成交额活跃核心标的"
                for s in active_stocks:
                    if s not in selected_stocks:
                        selected_stocks.append(s)
                    if len(selected_stocks) >= size:
                        break

        # 模式 3: 用户自选池驱动
        if mode == "watchlist":
            user_stocks = self.load_user_watchlist_stocks(allow_all_boards=allow_all_boards)
            if user_stocks:
                selected_stocks = user_stocks[:size]
                rationale = f"基于用户本地动态自选池 (selected_pool/watch_pool.csv) 聚合形成"

        # 安全兜底：如果完全脱机/离线，安全降级至离线基准测试池
        if not selected_stocks:
            is_fallback = True
            logger.warning("市场动态推断未获得实时标的，安全降级回退至基准测试池样本")
            try:
                from core.config import get_pool_stocks
                base_stocks = get_pool_stocks("mainboard_24")
                selected_stocks = [s for s in base_stocks if not is_blocked(s, allow_all=allow_all_boards)][:size]
            except Exception:
                selected_stocks = []
            rationale = "⚠️ 离线模式降级: 实时行情接口未联通，自动回退至离线基准测试对照样本"

        return {
            "stocks": selected_stocks,
            "universe": selected_stocks,
            "mode": mode,
            "count": len(selected_stocks),
            "rationale": rationale,
            "leading_sectors": leading_sectors,
            "generated_at": now_str,
            "is_fallback": is_fallback,
            "allow_all_boards": allow_all_boards,
        }
