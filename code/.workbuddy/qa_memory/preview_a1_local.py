#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""preview_a1_local.py — A1 记忆注入语义本地预演（不含服务器）

用镜像仓 code-server-mirror 的真实 mem_holographic 代码（store/retrieval/holographic
+ provider 边界层），仅打桩两处服务器依赖：
  1. config.config_loader.get_project_dir → 指向临时目录（db_dir 锚点）
  2. llm 对象 → None（mem_holographic 的 save/query 全链路不使用 LLM，正则抽取）

预演 A1 的核心语义：
  save_memory("我叫张三，我喜欢听粤语歌")  → 自动抽取落库（profile + preference）
  query_memory("我喜欢听什么音乐")         → 召回含 粤语 的条目（FTS5+LIKE+Jaccard(+HRR)）
  query_memory("我叫什么名字")             → 召回含 张三 的条目
  管理侧语义：search_facts(keyword=张三) 命中；update_fact 张三→张三丰 后旧词不召回；
              remove_fact 后不召回（A2 语义预演）
"""
import asyncio
import os
import shutil
import sys
import tempfile
import types
import unittest.mock as mock

MIRROR = os.environ.get(
    "YUHE_MIRROR",
    r"G:/demo/21_xiaozhi/code-server-mirror/yuhe-server")
sys.path.insert(0, MIRROR)

# 打桩 1：config.config_loader（mem_holographic._resolve_db_dir 的惰性 import）
# 注意：必须在 import provider 之前注册完整 config 包骨架（config.logger 是真实模块，
# 被 ..base 依赖；只有 config_loader 会被换成桩，避免其启动期 POST /config/server-base）
project_dir = tempfile.mkdtemp(prefix="e2e_mem_preview_")
_real_config = os.path.join(MIRROR, "config")
config_pkg = types.ModuleType("config")
config_pkg.__path__ = [_real_config]  # 真实 config/ 包（logger.py 可用）
config_loader = types.ModuleType("config.config_loader")
config_loader.get_project_dir = lambda: project_dir
sys.modules["config"] = config_pkg
sys.modules["config.config_loader"] = config_loader

# logger.py 顶层链（config_loader.load_config/read_config + settings.check_config_file）
# 全部替换为轻量桩：预演不碰服务器配置体系（load_config 是 async）
async def _load_config_stub(*a, **k):
    # logger.py 只读 config["log"]（data_dir/log_dir/log_level/log_format…）
    return {"log": {"data_dir": os.path.join(project_dir, "data"),
                    "log_dir": os.path.join(project_dir, "logs"),
                    "log_level": "INFO"}}

config_loader.load_config = _load_config_stub
config_loader.read_config = lambda *a, **k: {}
config_settings = types.ModuleType("config.settings")
config_settings.check_config_file = lambda *a, **k: None
sys.modules["config.settings"] = config_settings

from core.providers.memory.mem_holographic.mem_holographic import MemoryProvider  # noqa: E402

AGENT_ID = "preview-agent-001"
DEVICE_ID = "14:c1:9f:d1:33:48"
SESSION_1 = "preview-session-1"
SESSION_2 = "preview-session-2"

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"  {'✓' if cond else '✗'} {name}" + (f"  [{detail}]" if detail else ""))


def make_provider() -> MemoryProvider:
    # 与线上 ai_model_config Memory_mem_holographic 的 config_json 一致（202610051800.sql）
    config = {"type": "mem_holographic", "db_dir": "data/memory/",
              "auto_extract": True, "default_trust": 0.5,
              "min_trust_threshold": 0.3, "temporal_decay_half_life": 0}
    p = MemoryProvider(config)
    # 打桩 2：llm=None（mem_holographic 不用 LLM；role_id 等由 init_memory 设置）
    p.init_memory(role_id=AGENT_ID, llm=None, agent_id=AGENT_ID,
                  device_id=DEVICE_ID, session_id=SESSION_1)
    return p


class _Msg:  # 模拟 yuhe 对话消息对象（connection.dialogue 的元素形态）
    def __init__(self, role, content):
        self.role = role
        self.content = content


def main() -> int:
    print("=" * 62)
    print("A1 记忆注入语义 本地预演（真实 vendored 引擎 + 打桩 project_dir/llm）")
    print(f"  mirror: {MIRROR}")
    print(f"  project_dir(临时): {project_dir}")
    print("=" * 62)
    p = make_provider()
    store = p._store
    db_file = os.path.join(project_dir, "data", "memory", f"{AGENT_ID}.db")
    check("db 落在临时目录 data/memory/{agent_id}.db", os.path.exists(db_file), db_file)

    # ---- 会话1：注入（模拟 ASR 文本，正则抽取链路）----
    msgs = [_Msg("user", "我叫张三，我喜欢听粤语歌"),
            _Msg("assistant", "你好张三！粤语歌很好听呀。")]
    asyncio.run(p.save_memory(msgs, session_id=SESSION_1))
    all_facts = store.list_facts()
    check("自动抽取落库 ≥1 条", len(all_facts) >= 1, f"count={len(all_facts)}")
    zhang = [f for f in all_facts if "张三" in f["content"]]
    yue = [f for f in all_facts if "粤语" in f["content"]]
    check("含 张三 条目（profile 语义）", len(zhang) >= 1,
          "; ".join(f"{f['category']}:{f['content']}" for f in zhang))
    check("含 粤语 条目（preference 语义）", len(yue) >= 1,
          "; ".join(f"{f['category']}:{f['content']}" for f in yue))
    if zhang:
        f = zhang[0]
        check("信任分≈0.5（默认）", abs(f["trust_score"] - 0.5) < 1e-9, str(f["trust_score"]))
        check("status=active", f["status"] == "active")
        check("来源 device_id 记录", f["device_id"] == DEVICE_ID, f["device_id"] or "-")
        check("来源 session_id 记录", f["session_id"] == SESSION_1, f["session_id"] or "-")
        check("agent_id 记录", f["agent_id"] == AGENT_ID)

    # ---- 会话2：跨会话召回（新 session，同一 provider=同 agent 库）----
    p.session_id = SESSION_2
    r1 = asyncio.run(p.query_memory("你还记得我吗？我喜欢听什么音乐？"))
    check("query(我喜欢听什么音乐) 召回非空", bool(r1.strip()), r1.replace("\n", " | ")[:120])
    check("召回内容含 粤语", "粤语" in r1)
    r2 = asyncio.run(p.query_memory("我叫什么名字？"))
    check("query(我叫什么名字) 召回含 张三", "张三" in r2, r2.replace("\n", " | ")[:120])

    # ---- 管理侧语义预演（A2 同源同锁）----
    hit = store.search_facts(keyword="张三")
    check("管理检索 keyword=张三 命中", hit["total"] >= 1, f"total={hit['total']}")
    if zhang:
        fid = zhang[0]["fact_id"]
        # 编辑：张三 → 张三丰
        ok = store.update_fact(fid, content=zhang[0]["content"].replace("张三", "张三丰"))
        check("编辑条目成功", ok)
        r3 = asyncio.run(p.query_memory("我叫什么名字？"))
        check("编辑后新词 张三丰 可召回", "张三丰" in r3)
        r3b = asyncio.run(p.query_memory("张三"))
        check("编辑后旧词 张三 不再召回", "张三" not in r3b.replace("张三丰", ""))
        # 删除
        ok = store.remove_fact(fid)
        check("删除条目成功", ok)
        r4 = asyncio.run(p.query_memory("我叫什么名字？"))
        check("删除后 张三丰 不再召回", "张三丰" not in r4, r4.replace("\n", " | ")[:120])

    # ---- 清理临时目录 ----
    store.close()
    shutil.rmtree(project_dir, ignore_errors=True)
    print("-" * 62)
    n_pass = sum(1 for _, c in results if c)
    print(f"预演结果: {n_pass}/{len(results)} PASS")
    for name, c in results:
        if not c:
            print(f"  FAIL: {name}")
    return 0 if n_pass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
