"""
aStocks 被困持仓量化解套

四种量化策略:
  A. 阶梯减仓 — ATR触发四档每档25%
  B. 网格做T — 4格×1ATR，震荡区间高抛低吸
  C. 等额补仓 — 5条件门禁（RSI<30 + KDJ_J<0 + 地量 + 新低 + 主力流入）
  D. 波动率锚定换股 — 评分/价格/资金/板块四维筛选

独立运行，不依赖 TACN/TradingAgents 项目。
"""

import json
import math
from typing import Any, Dict, List, Optional, Tuple


class TrappedPositionAnalyzer:
    """被困持仓量化分析"""

    def __init__(self, cost_price: float, shares: int, klines: List[List],
                 latest_tech: Optional[Dict] = None):
        self.cost = cost_price
        self.shares = shares
        self.klines = klines

        if latest_tech is None and klines:
            try:
                from core.indicators.technical_indicators import calc_all
            except ImportError:
                from technical_indicators import calc_all
            tech = calc_all(klines)
            self.tech = tech["latest"]
        else:
            self.tech = latest_tech or {}

        self.current_price = self.tech.get("close", cost_price)
        self.total_cost = cost_price * shares
        self.current_value = self.current_price * shares
        self.unrealized_loss = self.current_value - self.total_cost
        self.loss_pct = (self.unrealized_loss / self.total_cost * 100) if self.total_cost > 0 else 0

    def diagnostic(self) -> Dict[str, Any]:
        """诊断画像"""
        atr = self.tech.get("atr", 0)
        close = self.current_price
        closes = [float(k[2]) for k in self.klines]
        highs = [float(k[3]) for k in self.klines]

        # 年高低点
        year_high = max(highs[-250:]) if len(highs) >= 250 else max(highs) if highs else close
        year_low = min(float(k[4]) for k in self.klines[-250:]) if len(self.klines) >= 250 else min(float(k[4]) for k in self.klines) if self.klines else close

        # 波动率（60日年化）
        if len(closes) >= 60:
            returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(-59, 0)]
            volatility_daily = (sum((r - sum(returns)/len(returns))**2 for r in returns) / len(returns)) ** 0.5
        else:
            volatility_daily = 0.02  # 默认2%

        # 凯利公式
        a = (self.cost - close) / close if close > 0 else 0  # 反弹幅度
        b = (close - self.tech.get("ma20", close * 0.9)) / close if close > 0 else 0.1
        p = 0.4  # 反弹概率（基于波动率假设）
        q = 1 - p
        kelly_f = ((p / a) - (q / b)) if a > 0 and b > 0 else 0

        return {
            "cost_price": self.cost,
            "shares": self.shares,
            "current_price": close,
            "total_cost": round(self.total_cost, 2),
            "current_value": round(self.current_value, 2),
            "unrealized_loss": round(self.unrealized_loss, 2),
            "loss_pct": round(self.loss_pct, 2),
            "atr_14": round(atr, 4),
            "volatility_daily": round(volatility_daily, 4),
            "year_high": round(year_high, 2),
            "year_low": round(year_low, 2),
            "kelly_f": round(kelly_f, 4),
            "kelly_interpretation": "数学上不该持有" if kelly_f < 0 else f"凯利仓位建议: {kelly_f*100:.1f}%",
            "ma5": self.tech.get("ma5", 0),
            "ma10": self.tech.get("ma10", 0),
            "ma20": self.tech.get("ma20", 0),
            "ma60": self.tech.get("ma60", 0),
        }

    def strategy_a_ladder(self) -> Dict[str, Any]:
        """策略A: 阶梯减仓 (四档，每档25%)"""
        atr = self.tech.get("atr", self.current_price * 0.02)
        close = self.current_price
        ma5 = self.tech.get("ma5", close * 0.98)
        ma20 = self.tech.get("ma20", close)

        tiers = [
            {"level": 1, "trigger_price": round(ma5, 2), "pct_of_position": 25,
             "label": "第一档: 反弹至MA5附近"},
            {"level": 2, "trigger_price": round(close + atr, 2), "pct_of_position": 25,
             "label": "第二档: 反弹1 ATR"},
            {"level": 3, "trigger_price": round(ma20, 2), "pct_of_position": 25,
             "label": "第三档: 反弹至MA20"},
            {"level": 4, "trigger_price": round(ma20 * 1.02, 2), "pct_of_position": 25,
             "label": "第四档: MA20上方2%（趋势可能逆转）"},
        ]

        return {"strategy": "A_阶梯减仓", "recommended": self.loss_pct > 8,
                "tiers": tiers, "total_shares": self.shares,
                "per_tier_shares": self.shares // 4}

    def strategy_b_grid(self) -> Dict[str, Any]:
        """策略B: 网格做T (4格×1ATR)"""
        atr = self.tech.get("atr", self.current_price * 0.02)
        close = self.current_price
        boll_lower = self.tech.get("boll_lower", close * 0.95)
        boll_mid = self.tech.get("boll_mid", close)

        grids = []
        for i in range(4):
            buy_price = round(boll_lower + i * atr * 0.8, 2)
            sell_price = round(buy_price + atr, 2)
            grids.append({"grid": i + 1, "buy": buy_price, "sell": sell_price,
                          "profit_per_round": round(sell_price - buy_price, 2)})

        return {
            "strategy": "B_网格做T",
            "recommended": 5 <= abs(self.loss_pct) <= 15,
            "warning": "仅适用于震荡区间！单边暴跌或暴涨时暂停",
            "grids": grids,
            "atr": round(atr, 2),
            "boll_range": f"{round(boll_lower, 2)} ~ {round(boll_mid, 2)}",
        }

    def strategy_c_replenish(self) -> Dict[str, Any]:
        """策略C: 等额补仓 (5条件门禁)"""
        kdj_j = self.tech.get("kdj_j", 50)
        rsi_val = self.tech.get("rsi", 50)

        # 地量判断
        if len(self.klines) >= 6:
            vols = [float(k[5]) for k in self.klines if float(k[5]) > 0]
            latest_vol = vols[-1]
            avg_vol = sum(vols[-6:-1]) / 5 if len(vols) >= 6 else latest_vol
            vol_ratio = latest_vol / avg_vol if avg_vol > 0 else 1
        else:
            vol_ratio = 1

        # 60日新低判断
        if len(self.klines) >= 60:
            lows_60 = [float(k[4]) for k in self.klines[-60:]]
            is_60d_low = self.current_price <= min(lows_60)
        else:
            is_60d_low = False

        checks = {
            "rsi_lt_30": {"passed": rsi_val < 30, "value": round(rsi_val, 1)},
            "kdj_j_lt_0": {"passed": kdj_j < 0, "value": round(kdj_j, 1)},
            "low_volume": {"passed": vol_ratio < 0.7, "value": round(vol_ratio, 2)},
            "new_60d_low": {"passed": is_60d_low, "value": is_60d_low},
            "main_force_inflow": {"passed": False, "value": "需资金流向数据确认"},
        }

        passed_count = sum(1 for c in checks.values() if c["passed"])
        can_execute = passed_count >= 3

        return {
            "strategy": "C_等额补仓",
            "recommended": False,  # 默认不推荐补仓
            "can_execute": can_execute,
            "required_pass": 3,
            "actual_pass": passed_count,
            "checks": checks,
            "warning": "等额补仓需≥3个条件同时满足！不够时禁止补仓",
        }

    def strategy_d_swap(self) -> Dict[str, Any]:
        """策略D: 波动率锚定换股"""
        return {
            "strategy": "D_换股",
            "recommended": abs(self.loss_pct) > 15,
            "method": "运行 a-share-strategy-mainboard-multi-swing-defensive/daily_decisions.py 获取候选池",
            "filters": [
                "排除科创板(688)/创业板(30)/北交所(8)",
                "排除同板块（系统性风险不换）",
                "目标评分必须 > 原持仓",
                "目标价与原持仓价差距 < 10%",
                "目标近5日主力净流入 > 0",
            ],
            "status": "需接入 daily_decisions.py 候选池",
        }

    def decision_tree(self) -> Dict[str, Any]:
        """量化决策树"""
        loss = abs(self.loss_pct)

        if loss < 5:
            return {"recommended": "策略E_持有等待",
                    "reason": "浮亏<5%，不值得操作。观察MA20支撑即可",
                    "strategies": ["E: 持有等待 + MA20防守"]}
        elif loss < 8:
            return {"recommended": "策略A+B",
                    "reason": "浮亏5-8%，阶梯减仓+网格做T",
                    "strategies": ["A: 阶梯减仓 (优先)", "B: 网格做T (辅助)"]}
        elif loss < 15:
            return {"recommended": "策略A+B",
                    "reason": "浮亏8-15%，阶梯减仓为主",
                    "strategies": ["A: 阶梯减仓 (主力)", "B: 网格做T (降本)"]}
        elif loss < 25:
            return {"recommended": "策略A+D",
                    "reason": "浮亏15-25%，减仓+换股",
                    "strategies": ["A: 阶梯减仓 (主力)", "D: 换股 (评估)"]}
        else:
            return {"recommended": "策略A_强制",
                    "reason": "浮亏>25%，承认错误，阶梯减仓回收资金",
                    "strategies": ["A: 阶梯减仓 (强制执行，放弃回本幻想)"]}

    def analyze(self) -> Dict[str, Any]:
        """全部分析"""
        return {
            "diagnostic": self.diagnostic(),
            "decision_tree": self.decision_tree(),
            "strategy_a_ladder": self.strategy_a_ladder(),
            "strategy_b_grid": self.strategy_b_grid(),
            "strategy_c_replenish": self.strategy_c_replenish(),
            "strategy_d_swap": self.strategy_d_swap(),
        }


# ─── CLI ──────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="aStocks 持仓量化解套")
    parser.add_argument("code", help="股票代码")
    parser.add_argument("--cost", type=float, required=True, help="持仓成本价")
    parser.add_argument("--shares", type=int, required=True, help="持仓股数")
    parser.add_argument("--count", type=int, default=250, help="K线数量")
    parser.add_argument("--json", action="store_true", default=True)
    args = parser.parse_args()

    try:
        from core.data.data_bridge import DataBridge
    except ImportError:
        from data_bridge import DataBridge
    klines = DataBridge.tencent_kline(args.code, args.count)

    if not klines or len(klines) < 26:
        print(json.dumps({"error": "K线数据不足"}, ensure_ascii=False))
        exit(1)

    analyzer = TrappedPositionAnalyzer(args.cost, args.shares, klines)
    result = analyzer.analyze()
    print(json.dumps(result, ensure_ascii=False, indent=2))
