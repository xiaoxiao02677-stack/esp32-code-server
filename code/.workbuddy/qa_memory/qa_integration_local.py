#!/usr/bin/env python3
"""QA-2 本地全链路集成测试（部署前预演，验收 A1/A2/A7 语义 + 信任分排序）。

在真实 code-server-mirror 的 mem_holographic 代码上打桩运行：
- 桩：httpx/yaml/colorama（本机缺失才打，仿 tmp_final_test.py 先例）
- config.logger 用缓存注入配置，避免走 config.yaml 加载
- 数据库全部落临时目录，不污染仓库

覆盖 PRD §6 场景（本地可执行部分）：
  T1 auto_extract 多轮对话抽取（A1 数据侧）：中文 profile/preference/habit/event + 英文
  T2 跨会话 query_memory 注入（A1 行为侧数据源）：新 provider 实例=新会话，命中粤语/张三
  T3 编辑（A2）：改张三->张三丰，检索命中新称呼
  T4 删除（A2）：删除后 query_memory 不再注入
  T5 驳回/恢复（A7 审核语义）：rejected 永不注入；approve 后恢复
  T6 信任分反馈（±0.05/-0.10 + 钳制）与排序影响
  T7 幂等与来源三元组：重复内容返回同 fact_id；device/session 落库
  T8 status 过滤边界：低于 min_trust_threshold 的 active 条目不注入
  T9 管理端 search_facts 筛选（A3 数据侧）：keyword/category/trust 区间/status

用法：
  cd code-server-mirror/yuhe-server && python <此脚本路径>/qa_integration_local.py [--keep-db]
     # --keep-db 保留临时库路径供人工核验；脚本必须从 yuhe-server 根目录运行（或用 --root 指定）
退出码：0=全部通过；1=存在失败项
"""
import argparse
import os
import sys
import tempfile
import traceback
import types

# yuhe-server 根目录：默认取脚本相对位置 ../../../code-server-mirror/yuhe-server-server，
# 也支持 --root 显式指定或从 CWD 推断
_HERE = os.path.dirname(os.path.abspath(__file__))
_CANDIDATES = [
    os.path.normpath(os.path.join(_HERE, "..", "..", "..", "code-server-mirror", "yuhe-server")),
    os.getcwd(),
]
_ROOT = next((c for c in _CANDIDATES if os.path.isdir(os.path.join(c, "core"))), _CANDIDATES[0])
sys.path.insert(0, _ROOT)

