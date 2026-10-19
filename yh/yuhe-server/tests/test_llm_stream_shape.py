"""LLM 流式响应形态回归测试（nointent tuple 崩溃修复）。

背景（生产 2026-10-19 13:38 事故）：
- 生产者条件（connection.py chat()）：intent_type in ("function_call", "nointent")
  且 functions 非空 → llm.response_with_functions() 产出 tuple 流 (content, tool_calls)；
- 消费者条件原来只判 intent_type == "function_call"，nointent 分支的 tuple
  落到 content = response → content.strip() 抛
  'tuple' object has no attribute 'strip' → 兜底话术「主人，小智现在有点忙」。

connection.py 顶部 import websockets（本机无该依赖）无法 import 整模块，
沿用 test_interrupt_switch 的源码文本断言方式验证两个条件始终对齐。
"""

import re
from pathlib import Path

SRC = Path("core/connection.py").read_text(encoding="utf-8")


def test_producer_and_consumer_conditions_aligned():
    """生产者与消费者对 nointent 的判定必须一致。"""
    producer = re.search(
        r'if self\.intent_type in \("function_call", "nointent"\) and functions is not None:\s*\n\s*# 使用支持functions的streaming接口\s*\n\s*llm_responses = self\.llm\.response_with_functions\(',
        SRC,
    )
    assert producer, "生产者应为 function_call/nointent 且 functions 非空时走 response_with_functions"

    consumer = re.search(
        r'if self\.intent_type in \("function_call", "nointent"\) and functions is not None:\s*\n\s*content, tools_call = response',
        SRC,
    )
    assert consumer, "消费者解包 tuple 的条件必须与生产者一致（含 nointent）"

    # 旧的单值条件（只认 function_call）不应再出现在消费端
    assert not re.search(
        r'if self\.intent_type == "function_call" and functions is not None:\s*\n\s*content, tools_call = response',
        SRC,
    ), "消费端不得回退到只认 function_call 的旧条件"


def test_nointent_initializes_unified_tool_handler():
    """nointent 模式必须初始化 UnifiedToolHandler（self.* 设备工具依赖）。"""
    assert 'if intent_type == "nointent":' in SRC
    assert "self.func_handler = UnifiedToolHandler(self)" in SRC


def test_tuple_unpack_guard_shape():
    """tuple 解包后对 dict 响应的兜底分支仍在（上游多形态兼容）。"""
    # response_with_functions 各 provider 均可能 yield (content, tool_calls)；
    # openai.py 亦有 dict 分支，解包后需保留 "content" in response 的兜底
    assert re.search(
        r'content, tools_call = response\s*\n\s*if "content" in response:',
        SRC,
    ), "tuple 解包后的 dict 兜底分支必须保留"
