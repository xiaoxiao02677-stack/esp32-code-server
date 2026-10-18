#!/usr/bin/env python3
"""QA-3: A9 性能预演（query_memory P95 ≤300ms @500 条中文事实）+ A10 回退安全。

A9：在本地真实 mem_holographic 代码上建 500 条中文事实库（模拟试点 Agent 量级），
    测 FactRetriever.search 与 MemoryProvider.query_memory 的 P50/P95/P99 延迟。
    基准口径：query_memory 引入的额外首响延迟 = provider 内同步检索耗时
    （connection.py L1126 future.result() 阻塞等待的就是这个）。
    阈值：P95 ≤ 300ms（PRD A9）。本地 Windows + numpy 2.4 完整走 FTS5+Jaccard+HRR；
    sandyun.top 部署后需真机复测（文件 I/O 差异）。

A10：验证引擎切回 mem_local_short 的"回退安全"语义：
    - holographic 数据文件（{db_dir}/{agent_id}.db + -wal/-shm）在切引擎后【不被删除】；
    - mem_local_short 行为不变（仍读写自己的 data/.memory.yaml，不动 holographic 文件）；
    - get_status() 双引擎徽标可用。
    本地用"模拟切换"：同时实例化两个 provider，各自 init 后对比文件系统状态。

用法：
  cd code-server-mirror/yuhe-server && python <此脚本路径>/qa_perf_rollback.py [--facts 500] [--rounds 50]
退出码：0=通过；1=存在失败项（性能阈值或回退安全断言）
"""
import argparse
import os
import statistics
import sys
import tempfile
import time
import traceback
import types

