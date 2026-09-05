# -*- coding: utf-8 -*-
"""
Tests for stock code decoupling and dynamic configuration loading.
Ensures the system is not constrained to specific hardcoded stocks.
"""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

from core.config import (
    DEFAULT_CYCLICAL_SECTORS,
    get_pool_stocks,
    load_stock_pools,
)
from core.strategy.execution_action_engine import ExecutionActionEngine
from core.strategy.fundamental_filter import FundamentalFilter


class TestStockCodeDecoupling(unittest.TestCase):
    """验证代码去硬编码与动态标的池解耦"""

    def setUp(self):
        # 模拟生成基本的K线数据 (24根)
        self.klines = [
            [f"2026-08-{i:02d}", 10.0 + i * 0.1, 10.2 + i * 0.1, 10.5 + i * 0.1, 9.8 + i * 0.1, 10000]
            for i in range(1, 25)
        ]

    def test_fundamental_filter_sector_cyclical_exemption(self):
        """测试基本面过滤：通过行业属性（如有色金属、煤炭）动态豁免周期股超高PE，不依赖写死代码"""
        ff = FundamentalFilter(max_pe=100.0)

        # 1. 洛阳钼业 (603993) - 未在旧的4只硬编码白名单中，但行业为有色金属
        quote_cyclical = {
            "price": 8.50,
            "pe": 125.0,  # > 100，本应被过滤
            "sector": "有色金属",
            "industry": "小金属",
        }
        res_cyclical = ff.inspect("603993", self.klines, quote=quote_cyclical)
        # 应该获得周期股高PE豁免，而非作为风险剔除
        pe_risk_flags = [f for f in res_cyclical["risk_flags"] if "超高PE" in f]
        self.assertEqual(len(pe_risk_flags), 0, f"周期股应豁免高PE，但不应出现超高PE风险: {pe_risk_flags}")
        self.assertTrue(any("周期股高PE豁免" in w for w in res_cyclical["warnings"]))

        # 2. 普通消费/科技股 (非周期) - 高PE必须被正常拦截
        quote_non_cyclical = {
            "price": 20.0,
            "pe": 150.0,
            "sector": "传媒",
            "industry": "游戏",
        }
        res_non_cyclical = ff.inspect("002624", self.klines, quote=quote_non_cyclical)
        pe_risk_flags2 = [f for f in res_non_cyclical["risk_flags"] if "超高PE" in f]
        self.assertGreater(len(pe_risk_flags2), 0, "非周期行业的高PE股票必须被严格拦截")

    def test_execution_action_engine_dynamic_names(self):
        """测试交易反应动作引擎：自动从 stock_pools.yaml 解析名称，不依赖硬编码15只股票"""
        all_names = ExecutionActionEngine.get_known_names()
        
        # 验证大盘基准存在
        self.assertIn("上证指数", all_names)
        self.assertEqual(all_names["上证指数"], "sh000001")

        # 验证从 stock_pools.yaml 自动加载的代表性股票
        self.assertIn("比亚迪", all_names)
        self.assertEqual(all_names["比亚迪"], "002594")
        self.assertIn("五粮液", all_names)
        self.assertEqual(all_names["五粮液"], "000858")
        self.assertIn("中信证券", all_names)
        self.assertEqual(all_names["中信证券"], "600030")

        # 自然语言意图测试：用户输入股票中文名可准确识别
        query_res = ExecutionActionEngine.parse_user_query("比亚迪目前怎么操作？")
        self.assertIn("002594", query_res.get("detected_codes", []))

    def test_config_stock_pools_ssot(self):
        """测试 stock_pools.yaml 统一加载与 fallback 机制"""
        pools_cfg = load_stock_pools()
        self.assertIn("pools", pools_cfg)
        self.assertIn("mainboard_24", pools_cfg["pools"])

        # get_pool_stocks 正常获取
        main_stocks = get_pool_stocks("mainboard_24")
        self.assertGreater(len(main_stocks), 10)

        # 未知池名称安全回退到默认池
        fallback_stocks = get_pool_stocks("unknown_nonexistent_pool")
        self.assertEqual(len(fallback_stocks), len(main_stocks))

    def test_action_plan_missing_code_defensive_behavior(self):
        """测试 action-plan 命令在缺少代码且无持仓时，安全提示而非静默分析茅台"""
        from core.commands.strategy_cmds import cmd_action_plan

        class DummyArgs:
            code = None
            opt_code = None
            cost = None
            shares = None
            count = 120

        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_action_plan(DummyArgs())

        out = buf.getvalue()
        self.assertIn("请指定股票代码", out)
        self.assertNotIn("贵州茅台", out)

    def test_fundamental_filter_no_hardcoded_whitelist(self):
        """测试 FundamentalFilter 不再硬编码特定个股白名单"""
        self.assertEqual(len(FundamentalFilter.DEFAULT_CYCLICAL_WHITELIST), 0)
        ff = FundamentalFilter()
        self.assertEqual(len(ff.cyclical_whitelist), 0)

    def test_board_permission_dynamic_control(self):
        """测试 is_blocked 支持动态传参与环境变量开启板块权限"""
        from core.strategy.pool_schema import is_blocked

        # 默认模式：阻断双创板与北交所
        self.assertTrue(is_blocked("300750"))
        self.assertTrue(is_blocked("688001"))
        self.assertTrue(is_blocked("830001"))
        self.assertFalse(is_blocked("600519"))
        self.assertFalse(is_blocked("000001"))

        # 参数模式：分别显式放行
        self.assertFalse(is_blocked("300750", allow_chinext=True))
        self.assertFalse(is_blocked("688001", allow_star=True))
        self.assertFalse(is_blocked("830001", allow_bse=True))
        self.assertFalse(is_blocked("300750", allow_all=True))
        self.assertFalse(is_blocked("688001", allow_all=True))

        # 环境变量模式：通过环境变量放行
        old_env = os.environ.get("ASTOCKS_ALLOW_CHINEXT")
        try:
            os.environ["ASTOCKS_ALLOW_CHINEXT"] = "1"
            self.assertFalse(is_blocked("300750"))
            self.assertTrue(is_blocked("688001"))  # 科创板依然阻断
        finally:
            if old_env is not None:
                os.environ["ASTOCKS_ALLOW_CHINEXT"] = old_env
            else:
                os.environ.pop("ASTOCKS_ALLOW_CHINEXT", None)

    def test_limit_prices_prefix_handling(self):
        """测试回测引擎涨跌停计算能够正确处理带前缀的代码"""
        from core.paper_trading.multi_backtest_engine import MultiBacktestEngine

        prev = 100.0
        # 科创板 20%
        up_star_pure, _ = MultiBacktestEngine._limit_prices("688001", prev)
        up_star_prefix, _ = MultiBacktestEngine._limit_prices("sh688001", prev)
        self.assertEqual(up_star_pure, 120.0)
        self.assertEqual(up_star_prefix, 120.0)

        # 创业板 20%
        up_chi_pure, _ = MultiBacktestEngine._limit_prices("300750", prev)
        up_chi_prefix, _ = MultiBacktestEngine._limit_prices("sz300750", prev)
        self.assertEqual(up_chi_pure, 120.0)
        self.assertEqual(up_chi_prefix, 120.0)

        # 北交所 30%
        up_bse_pure, _ = MultiBacktestEngine._limit_prices("830001", prev)
        up_bse_prefix, _ = MultiBacktestEngine._limit_prices("bj830001", prev)
        self.assertEqual(up_bse_pure, 130.0)
        self.assertEqual(up_bse_prefix, 130.0)

        # 主板 10%
        up_main_pure, _ = MultiBacktestEngine._limit_prices("600519", prev)
        up_main_prefix, _ = MultiBacktestEngine._limit_prices("sh600519", prev)
        self.assertEqual(up_main_pure, 110.0)
        self.assertEqual(up_main_prefix, 110.0)

    def test_screener_pipeline_cross_board(self):
        """测试选股扫描器在开启 allow_all_boards 时能正常加载跨板块标的"""
        import importlib.util
        from pathlib import Path

        root_dir = Path(__file__).resolve().parent.parent
        screen_path = root_dir / ".agents" / "skills" / "astock-screener-5a" / "scripts" / "screen.py"
        if not screen_path.exists():
            screen_path = root_dir / "skills" / "astock-screener-5a" / "scripts" / "screen.py"
        spec = importlib.util.spec_from_file_location("screen_mod", str(screen_path))
        screen_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(screen_mod)
        ScreenerPipeline = screen_mod.ScreenerPipeline

        # 默认不开启时，cross_board_growth 中的双创标的被阻断
        pipe_blocked = ScreenerPipeline(pool_name="cross_board_growth", allow_all_boards=False)
        self.assertEqual(len(pipe_blocked.candidates), 0)

        # 开启 allow_all_boards 后，能正常获得候选标的
        pipe_allowed = ScreenerPipeline(pool_name="cross_board_growth", allow_all_boards=True)
        self.assertGreater(len(pipe_allowed.candidates), 5)
        self.assertIn("300750", pipe_allowed.candidates)
        self.assertIn("688981", pipe_allowed.candidates)


if __name__ == "__main__":
    unittest.main()
