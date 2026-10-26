#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""共享授权 API 冒烟（token 版：超管 demo 的冒烟 token）
覆盖：shares 读/存/幂等/清空 + shareCount 角标 + 普通用户可见性（SQL 层验证）
"""
import json
import subprocess
import urllib.request

BASE = "http://127.0.0.1:8002/yuhe"
TOKEN = "smoketest00000000000000000000a1"
MYSQL = ["mysql", "-udebian-sys-maint", "-pqbZhrYBdP8DJDeet", "xiaozhi_esp32_server"]


def http(method, path, body=None, token=TOKEN):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def sql(q):
    return subprocess.run(MYSQL + ["-e", q], capture_output=True, text=True).stdout


def main():
    # 1. 超管 agent/list：应含全部智能体 + shareCount 字段
    lst = http("GET", "/agent/list").get("data") or []
    print(f"[1] superadmin /agent/list: {len(lst)} 个智能体（超管看全部）")
    assert len(lst) >= 1
    a0 = lst[0]
    aid = a0["id"]
    print(f"    首个: {a0.get('agentName')} shareCount={a0.get('shareCount')} deviceCount={a0.get('deviceCount')}")

    # 2. 找一个活跃普通用户做可见性验证（未删除、非超管）
    row = sql("SELECT id FROM sys_user WHERE deleted=0 AND super_admin=0 AND status=1 LIMIT 1").strip()
    lines = [l for l in row.splitlines() if l.strip() and l.strip() != "id"]
    uid = int(lines[0].strip()) if lines else None
    print(f"[2] 普通用户样本: id={uid}")

    # 3. 读共享配置（初始状态）
    cur = http("GET", f"/agent/{aid}/shares").get("data")
    print(f"[3] GET shares 初始: {json.dumps(cur, ensure_ascii=False)}")

    # 4. 保存：角色 3（user 普通用户组）+ 用户直享（若找到样本用户）
    shares = [{"targetType": "role", "targetId": 3}]
    if uid:
        shares.append({"targetType": "user", "targetId": uid})
    save = http("PUT", f"/agent/{aid}/shares", {"shares": shares})
    print(f"[4] PUT shares({len(shares)}条): code={save.get('code')}")

    # 5. 回读
    cur2 = http("GET", f"/agent/{aid}/shares").get("data")
    print(f"[5] 回读: {json.dumps(cur2, ensure_ascii=False)}")
    assert len(cur2) == len(shares), "save/echo mismatch"

    # 6. shareCount 角标
    lst2 = http("GET", "/agent/list").get("data") or []
    a2 = next((x for x in lst2 if x["id"] == aid), {})
    print(f"[6] shareCount after save = {a2.get('shareCount')}")
    assert a2.get("shareCount") == len(shares)

    # 7. 重复保存幂等
    http("PUT", f"/agent/{aid}/shares", {"shares": shares})
    cur3 = http("GET", f"/agent/{aid}/shares").get("data")
    print(f"[7] 重复保存后仍 {len(cur3)} 条（幂等 OK）")
    assert len(cur3) == len(shares)

    # 8. SQL 层验证共享行
    rows = sql(f"SELECT target_type, target_id FROM ai_agent_share WHERE agent_id='{aid}'").strip()
    lines = [l for l in rows.splitlines() if l.strip() and not l.startswith("target_type")]
    print(f"[8] DB 行: {lines}")
    assert len(lines) == len(shares), "db rows mismatch"

    # 9. 清空恢复
    http("PUT", f"/agent/{aid}/shares", {"shares": []})
    cur4 = http("GET", f"/agent/{aid}/shares").get("data")
    print(f"[9] 清空后: {json.dumps(cur4, ensure_ascii=False)}")
    assert not cur4
    cnt = sql(f"SELECT COUNT(*) FROM ai_agent_share WHERE agent_id='{aid}'").strip().splitlines()[-1]
    print(f"    DB 计数: {cnt}")
    assert cnt == "0"

    # 10. 普通用户可见性验证：test1 无共享时看不到别人的智能体 → 加共享后 countSharedToUser 命中
    if uid:
        cnt_sql = (f"SELECT COUNT(1) FROM ai_agent_share WHERE agent_id='{aid}'"
                   f" AND ((target_type='user' AND target_id={uid})"
                   f" OR (target_type='role' AND target_id IN"
                   f" (SELECT role_id FROM sys_user_role WHERE user_id={uid})))")
        # 先清空状态：不可见
        c0 = sql(cnt_sql).strip().splitlines()[-1]
        # 加用户直享
        http("PUT", f"/agent/{aid}/shares", {"shares": [{"targetType": "user", "targetId": uid}]})
        c1 = sql(cnt_sql).strip().splitlines()[-1]
        print(f"[10] test1 共享命中 SQL: 共享前={c0} 共享后={c1}")
        assert c0 == "0" and c1 == "1"
        # 清理
        http("PUT", f"/agent/{aid}/shares", {"shares": []})

    print("SMOKE ALL PASS")


if __name__ == "__main__":
    main()
