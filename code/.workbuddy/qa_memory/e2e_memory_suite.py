#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""e2e_memory_suite.py — 记忆功能 E2E 用户旅程测试（部署后 #7 阶段执行）

覆盖 PRD v1 §6 验收标准：A1（跨会话被记住）、A2（管理页 CRUD 生效）、
A6（mem0 未配 key 降级）、A10（切回 mem_local_short 回退安全）。
A3（搜索/筛选）、A9（性能）由 qa-api 的 API 级测试与联调覆盖，本套件专注设备对话链路。

使用方式：
  python e2e_memory_suite.py --case A1 | A2 | A6 | A10 | all
  python e2e_memory_suite.py --case all --skip-deployed   # 部署检查失败时打印 SKIP 而非 FAIL
  python e2e_memory_suite.py --case all --no-mysql        # 仅设备对话/HTTP，不直连 MySQL（切引擎由控制台执行）

退出码：0 = 全 PASS/SKIP；1 = 存在 FAIL；2 = 参数错误。
"""
import argparse
import asyncio
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
import urllib.request
import urllib.error

import websockets

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SSH_HELPER = os.path.join(os.path.dirname(SCRIPT_DIR), "ssh_run.py")

# ---- 环境（均可在命令行覆盖，部署后按需调整） ----
WS_URL = "ws://sandyun.top:8001/yuhe/v1/"
DEVICE_ID = "14:c1:9f:d1:33:48"
API_BASE = "http://sandyun.top:8001/yuhe"
MYSQL = ["mysql", "-uroot", "-p123456", "xiaozhi_esp32_server"]
AGENT_ID = "03532a34fcea46639099adb38474a2d9"
AGENT_DB = f"/root/xiaozhi-server/main/yuhe-server/data/memory/{AGENT_ID}.db"
REMOTE_LOG = "/root/xiaozhi-server/main/yuhe-server/data/app.log"

# MySQL 中 Memory 模型配置的 id
MEM_HOLO_ID = "Memory_mem_holographic"
MEM_LOCAL_ID = "Memory_mem_local_short"
MEM0_ID = "Memory_mem0ai"

# 专用 QA 用户（A6 归属；不触碰 demo 用户）
QA_USER_ID = "2110000000000000001"
QA_USER_NAME = "qa_mem_e2e"
QA_AGENT_ID = "21e2e000000000000000000000000001"
QA_DEVICE_ID = "e2:e2:qa:me:m0:01"

# A6 新增 mem0 配置 id（无 api_key），清理时删除
MEM0_NO_KEY_ID = "Memory_mem0ai_e2e_no_key"

# 失败话术（沿用 qa_session.py 口径）
FAIL_PHRASES = [
    "有点忙", "现在忙", "忙，稍", "抱歉", "对不起", "稍后再", "稍候",
    "无法", "不可用", "暂时不能用", "连接不上", "连不上",
    "没听清", "没听懂", "再说一遍", "出错了", "出了点问题",
    "Sorry", "sorry", "busy", "try again later",
]

# ---- 报告 ----
_REPORT = {"cases": [], "started": None, "ended": None}


def emit(verdict, case, checks, notes, details=None):
    _REPORT["cases"].append({
        "case": case, "verdict": verdict, "checks": checks,
        "notes": notes, "details": details or {},
    })


def log(msg):
    print(msg, flush=True)


def _s(value):
    if value is None:
        return None
    return round(float(value) * 1000)


def ssh(*commands, timeout=120):
    return subprocess.run([sys.executable, SSH_HELPER, *commands],
                          capture_output=True, text=True, timeout=timeout)


def mysql_cmd(sql: str) -> str:
    return f"{' '.join(MYSQL)} -e \"{sql}\" 2>/dev/null"


def _myssh_block(stdout, idx):
    blocks, current = [], None
    for line in stdout.splitlines():
        if line.startswith("$ "):
            current = []
            blocks.append(current)
        elif line.startswith("[rc="):
            current = None
        elif current is not None:
            current.append(line)
    return "\n".join(blocks[idx]) if idx < len(blocks) else ""


def ssh_text(cmd: str, timeout=120) -> str:
    proc = ssh(cmd, timeout=timeout)
    return _myssh_block(proc.stdout, 0)


def ssh_rc(cmd: str, timeout=120) -> int:
    proc = ssh(cmd, timeout=timeout)
    for line in proc.stdout.splitlines():
        if line.startswith("$ ") and "[rc=" in line:
            try:
                return int(line.split("[rc=")[1].rstrip("]"))
            except ValueError:
                pass
    return -1


def ssh_all(cmd: str, timeout=120):
    proc = ssh(cmd, timeout=timeout)
    return proc.stdout


def http_json(url, method="GET", data=None, token=None, timeout=20):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"code": -1, "msg": raw[:120]}
    except Exception as e:
        return None, {"code": -1, "msg": f"{type(e).__name__}: {e}"}


def md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


# ---- 部署检查 ----
def check_deployed() -> dict:
    out = ssh_text(f"ls /root/xiaozhi-server/main/yuhe-server/core/providers/memory/ 2>/dev/null")
    code_ok = "mem_holographic" in out
    out2 = ssh_text("curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8003/api/memory/agents")
    # 部署后 loopback middleware 对无 key 请求返回 401（404=路由未挂载，403=非回环源）。
    # 200/401 都证明路由已挂载；401 是无鉴权探测的预期态。
    route_ok = out2.strip() in ("200", "401")
    seed_ok = False
    seed_out = ssh_text(mysql_cmd(
        f"SELECT COUNT(*) FROM ai_model_config WHERE id='{MEM_HOLO_ID}' AND is_enabled=1"))
    try:
        seed_ok = int(seed_out.strip().splitlines()[-1]) > 0
    except (ValueError, IndexError):
        pass
    checks = {
        "远程含 mem_holographic 代码": code_ok,
        "/api/memory 路由已挂载": route_ok,
        f"ai_model_config 含 {MEM_HOLO_ID}": seed_ok,
    }
    return {"ok": all(checks.values()), "checks": checks,
            "evidence": {"providers": out.strip()[:200], "route": out2.strip()}}


# ---- QA 管理员 token（仅 demo 用户 + 专用 QA 用户各一行） ----
def token_mint(user_id: str, seed: str, expire_hours: int = 4) -> str:
    token = md5(seed)
    sql = (f"INSERT INTO sys_user_token (id, user_id, token, expire_date) "
           f"VALUES ((SELECT COALESCE(MAX(t.id),0)+1 FROM sys_user_token t), {user_id}, '{token}', "
           f"DATE_ADD(NOW(), INTERVAL {expire_hours} HOUR)) "
           f"ON DUPLICATE KEY UPDATE token=VALUES(token), expire_date=VALUES(expire_date)")
    ssh_text(mysql_cmd(sql))
    return token


def token_revoke(token: str):
    sql = f"DELETE FROM sys_user_token WHERE token='{token}'"
    ssh_text(mysql_cmd(sql))


# ---- 设备 WS 会话（复用 qa_session.py 协议） ----
def _turns_texts(turns):
    return [s for t in turns for s in t.get("sentences", [])]


async def _recv_until_quiet(ws, budget_s: float, results: dict):
    # 静默窗口 2.5s：LLM 首响应前的思考/排队期常超 1s（部署实测 TTS sentence_start
    # 延迟 >1s 导致答案被提前掐断），2.5s 兼顾快问快答与慢链路。
    deadline = time.time() + budget_s
    while time.time() < deadline:
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=min(2.5, deadline - time.time()))
        except asyncio.TimeoutError:
            return
        except websockets.ConnectionClosed:
            return
        if isinstance(msg, bytes):
            results["audio_frames"] += 1
            continue
        try:
            data = json.loads(msg)
        except json.JSONDecodeError:
            continue
        t = data.get("type")
        if t == "tts":
            if data.get("state") == "sentence_start":
                results["sentences"].append(data.get("text", ""))
            elif data.get("state") == "stop":
                results["tts_stop"] = True
        elif t == "stt":
            results["stt"].append(data.get("text", ""))
        elif t == "llm":
            results["emotion"] = data.get("emotion", "")


async def _device_turn(ws, session_id: str, text: str, budget_s: float = 60.0) -> dict:
    # budget 60s：function_call 链路（天气工具等）LLM 首响可达 10s+（部署实测
    # T2 天气问句 21:32:39→21:32:49 才出第一段语音），40s 内收完但 2.5s 静默窗
    # 判停过早会漏采，60s 总预算给慢链路留余量。
    results = {"sentences": [], "stt": [], "audio_frames": 0,
               "emotion": None, "tts_stop": False}
    await ws.send(json.dumps({"session_id": session_id, "type": "listen",
                              "state": "start", "mode": "manual"}))
    await ws.send(json.dumps({"session_id": session_id, "type": "listen",
                              "state": "detect", "text": text}))
    await ws.send(json.dumps({"session_id": session_id, "type": "listen",
                              "state": "stop"}))
    t0 = time.time()
    await _recv_until_quiet(ws, budget_s, results)
    results["total_s"] = round(time.time() - t0, 2)
    return results


async def device_session(device_id: str, client_id: str, session_id: str,
                         queries: list, settle_s: float = 6.0):
    headers = [("Authorization", "Bearer test"), ("Protocol-Version", "1"),
               ("Device-Id", device_id), ("Client-Id", client_id)]
    out = {"ok": False, "error": None, "turns": []}
    try:
        async with websockets.connect(WS_URL, additional_headers=headers,
                                      open_timeout=20, ping_interval=15) as ws:
            await ws.send(json.dumps({
                "type": "hello", "version": 1, "transport": "websocket",
                "audio_params": {"format": "opus", "sample_rate": 16000,
                                 "channels": 1, "frame_duration": 60}}))
            msg = await asyncio.wait_for(ws.recv(), timeout=15)
            if json.loads(msg).get("type") != "hello":
                raise RuntimeError(f"首消息非 hello: {msg[:80]}")
            out["ok"] = True
            # 排空开机问候（≤8s）
            drain = {"sentences": [], "stt": [], "audio_frames": 0,
                     "emotion": None, "tts_stop": False}
            await _recv_until_quiet(ws, 8.0, drain)
            for i, q in enumerate(queries, 1):
                tr = await _device_turn(ws, session_id, q)
                log(f"      [T{i}] Q={q}  A={' '.join(tr['sentences'])[:80]}")
                out["turns"].append(tr)
                await asyncio.sleep(1.0)
            # 记忆保存是守护线程：等一段让 save 完成
            await asyncio.sleep(settle_s)
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
        log(f"      [session error] {out['error']}")
    return out


# ---- SQLite 断言（远端 python3，无 sqlite3 CLI） ----
def remote_sqlite(db_path: str, sql: str) -> str:
    # 用 base64 传 SQL，规避三层引号嵌套（LIKE '%x%' 的结尾引号会与 ''' 闭合符
    # 粘连成 4 连引号导致远端 SyntaxError——部署实测踩坑）。
    sql_b64 = base64.b64encode(sql.encode("utf-8")).decode("ascii")
    return ssh_text(
        f"echo {sql_b64} | base64 -d > /tmp/e2e_q.sql && "
        f"python3 -c \"import sqlite3,sys;c=sqlite3.connect('{db_path}');"
        f"sql=open('/tmp/e2e_q.sql').read();print(c.execute(sql).fetchall());c.close()\""
    )


def fact_rows(agent_db: str, like: str) -> list:
    text = remote_sqlite(agent_db,
        f"SELECT fact_id, category, trust_score, status, device_id, session_id, content "
        f"FROM facts WHERE status='active' AND content LIKE '%{like}%'")
    rows = []
    for m in re.finditer(r"\((\d+),\s*'([^']*)',\s*([\d.]+),\s*'([^']*)',\s*'([^']*)',\s*'([^']*)',\s*'([^']*)'\)", text):
        rows.append({"fact_id": int(m.group(1)), "category": m.group(2),
                     "trust_score": float(m.group(3)), "status": m.group(4),
                     "device_id": m.group(5), "session_id": m.group(6),
                     "content": m.group(7)})
    return rows


# ---- A1 ----
def run_a1(args) -> dict:
    log("=" * 60)
    log("A1 跨会话被记住（demo Agent → mem_holographic）")
    log("=" * 60)
    checks, notes = {}, []
    cleanup = {"db_backed_up": False, "db_restored": False, "mysql_restored": False}

    # 0) 部署检查
    dep = check_deployed()
    if not dep["ok"]:
        return {"verdict": "SKIP" if args.skip_deployed else "FAIL",
                "checks": dep["checks"], "notes": [f"线上未部署（{dep['evidence']}）"],
                "cleanup": {}}

    # 1) 备份 + 切引擎（mysql update ai_agent + 重启 yuhe-server）
    bak = f"/tmp/e2e_memory_{AGENT_ID}_{time.strftime('%Y%m%d_%H%M%S')}.db.bak"
    backup_sql = f"SELECT mem_model_id FROM ai_agent WHERE id='{AGENT_ID}'"
    old_engine = ssh_text(mysql_cmd(backup_sql)).strip().splitlines()[-1].strip()
    ssh_text(mysql_cmd(
        f"UPDATE ai_agent SET mem_model_id='{MEM_HOLO_ID}' WHERE id='{AGENT_ID}'"))
    ssh_text(f"cp {AGENT_DB} {bak} 2>/dev/null")
    cleanup["db_backed_up"] = True
    cleanup["backup"] = bak
    cleanup["old_engine"] = old_engine

    # 2) 重启 yuhe-server（新连接生效）
    restart = ssh_all("systemctl restart yuhe-server 2>&1 || "
                      "(pkill -f 'python app.py' && sleep 2 && cd /root/xiaozhi-server/main/yuhe-server && nohup .venv/bin/python app.py > /tmp/xz_restart.log 2>&1 &)")
    log(f"      restart rc-err: {restart.strip()[-200:]}")
    time.sleep(8)
    up = ssh_text("ss -tlnp | grep -c ':8000 '").strip() == "1"
    checks["引擎切换后服务重启存活"] = up
    if not up:
        return {"verdict": "FAIL", "checks": checks, "notes": ["服务重启失败"], "cleanup": cleanup}

    # 3) 会话1：自我介绍
    log("      [会话1] 注入记忆…")
    s1 = asyncio.run(device_session(
        DEVICE_ID, "e2e-a1-s1", "e2e-a1-session-1",
        ["我叫张三，我喜欢听粤语歌"]))
    checks["会话1 连接正常"] = s1["ok"]
    if not s1["ok"]:
        return {"verdict": "FAIL", "checks": checks, "notes": [s1["error"]], "cleanup": cleanup}

    # 4) 会话2（新连接）：跨会话提问
    log("      [会话2] 新连接提问…")
    s2 = asyncio.run(device_session(
        DEVICE_ID, "e2e-a1-s2", "e2e-a1-session-2",
        ["你还记得我吗？我喜欢听什么音乐？", "我叫什么名字？"]))
    checks["会话2 连接正常"] = s2["ok"]
    all_text = "".join("".join(t["sentences"]) for t in s2["turns"])
    checks["回答包含 张三"] = "张三" in all_text
    checks["回答包含 粤语"] = "粤语" in all_text
    # 逐问句断言（T1=PRD 原文音乐问句，T2=名字问句）：修复 _merge_like_candidates 后均须命中
    if len(s2["turns"]) >= 2:
        t1_text = "".join(s2["turns"][0]["sentences"])
        t2_text = "".join(s2["turns"][1]["sentences"])
        checks["T1(音乐问句)回答含 粤语"] = "粤语" in t1_text
        checks["T2(名字问句)回答含 张三"] = "张三" in t2_text
        if not checks["T1(音乐问句)回答含 粤语"]:
            notes.append(f"T1 回答: {t1_text[:200]}")
        if not checks["T2(名字问句)回答含 张三"]:
            notes.append(f"T2 回答: {t2_text[:200]}")
    if not checks["回答包含 张三"] or not checks["回答包含 粤语"]:
        notes.append(f"会话2 完整回答: {all_text[:300]}")

    # 5) SQLite 断言：data/memory/{agent_id}.db 出现条目
    rows = fact_rows(AGENT_DB, "%")
    checks["holographic 库文件存在且有条目"] = len(rows) > 0
    zh = fact_rows(AGENT_DB, "张三")
    yue = fact_rows(AGENT_DB, "粤语")
    checks["条目含 张三（profile）"] = any("张三" in r["content"] for r in zh)
    checks["条目含 粤语（preference）"] = any("粤语" in r["content"] for r in yue)
    if zh:
        z = zh[0]
        checks["来源设备非空"] = bool(z["device_id"])
        checks["来源会话非空"] = bool(z["session_id"])
        notes.append(f"张三条目: cat={z['category']} trust={z['trust_score']} "
                     f"dev={z['device_id'] or '-'} sess={z['session_id'] or '-'}")
    for r in yue:
        notes.append(f"粤语条目: cat={r['category']} trust={r['trust_score']}")

    # 6) 管理 API 列表（经 manager-api，验证同源可见性）
    token = token_mint("2106728446262718466", "e2e-memory-a1-token")
    status, body = http_json(
        f"{API_BASE}/memory/facts?agent_id={AGENT_ID}&keyword=%E5%BC%A0%E4%B8%89&page=1&size=10",
        token=token)
    # PageData 序列化形态: {code,msg,data:{total:int,list:[...]}}
    page = body.get("data") or {}
    checks["管理 API 能列出 张三 条目"] = (status == 200 and body.get("code") == 0
                                     and (page.get("total") or 0) >= 1
                                     and len(page.get("list") or []) >= 1)
    if status != 200 or body.get("code") != 0:
        notes.append(f"管理 API 响应: {status} {body}")

    verdict = "PASS" if all(checks.values()) else "FAIL"
    return {"verdict": verdict, "checks": checks, "notes": notes,
            "details": {"s1": s1, "s2": s2, "facts": rows},
            "cleanup": cleanup, "_token": token}


# ---- A2 ----
def run_a2(args) -> dict:
    log("=" * 60)
    log("A2 管理页 CRUD 生效（编辑→对话引用；删除→对话不引用）")
    log("=" * 60)
    checks, notes = {}, []
    dep = check_deployed()
    if not dep["ok"]:
        return {"verdict": "SKIP" if args.skip_deployed else "FAIL",
                "checks": dep["checks"], "notes": [f"线上未部署（{dep['evidence']}）"], "cleanup": {}}

    token = token_mint("2106728446262718466", "e2e-memory-a2-token")
    cleanup = {"restored": False}

    # 1) 找条目
    status, body = http_json(
        f"{API_BASE}/memory/facts?agent_id={AGENT_ID}&keyword=%E5%BC%A0%E4%B8%89&page=1&size=10",
        token=token)
    items = (body.get("data") or {}).get("list") or []
    checks["列表命中 张三"] = status == 200 and body.get("code") == 0 and len(items) > 0
    if not items:
        notes.append("未找到 张三 条目（先跑 A1？）")
        return {"verdict": "FAIL", "checks": checks, "notes": notes, "cleanup": cleanup}
    fact = items[0]
    fid = fact.get("fact_id")
    old_content = fact.get("content")
    log(f"      目标条目 fact_id={fid} content={old_content}")

    # 2) 编辑 → 张三丰
    new_content = old_content.replace("张三", "张三丰")
    status, body = http_json(f"{API_BASE}/memory/facts/{fid}",
                             method="PUT",
                             data={"agent_id": AGENT_ID, "content": new_content},
                             token=token)
    checks["编辑成功"] = status == 200 and body.get("code") == 0 and "张三丰" in body.get("data", {}).get("content", "")

    # 3) 设备对话问名字 → 断言引用 张三丰
    s1 = asyncio.run(device_session(DEVICE_ID, "e2e-a2-s1", "e2e-a2-session-1", ["我叫什么名字？"]))
    checks["对话连接正常"] = s1["ok"]
    all_text = "".join("".join(t["sentences"]) for t in s1["turns"])
    checks["回答引用 张三丰"] = "张三丰" in all_text
    checks["回答不再引用 张三"] = "张三" not in all_text.replace("张三丰", "")
    if not checks["回答引用 张三丰"]:
        notes.append(f"编辑后回答: {all_text[:300]}")

    # 4) 删除条目
    status, body = http_json(f"{API_BASE}/memory/facts/{fid}?agent_id={AGENT_ID}",
                             method="DELETE", token=token)
    checks["删除成功"] = status == 200 and body.get("code") == 0

    # 5) 再问 → 不引用
    s2 = asyncio.run(device_session(DEVICE_ID, "e2e-a2-s2", "e2e-a2-session-2", ["我叫什么名字？"]))
    all_text2 = "".join("".join(t["sentences"]) for t in s2["turns"])
    checks["删除后回答不引用 张三丰"] = "张三丰" not in all_text2
    if not checks["删除后回答不引用 张三丰"]:
        notes.append(f"删除后回答: {all_text2[:300]}")

    verdict = "PASS" if all(checks.values()) else "FAIL"
    return {"verdict": verdict, "checks": checks, "notes": notes,
            "details": {"edited_content": new_content, "s1": s1, "s2": s2},
            "cleanup": cleanup, "_token": token}


# ---- A6 ----
def run_a6(args) -> dict:
    log("=" * 60)
    log("A6 mem0 未配 key 降级（专用 QA Agent，不触碰 demo）")
    log("=" * 60)
    checks, notes = {}, []
    dep = check_deployed()
    if not dep["ok"]:
        return {"verdict": "SKIP" if args.skip_deployed else "FAIL",
                "checks": dep["checks"], "notes": [f"线上未部署（{dep['evidence']}）"], "cleanup": {}}

    cleanup = {"token": None}
    token = token_mint("2106728446262718466", "e2e-memory-a6-token")
    cleanup["token"] = token

    # 1) 建专用 QA 用户（幂等）
    ssh_text(mysql_cmd(
        f"INSERT INTO sys_user (id, username, password, super_admin, status, create_date) "
        f"VALUES ('{QA_USER_ID}', '{QA_USER_NAME}', 'e2e-unused', 0, 1, NOW()) "
        f"ON DUPLICATE KEY UPDATE status=1"))

    # 2) 新增 mem0 配置（无 api_key）
    cfg = ('{"type": "mem0ai", "api_key": "", "base_url": "", '
           '"auto_extract": true, "default_trust": 0.5, "min_trust_threshold": 0.3}')
    ssh_text(mysql_cmd(
        f"INSERT INTO ai_model_config (id, model_type, model_code, model_name, is_default, is_enabled, "
        f"config_json, sort, creator, create_date) "
        f"VALUES ('{MEM0_NO_KEY_ID}', 'Memory', 'mem0ai', 'Mem0 E2E 无Key', 0, 1, '{cfg}', 9, 1, NOW()) "
        f"ON DUPLICATE KEY UPDATE is_enabled=1"))

    # 3) 建专用 QA Agent（user_id=QA_USER_ID）
    # ⚠️ ai_agent 无 status 列（部署实测 desc，QA 原 SQL 按错误表结构写、INSERT 一直
    #    1054 失败被 2>/dev/null 吞掉 → Agent 行从未建成 → Java 查 Agent Total:0 →
    #    下发空配置 → Python 实例化组件失败 'TTS'）。
    # 模型列+TTS 音色照抄 demo Agent（TTS_EdgeTTS0009/粤语），保证会话组件齐备。
    ssh_text(mysql_cmd(f"DELETE FROM ai_agent WHERE id='{QA_AGENT_ID}'"))
    ssh_text(mysql_cmd(
        f"INSERT INTO ai_agent (id, user_id, agent_code, agent_name, mem_model_id, "
        f"asr_model_id, vad_model_id, llm_model_id, tts_model_id, tts_voice_id, tts_language, "
        f"tts_volume, tts_rate, tts_pitch, intent_model_id, vllm_model_id, slm_model_id, chat_history_conf, creator, created_at) "
        f"VALUES ('{QA_AGENT_ID}', '{QA_USER_ID}', 'qa-mem0-agent', 'QA-mem0-测试', '{MEM0_NO_KEY_ID}', "
        f"'ASR_FunASR', 'VAD_SileroVAD', 'LLM_DeepSeek', 'TTS_EdgeTTS', 'TTS_EdgeTTS0009', '粤语', "
        f"97, 36, 31, 'Intent_function_call', 'VLLM_ChatGLMVLLM', 'LLM_DeepSeek', 1, '{QA_USER_ID}', NOW())"))

    # 3.5) 注册专用测试设备（WS 网关 hello 校验要求设备已绑定 Agent——部署实测：
    #       未注册设备首消息即被拒"没有找到该设备的版本"）。id=mac_address，board/app_version
    #       沿用已验证可连的 my-s3-tft/2.5.1 组合，清理时随 QA Agent 一并删除。
    ssh_text(mysql_cmd(
        f"INSERT INTO ai_device (id, user_id, mac_address, board, agent_id, app_version, sort, "
        f"creator, create_date) "
        f"VALUES ('{QA_DEVICE_ID}', '{QA_USER_ID}', '{QA_DEVICE_ID}', 'my-s3-tft', "
        f"'{QA_AGENT_ID}', '2.5.1', 0, '{QA_USER_ID}', NOW()) "
        f"ON DUPLICATE KEY UPDATE agent_id='{QA_AGENT_ID}'"))

    # 4) 模拟设备对话（专用 Device-Id）
    s1 = asyncio.run(device_session(
        QA_DEVICE_ID, "e2e-a6-s1", "e2e-a6-session-1",
        ["你好呀，跟我打个招呼吧", "今天天气怎么样？"]))
    checks["对话连接正常"] = s1["ok"]
    checks["两轮均有回复"] = len(s1["turns"]) == 2 and all(len(t["sentences"]) > 0 for t in s1["turns"])
    all_text = "".join("".join(t["sentences"]) for t in s1["turns"])
    fail_hits = [p for p in FAIL_PHRASES if p in all_text]
    checks["无失败话术"] = not fail_hits
    if fail_hits:
        notes.append(f"失败话术命中: {fail_hits}")
    if not s1["ok"]:
        notes.append(f"会话错误: {s1['error']}")

    # 5) 服务端日志：mem0 未配 key 的告警不阻塞（仅记录，不断言 ERROR 数）
    log_out = ssh_text(
        f"grep -a 'Mem0ai' {REMOTE_LOG} | tail -3")
    notes.append(f"mem0 日志尾部: {log_out.strip()[-200:]}")

    # 6) 管理端 /memory/agents 徽标：QA Agent engine=mem0ai 且 available=false
    # ⚠️ listAgents 按 user_id 隔离（产品正确语义）：QA Agent 属主是 QA 用户，
    #    管理员 token 看不到它（部署实测）。改用 QA 用户自己的 token 查询。
    qa_token = token_mint(QA_USER_ID, "e2e-memory-a6-qa-owner-token")
    status, body = http_json(f"{API_BASE}/memory/agents", token=qa_token)
    checks["/memory/agents 调用成功"] = status == 200 and body.get("code") == 0
    agents = body.get("data", []) or []
    qa_vo = next((a for a in agents if a.get("agentId") == QA_AGENT_ID or a.get("agent_id") == QA_AGENT_ID), None)
    if qa_vo:
        checks["QA Agent 引擎为 mem0ai"] = qa_vo.get("engine") == "mem0ai"
        checks["available=false 徽标"] = qa_vo.get("available") is False
        notes.append(f"QA Agent VO: {qa_vo}")
    else:
        checks["QA Agent 出现在列表"] = False
        notes.append(f"未在 /memory/agents 找到 QA Agent；返回: {str(agents)[:200]}")

    verdict = "PASS" if all(checks.values()) else "FAIL"
    return {"verdict": verdict, "checks": checks, "notes": notes,
            "details": {"s1": s1, "agents_vo": agents}, "cleanup": cleanup,
            "_token": token, "_qa_token": qa_token}


# ---- A10 ----
def run_a10(args) -> dict:
    log("=" * 60)
    log("A10 回退安全（holographic → mem_local_short）")
    log("=" * 60)
    checks, notes = {}, []
    dep = check_deployed()
    if not dep["ok"]:
        return {"verdict": "SKIP" if args.skip_deployed else "FAIL",
                "checks": dep["checks"], "notes": [f"线上未部署（{dep['evidence']}）"], "cleanup": {}}
    cleanup = {"mysql_restored": False}

    # 0) 前置：demo 当前应为 holographic（A1 遗留）且库中有条目
    cur = ssh_text(mysql_cmd(
        f"SELECT mem_model_id FROM ai_agent WHERE id='{AGENT_ID}'")).strip().splitlines()[-1].strip()
    if cur != MEM_HOLO_ID:
        return {"verdict": "SKIP", "checks": {"前置：demo 当前引擎为 holographic": False},
                "notes": [f"当前引擎为 {cur}，请先执行 A1 建立 holographic 数据"], "cleanup": cleanup}
    checks["前置：demo 当前引擎为 holographic"] = True
    n_before = len(fact_rows(AGENT_DB, "%"))
    checks["前置：holographic 库有条目"] = n_before > 0

    # 1) 切回 mem_local_short + 重启
    ssh_text(mysql_cmd(
        f"UPDATE ai_agent SET mem_model_id='{MEM_LOCAL_ID}' WHERE id='{AGENT_ID}'"))
    ssh_all("systemctl restart yuhe-server 2>&1 || (pkill -f 'python app.py' && sleep 2 && cd /root/xiaozhi-server/main/yuhe-server && nohup .venv/bin/python app.py > /tmp/xz_restart.log 2>&1 &)")
    time.sleep(8)
    up = ssh_text("ss -tlnp | grep -c ':8000 '").strip() == "1"
    checks["切换回退后服务存活"] = up

    # 2) 对话正常（压缩档案行为）
    s1 = asyncio.run(device_session(DEVICE_ID, "e2e-a10-s1", "e2e-a10-session-1", ["你好呀"]))
    checks["对话连接正常"] = s1["ok"]
    checks["对话有回复"] = s1["ok"] and len(s1["turns"]) == 1 and len(s1["turns"][0]["sentences"]) > 0
    if not s1["ok"]:
        notes.append(f"会话错误: {s1['error']}")

    # 3) holographic 库文件仍在，条目数不变
    n_after = len(fact_rows(AGENT_DB, "%"))
    checks["holographic 数据保留不丢失"] = n_after >= n_before
    notes.append(f"条目数: 切回前 {n_before} → 切回后 {n_after}")

    verdict = "PASS" if all(checks.values()) else "FAIL"
    return {"verdict": verdict, "checks": checks, "notes": notes,
            "details": {"facts_before": n_before, "facts_after": n_after, "s1": s1},
            "cleanup": cleanup}


# ---- 清理 ----
def do_cleanup(case: str, ctx: dict):
    log(f"[cleanup] {case} …")
    token = ctx.get("_token")
    if token:
        token_revoke(token)

    if case == "A1":
        if ctx.get("cleanup", {}).get("mysql_restored"):
            return
        old = ctx.get("cleanup", {}).get("old_engine")
        if old:
            ssh_text(mysql_cmd(
                f"UPDATE ai_agent SET mem_model_id='{old}' WHERE id='{AGENT_ID}'"))
            ctx["cleanup"]["mysql_restored"] = True
        # holographic 库保留（A2/A10 与后续验证需要），备份文件也保留
        if ctx.get("cleanup", {}).get("backup"):
            log(f"      备份保留: {ctx['cleanup']['backup']}")

    elif case == "A2":
        # 删除型用例无残留（条目已删）；仅清理 token
        pass

    elif case == "A6":
        # 专用资源全清（QA 用户/Agent/配置/token）；demo 零接触
        qa_token = ctx.get("_qa_token")
        if qa_token:
            token_revoke(qa_token)
        ssh_text(mysql_cmd(f"DELETE FROM ai_agent WHERE id='{QA_AGENT_ID}'"))
        ssh_text(mysql_cmd(f"DELETE FROM ai_device WHERE id='{QA_DEVICE_ID}'"))
        ssh_text(mysql_cmd(f"DELETE FROM ai_model_config WHERE id='{MEM0_NO_KEY_ID}'"))
        ssh_text(mysql_cmd(
            f"DELETE FROM sys_user WHERE id='{QA_USER_ID}' AND username='{QA_USER_NAME}'"))
        log("      QA Agent / mem0 配置 / QA 用户已删除")

    elif case == "A10":
        if ctx.get("verdict") == "SKIP" or ctx.get("cleanup", {}).get("mysql_restored"):
            return
        ssh_text(mysql_cmd(
            f"UPDATE ai_agent SET mem_model_id='{MEM_HOLO_ID}' WHERE id='{AGENT_ID}'"))
        ctx["cleanup"]["mysql_restored"] = True
        log("      demo 引擎恢复为 mem_holographic（A1/A2 数据仍在）")


# ---- 主流程 ----
def main():
    ap = argparse.ArgumentParser(description="记忆功能 E2E 用户旅程（部署后执行）")
    ap.add_argument("--case", choices=["A1", "A2", "A6", "A10", "all"], default="all")
    ap.add_argument("--skip-deployed", action="store_true",
                    help="部署检查失败时判 SKIP（默认 FAIL）")
    ap.add_argument("--no-cleanup", action="store_true", help="不执行清理（排查现场用）")
    ap.add_argument("--agent-id", default=AGENT_ID)
    ap.add_argument("--device-id", default=DEVICE_ID)
    args = ap.parse_args()

    _REPORT["started"] = time.strftime("%Y-%m-%d %H:%M:%S")
    order = ["A1", "A2", "A6", "A10"] if args.case == "all" else [args.case]
    if args.case == "all":
        log("提示：all 依赖顺序 A1→A2→A10（A2 用 A1 的条目；A10 前置 A1 数据）；A6 独立。")

    results = {}
    for case in order:
        try:
            fn = {"A1": run_a1, "A2": run_a2, "A6": run_a6, "A10": run_a10}[case]
            ctx = fn(args)
            results[case] = ctx
            emit(ctx["verdict"], case, ctx["checks"], ctx["notes"], ctx.get("details"))
            log(f"[{case}] verdict={ctx['verdict']} checks={ctx['checks']}")
            if not args.no_cleanup:
                do_cleanup(case, ctx)
        except Exception as e:
            import traceback
            traceback.print_exc()
            emit("FAIL", case, {}, [f"EXCEPTION: {type(e).__name__}: {e}"])
            log(f"[{case}] EXCEPTION {e}")

    _REPORT["ended"] = time.strftime("%Y-%m-%d %H:%M:%S")
    verdicts = [c["verdict"] for c in _REPORT["cases"]]
    if any(v == "FAIL" for v in verdicts):
        exit_code = 1
    else:
        exit_code = 0

    report_path = os.path.join(SCRIPT_DIR, "reports",
                               f"e2e_memory_{time.strftime('%Y%m%d_%H%M%S')}.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(_REPORT, f, ensure_ascii=False, indent=2)
    log(f"[report] {report_path}")
    log(f"[GATE] {verdicts} → exit {exit_code}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
