from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


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


def test_mock_provider_is_guarded_by_explicit_test_mode() -> None:
    factory = (ROOT / "scripts/server/llm/factory.py").read_text(encoding="utf-8")
    assert 'server_settings.runtime_mode != "test"' in factory
    assert "return MockLLMProvider" in factory
    assert factory.index('server_settings.runtime_mode != "test"') < factory.index("return MockLLMProvider")
