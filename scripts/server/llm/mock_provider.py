# -*- coding: utf-8 -*-
"""
server.llm.mock_provider - Offline Mock LLM Provider for unit testing and local offline demos.
Simulates realistic ReAct streaming, thoughts, and tool calling without external API keys.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, AsyncIterator, Dict, List, Optional

from server.llm.base import BaseLLMProvider, LLMStreamChunk


class MockLLMProvider(BaseLLMProvider):
    """Mock LLM Provider for testing and offline development."""

    def __init__(self, model_name: str = "mock", **kwargs: Any) -> None:
        super().__init__(model_name, **kwargs)

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
        **kwargs: Any,
    ) -> AsyncIterator[LLMStreamChunk]:
        # Check if the last message is a tool response (Observation)
        last_msg = messages[-1] if messages else {}
        is_tool_response = last_msg.get("role") == "tool"

        if is_tool_response:
            # Second turn: synthesize answer based on tool observation
            tool_content = last_msg.get("content", "")
            summary = "已获取最新量化数据。"
            try:
                data = json.loads(tool_content)
                if isinstance(data, dict):
                    if "code" in data:
                        summary = f"已获取标的 {data.get('name', '')}({data.get('code')}) 最新分析结果。"
            except Exception:
                pass

            yield LLMStreamChunk(thought="正在结合量化工具返回数据进行深度归纳，准备输出严格符合实战三原则的操盘动作单...")
            await asyncio.sleep(0.02)

            response_text = (
                f"\n\n### 📊 量化投研与操盘决议\n\n"
                f"{summary}\n\n"
                f"根据 A-Stock Agents 量化内核实时计算与实战三原则规范：\n"
                f"1. **最低保本卖出价**：已核算全部税费并强制向上进位至分位（`math.ceil`），拒绝任何摩擦磨损；\n"
                f"2. **三级风控止损阶梯**：\n"
                f"   - **T0 警戒线 (-3%)**：密切盯盘，准备减仓或对冲；\n"
                f"   - **T1 减仓线 (-5%)**：触发即减仓 50% 防守；\n"
                f"   - **T2 绝杀线 (-8%)**：无条件清仓止损；\n"
                f"3. **三场景即时动作单**：\n"
                f"   - **开盘冲高**：若高开超 2% 但分时未放量突破，分批挂单减仓；\n"
                f"   - **盘中窄幅震荡**：持仓不动，以保本价为止盈锚点；\n"
                f"   - **盘中跳水急跌**：触及警戒线立即执行纪律减仓。\n"
            )

            chunk_size = 20
            for i in range(0, len(response_text), chunk_size):
                sub = response_text[i : i + chunk_size]
                yield LLMStreamChunk(delta_text=sub)
                await asyncio.sleep(0.01)

            yield LLMStreamChunk(finish_reason="stop", usage={"prompt_tokens": 120, "completion_tokens": 200, "total_tokens": 320})
            return

        # First turn: analyze user query to see if tools should be triggered
        user_query = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_query = m.get("content", "")
                break

        # Extract 6-digit stock code if present
        code_match = re.search(r"\b(00\d{4}|30\d{4}|60\d{4}|68\d{4})\b", user_query)
        target_code = code_match.group(1) if code_match else None
        if not target_code and "茅台" in user_query:
            target_code = "600519"
        elif not target_code and "平安" in user_query:
            target_code = "000001"

        if tools and target_code:
            # Trigger tool call: action plan or quote
            tool_name = "astock_action_plan" if ("动作" in user_query or "保本" in user_query or "成本" in user_query) else "astock_quote"
            args = {"code": target_code}
            if tool_name == "astock_action_plan":
                args["cost"] = 1350.0
                args["shares"] = 100

            yield LLMStreamChunk(thought=f"检测到股票标的 {target_code}，正在调度底层量化工具 `{tool_name}` 获取真实行情与保本价...")
            await asyncio.sleep(0.02)

            yield LLMStreamChunk(
                tool_calls=[
                    {
                        "id": "call_mock_001",
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(args, ensure_ascii=False),
                        },
                    }
                ],
                finish_reason="tool_calls",
            )
            return

        elif tools and ("选股" in user_query or "5a" in user_query.lower() or "推荐" in user_query):
            # Trigger 5a screener tool
            yield LLMStreamChunk(thought="用户请求多维选股评分，调度 5A 旋转选股引擎...")
            await asyncio.sleep(0.02)
            yield LLMStreamChunk(
                tool_calls=[
                    {
                        "id": "call_mock_screen_001",
                        "type": "function",
                        "function": {
                            "name": "astock_screen_5a",
                            "arguments": json.dumps({"top_n": 5}, ensure_ascii=False),
                        },
                    }
                ],
                finish_reason="tool_calls",
            )
            return

        # Regular conversational response
        yield LLMStreamChunk(thought="用户进行日常咨询，正在生成量化投研指引...")
        await asyncio.sleep(0.02)
        greeting_text = (
            "您好！我是 A-Stock Agents 智能投研助手。\n"
            "我可以为您提供：\n"
            "- **实时行情与技术形态**（支持日K/周K、MACD背离、水下二次金叉）；\n"
            "- **精确保本价与动作单**（严格印花税、最低5元佣金与 math.ceil 进位）；\n"
            "- **5A 多维共振选股**（量价/基本面/估值/主线旋转）；\n"
            "- **7角色多空辩论与持仓诊断**。\n\n"
            "您可以直接输入股票代码（如 `600519`）、'帮我算茅台保本价' 或 '5A选股' 进行体验！"
        )
        for i in range(0, len(greeting_text), 15):
            yield LLMStreamChunk(delta_text=greeting_text[i : i + 15])
            await asyncio.sleep(0.01)

        yield LLMStreamChunk(finish_reason="stop", usage={"prompt_tokens": 50, "completion_tokens": 150, "total_tokens": 200})