_HERE = os.path.dirname(os.path.abspath(__file__))
_CANDIDATES = [
    os.path.normpath(os.path.join(_HERE, "..", "..", "..", "code-server-mirror", "yuhe-server")),
    os.getcwd(),
]
_ROOT = next((c for c in _CANDIDATES if os.path.isdir(os.path.join(c, "core"))), _CANDIDATES[0])
sys.path.insert(0, _ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

PASS = FAIL = 0
FAILED = []


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        FAILED.append(name)
        print(f"  [FAIL] {name} {extra}")


def section(title):
    print(f"\n== {title} ==")


_CN_FACT_TEMPLATES = [
    "用户最喜欢的歌手是陈奕迅",
    "用户每天早上都要喝一杯咖啡",
    "用户家住在广州天河区",
    "用户最爱的电影是霸王别姬",
    "用户喜欢在周末去公园散步",
    "用户的宠物是一只橘猫",
    "用户最常听的是粤语流行歌",
    "用户的工作是软件工程师",
    "用户喜欢吃川菜和火锅",
    "用户每天晚上十一点睡觉",
]


def build_facts(n):
    return [f"{_CN_FACT_TEMPLATES[i % len(_CN_FACT_TEMPLATES)]}（第{i}号）" for i in range(n)]


def perf_probe():
    parser = argparse.ArgumentParser()
    parser.add_argument("--facts", type=int, default=500)
    parser.add_argument("--rounds", type=int, default=50)
    args = parser.parse_args()

    tmpdir = tempfile.mkdtemp(prefix="qa_memory_perf_")
    print(f"临时目录: {tmpdir}")

    try:
        import httpx  # noqa: F401
    except ImportError:
        hstub = types.ModuleType("httpx")
        hstub.AsyncClient = object
        hstub.Client = object
        sys.modules["httpx"] = hstub
    try:
        import colorama  # noqa: F401
    except ImportError:
        stub = types.ModuleType("colorama")
        w32 = types.ModuleType("colorama.win32")
        w32.winapi_test = lambda *a, **k: False
        stub.win32 = w32
        sys.modules["colorama"] = stub
        sys.modules["colorama.win32"] = w32

    from core.utils.cache.manager import cache_manager, CacheType
    cache_manager.set(CacheType.CONFIG, "main_config", {
        "log": {"log_level": "WARNING", "log_dir": os.path.join(tmpdir, "logs"),
                "log_file": "perf.log", "data_dir": os.path.join(tmpdir, "data")},
        "server": {"auth_key": "k"},
        "selected_module": {},
    })

    from core.providers.memory.mem_holographic.mem_holographic import MemoryProvider, get_store
    from core.providers.memory.mem_holographic.retrieval import FactRetriever
    from core.providers.memory.mem_holographic import holographic as hrr

    section(f"A9 性能预演：{args.facts} 条中文事实（numpy={hrr._HAS_NUMPY}）")
    AGENT = "perf-agent"

    t0 = time.perf_counter()
    store = get_store(AGENT, db_dir=tmpdir)
    for i, content in enumerate(build_facts(args.facts)):
        store.add_fact(content, category="preference" if i % 2 == 0 else "habit")
    t_load = time.perf_counter() - t0
    print(f"   建库+写入 {args.facts} 条耗时: {t_load*1000:.0f} ms")
    check(f"写入 {args.facts} 条完成（建库无异常）", store.count_facts() >= args.facts,
          f"count={store.count_facts()}")

    retriever = FactRetriever(store=store)
    provider = MemoryProvider({"db_dir": tmpdir, "default_trust": 0.5,
                               "min_trust_threshold": 0.3, "auto_extract": True})
    provider.init_memory(role_id=AGENT, llm=None, agent_id=AGENT,
                         device_id="dev-perf", session_id="perf-sess")

    queries = [
        "用户喜欢喝什么？",
        "最喜欢的歌手是谁？",
        "用户住在哪里？",
        "周末喜欢做什么？",
        "宠物的名字是什么？",
    ]

    # 预热（缓存/连接稳定后测）
    for q in queries[:2]:
        retriever.search(q, min_trust=0.3, limit=5)

    section("retriever.search 延迟（同步检索核心路径）")
    latencies = []
    for rnd in range(args.rounds):
        q = queries[rnd % len(queries)]
        t0 = time.perf_counter()
        retriever.search(q, min_trust=0.3, limit=5)
        latencies.append((time.perf_counter() - t0) * 1000)
    p50 = statistics.median(latencies)
    p95 = sorted(latencies)[int(len(latencies) * 0.95) - 1] if len(latencies) >= 20 else sorted(latencies)[-1]
    p99 = sorted(latencies)[int(len(latencies) * 0.99) - 1] if len(latencies) >= 100 else sorted(latencies)[-1]
    print(f"   P50={p50:.1f}ms P95={p95:.1f}ms P99={p99:.1f}ms max={max(latencies):.1f}ms")
    check("A9 P95 ≤ 300ms", p95 <= 300, f"P95={p95:.1f}ms")

    section("MemoryProvider.query_memory 端到端（含注入格式化）")
    import asyncio
    q_latencies = []
    for rnd in range(min(args.rounds, 20)):
        q = queries[rnd % len(queries)]
        t0 = time.perf_counter()
        asyncio.run(provider.query_memory(q))
        q_latencies.append((time.perf_counter() - t0) * 1000)
    q_p95 = sorted(q_latencies)[int(len(q_latencies) * 0.95) - 1]
    print(f"   P95={q_p95:.1f}ms（含 asyncio.run 开销，线上为常驻事件循环，实际更低）")
    check("A9 query_memory P95 ≤ 300ms", q_p95 <= 300, f"P95={q_p95:.1f}ms")

    # ================= A10 回退安全 =================
    section("A10 回退安全：切回 mem_local_short 后 holographic 数据保留")
    db_file = os.path.join(tmpdir, f"{AGENT}.db")
    pre_files = sorted(os.listdir(tmpdir))
    print(f"   切换前 holographic 目录内容: {pre_files}")
    check("A10-1 holographic 库文件存在（{agent}.db）", os.path.exists(db_file))
    check("A10-2 WAL/SHM 伴随文件存在（WAL 模式）",
          os.path.exists(db_file + "-wal") or os.path.exists(db_file + "-shm"),
          f"files={pre_files}")

    # 模拟控制台切换：实例化 mem_local_short provider（真实代码，不 mock）。
    # mem_local_short 的 import 链拉进 core.utils.util -> opuslib_next/pydub/requests
    # （音频/HTTP 工具，与本测试语义无关），缺失时逐层补桩（tmp_final_test 同先例）。
    def _stub_audio_util_chain():
        import importlib
        for name, attrs in (
            ("requests", {"post": lambda *a, **k: None, "get": lambda *a, **k: None}),
            ("opuslib_next", {"Decoder": object, "Encoder": object}),
            ("pydub", {}),
        ):
            try:
                importlib.import_module(name)
                continue
            except ImportError:
                m = types.ModuleType(name)
                for k, v in attrs.items():
                    setattr(m, k, v)
                sys.modules[name] = m
        # pydub.AudioSegment：from pydub import AudioSegment 形式
        if not hasattr(sys.modules.get("pydub"), "AudioSegment"):
            pd = sys.modules["pydub"]
            seg = types.SimpleNamespace(from_file=lambda *a, **k: None)
            pd.AudioSegment = seg
        try:
            importlib.import_module("core.providers.memory.mem_local_short.mem_local_short")
        except ImportError as e:
            # 其余缺失模块统一补空桩（只要不触碰音频工具就不会被调用）
            m = types.ModuleType(e.name)
            sys.modules[e.name] = m
            importlib.import_module("core.providers.memory.mem_local_short.mem_local_short")

    try:
        _stub_audio_util_chain()
        from core.providers.memory.mem_local_short.mem_local_short import MemoryProvider as LocalShortProvider
        local = LocalShortProvider({}, summary_memory=None)
        local.init_memory(role_id=AGENT, llm=None, summary_memory="旧压缩档案",
                          save_to_file=False)  # 服务器为 API 模式，不写本地 yaml
        post_files = sorted(os.listdir(tmpdir))
        db_exists_after = os.path.exists(db_file)
        print(f"   切换后目录内容: {post_files}")
        check("A10-3 切换引擎后 {agent}.db 完好保留", db_exists_after)
        check("A10-4 切换后目录无新增/删除 holographic 文件", pre_files == post_files,
              f"pre={pre_files} post={post_files}")
        status = local.get_status()
        check("A10-5 mem_local_short get_status 可用（徽标）",
              status.get("engine") == "mem_local_short" and status.get("available") is True,
              f"status={status}")
        holo_status = provider.get_status()
        check("A10-6 mem_holographic get_status 可用（徽标）",
              holo_status.get("engine") == "mem_holographic" and holo_status.get("available") is True,
              f"status={holo_status}")
    except Exception as e:
        check("A10-3~6 mem_local_short 共存模拟", False, f"异常: {type(e).__name__}: {e}")

    # 切回 holographic：数据仍在（重新取 store 读库）
    store2 = get_store(AGENT, db_dir=tmpdir)
    check("A10-7 切回 holographic 后条目数不变（数据未丢失）", store2.count_facts() >= args.facts,
          f"count={store2.count_facts()}")

    try:
        store.close()
    except Exception:
        pass
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)

    print(f"\n==== RESULT: {PASS} passed, {FAIL} failed ====")
    if FAILED:
        print("Failed:", FAILED)
        sys.exit(1)


if __name__ == "__main__":
    try:
        perf_probe()
    except Exception:
        traceback.print_exc()
        sys.exit(2)
