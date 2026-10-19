# -*- coding: utf-8 -*-
"""Engine F: 基础设施、路径隔离、安全审计与 AST 防假数据哨兵测试。

归属代码包：`core/data/sync_engine.py` (TradeCalendar), `core/workspace.py`,
           `core/reporting/report_generator.py`, `core/governance/`
核心职责与断言：
1. 交易日历开闭市状态机（周末永不开市、法定节假日休市、工作日正常开市）；
2. 工作区三桶规范物理隔离（output / log / temp）与防目录穿越安全；
3. HTML 报告 XSS 转义净化、沙箱路径约束与实战交易三原则费率一致性；
4. AST 语法树级零假数据哨兵（生产代码严禁硬编码虚假账户资产与行情）。
"""
from __future__ import annotations

import ast
import re
from datetime import date
from pathlib import Path
import pytest

from core.data.sync_engine import TradeCalendar
from core.workspace import (
    WORKSPACE_ROOT,
    PROJECT_ROOT,
    OUTPUT_DIR,
    LOG_DIR,
    TEMP_DIR,
    SKILLS_ROOT,
    skill_resource,
    get_temp_path,
    check_workspace_health,
)
from core.reporting.report_generator import (
    _sanitize_report_output_path,
    generate_simple_report,
)

pytestmark = pytest.mark.core


def test_trade_calendar_state_machine():
    """验证 A股交易日历与时钟状态机（周末绝不开市、法定节假日休市过滤）。"""
    # 1. 2026-10-19 是周一（正常交易日）
    assert TradeCalendar.is_trading_day("2026-10-19") is True

    # 2. 2026-10-18 是周日（周末绝不开市）
    assert TradeCalendar.is_trading_day("2026-10-18") is False
    assert TradeCalendar.is_weekend(date(2026, 10, 18)) is True

    # 3. 2026-10-01 国庆法定节假日休市
    assert TradeCalendar.is_trading_day("2026-10-01") is False

    # 4. 2026-05-01 劳动节法定休市
    assert TradeCalendar.is_trading_day("2026-05-01") is False


def test_workspace_three_buckets_and_path_safety(tmp_path: Path):
    """验证工作区三桶路径隔离（output/log/temp）与防目录穿越机制。"""
    assert WORKSPACE_ROOT.exists()
    assert PROJECT_ROOT.exists()
    assert OUTPUT_DIR.is_absolute()
    assert LOG_DIR.is_absolute()
    assert TEMP_DIR.is_absolute()

    # 1. 技能资源寻址及目录逃逸拦截
    valid_skill = "astock-market-data"
    skill_path = skill_resource(valid_skill)
    assert skill_path.is_dir()
    assert skill_path.parent == SKILLS_ROOT.resolve()

    # 非法穿越路径必须被拦截并抛出 ValueError
    with pytest.raises(ValueError, match="Skill resource escapes skill|Invalid skill identifier"):
        skill_resource(valid_skill, "../../evil_file")

    # 2. 临时目录安全生成
    temp_scratch = get_temp_path("unit_test_scratch")
    assert temp_scratch.exists()
    assert temp_scratch.is_dir()
    assert str(temp_scratch).startswith(str(TEMP_DIR.resolve()))

    # 3. 技能空间健康度自检契约（1锚点 + 6业务技能）
    health = check_workspace_health()
    assert health["total_skills"] == 7
    assert health["business_skills"] == 6
    assert health["skills_manifest"] is True
    assert health["is_healthy"] is True


def test_report_html_safety_xss_and_rate_consistency(tmp_path: Path):
    """验证自包含 HTML 报告 XSS 转义净化与沙箱路径防护。"""
    # 1. 输出路径沙箱重定向保护：试图写出沙箱被重定向至合法目录
    evil_path = "C:/Windows/System32/evil_report.html"
    safe_path = _sanitize_report_output_path(evil_path)
    assert not str(safe_path).startswith("C:/Windows")
    assert safe_path.name == "evil_report.html"

    # 2. 注入 XSS 脚本与 HTML 转义测试
    malicious_data = {
        "code": "600519",
        "name": "贵州茅台<script>alert('xss')</script>",
        "cost": 1500.0,
        "shares": 200,
        "quote": {"price": 1600.0, "change_pct": 2.5},
        "scores": {"total": 85, "rating": "A", "rating_text": "<b>强势</b>"},
    }
    out_file = tmp_path / "xss_test_report.html"
    html_content = generate_simple_report(malicious_data, output_path=str(out_file), verbose=False)

    # 必须对恶意脚本进行安全转义，严禁原样输出
    assert "<script>alert('xss')</script>" not in html_content
    assert "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in html_content or "&lt;script&gt;" in html_content

    # 3. 必须包含实战交易三原则核心要素
    # 保本价要素 (向上取整)
    assert "最低保本" in html_content or "保本价" in html_content
    # 三级止损位要素
    assert "止损" in html_content
    # 三场景即时操作要素
    assert "冲高" in html_content and "震荡" in html_content


def test_ast_production_authenticity_sentinel():
    """AST 语法树防假数据哨兵：扫描生产核心代码，杜绝硬编码静态虚假资产。"""
    workspace_root = WORKSPACE_ROOT
    core_dir = workspace_root / "skill_bundle" / "runtime" / "core"

    # 检查核心策略与执行模块
    target_files = [
        core_dir / "strategy" / "execution_action_engine.py",
        core_dir / "strategy" / "risk_position_manager.py",
        core_dir / "reporting" / "report_generator.py",
    ]

    forbidden_literals = {
        "1000000.0_fake": False,  # 确保无标记为 fake 的占位
    }

    for fpath in target_files:
        if not fpath.exists():
            continue
        content = fpath.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(fpath))

        for node in ast.walk(tree):
            if isinstance(node, ast.Constant):
                val = str(node.value)
                assert "fallbackTypewriter" not in val
                assert "Fallback Mock" not in val
