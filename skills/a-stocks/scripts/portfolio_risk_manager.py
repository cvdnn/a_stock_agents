#!/usr/bin/env python3
"""组合级风险管理模块 (Portfolio Risk Manager)

纯Python标准库实现, 不依赖pandas/numpy。

四大功能:
1. 波动率目标(Volatility Targeting): 目标年化波动率15%, 动态调整仓位
2. 相关性矩阵分散化: 持仓间相关系数>0.7减仓
3. 组合回撤控制: 浮亏>5%减半, >10%仅留A级, >15%清仓冷却
4. 行业/板块暴露限制: 单行业≤30%, 单板块≤25%, 单股≤15%

K线格式: [[date, open, close, high, low, volume], ...]
"""

import math
import json


class PortfolioRiskManager:
    """组合级风险管理器

    四大功能:
    1. 波动率目标(Volatility Targeting): 目标年化波动率15%, 动态调整仓位
    2. 相关性矩阵分散化: 持仓间相关系数>0.7减仓
    3. 组合回撤控制: 浮亏>5%减半, >10%仅留A级, >15%清仓冷却
    4. 行业/板块暴露限制: 单行业≤30%, 单板块≤25%, 单股≤15%
    """

    def __init__(self, target_volatility=0.15, max_single_stock=0.15,
                 max_single_sector=None, max_single_industry=None,
                 drawdown_thresholds=None,
                 correlation_threshold=None,
                 config_path=None):
        """初始化

        参数优先级: 显式参数 > config.yaml > 默认值

        Args:
            target_volatility: 目标年化波动率(默认15%)
            max_single_stock: 单股最大仓位(15%)
            max_single_sector: 单板块最大仓位(25%)
            max_single_industry: 单行业最大仓位(30%)
            drawdown_thresholds: 回撤阈值(5%, 10%, 15%)
            correlation_threshold: 相关性减仓阈值(0.7)
            config_path: config.yaml 路径(可选, 自动探测)
        """
        # 尝试从 config.yaml 加载
        cfg = {}
        if config_path is None:
            import os
            for p in [
                os.path.join(os.path.dirname(__file__), "..", "config.yaml"),
                os.path.expanduser("skills/a-stocks/config.yaml"),
            ]:
                if os.path.exists(p):
                    config_path = p
                    break
        if config_path:
            try:
                import yaml
                with open(config_path) as f:
                    cfg = yaml.safe_load(f) or {}
            except Exception:
                pass

        pr_cfg = cfg.get("portfolio_risk", {})

        self.target_volatility = target_volatility if target_volatility is not None else pr_cfg.get("target_volatility", 0.15)
        self.max_single_stock = max_single_stock if max_single_stock is not None else pr_cfg.get("max_single_stock", 0.15)
        self.max_single_sector = max_single_sector if max_single_sector is not None else pr_cfg.get("max_single_sector", 0.25)
        self.max_single_industry = max_single_industry if max_single_industry is not None else pr_cfg.get("max_single_industry", 0.30)
        self.drawdown_thresholds = tuple(drawdown_thresholds) if drawdown_thresholds is not None else tuple(pr_cfg.get("drawdown_thresholds", (0.05, 0.10, 0.15)))
        self.correlation_threshold = correlation_threshold if correlation_threshold is not None else pr_cfg.get("correlation_threshold", 0.7)

    # ==================================================================
    # 内部辅助方法
    # ==================================================================

    @staticmethod
    def _calc_daily_returns(klines):
        """从K线提取日收益率序列

        日收益率 = (close[i] - close[i-1]) / close[i-1]
        K线格式: [date, open, close, high, low, volume]
        close 在 index 2

        Returns:
            list[float]: 日收益率列表, 长度 = len(klines) - 1
        """
        if not klines or len(klines) < 2:
            return []
        returns = []
        for i in range(1, len(klines)):
            prev_close = float(klines[i - 1][2])
            curr_close = float(klines[i][2])
            if prev_close == 0:
                continue
            r = (curr_close - prev_close) / prev_close
            returns.append(r)
        return returns

    @staticmethod
    def _mean(values):
        """计算均值"""
        n = len(values)
        if n == 0:
            return 0.0
        return sum(values) / n

    @staticmethod
    def _variance(values):
        """计算总体方差(除以N)"""
        n = len(values)
        if n == 0:
            return 0.0
        m = PortfolioRiskManager._mean(values)
        ss = sum((v - m) ** 2 for v in values)
        return ss / n

    @staticmethod
    def _std(values):
        """计算总体标准差"""
        return math.sqrt(PortfolioRiskManager._variance(values))

    # ==================================================================
    # 静态计算方法
    # ==================================================================

    @staticmethod
    def calc_annualized_volatility(klines, period=20):
        """计算年化波动率

        日收益率 = (close[i] - close[i-1]) / close[i-1]
        年化波动率 = std(日收益率, 总体) * sqrt(252)

        Args:
            klines: K线列表 [[date, open, close, high, low, volume], ...]
            period: 用于截取最近period个交易日(默认20), 数据不足时用全部

        Returns:
            float: 年化波动率(如0.15表示15%)
        """
        if not klines or len(klines) < 2:
            return 0.0

        # 取最近 period+1 根K线以保证至少 period 个日收益率
        if len(klines) > period + 1:
            data = klines[-(period + 1):]
        else:
            data = klines

        returns = PortfolioRiskManager._calc_daily_returns(data)
        if len(returns) < 2:
            return 0.0

        # 总体标准差
        std_daily = PortfolioRiskManager._std(returns)
        annualized = std_daily * math.sqrt(252)
        return annualized

    @staticmethod
    def calc_correlation(klines_a, klines_b):
        """计算两只股票的相关系数

        基于日收益率序列的皮尔逊相关系数

        Args:
            klines_a: 股票A的K线
            klines_b: 股票B的K线

        Returns:
            float: 皮尔逊相关系数(-1到1)
        """
        returns_a = PortfolioRiskManager._calc_daily_returns(klines_a)
        returns_b = PortfolioRiskManager._calc_daily_returns(klines_b)

        if len(returns_a) < 2 or len(returns_b) < 2:
            return 0.0

        # 按长度短的截取(尾部对齐, 使用最近的共同区间)
        min_len = min(len(returns_a), len(returns_b))
        if min_len < 2:
            return 0.0

        ra = returns_a[-min_len:]
        rb = returns_b[-min_len:]

        mean_a = PortfolioRiskManager._mean(ra)
        mean_b = PortfolioRiskManager._mean(rb)

        # 总体协方差
        cov_sum = sum((ra[i] - mean_a) * (rb[i] - mean_b) for i in range(min_len))
        cov = cov_sum / min_len

        var_a = PortfolioRiskManager._variance(ra)
        var_b = PortfolioRiskManager._variance(rb)

        denom = math.sqrt(var_a * var_b)
        if denom == 0:
            return 0.0

        correlation = cov / denom
        # 裁剪到[-1, 1]防止浮点误差
        correlation = max(-1.0, min(1.0, correlation))
        return correlation

    # ==================================================================
    # 波动率目标仓位调整
    # ==================================================================

    def volatility_target_position(self, klines, base_position=0.10):
        """波动率目标仓位调整

        仓位 = min(target_vol / actual_vol * base_position, base_position * 1.5)
        - 如果实际波动率 > 目标 * 2, 仓位减半
        - 如果实际波动率 < 目标 * 0.5, 仓位不增加(上限 base_position * 1.5)

        Args:
            klines: K线列表
            base_position: 基础仓位(默认10%)

        Returns:
            dict: {
                "adjusted_position": float,
                "actual_vol": float,
                "target_vol": float,
                "vol_ratio": float,
            }
        """
        actual_vol = self.calc_annualized_volatility(klines)
        target_vol = self.target_volatility

        if actual_vol == 0:
            # 无法计算波动率, 用基础仓位
            return {
                "adjusted_position": base_position,
                "actual_vol": 0.0,
                "target_vol": target_vol,
                "vol_ratio": 0.0,
            }

        vol_ratio = actual_vol / target_vol
        raw_position = (target_vol / actual_vol) * base_position
        adjusted_position = min(raw_position, base_position * 1.5)

        # 特殊规则: 如果实际波动率 > 目标*2, 仓位减半
        if actual_vol > target_vol * 2:
            adjusted_position = base_position * 0.5

        # 确保仓位非负
        adjusted_position = max(0.0, adjusted_position)

        return {
            "adjusted_position": round(adjusted_position, 6),
            "actual_vol": round(actual_vol, 6),
            "target_vol": target_vol,
            "vol_ratio": round(vol_ratio, 6),
        }

    # ==================================================================
    # 相关性分散化调整
    # ==================================================================

    def correlation_adjustment(self, holdings, klines_map):
        """相关性分散化调整

        Args:
            holdings: [{"code", "weight", ...}, ...]
            klines_map: {"code": klines}

        Returns:
            dict: {
                "correlation_matrix": {"codeA_codeB": float, ...},
                "high_correlation_pairs": [{"code_a", "code_b", "correlation", "action": "reduce"}, ...],
                "adjustments": [{"code", "original_weight", "adjusted_weight", "reason"}, ...],
                "herfindahl_index": float,  # 1/sum(weight^2), 有效持仓数
            }
        """
        codes = [h["code"] for h in holdings]
        correlation_matrix = {}
        high_correlation_pairs = []

        # 计算所有两两相关系数
        for i in range(len(codes)):
            for j in range(i + 1, len(codes)):
                code_a = codes[i]
                code_b = codes[j]
                kl_a = klines_map.get(code_a, [])
                kl_b = klines_map.get(code_b, [])
                corr = self.calc_correlation(kl_a, kl_b)
                pair_key = f"{code_a}_{code_b}"
                correlation_matrix[pair_key] = round(corr, 6)

                if abs(corr) > self.correlation_threshold:
                    high_correlation_pairs.append({
                        "code_a": code_a,
                        "code_b": code_b,
                        "correlation": round(corr, 6),
                        "action": "reduce",
                    })

        # 根据高相关性对进行调整: 对相关对中weight较大的一方减仓10%
        adjustments = []
        adjusted_weights = {h["code"]: h["weight"] for h in holdings}

        for pair in high_correlation_pairs:
            code_a = pair["code_a"]
            code_b = pair["code_b"]
            orig_a = adjusted_weights.get(code_a, 0)
            orig_b = adjusted_weights.get(code_b, 0)
            # 对权重较大的减仓10%
            if orig_a >= orig_b:
                new_weight = orig_a * 0.9
                adjusted_weights[code_a] = new_weight
                adjustments.append({
                    "code": code_a,
                    "original_weight": round(orig_a, 6),
                    "adjusted_weight": round(new_weight, 6),
                    "reason": f"与{code_b}相关性{pair['correlation']:.2f}>阈值{self.correlation_threshold}, 减仓10%",
                })
            else:
                new_weight = orig_b * 0.9
                adjusted_weights[code_b] = new_weight
                adjustments.append({
                    "code": code_b,
                    "original_weight": round(orig_b, 6),
                    "adjusted_weight": round(new_weight, 6),
                    "reason": f"与{code_a}相关性{pair['correlation']:.2f}>阈值{self.correlation_threshold}, 减仓10%",
                })

        # Herfindahl指数 = 1 / sum(weight_i^2), 表示有效持仓数
        # 使用调整后的权重
        weight_values = list(adjusted_weights.values())
        sum_sq = sum(w ** 2 for w in weight_values)
        herfindahl_index = (1.0 / sum_sq) if sum_sq > 0 else 0.0

        return {
            "correlation_matrix": correlation_matrix,
            "high_correlation_pairs": high_correlation_pairs,
            "adjustments": adjustments,
            "herfindahl_index": round(herfindahl_index, 4),
        }

    # ==================================================================
    # 组合回撤控制
    # ==================================================================

    def check_drawdown_control(self, portfolio_pnl_pct):
        """组合回撤控制

        Args:
            portfolio_pnl_pct: 组合浮亏百分比(负数, 如-5.0表示浮亏5%)
                正数表示盈利, 不触发任何减仓

        Returns:
            dict: {
                "level": "normal"/"warning"/"serious"/"critical",
                "action": "hold"/"reduce_half"/"keep_a_only"/"liquidate",
                "threshold_triggered": float,
                "message": str,
                "cooldown_days": int,  # 清仓后冷却天数
            }
        """
        # portfolio_pnl_pct: -5.0表示浮亏5%, 阈值为小数(0.05=5%)
        # 转换为小数后比较
        loss_pct = abs(portfolio_pnl_pct) / 100.0 if portfolio_pnl_pct < 0 else 0

        t1, t2, t3 = self.drawdown_thresholds  # (0.05, 0.10, 0.15)

        if loss_pct > t3:
            # 浮亏>15%: 全清+冷却
            return {
                "level": "critical",
                "action": "liquidate",
                "threshold_triggered": t3,
                "message": f"组合浮亏{loss_pct*100:.1f}%超过{t3*100:.0f}%阈值, 执行清仓并进入冷却期",
                "cooldown_days": 7,
            }
        elif loss_pct > t2:
            # 浮亏>10%: 仅留A级
            return {
                "level": "serious",
                "action": "keep_a_only",
                "threshold_triggered": t2,
                "message": f"组合浮亏{loss_pct*100:.1f}%超过{t2*100:.0f}%阈值, 仅保留A级(最高质量)持仓",
                "cooldown_days": 0,
            }
        elif loss_pct > t1:
            # 浮亏>5%: 减半
            return {
                "level": "warning",
                "action": "reduce_half",
                "threshold_triggered": t1,
                "message": f"组合浮亏{loss_pct*100:.1f}%超过{t1*100:.0f}%阈值, 所有持仓减半",
                "cooldown_days": 0,
            }
        else:
            return {
                "level": "normal",
                "action": "hold",
                "threshold_triggered": 0.0,
                "message": f"组合浮亏{loss_pct*100:.1f}%, 未触发回撤控制阈值, 维持持仓",
                "cooldown_days": 0,
            }

    # ==================================================================
    # 行业/板块暴露检查
    # ==================================================================

    def check_sector_exposure(self, holdings):
        """行业暴露检查

        Args:
            holdings: [{"code", "weight", "sector", "industry"}, ...]

        Returns:
            dict: {
                "sector_exposure": {"sector_name": total_weight, ...},
                "industry_exposure": {"industry_name": total_weight, ...},
                "stock_exposure": {"code": weight, ...},
                "violations": [{"type": "stock"/"sector"/"industry", "name": str, "weight": float, "limit": float, "excess": float}, ...],
                "passed": bool,
            }
        """
        sector_exposure = {}
        industry_exposure = {}
        stock_exposure = {}
        violations = []

        for h in holdings:
            code = h.get("code", "")
            weight = h.get("weight", 0)
            sector = h.get("sector", "未知")
            industry = h.get("industry", "未知")

            # 单股暴露
            stock_exposure[code] = stock_exposure.get(code, 0) + weight

            # 板块暴露
            sector_exposure[sector] = sector_exposure.get(sector, 0) + weight

            # 行业暴露
            industry_exposure[industry] = industry_exposure.get(industry, 0) + weight

        # 检查单股违规
        for code, w in stock_exposure.items():
            if w > self.max_single_stock:
                violations.append({
                    "type": "stock",
                    "name": code,
                    "weight": round(w, 6),
                    "limit": self.max_single_stock,
                    "excess": round(w - self.max_single_stock, 6),
                })

        # 检查单板块违规
        for sector, w in sector_exposure.items():
            if w > self.max_single_sector:
                violations.append({
                    "type": "sector",
                    "name": sector,
                    "weight": round(w, 6),
                    "limit": self.max_single_sector,
                    "excess": round(w - self.max_single_sector, 6),
                })

        # 检查单行业违规
        for industry, w in industry_exposure.items():
            if w > self.max_single_industry:
                violations.append({
                    "type": "industry",
                    "name": industry,
                    "weight": round(w, 6),
                    "limit": self.max_single_industry,
                    "excess": round(w - self.max_single_industry, 6),
                })

        return {
            "sector_exposure": {k: round(v, 6) for k, v in sector_exposure.items()},
            "industry_exposure": {k: round(v, 6) for k, v in industry_exposure.items()},
            "stock_exposure": {k: round(v, 6) for k, v in stock_exposure.items()},
            "violations": violations,
            "passed": len(violations) == 0,
        }

    # ==================================================================
    # 综合风险报告
    # ==================================================================

    def generate_risk_report(self, holdings, klines_map, portfolio_pnl_pct=0):
        """生成完整组合风险报告

        Args:
            holdings: [{"code", "weight", "sector", "industry", "klines"(可选)}, ...]
            klines_map: {"code": klines}
            portfolio_pnl_pct: 组合当前盈亏%(正=盈利, 负=浮亏)

        Returns:
            dict: {
                "summary": {
                    "total_positions": int,
                    "total_weight": float,
                    "herfindahl_index": float,
                    "portfolio_volatility": float,
                    "max_drawdown_action": str,
                    "sector_violations": int,
                },
                "volatility_targeting": [...],
                "correlation": {...},
                "drawdown_control": {...},
                "sector_exposure": {...},
                "recommendations": [str, ...],
            }
        """
        recommendations = []

        # --- 1. 波动率目标 ---
        vol_results = []
        for h in holdings:
            code = h["code"]
            kl = klines_map.get(code, h.get("klines", []))
            result = self.volatility_target_position(kl, base_position=h.get("weight", 0.10))
            result["code"] = code
            vol_results.append(result)

            vol_ratio = result.get("vol_ratio", 1.0)
            if vol_ratio > 2.0:
                recommendations.append(
                    f"[波动率] {code}实际波动率{result['actual_vol']:.1%} > 目标2倍, 建议仓位减半"
                )
            elif vol_ratio < 0.5:
                recommendations.append(
                    f"[波动率] {code}实际波动率{result['actual_vol']:.1%} < 目标50%, 仓位上限{result['adjusted_position']:.1%}"
                )

        # --- 2. 相关性分析 ---
        corr_result = self.correlation_adjustment(holdings, klines_map)
        for adj in corr_result.get("adjustments", []):
            recommendations.append(
                f"[相关性] {adj['code']} {adj['reason']}"
            )
        hhi = corr_result.get("herfindahl_index", 0)
        if hhi < 2.0 and len(holdings) > 1:
            recommendations.append(
                f"[分散度] Herfindahl指数={hhi:.2f}, 有效持仓数过低, 组合集中度高, 建议增加持仓分散度"
            )

        # --- 3. 回撤控制 ---
        dd_result = self.check_drawdown_control(portfolio_pnl_pct)
        if dd_result["action"] != "hold":
            recommendations.append(
                f"[回撤控制] {dd_result['message']}"
            )
        if dd_result["action"] == "reduce_half":
            recommendations.append("[回撤控制] 执行: 所有持仓减半")
        elif dd_result["action"] == "keep_a_only":
            recommendations.append("[回撤控制] 执行: 仅保留A级持仓, 其余清仓")
        elif dd_result["action"] == "liquidate":
            recommendations.append(f"[回撤控制] 执行: 全部清仓, 冷却{dd_result['cooldown_days']}天")

        # --- 4. 行业暴露 ---
        sector_result = self.check_sector_exposure(holdings)
        for v in sector_result.get("violations", []):
            type_map = {"stock": "单股", "sector": "单板块", "industry": "单行业"}
            recommendations.append(
                f"[暴露限制] {type_map.get(v['type'], v['type'])} {v['name']} "
                f"权重{v['weight']:.1%}超限(上限{v['limit']:.1%}, 超出{v['excess']:.1%}), 建议减仓"
            )

        # --- 组合波动率(加权) ---
        portfolio_vol = 0.0
        total_weight = sum(h.get("weight", 0) for h in holdings)
        for h in holdings:
            code = h["code"]
            kl = klines_map.get(code, h.get("klines", []))
            w = h.get("weight", 0)
            vol = self.calc_annualized_volatility(kl)
            portfolio_vol += (w / total_weight * vol) if total_weight > 0 else 0

        # --- Summary ---
        summary = {
            "total_positions": len(holdings),
            "total_weight": round(total_weight, 6),
            "herfindahl_index": round(hhi, 4),
            "portfolio_volatility": round(portfolio_vol, 6),
            "max_drawdown_action": dd_result["action"],
            "sector_violations": len(sector_result.get("violations", [])),
        }

        # --- 5. 单股止损联动 (调用 risk_manager) ---
        per_stock_stops = []
        try:
            from risk_manager import RiskManager
            from technical_indicators import calc_all

            for h in holdings:
                code = h["code"]
                entry_price = h.get("entry_price")
                if entry_price is None:
                    continue
                kl = klines_map.get(code, h.get("klines", []))
                if not kl or len(kl) < 20:
                    continue
                tech = calc_all(kl)
                latest = tech.get("latest", {})
                stops = RiskManager.calc_stop_losses(entry_price, latest)
                current_price = float(kl[-1][2])

                # 判断是否触发止损
                triggered = None
                if current_price <= stops["t2_ma20"]["price"]:
                    triggered = "T2清仓"
                elif current_price <= stops["t1_ma10"]["price"]:
                    triggered = "T1减半"
                elif current_price <= stops["t0_intraday"]["price"]:
                    triggered = "T0即时清仓"

                per_stock_stops.append({
                    "code": code,
                    "entry_price": entry_price,
                    "current_price": round(current_price, 2),
                    "t0": stops["t0_intraday"]["price"],
                    "t1": stops["t1_ma10"]["price"],
                    "t2": stops["t2_ma20"]["price"],
                    "triggered": triggered,
                })

                if triggered:
                    recommendations.append(
                        f"[单股止损] {code}触发{triggered}: "
                        f"现价{current_price:.2f}, 入场{entry_price:.2f}, "
                        f"T0={stops['t0_intraday']['price']}, "
                        f"T1={stops['t1_ma10']['price']}, "
                        f"T2={stops['t2_ma20']['price']}"
                    )
        except ImportError:
            pass  # risk_manager 不可用时跳过

        # 如果没有建议, 加一条正常
        if not recommendations:
            recommendations.append("[正常] 组合风险指标均在可控范围内, 维持当前持仓")

        return {
            "summary": summary,
            "volatility_targeting": vol_results,
            "correlation": corr_result,
            "drawdown_control": dd_result,
            "sector_exposure": sector_result,
            "per_stock_stops": per_stock_stops,
            "recommendations": recommendations,
        }


# ======================================================================
# CLI入口
# ======================================================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="组合风险管理")
    parser.add_argument("--holdings", help="持仓JSON文件路径")
    parser.add_argument("--pnl", type=float, default=0, help="组合浮亏%")
    parser.add_argument("--json", action="store_true", default=True)
    args = parser.parse_args()

    from data_bridge import DataBridge

    if args.holdings:
        with open(args.holdings, "r") as f:
            holdings = json.loads(f.read())
    else:
        # 默认示例
        holdings = [
            {"code": "600519", "weight": 0.15, "sector": "白酒", "industry": "食品饮料"},
            {"code": "000400", "weight": 0.10, "sector": "电气设备", "industry": "电力设备"},
            {"code": "002230", "weight": 0.08, "sector": "AI", "industry": "计算机"},
        ]

    klines_map = {}
    bridge = DataBridge()
    for h in holdings:
        klines_map[h["code"]] = bridge.tencent_kline(h["code"], 60)

    mgr = PortfolioRiskManager()
    report = mgr.generate_risk_report(holdings, klines_map, args.pnl)
    print(json.dumps(report, ensure_ascii=False, indent=2))
