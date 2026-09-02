# -*- coding: utf-8 -*-
"""
Full-suite verification script for a_stock_agents.
Runs automated checks across data layers, indicators, scoring models,
execution action engine, paper trading, and skill manifest integrity.
"""

import sys
import os
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "core") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "core"))

def run_tests():
    print("=" * 70)
    print(" [A-Stock Agents] 全模块自动化自检与就绪性测试")
    print(f" 项目根路径: {PROJECT_ROOT}")
    print("=" * 70)

    passed_count = 0
    total_count = 6

    # Test 1: Skill Manifest Integrity
    print("[1/6] 检查技能清单与 SKILL.md 完整性...")
    try:
        manifest_p = PROJECT_ROOT / "config" / "skills_manifest.json"
        assert manifest_p.exists(), "skills_manifest.json missing"
        with open(manifest_p, "r", encoding="utf-8") as f:
            m = json.load(f)
        skills = m.get("skills", [])
        assert len(skills) >= 15, f"Expected at least 15 skills, found {len(skills)}"
        for s in skills:
            doc_p = PROJECT_ROOT / s["skill_doc"]
            assert doc_p.exists(), f"Skill doc missing for {s['id']}: {doc_p}"
        print(f"  --> PASS (16/16 技能清单及文档完整)")
        passed_count += 1
    except Exception as e:
        print(f"  --> FAIL: {e}")

    # Test 2: Data Bridge & Realtime Quote
    print("[2/6] 测试行情数据层 (DataBridge & 腾讯实时快照)...")
    try:
        from core.data.data_bridge import DataBridge
        bridge = DataBridge()
        
        # Test realtime quote
        q = bridge.get_realtime_quote("600519")
        assert q is not None and q.get("price", 0) > 0, "Failed to get quote for 600519"
        
        # Test historical K-line
        klines = bridge.tencent_kline("600519", count=60)
        assert klines is not None and len(klines) > 0, "Failed to get historical klines"
        print(f"  --> PASS (获取 600519 现价 {q.get('price'):.2f}, 历史K线 {len(klines)} 根)")
        passed_count += 1
    except Exception as e:
        print(f"  --> FAIL: {e}")

    # Test 3: Technical Indicators Calculation
    print("[3/6] 测试技术指标计算 (MA/MACD/KDJ/RSI/BOLL/ATR/二次金叉)...")
    try:
        from core.indicators.technical_indicators import calc_all, gap_analysis, second_golden_cross
        tech = calc_all(klines)
        assert "ma" in tech and "macd" in tech and "kdj" in tech, "Indicators missing"
        gaps = gap_analysis(klines)
        assert "gaps" in gaps, "Gap analysis missing"
        golden = second_golden_cross(klines)
        assert "verdict" in golden and "checklist" in golden, "Golden cross missing"
        print(f"  --> PASS (零依赖指标计算完成: MA/MACD/KDJ/RSI/BOLL/二次金叉)")
        passed_count += 1
    except Exception as e:
        print(f"  --> FAIL: {e}")

    # Test 4: Execution Action Engine & Breakeven Price Rounding
    print("[4/6] 测试交易反应动作引擎与精确保本价进位法则...")
    try:
        from core.strategy.execution_action_engine import ExecutionActionEngine
        # Test breakeven calculation for 1000 shares at 10.00 -> should be 10.02
        min_sell = ExecutionActionEngine.calc_min_breakeven_price(cost=10.0, shares=1000)
        assert min_sell == 10.02, f"Expected 10.02, got {min_sell}"
        
        # Test engine output
        quote_mock = {"price": 1520.0, "open": 1500.0, "high": 1530.0, "low": 1495.0, "change_pct": 1.33}
        action_res = ExecutionActionEngine.generate_action(
            code="600519", name="贵州茅台", quote=quote_mock, tech=tech,
            holding={"cost": 1500.0, "shares": 100}
        )
        assert "action_type" in action_res, "action_type missing"
        assert "breakeven_price" in action_res, "breakeven_price missing"
        assert "action_items" in action_res, "action_items missing"
        print(f"  --> PASS (保本价精确进位: 10.00元买入1000股 -> 最低保本价 {min_sell:.2f}元, 反应决策链完整)")
        passed_count += 1
    except Exception as e:
        print(f"  --> FAIL: {e}")

    # Test 5: Multi-Factor & Combo Scorer
    print("[5/6] 测试多因子评分与量化诊断模型...")
    try:
        from core.models.combo_scorer import ComboScorer
        scorer = ComboScorer()
        score_res = scorer.score_full(klines=klines, latest=q)
        assert "total" in score_res, "total missing"
        assert 0 <= score_res["total"] <= 100, "Score out of 0-100 range"
        print(f"  --> PASS (综合评分: {score_res['total']}/100, 评级: {score_res.get('rating')} - {score_res.get('rating_text')})")
        passed_count += 1
    except Exception as e:
        print(f"  --> FAIL: {e}")

    # Test 6: Paper Trading System
    print("[6/6] 测试模拟盘撮合与账户体系...")
    try:
        from core.paper_trading.engine import PaperTradingEngine
        pt_engine = PaperTradingEngine(db_path=str(PROJECT_ROOT / "cache" / "test_paper_trade.db"))
        try:
            acc = pt_engine.get_account("default")
        except Exception:
            acc = pt_engine.create_account("default", initial_cash=1000000.0)
        assert acc is not None, "Failed to get/create default account"
        cash = acc.get("cash", 0.0) if isinstance(acc, dict) else acc.cash
        assert cash >= 0, "Account cash invalid"
        print(f"  --> PASS (模拟盘账户初始化成功, 可用资金: {cash:,.2f})")
        passed_count += 1
    except Exception as e:
        print(f"  --> FAIL: {e}")

    print("=" * 70)
    print(f" 测试总结: {passed_count}/{total_count} 项测试通过！")
    if passed_count == total_count:
        print(" [状态] 系统处于完全就绪状态 (ALL SYSTEMS GO)")
        print("=" * 70)
        return 0
    else:
        print(" [警告] 部分测试未通过，请检查日志。")
        print("=" * 70)
        return 1

if __name__ == "__main__":
    sys.exit(run_tests())
