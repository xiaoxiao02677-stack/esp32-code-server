#!/usr/bin/env python3
"""On-server E2E: instantiate mem_hybrid, run save_memory with a fake conversation,
verify regex extraction + LLM summary + LLM distillation all land in SQLite."""
import asyncio
import json
import subprocess
import sys

sys.path.insert(0, "/root/xiaozhi-server/main/yuhe-server")

# 从 DB 拿真实 LLM_DeepSeek 配置（含真 key）
llm_row = subprocess.run(
    ["mysql", "-uroot", "-p123456", "xiaozhi_esp32_server", "-N", "-B",
     "-e", "SELECT config_json FROM ai_model_config WHERE id='LLM_DeepSeek'"],
    capture_output=True, text=True).stdout.strip().splitlines()[-1]
LLM_CFG = json.loads(llm_row)

from core.providers.memory.mem_hybrid.mem_hybrid import MemoryProvider

CONFIG = {
    "type": "mem_hybrid", "llm": "LLM_DeepSeek", "db_dir": "data/memory/",
    "auto_extract": True, "distill_facts": True, "distill_max_facts": 5,
    "default_trust": 0.5, "min_trust_threshold": 0.3, "temporal_decay_half_life": 0,
}


class FakeMsg:
    def __init__(self, role, content):
        self.role = role
        self.content = content


async def main():
    # 记忆库隔离：用 QA 专用 agent_id，不污染生产记忆
    from core.utils import llm as llm_utils
    llm = llm_utils.create_instance(LLM_CFG["type"], LLM_CFG)

    p = MemoryProvider(CONFIG)
    p.init_memory(role_id="qa-hybrid-test-agent", llm=llm,
                  agent_id="qa-hybrid-test-agent", device_id="test", session_id="qa-sess")

    msgs = [
        FakeMsg("user", "你好呀"),
        FakeMsg("assistant", "你好呀～今天想聊点什么？"),
        FakeMsg("user", "我最近搬到深圳了，在南山上班，每天通勤要一个小时，累死了。"),
        FakeMsg("assistant", "通勤一小时确实辛苦，记得路上听点轻松的东西～"),
        FakeMsg("user", "嗯，我平时喜欢听粤语歌放松，晚上会跑步。对了，我对花生过敏，这点很重要。"),
        FakeMsg("assistant", "记住啦：花生过敏这个一定注意安全！"),
    ]

    print("== save_memory 开始（正则抽取 + LLM 总结 + LLM 沉淀）==")
    await p.save_memory(msgs, session_id="qa-sess")

    # 验证长期库
    facts = p._store.list_facts(limit=50)
    print(f"\n长期库事实数: {len(facts)}")
    for f in facts:
        print(f"  [{f.get('category')}] {f.get('content')[:50]}")

    # 验证短期总结
    sm = p.summary_memory or ""
    print(f"\n短期总结长度: {len(sm)} 字符")
    print("总结片段:", sm[:200].replace("\n", " "))

    # 验证检索
    r = await p.query_memory("用户对什么过敏")
    print(f"\n检索'过敏': {r[:100]}")
    r2 = await p.query_memory("用户住哪里")
    print(f"检索'住哪': {r2[:100]}")

    ok = len(facts) >= 2 and len(sm) > 50 and ("花生" in (r or "") or "深圳" in (r2 or ""))
    print("\nRESULT:", "PASS ✓" if ok else "CHECK MANUALLY")


asyncio.run(main())