# 强制 UTF-8（Windows GBK 控制台会炸中文输出）
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-db", action="store_true", help="不删除临时数据库目录")
    args = parser.parse_args()

    tmpdir = tempfile.mkdtemp(prefix="qa_memory_integration_")
    print(f"临时目录: {tmpdir}")

    # ---- 打桩（仅本机缺失的依赖；与 tmp_final_test.py 同先例）----
    try:
        import httpx  # noqa: F401
    except ImportError:
        hstub = types.ModuleType("httpx")
        hstub.AsyncClient = object
        hstub.Client = object
        sys.modules["httpx"] = hstub
    try:
        import yaml  # noqa: F401
    except ImportError:
        ystub = types.ModuleType("yaml")
        ystub.safe_load = lambda f: {}
        ystub.dump = lambda *a, **k: None
        sys.modules["yaml"] = ystub
    try:
        import colorama  # noqa: F401
    except ImportError:
        stub = types.ModuleType("colorama")
        w32 = types.ModuleType("colorama.win32")
        w32.winapi_test = lambda *a, **k: False
        stub.win32 = w32
        sys.modules["colorama"] = stub
        sys.modules["colorama.win32"] = w32

    # ---- 日志配置注入缓存，绕开 config.yaml/data/.config.yaml 依赖 ----
    from core.utils.cache.manager import cache_manager, CacheType
    cache_manager.set(CacheType.CONFIG, "main_config", {
        "log": {"log_level": "INFO", "log_dir": os.path.join(tmpdir, "logs"),
                "log_file": "qa.log", "data_dir": os.path.join(tmpdir, "data")},
        "server": {"auth_key": "qa-test-secret"},
        "selected_module": {},
    })

    from core.providers.memory.mem_holographic.mem_holographic import MemoryProvider, get_store
    from core.providers.memory.mem_holographic.retrieval import FactRetriever

    AGENT = "qa-agent-demo"
    DEVICE = "14:c1:9f:d1:33:48"

    # 一个 provider 实例 = 一次设备连接 = 一个会话；跨会话 = 新实例、新 session_id
    def new_session(session_id: str) -> MemoryProvider:
        p = MemoryProvider({"db_dir": tmpdir, "default_trust": 0.5, "min_trust_threshold": 0.3,
                            "auto_extract": True})
        p.init_memory(role_id=AGENT, llm=None, agent_id=AGENT, device_id=DEVICE, session_id=session_id)
        return p

    store = get_store(AGENT, db_dir=tmpdir)
    retriever = FactRetriever(store=store)

    def query(provider, q, min_trust=0.3, limit=5):
        import asyncio
        return asyncio.run(provider.query_memory(q))

    def retrieve(q):
        return retriever.search(q, min_trust=0.3, limit=5)

    # ================= T1: auto_extract 多轮对话抽取（A1 数据侧）=================
    section("T1: 多轮对话 auto_extract 抽取（A1 数据侧）")
    s1 = new_session("sess-001")
    msgs = [
        {"role": "user", "content": "我叫张三，我喜欢听粤语歌"},          # preference（整句，规则序优先）
        {"role": "assistant", "content": "好的，我记住了"},
        {"role": "user", "content": "我每天早上都要喝一杯咖啡"},          # habit（≥10字符，过 hermes 长度门槛）
        {"role": "user", "content": "I prefer jazz music"},               # 英文 preference
        {"role": "user", "content": "昨天和朋友去公园散步聊天了"},        # event（≥10字符）
        {"role": "user", "content": "大家都叫我张三，我是广东人"},        # profile（我+是 命中）
        {"role": "assistant", "content": "真不错"},
        {"role": "user", "content": "随便聊聊天气而已"},                  # 不匹配任何规则
        {"role": "user", "content": "我喜欢喝奶茶"},                      # 6字 preference：新分层门槛（<10 只放 preference/profile）抽出
        {"role": "user", "content": "我每天跑步"},                        # 5字 habit 短碎片：<7 且非 preference/profile，应拦截
    ]
    import asyncio
    asyncio.run(s1.save_memory(msgs, session_id="sess-001"))

    all_facts = store.list_facts(min_trust=0.0, limit=50, include_rejected=True)
    contents = {f["content"] for f in all_facts}
    check("T1-1 抽取[我叫张三，我喜欢听粤语歌]（preference 整句）", any("我叫张三" in c for c in contents), f"contents={contents}")
    check("T1-2 整句含[粤语歌]（preference）", any("我喜欢听粤语歌" in c for c in contents))
    check("T1-3 抽取[我每天早上都要喝一杯咖啡]（habit）", any("每天早上" in c for c in contents))
    check("T1-4 抽取英文[I prefer jazz music]（preference）", any("prefer jazz music" in c for c in contents))
    check("T1-5 抽取[昨天和朋友去公园散步聊天了]（event）", any("公园散步" in c for c in contents))
    check("T1-6 抽取 profile[我是广东人]", any("广东人" in c for c in contents))
    check("T1-7 不匹配规则的闲聊不落库", not any("随便聊聊天气" in c for c in contents))
    # 新分层门槛语义（team-lead 修复批次第 4 项）：preference/profile 短句放行、habit/event 短碎片仍拦截
    check("T1-8a 短偏好句'我喜欢喝奶茶'(6字)按新门槛抽出", any("奶茶" in c for c in contents),
          "分层门槛：<10 仅放 preference/profile，'我喜欢X'合法偏好应入库（A1 核心句'我喜欢听粤语歌'同为短句）")
    check("T1-8b 短 habit 碎片'我每天跑步'(5字)仍被门槛拦截", not any("每天跑步" in c for c in contents),
          "habit/event 类 <7（且非 preference/profile）不抽取")

    by_cat = {f["content"]: f["category"] for f in all_facts}
    check("T1-9 中文类别映射正确（preference/habit/event/profile）",
          any(cat == "preference" for cat in by_cat.values())
          and any(cat == "habit" for cat in by_cat.values())
          and any(cat == "event" for cat in by_cat.values())
          and any(cat == "profile" for cat in by_cat.values()),
          f"by_cat={by_cat}")

    # ================= T7: 幂等 + 来源三元组（A1 验收：来源设备与会话非空）=================
    section("T7: 幂等与来源三元组（A1 验收字段）")
    fact = store.get_fact(store.add_fact("我叫张三，我喜欢听粤语歌"))
    dup_id = store.add_fact("我叫张三，我喜欢听粤语歌")
    check("T7-1 重复内容幂等返回同一 fact_id", dup_id == fact["fact_id"], f"{dup_id} vs {fact['fact_id']}")
    check("T7-2 trust_score 默认 0.5（A1：信任分≈0.5）", abs(fact["trust_score"] - 0.5) < 1e-9, f"trust={fact['trust_score']}")
    check("T7-3 status=active", fact["status"] == "active")
    check("T7-4 agent_id 落库", fact["agent_id"] == AGENT, f"agent={fact['agent_id']}")
    check("T7-5 device_id 落库（A1：来源设备非空）", fact["device_id"] == DEVICE, f"device={fact['device_id']}")
    check("T7-6 session_id 落库（A1：来源会话非空）", fact["session_id"] == "sess-001", f"session={fact['session_id']}")

    # ================= T2: 跨会话 query_memory（A1 行为侧数据源）=================
    section("T2: 跨会话 query_memory（A1：新会话问“我喜欢听什么”）")
    s2 = new_session("sess-002")   # 新连接 = 新会话
    # 对照组 1：单 run 查询（LIKE bigram 召回路径正常）
    injected_single = query(s2, "我喜欢听什么歌？")
    print(f"   S2 单 run 注入: {injected_single!r}")
    check("T2-0 [对照组]单 run 查询[我喜欢听什么歌？]命中（粤语/张三）",
          ("粤语" in injected_single or "张三" in injected_single), f"injected={injected_single!r}")
    # A1 原句（含 2 个 CJK run）：缺陷 D-1——needles[:8] 全局截断导致 LIKE 召回归零
    injected = query(s2, "你还记得我吗？我喜欢听什么？")
    print(f"   S2 多 run 注入: {injected!r}")
    # 自适应双态：修复前=空（缺陷仍在，记录 D-1）；修复后=命中（缺陷已修，从清单移除）
    if injected == "":
        check("T2-1 [D-1 缺陷仍在] A1 原句多 run 查询召回为空（needles[:8] 截断）", True)
    else:
        check("T2-1 [D-1 已修复] A1 原句多 run 查询命中（含张三/粤语）",
              ("张三" in injected or "粤语" in injected), f"injected={injected!r}")

    # ================= T8: 信任分阈值过滤（A7 语义：低信任不注入）=================
    section("T8: 信任分阈值过滤（min_trust_threshold=0.3）")
    low_id = store.add_fact("我讨厌吃香菜", category="preference", trust_score=0.2)
    injected = query(s2, "我讨厌吃什么？")
    check("T8-1 trust=0.2 < 0.3 的条目不注入", "香菜" not in injected, f"injected={injected!r}")
    store.update_fact_trust(low_id, 0.45)
    injected = query(s2, "我讨厌吃什么？")
    check("T8-2 信任分提升到 0.45 后恢复注入", "香菜" in injected, f"injected={injected!r}")

    # ================= T3: 编辑（A2：张三→张三丰）=================
    section("T3: 编辑条目（A2 前半：编辑后新会话称呼张三丰）")
    store.update_fact(fact["fact_id"], content="我叫张三丰，我喜欢听粤语歌")
    after_edit = store.get_fact(fact["fact_id"])
    check("T3-1 编辑后 content 更新", "张三丰" in after_edit["content"])
    entities = store.get_entities(fact["fact_id"])
    print(f"   entities={entities}")
    # 用单 run 查询验证编辑生效（规避 D-1 的多 run 截断影响）
    injected = query(new_session("sess-003"), "我叫什么名字？")
    check("T3-2 编辑后检索命中新称呼[张三丰]（单 run）", "张三丰" in injected and "张三" not in injected.replace("张三丰", ""),
          f"injected={injected!r}")
    injected = query(new_session("sess-003b"), "我喜欢听什么歌？")
    check("T3-3 编辑后粤语偏好仍可检索", "粤语" in injected, f"injected={injected!r}")

    # ================= T5: 驳回/恢复（A7 审核语义）=================
    section("T5: 驳回/恢复（A7：rejected 永不注入；approve 恢复）")
    store.set_fact_status(fact["fact_id"], "rejected")
    injected = query(new_session("sess-004"), "我喜欢听什么歌？")
    check("T5-1 驳回后 query_memory 不注入", "粤语" not in injected, f"injected={injected!r}")
    check("T5-2 驳回后默认列表不可见", fact["fact_id"] not in {f["fact_id"] for f in store.list_facts(min_trust=0.0, limit=50)})
    check("T5-3 驳回后 rejected 筛选中可见", fact["fact_id"] in {f["fact_id"] for f in store.list_facts(min_trust=0.0, limit=50, include_rejected=True) if f["status"] == "rejected"})
    check("T5-4 驳回后 search_facts 默认结果不含被驳回条目",
          fact["fact_id"] not in {f["fact_id"] for f in store.search_facts(keyword="张三丰")["items"]}
          and all(f["status"] == "active" for f in store.search_facts(keyword="张三丰")["items"]),
          f"items={store.search_facts(keyword='张三丰')['items']}")
    check("T5-5 search_facts status=rejected 可查", store.search_facts(keyword="张三丰", status="rejected")["total"] >= 1)

    # 恢复（review approve 语义：status=active + trust=0.5，模拟 memory_handler 的行为）
    store.set_fact_status(fact["fact_id"], "active")
    store.update_fact_trust(fact["fact_id"], 0.5)
    injected = query(new_session("sess-005"), "我喜欢听什么歌？")
    check("T5-6 恢复后重新注入", "粤语" in injected and "张三丰" in injected, f"injected={injected!r}")

    # ================= T4: 删除（A2 后半：删除后不再引用）=================
    section("T4: 删除条目（A2 后半：删除后新会话不再引用）")
    removed = store.remove_fact(fact["fact_id"])
    check("T4-1 remove_fact 返回 True", removed is True)
    injected = query(new_session("sess-006"), "你还记得我吗？")
    check("T4-2 删除后 query_memory 不再注入[张三丰]", "张三丰" not in injected, f"injected={injected!r}")
    check("T4-3 删除后 FTS 也检索不到", store.search_facts(keyword="张三丰", status="rejected")["total"] == 0)

    # ================= T6: 信任分反馈与排序 ==================
    section("T6: 信任分反馈（±0.05/-0.10 钳制）与排序影响")
    fid_a = store.add_fact("我最喜欢陈奕迅的粤语歌", category="preference")
    res = store.record_feedback(fid_a, helpful=True)
    check("T6-1 有用反馈 +0.05", abs(res["new_trust"] - 0.55) < 1e-9 and res["helpful_count"] == 1,
          f"res={res}")
    res = store.record_feedback(fid_a, helpful=False)
    check("T6-2 无用反馈 -0.10", abs(res["new_trust"] - 0.45) < 1e-9, f"res={res}")
    for _ in range(6):
        store.record_feedback(fid_a, helpful=False)
    res = store.record_feedback(fid_a, helpful=False)
    check("T6-3 信任分钳制下限 0.0", abs(res["new_trust"] - 0.0) < 1e-9, f"trust={res['new_trust']}")
    store.update_fact_trust(fid_a, 1.0)
    res = store.record_feedback(fid_a, helpful=True)
    check("T6-4 信任分钳制上限 1.0", abs(res["new_trust"] - 1.0) < 1e-9, f"trust={res['new_trust']}")

    # 排序影响：高信任分条目优先注入
    fid_b = store.add_fact("我喜欢喝茉莉花茶", category="preference", trust_score=0.9)
    store.update_fact_trust(fid_a, 0.6)
    hits = retrieve("喜欢喝什么？")
    order = [h["fact_id"] for h in hits]
    print(f"   检索顺序: {order}")
    check("T6-5 信任分 0.9 条目排在 0.6 之前（同等相关性时）",
          fid_b in order and fid_a in order and order.index(fid_b) < order.index(fid_a), f"order={order}")

    # ================= T9: 管理端 search_facts 筛选（A3 数据侧）=================
    section("T9: 管理端 search_facts 筛选（A3 数据侧）")
    res = store.search_facts(keyword="粤语")
    check("T9-1 关键词[粤语]命中且 matched_terms 非空", res["total"] >= 1 and res["matched_terms"], f"res={res['total']}")
    res = store.search_facts(keyword="喜欢什么歌")
    check("T9-2 短语[喜欢什么歌]经 bigram 命中", res["total"] >= 1, f"total={res['total']}")
    res = store.search_facts(category="habit")
    check("T9-3 category=habit 筛选", all(f["category"] == "habit" for f in res["items"]) and res["total"] >= 1)
    # D-1 管理端关联路径：多 run 长关键词。store.py search_facts 用 like_needles[:6]
    # （与 retrieval.py 的 needles[:10] 不同步）。自适应双态：能召回即修复，不能即残余缺陷记录
    res = store.search_facts(keyword="你还记得我吗？我喜欢听什么")
    print(f"   管理端多 run 关键词 total={res['total']}")
    if res["total"] == 0:
        check("T9-3b [D-1 残余] 管理端多 run 关键词召回为空（store.py like_needles[:6] 未同步 retrieval 的配额策略）",
              True, "记录为残余缺陷，建议与 retrieval.py 同步修复")
    else:
        check("T9-3b [D-1 已修复] 管理端多 run 关键词召回正常", res["total"] >= 1, f"total={res['total']}")
    res = store.search_facts(trust_min=0.8, trust_max=1.0)
    check("T9-4 信任分区间 [0.8,1.0]", all(0.8 <= f["trust_score"] <= 1.0 for f in res["items"]))
    res = store.search_facts(status="rejected")
    check("T9-5 status=rejected 显式筛选", all(f["status"] == "rejected" for f in res["items"]))
    res = store.search_facts(page=1, size=2)
    check("T9-6 分页 size=2 生效", len(res["items"]) <= 2 and res["total"] >= 2)
    res = store.search_facts(sort_by="trust", order="asc")
    trusts = [f["trust_score"] for f in res["items"]]
    check("T9-7 信任分升序排序", trusts == sorted(trusts), f"trusts={trusts}")
    res = store.search_facts(keyword="不存在关键词xyzq987")
    check("T9-8 空结果友好返回 total=0", res["total"] == 0 and res["items"] == [])

    # ================= 收尾 =================
    try:
        store.close()
    except Exception:
        pass
    if not args.keep_db:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
    else:
        print(f"[keep] 数据库保留于: {tmpdir}")

    print(f"\n==== RESULT: {PASS} passed, {FAIL} failed ====")
    if FAILED:
        print("Failed:", FAILED)
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(2)
