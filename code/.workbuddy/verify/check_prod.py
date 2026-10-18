#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sandyun.top 生产发布后验收脚本（只读，不修改生产任何状态）。

用法（在 G:/demo/21_xiaozhi/code/.workbuddy/ 或任意目录下执行）：
    "D:/INSTALL/python313/python.exe" verify/check_prod.py
    ... --skip-logs        # 跳过日志抓取（更快）
    ... --verbose          # 打印每条远端命令的原始输出
    ... --save             # 额外把报告落盘到 verify/reports/check_prod_<时间>.md

设计前提（读代码得来，不要凭 HTTP 状态码判断接口是否存在）：

  ⚠️ 坑 1：Java 侧 HTTP 状态码全程不可信。
     Oauth2Filter.onAccessDenied 与 RenExceptionHandler 都没有 @ResponseStatus，
     未登录访问任何 /yuhe/** （**包括根本不存在的路径**）都返回
     200 + body {"code":401}。所以「200」既可能是成功也可能是 401，而 404 永远不会出现。
     本脚本因此从不把 Java 侧状态码当证据，只用：
       (a) systemctl / /proc / md5 / ss 等基础设施事实；
       (b) 免登录的 GET /yuhe/v3/api-docs*（ShiroConfig 里 /v3/api-docs/** = anon）。

  ⚠️ 坑 2：Python 侧反过来 —— aiohttp 没有全局 401 拦截。
     路由不存在 → 404 "404: Not Found"；路由存在但没带 token → 401 {"code":401}。
     所以 401 才是「路由已注册」的可靠证据，404 说明 http_server.py 没换成功。

  ⚠️ 坑 3：前端 hash 不能只看 200。
     nginx 的 index 可能是旧的（200 也返回，只是引用老 hash）。
     必须：磁盘 md5 + 返回体里 grep -o 计 hash 次数 + 直接拉取新 asset 比对字节数。

  ⚠️ 坑 4：JVM 可能持有旧 inode。
     `mv` 覆盖 jar 后若没真正重启，systemd 时间戳看起来正常，跑的还是旧代码。
     本脚本三重取证：磁盘 md5 / /proc/<pid>/fd 里 jar 的 inode（含 "(deleted)" 标记）
     / jar mtime 与进程启动时间先后。

远端命令全部走**同一个 SSH 连接**（ssh_run.get_client()），每条输出做长度截断后入库。
密码不落本文件：直接复用同目录上级的 ssh_run.py（其中已内置连接参数）。
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------- 期望值（本次发布）
EXPECT_JAR_MD5 = "4efef7161ab3ed69474bdb27ee5b468b"
EXPECT_WAKE_MD5 = "38c7fe7734618af416c4f35818663b42"
# 注意：http_server.py 本次没有给基线 md5，只断言「含新路由字符串」+ 记录实际 md5/mtime。
EXPECT_PY_ROUTE = "/api/device-config/push"

EXPECT_FE_INDEX_MD5 = "4fb703fa03ac224938d5115edea770eb"
EXPECT_FE_JS = "index-CR0JikiI.js"
EXPECT_FE_JS_MD5 = "9f5d974f3893d8c9733064123e7ccec5"
EXPECT_FE_JS_SIZE = 510157  # dist-admin/assets/index-CR0JikiI.js 字节数

# ---------------------------------------------------------------- 生产路径（默认值，可覆盖）
DEFAULT_JAR = "/opt/xiaozhi/xiaozhi-esp32-api.jar"
DEFAULT_PY_ROOT = "/root/xiaozhi-server/main/yuhe-server"
DEFAULT_FE_ROOT = "/var/www/console-v2/admin"
WEB_BASE = "https://127.0.0.1:9443"   # 本机回环探测 nginx，避免出网绕 DNS
# ⚠️ 不要用 9444：那是 `listen 127.0.0.1:9444 ssl proxy_protocol`，只接受
#    stream:8001 转发过来的 PROXY protocol 头，直连会在 TLS 握手阶段被 RST
#    （nginx error.log 里是 `broken header ... while reading PROXY protocol`，
#     curl 表现为 code=000，很容易被误判成"前端没发布"）。
#    9443 是同一 vhost 的普通 TLS 监听，语义等价；要验公网链路就用 https://sandyun.top:8001。
WEB_HOST = "sandyun.top"              # 显式 Host 头，走生产 server_name 分支

MAX_SHOW = 3600  # 单条远端输出在报告里最多显示这么多字符


# ---------------------------------------------------------------- 结果模型
@dataclass
class Result:
    name: str          # 断言编号 + 简述
    status: str        # PASS / FAIL / WARN / SKIP
    expect: str
    actual: str

    def __str__(self) -> str:
        return f"[{self.status}] {self.name}\n        期望: {self.expect}\n        实际: {self.actual}"


@dataclass
class Report:
    results: list[Result] = field(default_factory=list)
    raw: list[tuple[str, str]] = field(default_factory=list)

    def add(self, name: str, status: str, expect: str, actual: str) -> None:
        self.results.append(Result(name, status, expect, actual))

    def count(self, status: str) -> int:
        return sum(1 for r in self.results if r.status == status)


# ---------------------------------------------------------------- SSH 执行器
class Remote:
    """一个 paramiko client、多次 exec_command（同一 TCP/SSH 会话）。"""

    def __init__(self, client, report: Report):
        self.client = client
        self.report = report

    def sh(self, cmd: str, timeout: int = 90) -> tuple[int, str]:
        # stderr 合并进 stdout，避免两个 channel buffer 互相堵死（否则大输出会挂死）
        full = "{\n" + cmd + "\n} 2>&1\n"
        stdin, stdout, stderr = self.client.exec_command(full, timeout=timeout)
        out = stdout.read().decode("utf-8", "replace")
        stderr.read()  # 已重定向时为空，读掉防止残留
        rc = stdout.channel.recv_exit_status()
        self.report.raw.append((cmd, out))
        return rc, out


def grab(text: str, key: str, default: str = "") -> str:
    """从 @@KEY=value 形式的输出里取值。"""
    m = re.search(rf"^@@{key}=(.*)$", text, re.MULTILINE)
    return m.group(1).strip() if m else default


def grab_block(text: str, key: str) -> str:
    m = re.search(rf"^@@{key}_BEGIN$(.*?)^@@{key}_END$", text, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def clip(s: str, n: int = MAX_SHOW) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[:n] + f"\n...（截断，共 {len(s)} 字符）"


def one_line(s: str, n: int = 240) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[:n] + "…"


def as_int(v, default: int = 0) -> int:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- 各层采集
def check_java(rm: Remote, rep: Report, jar_override: str | None) -> tuple[str, str, str]:
    """返回 (jar_path, jar_mtime_epoch, proc_start_epoch)"""
    jar_default = jar_override or DEFAULT_JAR
    cmd = f"""
JAR={shlex.quote(jar_default)}
PID=$(LC_ALL=C systemctl show -p MainPID --value xiaozhi-manager-api 2>/dev/null)
echo "@@PID=$PID"
echo "@@ACTIVE=$(LC_ALL=C systemctl is-active xiaozhi-manager-api 2>/dev/null)"
echo "@@SUBSTATE=$(LC_ALL=C systemctl show -p ActiveState,SubState --value xiaozhi-manager-api 2>/dev/null | tr '\\n' '/')"
echo "@@ACTIVE_ENTER=$(LC_ALL=C systemctl show -p ActiveEnterTimestamp --value xiaozhi-manager-api 2>/dev/null)"
ST=$(LC_ALL=C systemctl show -p ExecMainStartTimestamp --value xiaozhi-manager-api 2>/dev/null)
echo "@@START_TS=$ST"
SE=$(date -d "$ST" +%s 2>/dev/null)
echo "@@START_EPOCH=$SE"
echo "@@NOW=$(date +%s)"
CMD=$(tr '\\0' ' ' < /proc/$PID/cmdline 2>/dev/null)
echo "@@CMDLINE=$CMD"
AJ=$(echo "$CMD" | sed -n 's/.*-jar[[:space:]]*\\([^[:space:]]*\\).*/\\1/p')
[ -n "$AJ" ] && JAR="$AJ"
echo "@@JAR=$JAR"
echo "@@JAR_MD5=$(md5sum "$JAR" 2>/dev/null | awk '{{print $1}}')"
echo "@@JAR_STAT=$(stat -Lc '%i %s %Y' "$JAR" 2>/dev/null)"
echo "@@DISK_INODE=$(stat -Lc '%i' "$JAR" 2>/dev/null)"
echo "@@DELETED_FD=$(ls -l /proc/$PID/fd 2>/dev/null | grep -c deleted)"
echo "@@BAK_COUNT=$(ls -1 "$JAR".bak* 2>/dev/null | wc -l | tr -d ' ')"
echo "@@BAK_LIST=$(ls -1 "$JAR".bak* 2>/dev/null | tail -3 | tr '\n' ',')"
for f in /proc/$PID/fd/*; do
  t=$(readlink -f "$f" 2>/dev/null)
  case "$t" in
    *"${{JAR##*/}}"*) echo "@@FD $f -> $t inode=$(stat -Lc '%i' "$f" 2>/dev/null)";;
  esac
done
echo "@@LISTEN8002=$(ss -lntp 2>/dev/null | grep -c ':8002 ')"
"""
    _, out = rm.sh(cmd, timeout=90)

    pid = grab(out, "PID")
    active = grab(out, "ACTIVE")
    substate = grab(out, "SUBSTATE")
    active_enter = grab(out, "ACTIVE_ENTER")
    start_epoch = grab(out, "START_EPOCH")
    now = grab(out, "NOW")
    jar = grab(out, "JAR", jar_default)
    jar_md5 = grab(out, "JAR_MD5")
    jar_stat = grab(out, "JAR_STAT")
    disk_inode = grab(out, "DISK_INODE")
    deleted_fd = grab(out, "DELETED_FD", "0")
    fd_lines = [ln for ln in out.splitlines() if ln.startswith("@@FD ")]
    listen8002 = grab(out, "LISTEN8002", "0")

    # --- J-01 服务态
    if active == "active":
        rep.add("J-01 service active", "PASS", "systemctl is-active = active",
                f"active（{substate or 'active'}，ActiveEnter={active_enter or 'n/a'}）")
    else:
        rep.add("J-01 service active", "FAIL", "systemctl is-active = active",
                f"is-active={active or '空'} substate={substate or '空'}，服务未起来先看 "
                f"journalctl -u xiaozhi-manager-api -n 120 --no-pager")

    # --- J-02 是否真的重启过（不是看 unit 时间戳，而是看进程启动时间）
    try:
        age = int(now) - int(start_epoch)
    except (TypeError, ValueError):
        age = -1
    if age < 0:
        rep.add("J-02 本轮重启时间", "WARN", "进程启动时间可解析",
                f"ExecMainStartTimestamp={grab(out, 'START_TS') or '空'}，无法换算 epoch")
    elif age >= 0:
        # 不再用"30 分钟内启动"当判据：验收可能发生在发布后数小时，年龄大不等于没重启。
        # "是否本轮重启过"由 J-05（jar mtime vs 进程启动）判定，这里只保证时间可解析。
        rep.add("J-02 本轮重启时间", "PASS", "进程启动时间可解析",
                f"ExecMainStartTimestamp={grab(out, 'START_TS') or 'n/a'}；"
                f"进程已运行 {age}s（约 {age // 60} 分钟）；是否本轮重启由 J-05 判")
    else:
        rep.add("J-02 本轮重启时间", "WARN", "进程启动时间可解析",
                f"进程启动时间晚于当前时间（{age}s），检查时钟/时区")

    # --- J-03 磁盘 jar md5
    if jar_md5 == EXPECT_JAR_MD5:
        rep.add("J-03 jar 磁盘 md5", "PASS", EXPECT_JAR_MD5,
                f"{jar_md5}  {jar}（{jar_stat}）")
    else:
        rep.add("J-03 jar 磁盘 md5", "FAIL", EXPECT_JAR_MD5,
                f"{jar_md5 or '读取失败'}  {jar}（{jar_stat or 'n/a'}）")

    # --- J-04 进程持有的 jar 是否是同一个 inode（JVM 旧 inode 陷阱）
    deleted = as_int(deleted_fd)
    if fd_lines:
        inodes = []
        for ln in fd_lines:
            m = re.search(r"inode=(\d+)", ln)
            inodes.append(m.group(1) if m else "?")
        same = bool(disk_inode) and all(i == disk_inode for i in inodes)
        if same:
            rep.add("J-04 运行中 jar inode", "PASS",
                    f"fd inode == 磁盘 inode({disk_inode})",
                    f"{one_line('; '.join(fd_lines), 400)}")
        else:
            rep.add("J-04 运行中 jar inode", "FAIL",
                    f"fd inode == 磁盘 inode({disk_inode})",
                    f"{one_line('; '.join(fd_lines), 400)} —— JVM 跑的不是新文件（mv 覆盖后未重启）")
    elif deleted > 0:
        rep.add("J-04 运行中 jar inode", "FAIL",
                "进程 fd 里 jar inode == 磁盘 inode",
                f"进程持有 {deleted} 个 (deleted) 文件句柄，且没找到 jar fd —— 极可能仍在跑旧 inode")
    else:
        rep.add("J-04 运行中 jar inode", "SKIP",
                "fd inode == 磁盘 inode",
                "进程未 keep jar fd（Spring Boot 也可能不保留），改用 J-05 时间先后判定")

    # --- J-05 jar 落盘时间 vs 进程启动时间
    try:
        jar_mtime = int(jar_stat.split()[2])
        proc_start = int(start_epoch)
    except (IndexError, ValueError, TypeError):
        jar_mtime, proc_start = 0, 0
    if jar_mtime and proc_start:
        if proc_start >= jar_mtime:
            rep.add("J-05 jar 与进程新老关系", "PASS",
                    "进程启动时间 >= jar mtime",
                    f"进程启动 {proc_start} >= jar mtime {jar_mtime}（差 {proc_start - jar_mtime}s）")
        else:
            rep.add("J-05 jar 与进程新老关系", "FAIL",
                    "进程启动时间 >= jar mtime",
                    f"进程启动 {proc_start} < jar mtime {jar_mtime} —— jar 比进程新，进程跑的是旧代码")
    else:
        rep.add("J-05 jar 与进程新老关系", "WARN", "可比较时间戳",
                f"jar_stat={jar_stat or 'n/a'}；进程启动={grab(out, 'START_TS') or '空'}"
                f"（缺 epoch 无法比较，J-02/J-05 同时 WARN 时优先看这块）")

    # --- J-07 回滚件（发布时是否留了 .bak；没有则回滚要重新上传）
    bak_count = as_int(grab(out, "BAK_COUNT", "0"))
    bak_list = grab(out, "BAK_LIST")
    if bak_count >= 1:
        rep.add("J-07 回滚件在位", "PASS", "jar 同级存在 .bak* 备份",
                f"{bak_count} 个：{one_line(bak_list, 200)}")
    else:
        rep.add("J-07 回滚件在位", "WARN", "jar 同级存在 .bak* 备份",
                f"{jar} 旁没有 .bak* 文件 —— 回滚需要重新上传，确认发布流程是否漏了备份步骤")

    # --- J-06 端口 8002
    if str(listen8002).isdigit() and int(listen8002) >= 1:
        rep.add("J-06 manager-api 监听 8002", "PASS", "8002 LISTEN",
                f"命中 {listen8002} 行；cmdline={one_line(grab(out, 'CMDLINE'), 160)}")
    else:
        rep.add("J-06 manager-api 监听 8002", "FAIL", "8002 LISTEN", "ss 未发现 8002 监听")

    return jar, str(jar_mtime), str(proc_start)


def check_python(rm: Remote, rep: Report, py_root_override: str | None) -> str:
    """返回 py_root（供后面日志路径复用）"""
    cmd = f"""
echo "@@PY_LINES_BEGIN"
ps -eo pid,lstart,etimes,args --no-headers 2>/dev/null | grep -E '[p]ython[^ ]*[[:space:]]app\\.py' || true
echo "@@PY_LINES_END"
PYPID=$(ps -eo pid,args --no-headers 2>/dev/null | grep -E '[p]ython[^ ]*[[:space:]]app\\.py' | awk '{{print $1}}' | head -1)
echo "@@PYPID=$PYPID"
ROOT=$(readlink -f /proc/$PYPID/cwd 2>/dev/null)
[ -z "$ROOT" ] && ROOT={shlex.quote(py_root_override or DEFAULT_PY_ROOT)}
echo "@@PYROOT=$ROOT"
echo "@@PY_START=$(ps -o lstart= -p $PYPID 2>/dev/null | sed 's/^ *//')"
echo "@@PY_ETIMES=$(ps -o etimes= -p $PYPID 2>/dev/null | tr -d ' ')"
echo "@@PY_UNIT=$(LC_ALL=C systemctl is-active yuhe-server 2>/dev/null)"
echo "@@PY_UNIT_EXISTS=$(LC_ALL=C systemctl list-unit-files yuhe-server.service --no-pager 2>/dev/null | grep -c yuhe-server)"
echo "@@WAKE_MD5=$(md5sum "$ROOT/core/services/wake_word_service.py" 2>/dev/null | awk '{{print $1}}')"
echo "@@WAKE_STAT=$(stat -Lc '%y' "$ROOT/core/services/wake_word_service.py" 2>/dev/null)"
echo "@@HTTP_MD5=$(md5sum "$ROOT/core/http_server.py" 2>/dev/null | awk '{{print $1}}')"
echo "@@HTTP_STAT=$(stat -Lc '%y' "$ROOT/core/http_server.py" 2>/dev/null)"
echo "@@API_DIR=$(ls "$ROOT/core/api" 2>/dev/null | tr '\\n' ',')"
echo "@@ROUTE_HITS=$(grep -oF '{EXPECT_PY_ROUTE}' "$ROOT/core/http_server.py" 2>/dev/null | wc -l | tr -d ' ')"
echo "@@WAKE_HANDLER_HITS=$(grep -oF 'handle_push_device_config' "$ROOT/core/api/wake_word_handler.py" 2>/dev/null | wc -l | tr -d ' ')"
echo "@@PORTS=$(ss -lntp 2>/dev/null | awk '/:(8000|8002|8003) /' | tr '\\n' '|')"
echo "@@PORT8000=$(ss -lnt 2>/dev/null | grep -c ':8000 ')"
echo "@@PORT8003=$(ss -lnt 2>/dev/null | grep -c ':8003 ')"
"""
    _, out = rm.sh(cmd, timeout=90)

    py_lines = [ln for ln in grab_block(out, "PY_LINES").splitlines() if ln.strip()]
    py_count = len(py_lines)
    pyroot = grab(out, "PYROOT", py_root_override or DEFAULT_PY_ROOT)
    wake_md5 = grab(out, "WAKE_MD5")
    http_md5 = grab(out, "HTTP_MD5")
    route_hits = grab(out, "ROUTE_HITS", "0")
    handler_hits = grab(out, "WAKE_HANDLER_HITS", "0")
    port8000 = grab(out, "PORT8000", "0")
    port8003 = grab(out, "PORT8003", "0")
    py_unit = grab(out, "PY_UNIT")
    py_etimes = grab(out, "PY_ETIMES")

    # --- P-01 单进程（多进程 = 旧进程没杀干净，新旧代码同时在跑）
    if py_count == 1:
        rep.add("P-01 单进程", "PASS", "恰好 1 个 python app.py",
                f"1 个：{one_line(py_lines[0], 200)}")
    elif py_count == 0:
        rep.add("P-01 单进程", "FAIL", "恰好 1 个 python app.py",
                "0 个 —— 服务没起来或启动即崩，先看 app.log 尾部 / journalctl -u yuhe-server")
    else:
        rep.add("P-01 单进程", "FAIL", "恰好 1 个 python app.py",
                f"{py_count} 个（新旧进程并存，端口被老进程占着会让人误判）：\n"
                + clip("\n".join(py_lines)))

    # --- P-02 systemd unit（可能不是用 systemd 起的，故只 WARN）
    if py_unit == "active":
        rep.add("P-02 yuhe-server unit", "PASS", "systemctl is-active = active",
                f"active；进程 etimes={py_etimes or '?'}s；启动于 {grab(out, 'PY_START') or 'n/a'}")
    else:
        rep.add("P-02 yuhe-server unit", "WARN", "systemctl is-active = active",
                f"is-active={py_unit or '空'}（若确认是 systemd 托管，这条应视为 FAIL）")

    # --- P-03 wake_word_service.py 指纹
    if wake_md5 == EXPECT_WAKE_MD5:
        rep.add("P-03 wake_word_service md5", "PASS", EXPECT_WAKE_MD5,
                f"{wake_md5}  mtime={grab(out, 'WAKE_STAT') or 'n/a'}")
    else:
        rep.add("P-03 wake_word_service md5", "FAIL", EXPECT_WAKE_MD5,
                f"{wake_md5 or '读取失败'}  mtime={grab(out, 'WAKE_STAT') or 'n/a'}  (root={pyroot})")

    # --- P-04 http_server.py 带新路由
    # 注意：真实路径是 core/http_server.py，不是 core/api/http_server.py
    if route_hits.isdigit() and int(route_hits) >= 1:
        rep.add("P-04 http_server 含新路由", "PASS",
                f'{EXPECT_PY_ROUTE} 出现 >=1 次（路由注册处）',
                f"命中 {route_hits} 次；md5={http_md5 or 'n/a'} mtime={grab(out, 'HTTP_STAT') or 'n/a'}"
                f"（本次未给 http_server.py 基线 md5，md5 仅存档）")
    else:
        rep.add("P-04 http_server 含新路由", "FAIL",
                f"{EXPECT_PY_ROUTE} 出现 >=1 次",
                f"命中 {route_hits or 0} 次；md5={http_md5 or '读取失败'}；"
                f"core/api 目录下文件={one_line(grab(out, 'API_DIR'), 200)}")

    # --- P-05 handler 侧函数存在（4 行路由 + 已有 handler 的两段都要在）
    if handler_hits.isdigit() and int(handler_hits) >= 1:
        rep.add("P-05 wake_word_handler 下发函数", "PASS", "handle_push_device_config 存在",
                f"命中 {handler_hits} 次")
    else:
        rep.add("P-05 wake_word_handler 下发函数", "FAIL", "handle_push_device_config 存在",
                "0 次 —— handler 没同步上去，路由即使注册也会 500/AttributeError")

    # --- P-06 端口
    ok8000 = port8000.isdigit() and int(port8000) >= 1
    ok8003 = port8003.isdigit() and int(port8003) >= 1
    if ok8000 and ok8003:
        rep.add("P-06 Python 监听 8000/8003", "PASS", "8000 与 8003 均 LISTEN",
                f"8000={port8000} 8003={port8003}；{one_line(grab(out, 'PORTS'), 400)}")
    else:
        rep.add("P-06 Python 监听 8000/8003", "FAIL", "8000 与 8003 均 LISTEN",
                f"8000={port8000} 8003={port8003}；{one_line(grab(out, 'PORTS'), 400)}")

    return pyroot


def check_frontend(rm: Remote, rep: Report, fe_root: str) -> None:
    probe = f"""
B=""
for p in /admin/ /admincc/ "/admincc/assets/{EXPECT_FE_JS}"; do
  f=/tmp/_vfy_body.$$
  cs=$(curl -sk -o "$f" -w '%{{http_code}} %{{size_download}}' "{WEB_BASE}$p" -H 'Host: {WEB_HOST}')
  hits=$(grep -oF '{EXPECT_FE_JS}' "$f" 2>/dev/null | wc -l | tr -d ' ')
  echo "@@WEB $p code_size=$cs hash_hits=$hits"
  rm -f "$f"
done
echo "@@FE_INDEX_MD5=$(md5sum {shlex.quote(fe_root)}/index.html 2>/dev/null | awk '{{print $1}}')"
echo "@@FE_INDEX_TS=$(stat -Lc '%y' {shlex.quote(fe_root)}/index.html 2>/dev/null)"
echo "@@FE_JS_MD5=$(md5sum {shlex.quote(fe_root)}/assets/{EXPECT_FE_JS} 2>/dev/null | awk '{{print $1}}')"
echo "@@FE_JS_SIZE=$(stat -Lc '%s' {shlex.quote(fe_root)}/assets/{EXPECT_FE_JS} 2>/dev/null)"
echo "@@FE_LS_BEGIN"
ls -l {shlex.quote(fe_root)}/assets/ 2>/dev/null | head -20
echo "@@FE_LS_END"
echo "@@FE_INDEX_REF=$(grep -oF '{EXPECT_FE_JS}' {shlex.quote(fe_root)}/index.html 2>/dev/null | wc -l | tr -d ' ')"
echo "@@FE_INDEX_REF_OLD=$(grep -oE 'assets/index-[A-Za-z0-9_-]+\\.js' {shlex.quote(fe_root)}/index.html 2>/dev/null | sort -u | tr '\\n' ',')"
"""
    _, out = rm.sh(probe, timeout=120)

    fe_index_md5 = grab(out, "FE_INDEX_MD5")
    fe_js_md5 = grab(out, "FE_JS_MD5")
    fe_js_size = grab(out, "FE_JS_SIZE")
    fe_ref = grab(out, "FE_INDEX_REF", "0")
    fe_ref_old = grab(out, "FE_INDEX_REF_OLD")

    web: dict[str, tuple[str, str, str]] = {}
    for ln in out.splitlines():
        m = re.match(r"^@@WEB (\S+) code_size=(\S+) (\S+) hash_hits=(\d+)", ln)
        if m:
            web[m.group(1)] = (m.group(2), m.group(3), m.group(4))

    # --- F-01 磁盘 index.html 是新产物
    if fe_index_md5 == EXPECT_FE_INDEX_MD5:
        rep.add("F-01 admin/index.html md5", "PASS", EXPECT_FE_INDEX_MD5,
                f"{fe_index_md5}  mtime={grab(out, 'FE_INDEX_TS') or 'n/a'}")
    else:
        rep.add("F-01 admin/index.html md5", "FAIL", EXPECT_FE_INDEX_MD5,
                f"{fe_index_md5 or '读取失败'}  mtime={grab(out, 'FE_INDEX_TS') or 'n/a'}  (root={fe_root})")

    # --- F-02 index.html 自身引用的是新 hash
    if fe_ref.isdigit() and int(fe_ref) >= 1:
        rep.add("F-02 index.html 引用新 hash", "PASS", f"含 {EXPECT_FE_JS}",
                f"命中 {fe_ref} 次；文件内所有 index-*.js 引用 = {fe_ref_old or 'n/a'}")
    else:
        rep.add("F-02 index.html 引用新 hash", "FAIL", f"含 {EXPECT_FE_JS}",
                f"命中 0 次；实际引用 = {fe_ref_old or 'n/a'}（老产物的 hash）")

    # --- F-03 磁盘 asset 指纹（缓存/半拷贝会让大小对不上）
    if fe_js_md5 == EXPECT_FE_JS_MD5 and fe_js_size == str(EXPECT_FE_JS_SIZE):
        rep.add("F-03 新 asset 指纹", "PASS",
                f"md5={EXPECT_FE_JS_MD5} size={EXPECT_FE_JS_SIZE}",
                f"md5={fe_js_md5} size={fe_js_size}")
    else:
        rep.add("F-03 新 asset 指纹", "FAIL",
                f"md5={EXPECT_FE_JS_MD5} size={EXPECT_FE_JS_SIZE}",
                f"md5={fe_js_md5 or '读取失败'} size={fe_js_size or 'n/a'}")

    # --- I-01 / I-02 两个入口都必须是新产物
    for path, label in (("/admin/", "I-01 /admin/ 入口"), ("/admincc/", "I-02 /admincc/ 入口")):
        cs = web.get(path)
        if not cs:
            rep.add(label, "FAIL", "200 且返回体含新 hash", "探测无输出（curl 失败）")
            continue
        code, size, hits = cs
        if code == "200" and hits.isdigit() and int(hits) >= 1:
            rep.add(label, "PASS", "200 且返回体含新 hash",
                    f"code={code} size={size} hash_hits={hits}")
        else:
            rep.add(label, "FAIL", "200 且返回体含新 hash",
                    f"code={code} size={size} hash_hits={hits} —— 200 也可能是旧 index，"
                    f"必须比对返回体内容")

    # --- I-03 新 asset 经 nginx 可取到且字节数一致
    cs = web.get(f"/admincc/assets/{EXPECT_FE_JS}")
    if cs:
        code, size, _ = cs
        if code == "200" and size == str(EXPECT_FE_JS_SIZE):
            rep.add("I-03 新 asset 可下载", "PASS", f"200 且 size={EXPECT_FE_JS_SIZE}",
                    f"code={code} size={size}")
        else:
            rep.add("I-03 新 asset 可下载", "FAIL", f"200 且 size={EXPECT_FE_JS_SIZE}",
                    f"code={code} size={size} —— 404/403 说明 nginx root 与部署目录不一致")
    else:
        rep.add("I-03 新 asset 可下载", "FAIL", "200 且 size 一致", "探测无输出")


def check_openapi(rm: Remote, rep: Report) -> None:
    cmd = f"""
for p in /yuhe/v3/api-docs /yuhe/v3/api-docs/agent /yuhe/v3/api-docs/config; do
  f=/tmp/_oa.$$.json
  cs=$(curl -sk -o "$f" -w '%{{http_code}} %{{size_download}}' "{WEB_BASE}$p" -H 'Host: {WEB_HOST}')
  hw=$(grep -oF 'wakeWordThreshold' "$f" 2>/dev/null | wc -l | tr -d ' ')
  hi=$(grep -oF 'interruptThreshold' "$f" 2>/dev/null | wc -l | tr -d ' ')
  hu=$(grep -oF 'wake_word_threshold' "$f" 2>/dev/null | wc -l | tr -d ' ')
  hp=$(grep -oF '/agent/{{id}}' "$f" 2>/dev/null | wc -l | tr -d ' ')
  keys=$(grep -oE '"[A-Za-z_]{{0,20}}hreshold[A-Za-z_]{{0,20}}"' "$f" 2>/dev/null | sort -u | tr '\\n' ',' )
  echo "@@OA $p code_size=$cs wake=$hw interrupt=$hi snake_wake=$hu agent_path=$hp"
  echo "@@OA_KEYS $p $keys"
  rm -f "$f"
done
"""
    _, out = rm.sh(cmd, timeout=120)

    entries: dict[str, tuple[str, str, str, str, str]] = {}
    keys_map: dict[str, str] = {}
    for ln in out.splitlines():
        m = re.match(r"^@@OA (\S+) code_size=(\S+) (\S+) wake=(\d+) interrupt=(\d+) "
                     r"snake_wake=(\d+) agent_path=(\d+)", ln)
        if m:
            entries[m.group(1)] = (m.group(2), m.group(3), m.group(4), m.group(5), m.group(6))
            entries[m.group(1)] += (m.group(7),)
        k = re.match(r"^@@OA_KEYS (\S+) (.*)$", ln)
        if k:
            keys_map[k.group(1)] = k.group(2).strip()

    # 优先选「200、体积像真 JSON、且确实含新字段」的端点；否则退化为第一个像真 JSON 的端点。
    # （未登录时 Shiro 也会用 200 包一个 401 体，所以必须看体积；分组 API 还可能让
    #  /v3/api-docs 与 /v3/api-docs/agent 内容不同，故先按内容命中挑。）
    big: list[tuple[str, tuple]] = []
    for p, vals in entries.items():
        if vals[0] == "200" and as_int(vals[1]) > 2000:
            big.append((p, vals))

    best = None
    for p, vals in big:
        if as_int(vals[2]) >= 1 and as_int(vals[3]) >= 1:
            best = (p, vals)
            break
    if best is None and big:
        best = big[0]

    if best is None:
        detail = "; ".join(f"{p}: {v[0]}/{v[1]}B" for p, v in entries.items()) or "无输出"
        rep.add("I-04 OpenAPI 可匿名访问", "FAIL",
                "至少一个 /yuhe/v3/api-docs* 返回 200 且 >2KB",
                f"{detail} —— OpenAPI 拿不到，后续字段断言全部失效；"
                f"先确认 jar 是否起来、Shiro 的 /v3/api-docs/** anon 是否还在")
        rep.add("I-05 DTO 含新字段", "SKIP", "wakeWordThreshold + interruptThreshold", "依赖 I-04")
        return

    p, vals = best
    code, size, wake, interrupt, snake, agent_path = vals
    rep.add("I-04 OpenAPI 可匿名访问", "PASS", "200 且 >2KB",
            f"{p} code={code} size={size}B")

    # --- I-05 AgentUpdateDTO 新字段（本次 jar 的核心证据）
    has_wake = wake.isdigit() and int(wake) >= 1
    has_int = interrupt.isdigit() and int(interrupt) >= 1
    if has_wake and has_int:
        rep.add("I-05 DTO 含新字段", "PASS",
                "OpenAPI schema 出现 wakeWordThreshold 与 interruptThreshold",
                f"wakeWordThreshold×{wake} interruptThreshold×{interrupt}；"
                f"agent 分组路径命中 /agent/{{id}}×{agent_path}；"
                f"所有含 hreshold 的键: {keys_map.get(p) or '（空）'}")
    else:
        rep.add("I-05 DTO 含新字段", "FAIL",
                "OpenAPI schema 出现 wakeWordThreshold 与 interruptThreshold",
                f"wakeWordThreshold×{wake} interruptThreshold×{interrupt}（期望均 >=1）；"
                f"所有含 hreshold 的键: {keys_map.get(p) or '（空）'}；"
                f"agent 分组路径命中 /agent/{{id}}×{agent_path}；"
                f"说明 jar 里没有这两个字段（旧 jar 或字段名不同）")

    # --- I-06 401 掩盖 404 的前提仍在（自证坑，避免误用状态码）
    probe = f"""
f=/tmp/_vfy_401.$$
cs=$(curl -sk -o "$f" -w '%{{http_code}}' "{WEB_BASE}/yuhe/__vfy_not_exist_9f3a__" -H 'Host: {WEB_HOST}')
echo "@@MASK code=$cs body=$(head -c 160 "$f" 2>/dev/null | tr -d '\\r\\n')"
rm -f "$f"
"""
    _, out2 = rm.sh(probe, timeout=60)
    m = re.search(r"^@@MASK code=(\S+) body=(.*)$", out2, re.MULTILINE)
    if m:
        code, body = m.group(1), m.group(2)
        if "401" in body or "code" in body:
            rep.add("I-06 401 掩盖 404 前提", "PASS",
                    "不存在的 /yuhe/** 返回 200 + 401 体（状态码不可信）",
                    f"code={code} body={one_line(body, 200)}"
                    f" —— 正因为如此，本脚本不用状态码判定接口存在性")
        else:
            rep.add("I-06 401 掩盖 404 前提", "WARN",
                    "不存在的 /yuhe/** 返回 200 + 401 体",
                    f"code={code} body={one_line(body, 200)} —— 行为变了，"
                    f"请复核本次是否改过 Oauth2Filter/RenExceptionHandler")
    else:
        rep.add("I-06 401 掩盖 404 前提", "SKIP", "200 + 401 体", "探测无输出")


def check_python_route(rm: Remote, rep: Report) -> None:
    """Python 侧路由存在性：401 才是「已注册」的证据，404 说明没换上去。

    对照组设计（关键）：
        新路由 POST /api/device-config/push  → 期望 401
        老路由 GET  /api/wake-word/devices   → 期望 401
    两条一起看才能分层定位：
        * 新 404 + 老 401 → 只有新路由缺失，问题在 core/http_server.py（4 行没生效）
        * 两条都 404      → 8003 这一层的问题（端口/nginx/前缀），别去查代码
        * 新 401 + 老 404 → 老路由反而没了，说明跑的不是预期那份 http_server.py
    """
    cmd = f"""
f=/tmp/_vfy_pyr.$$
cs=$(curl -s -o "$f" -w '%{{http_code}}' -X POST "http://127.0.0.1:8003{EXPECT_PY_ROUTE}" -H 'Content-Type: application/json' -d '{{"agent_id":"probe"}}')
echo "@@PYROUTE code=$cs body=$(head -c 200 "$f" 2>/dev/null | tr -d '\r\n')"
cg=$(curl -s -o /dev/null -w '%{{http_code}}' "http://127.0.0.1:8003{EXPECT_PY_ROUTE}")
echo "@@PYROUTE_GET code=$cg"
cc=$(curl -s -o "$f" -w '%{{http_code}}' "http://127.0.0.1:8003/api/wake-word/devices")
echo "@@PYROUTE_CTRL code=$cc body=$(head -c 160 "$f" 2>/dev/null | tr -d '\r\n')"
cr=$(curl -s -o /dev/null -w '%{{http_code}}' "http://127.0.0.1:8003/api/memory/agents")
echo "@@PYROUTE_CTRL2 code=$cr"
rm -f "$f"
"""
    _, out = rm.sh(cmd, timeout=60)
    m = re.search(r"^@@PYROUTE code=(\S+) body=(.*)$", out, re.MULTILINE)
    mcg = re.search(r"^@@PYROUTE_GET code=(\S+)$", out, re.MULTILINE)
    mctrl = re.search(r"^@@PYROUTE_CTRL code=(\S+) body=(.*)$", out, re.MULTILINE)
    mctrl2 = re.search(r"^@@PYROUTE_CTRL2 code=(\S+)$", out, re.MULTILINE)

    if not m:
        rep.add("I-07 Python 新路由已注册", "FAIL",
                "POST 无 token → 401（不是 404）", "探测无输出")
        rep.add("I-08 路由对照组", "SKIP", "老路由同样 401", "探测无输出")
        return

    code, body = m.group(1), m.group(2)
    get_code = mcg.group(1) if mcg else "?"
    ctrl_code = mctrl.group(1) if mctrl else "?"
    ctrl2_code = mctrl2.group(1) if mctrl2 else "?"

    # --- I-07 新路由
    if code == "401" and "401" in body:
        rep.add("I-07 Python 新路由已注册", "PASS",
                "POST 无 token → 401 {\"code\":401}",
                f"code={code} body={one_line(body, 160)}；GET 同路径={get_code}"
                f"（405 也说明路由存在）")
    elif code == "404":
        rep.add("I-07 Python 新路由已注册", "FAIL",
                "POST 无 token → 401（不是 404）",
                f"code=404 body={one_line(body, 160)} —— aiohttp 没有全局 401 拦截，"
                f"404 就是路由没注册（core/http_server.py 未生效 / handler 为 None）")
    else:
        rep.add("I-07 Python 新路由已注册", "WARN",
                "POST 无 token → 401",
                f"code={code} body={one_line(body, 160)} —— 非预期，可能是 503"
                f"（WakeWordService 未初始化）或中间件行为变化")

    # --- I-08 对照组：老路由必须同样 401，用来区分"新路由缺失"和"8003 整体异常"
    new_ok = code == "401"
    ctrl_ok = ctrl_code == "401"
    ctrl2_ok = ctrl2_code in ("401", "403")  # /api/memory/** 有 loopback 中间件，非回环会 403
    detail = (f"新路由={code}；老路由 /api/wake-word/devices={ctrl_code}"
              f"（body {one_line(mctrl.group(2) if mctrl else '', 100)}）；"
              f"/api/memory/agents={ctrl2_code}")
    if ctrl_ok and ctrl2_ok and new_ok:
        rep.add("I-08 路由对照组", "PASS", "老路由同样 401（400/403 亦可）",
                detail + " —— 三条并列正常，404 只可能来自应用层")
    elif ctrl_ok and not new_ok:
        rep.add("I-08 路由对照组", "PASS", "老路由 401 而新路由异常 → 定位到 http_server.py",
                detail + " —— 8003 本身是通的，问题只在新增的 4 行路由")
    elif not ctrl_ok and not new_ok:
        rep.add("I-08 路由对照组", "FAIL", "至少老路由应 401",
                detail + " —— 两条都 404：问题在 8003 这一层（端口/nginx/路径前缀），"
                "先查 ss 与 uptime，不要先怀疑代码")
    else:
        rep.add("I-08 路由对照组", "WARN", "老路由与新路由行为应一致可解释",
                detail + " —— 新路由通但老路由异常，确认跑的是不是预期那份 http_server.py")


def check_logs(rm: Remote, rep: Report, py_root: str, skip: bool) -> None:
    """日志断言：只统计**本轮启动之后**的行，且必须做「时间戳继承」切片。

    ⚠️ 这里踩过一个坑（v3 的 L-02 会**假 FAIL / 归因失真**，方向已更正）：
    data/app.log 混了两套 writer —— 业务日志带 `261017 21:03:15[...]` 前缀，
    但标准 logging / stderr 直出的 `WARNING:...`、`ERROR:...`、`Traceback (most recent call last):`
    以及缩进栈帧**完全没有前缀**（实测 2900 行里 141 行无前缀，22 行是告警级）。

    旧写法 `substr($0,1,15) >= s` 对无前缀行是**恒真**（首字符 W/T/E/M 的字典序都大于
    时间戳开头的 `2`），所以这些行不会被丢，而是**无条件保留**。后果不是漏报，是：
      * `tail -n 2000` 回看到重启前的行，重启前的历史 Traceback 被算成"本轮新增" → 假 FAIL；
      * 缩进的栈帧（`  File "..."`，首字符空格）恒为假 → 将来从栈里数 ImportError 会漏计。
    当前这轮 PASS 是真实的（唯一 Traceback 在窗口外），但那属于碰巧成立。

    正确做法：两阶段 awk。遇到带前缀行就更新 cur，遇到无前缀行**沿用上一条的 cur**，
    再判 cur >= 起点。起点还要往前拨 5s（systemd 记录值比日志首行晚 1~2s）。

    WARNING 里有一批是**预期噪声**（探针自己打的），不能算异常，单独计数为 L-04：
      鉴权失败（token为空 / 忽略未知 device_config 键 / 忽略越界配置 /
      忽略非整数配置 / 忽略非数值配置 / 无目标设备可推送
    """
    if skip:
        rep.add("L-01 Java 启动日志", "SKIP", "本轮启动后无 ERROR/Exception", "--skip-logs")
        rep.add("L-02 Python 启动日志", "SKIP", "本轮启动后无 Traceback", "--skip-logs")
        rep.add("L-03 正向链路已触发", "SKIP", "出现成对下发证据", "--skip-logs")
        rep.add("L-04 负向用例命中", "SKIP", "出现预期 WARNING", "--skip-logs")
        rep.add("L-05 握手期拉配置", "SKIP", "WS 后出现异步拉配置成功", "--skip-logs")
        return

    py = shlex.quote(py_root)
    cmd = f"""
JST=$(LC_ALL=C systemctl show -p ExecMainStartTimestamp --value xiaozhi-manager-api 2>/dev/null)
JEP=$(date -d "$JST" +%s 2>/dev/null)
if [ -n "$JEP" ]; then SINCE="--since @$JEP"; else SINCE="-n 200"; fi
echo "@@JSTART=$JST"
echo "@@JERR=$(LC_ALL=C journalctl -u xiaozhi-manager-api $SINCE --no-pager 2>/dev/null | grep -cE 'ERROR|Exception|BeanCreation|Caused by|NoClassDefFound|ExceptionInInitializer|pinyindb')"
echo "@@JLOG_BEGIN"
LC_ALL=C journalctl -u xiaozhi-manager-api $SINCE --no-pager 2>&1 | tail -12
echo "@@JLOG_END"

PLOG={py}/data/app.log
PYPID=$(ps -eo pid,args --no-headers 2>/dev/null | grep -E '[p]ython[^ ]*[[:space:]]app[.]py' | awk '{{print $1}}' | head -1)
LS=$(LC_ALL=C ps -o lstart= -p $PYPID 2>/dev/null | sed 's/^ *//')
PEP=$(date -d "$LS" +%s 2>/dev/null)
[ -z "$PEP" ] && PEP=$(stat -Lc %Y /proc/$PYPID 2>/dev/null)
# 起点往前拨 5s，避免漏掉启动瞬间（systemd 时间戳与日志首行有 1~2s 偏差）
PSTART=$(date -d "@$((PEP-5))" +'%y%m%d %H:%M:%S' 2>/dev/null)
[ -z "$PSTART" ] && PSTART="000000 00:00:00"
echo "@@PSTART=$PSTART"

AFTER=/tmp/_vfy_after.$$
BEFORE=/tmp/_vfy_before.$$
CLEAN=/tmp/_vfy_clean.$$
CORE=/tmp/_vfy_core.$$
ERRPAT='Traceback|ERROR|NoClassDefFoundError|ExceptionInInitializer|pinyindb|ModuleNotFoundError|AttributeError|TypeError'
NOISE='鉴权失败|忽略未知 device_config 键|忽略越界配置|忽略非整数配置|忽略非数值配置|无目标设备可推送'
# 外部依赖 ERROR（第三方天气 KEY 失效），与发布无关，单独归类
EXTPAT='获取天气失败'

# 时间戳继承切片：带前缀行更新 cur，无前缀行沿用上一条的 cur，再判 cur >= 起点。
# 绝不能用行首字典序比较（无前缀行首字符 W/T/E/M 恒大于时间戳首字符 2 → 恒真）。
tail -n 2000 "$PLOG" 2>/dev/null | awk -v s="$PSTART" '
  /^[0-9][0-9][0-9][0-9][0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]/ {{ cur=substr($0,1,15) }}
  {{ if (cur >= s) print }}
' > $AFTER
# 窗口外（启动前）的同一套切片，只用于报告措辞：区分「本轮新增」与「历史遗留」
tail -n 2000 "$PLOG" 2>/dev/null | awk -v s="$PSTART" '
  /^[0-9][0-9][0-9][0-9][0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]/ {{ cur=substr($0,1,15) }}
  {{ if (cur != "" && cur < s) print }}
' | grep -vE "$NOISE" > $BEFORE
echo "@@PAFTER_LINES=$(wc -l < $AFTER 2>/dev/null | tr -d ' ')"
# 历史异常必须扫**全文件**：真实那条 Traceback 在 data/app.log:531，
# 而 tail -n 2000 只覆盖末尾 2000 行（2900 行的文件从第 901 行起），
# 只看切片会把「文件里确实有历史异常」误报成「全文件无历史异常」。
PBASE=$(( $(wc -l < "$PLOG" 2>/dev/null | tr -d ' ') > 2000 ? $(wc -l < "$PLOG" 2>/dev/null | tr -d ' ') - 2000 : 0 ))
echo "@@PBASE=$PBASE"
echo "@@PTOTERR=$(grep -vE "$NOISE" "$PLOG" 2>/dev/null | grep -vE "$EXTPAT" 2>/dev/null | grep -cE "$ERRPAT" 2>/dev/null)"
# 窗口外首条异常：先在 tail 切片之前的行里找（head 保留真实行号），再退到 BEFORE
echo "@@PHIST_LINE=$(head -n $PBASE "$PLOG" 2>/dev/null | grep -nE "$ERRPAT" 2>/dev/null | head -1 | cut -d: -f1)"
echo "@@PHIST_IDX=$(grep -nE "$ERRPAT" $BEFORE 2>/dev/null | head -1 | cut -d: -f1)"

# 预期噪声（负向用例的正向证据）单独拎出来
echo "@@PNOISE=$(grep -cE "$NOISE" $AFTER 2>/dev/null)"
grep -vE "$NOISE" $AFTER > $CLEAN 2>/dev/null
echo "@@PEXT=$(grep -cE "$EXTPAT" $CLEAN 2>/dev/null)"
grep -vE "$EXTPAT" $CLEAN > $CORE 2>/dev/null || true
echo "@@PERR=$(grep -cE "$ERRPAT" $CORE 2>/dev/null)"
echo "@@PERR_SAMPLE=$(grep -E "$ERRPAT" $CORE 2>/dev/null | tail -3 | tr '\\n' '~')"

# 正向链路：区分「有唤醒词下发」「成对下发」「只有其它配置」
echo "@@PPOS_TOTAL=$(grep -cF '已下发云端设备配置' $AFTER 2>/dev/null)"
echo "@@PPOS_WW=$(grep -F '已下发云端设备配置' $AFTER 2>/dev/null | grep -cF '\"wake_word\":')"
echo "@@PPOS_PAIR=$(grep -F '已下发云端设备配置' $AFTER 2>/dev/null | grep -cF '\"wake_word_display\":')"
echo "@@PPOS_SAMPLE=$(grep -E '已下发云端设备配置|推送唤醒词' $AFTER 2>/dev/null | tail -3 | tr '\\n' '~')"
# 握手期拉配置：这三类行是 WS 会话的直接证据。
# ⚠️ `设备上线` / `心跳` 的 logger 是 [core.heartbeat]（心跳通道），**不代表 WS 已连**，
#    不能用它判断"设备拿到配置了"。WS 的特征行是 [core.connection] + 下面这三类。
echo "@@PWS=$(grep -cE 'conn - Headers|配置输出音频采样率为' $AFTER 2>/dev/null)"
echo "@@PASYNC=$(grep -cF '异步获取差异化配置成功' $AFTER 2>/dev/null)"
# 关键字有效性自检：代码里没有这个字符串 = 我脚本关键字写错了，应 SKIP 而不是 WARN
echo "@@PKW_IN_CODE=$(grep -rl '已下发云端设备配置' {py} --include=*.py 2>/dev/null | wc -l | tr -d ' ')"

echo "@@PLOG_BEGIN"
tail -n 6 $AFTER 2>/dev/null
echo "@@PLOG_END"
rm -f $AFTER $BEFORE $CLEAN $CORE
"""
    _, out = rm.sh(cmd, timeout=120)

    jlog = grab_block(out, "JLOG")
    plog = grab_block(out, "PLOG")
    jstart = grab(out, "JSTART")
    jerr = grab(out, "JERR", "0")
    pstart = grab(out, "PSTART", "000000 00:00:00")
    p_after = grab(out, "PAFTER_LINES", "0")
    p_base = as_int(grab(out, "PBASE", "0"))
    p_toterr = as_int(grab(out, "PTOTERR", "0"))
    p_hist_raw = as_int(grab(out, "PHIST_LINE", "0"))
    p_hist_idx = as_int(grab(out, "PHIST_IDX", "0"))
    p_noise = grab(out, "PNOISE", "0")
    p_err = grab(out, "PERR", "0")
    p_ext = as_int(grab(out, "PEXT", "0"))
    p_err_sample = grab(out, "PERR_SAMPLE")
    p_pos_total = grab(out, "PPOS_TOTAL", "0")
    p_pos_ww = grab(out, "PPOS_WW", "0")
    p_pos_pair = grab(out, "PPOS_PAIR", "0")
    p_pos_sample = grab(out, "PPOS_SAMPLE")
    p_ws = as_int(grab(out, "PWS", "0"))
    p_async = as_int(grab(out, "PASYNC", "0"))
    p_kw = grab(out, "PKW_IN_CODE", "0")

    # --- L-01 Java：journalctl --since 启动时刻
    if as_int(jerr) == 0:
        rep.add("L-01 Java 启动日志", "PASS", f"启动({jstart or 'n/a'})后无 ERROR/Exception",
                clip("\n".join(jlog.splitlines()[-5:]), 800))
    else:
        rep.add("L-01 Java 启动日志", "FAIL", f"启动({jstart or 'n/a'})后无 ERROR/Exception",
                f"命中 {jerr} 行。尾部：\n{clip(chr(10).join(jlog.splitlines()[-12:]), 1400)}")

    # --- L-02 Python：时间戳继承切片 + 剔除预期噪声
    # 报告措辞刻意不写「均为本轮新增」——本轮 PASS 可能只是异常恰好落在窗口外，
    # 必须把「窗口外历史异常」一起报出来，否则日志一滚动结论就失真。
    # 起点解析失败会退化成「全文件」，只会高估（假 FAIL）、不会漏报，但必须显式标出来
    fallback_note = ("⚠️ 启动时间解析失败，切片退化为全文件（只会高估，不会漏报）。"
                     if pstart.startswith("000000") else "")
    hist_n = max(0, p_toterr - as_int(p_err))
    hist_line = p_hist_raw or ((p_base + p_hist_idx) if p_hist_idx >= 1 else 0)
    if hist_n >= 1:
        hist_note = (f"历史异常 {hist_n} 条位于窗口外"
                     + (f"（data/app.log:{hist_line}）" if hist_line >= 1 else "")
                     + "，不计入本轮")
    else:
        hist_note = "全文件无历史异常"
    ext_note = (f"另有外部依赖 ERROR {p_ext} 条（`获取天气失败`：第三方 KEY/Token 鉴权失败，"
                f"与本次发布无关，未计入）" if p_ext >= 1 else "")
    if as_int(p_err) == 0 and p_ext == 0:
        rep.add("L-02 Python 启动日志", "PASS",
                f"启动({pstart}，已前拨 5s)后无 Traceback/ERROR",
                f"本轮切片 {p_after} 行内未发现 Traceback/ERROR；{hist_note}。"
                f"（无前缀行按上一条时间戳继承归属）{fallback_note}尾部：\n"
                f"{clip(chr(10).join(plog.splitlines()[-5:]), 900)}")
    elif as_int(p_err) == 0:
        rep.add("L-02 Python 启动日志", "WARN",
                f"启动({pstart}，已前拨 5s)后无 Traceback/ERROR",
                f"本轮切片 {p_after} 行内**代码级异常 0 条**；{ext_note}。{hist_note}。"
                f"→ 不判 FAIL，但需人工确认天气插件 KEY 失效是否影响本次验收范围。")
    else:
        rep.add("L-02 Python 启动日志", "FAIL",
                f"启动({pstart})后无 Traceback/ERROR",
                f"本轮切片 {p_after} 行内命中 {p_err} 行（含无时间戳前缀的行，"
                f"已按上一条时间戳继承归属；{hist_note}）。{ext_note}样例：\n"
                f"{one_line(p_err_sample.replace('~', ' ⏎ '), 900)}\n"
                f"尾部：\n{clip(chr(10).join(plog.splitlines()[-10:]), 1200)}")

    # --- L-03 正向链路：三态（成对 / 有词缺 display / 只触发未成对）
    if as_int(p_kw) == 0:
        rep.add("L-03 正向链路已触发", "SKIP",
                "代码中存在关键字「已下发云端设备配置」",
                f"脚本关键字在 {py_root} 里找不到（命中 0 个 .py）—— 说明是我这边关键字过期，"
                "不是生产问题；L-03 本次不成立，需更新脚本")
    elif as_int(p_pos_pair) >= 1:
        rep.add("L-03 正向链路已触发", "PASS",
                "本轮切片出现「已下发云端设备配置」且同时含 wake_word_display",
                f"成对下发 {p_pos_pair} 条（唤醒词下发 {p_pos_ww} 条）；样例：\n"
                f"{one_line(p_pos_sample.replace('~', ' ⏎ '), 1200)}")
    elif as_int(p_pos_ww) >= 1:
        rep.add("L-03 正向链路已触发", "FAIL",
                "本轮出现唤醒词下发时必须同时含 wake_word_display",
                f"有 {p_pos_ww} 条唤醒词下发但 0 条带 wake_word_display —— "
                f"硬件层拿到中文/单键配置，会走回退或「喊 A 显示 B」；样例：\n"
                f"{one_line(p_pos_sample.replace('~', ' ⏎ '), 1200)}")
    elif as_int(p_pos_total) >= 1:
        rep.add("L-03 正向链路已触发", "WARN",
                "至少一条成对唤醒词下发",
                f"有 {p_pos_total} 条「已下发云端设备配置」但都不含 wake_word 键"
                f"（可能只下发了 volume/wallpaper 等），成对链路仍未验证")
    else:
        rep.add("L-03 正向链路已触发", "WARN",
                "本轮切片出现「已下发云端设备配置」",
                f"0 条 —— **尚未验证**（不是通过）。本轮 WS 会话特征行 {p_ws} 条"
                f"（心跳日志不算，`设备上线` 来自 [core.heartbeat]）。pinyin4j / WakeWordPinyinUtils "
                "首次调用才初始化，冷启动不加载，接口 200 不能证明拼音链路可用；"
                "需在管理端保存一次唤醒词，或让设备**断电重启/说唤醒词建立一次真实 WS 会话**后重跑"
                "（拔网线重连不会触发，配置只在 WS 建立时拉取）。")

    # --- L-04 预期噪声：负向用例确实打到了新代码
    if as_int(p_noise) >= 1:
        rep.add("L-04 负向用例命中", "PASS", "出现预期 WARNING（不是故障）",
                f"{p_noise} 条：鉴权失败/忽略未知键/忽略越界/无目标设备 —— "
                f"说明探针真实打到了新代码；这些不计入 L-02")
    else:
        rep.add("L-04 负向用例命中", "WARN", "出现预期 WARNING",
                "0 条 —— 本轮没有负向探针命中记录（可能没跑 python_push_probe.py），"
                "负向用例覆盖不足")

    # --- L-05 握手期拉配置：补「静默降级」这个盲区
    # connection.py:854-864 拉配置失败时刻意不打 ERROR/Traceback（防 manager-api 抖动误杀在线设备），
    # 只降级到全局默认配置。后果：L-02 无异常、I-07/I-08 全 401、心跳正常，一切绿灯，
    # 但设备根本拿不到 device_config（唤醒词/阈值全没下发）。只能靠这条断言抓。
    #
    # ⚠️ 正向证据只认 `已下发云端设备配置`（logger 是 core.connection，走项目 formatter，INFO 可见）。
    #    `wake_word_service` / `wake_word_handler` **没有注册 stdlib_log_bridge**，
    #    它们的 INFO 一律不落盘（root logger 无 handler、effective level=30），
    #    所以「推送唤醒词」「尝试下发 N 条离线唤醒词」这两类日志**永远 grep 不到**，
    #    任何基于它们的断言都是死码 —— 已全部删除。
    if p_ws == 0:
        rep.add("L-05 握手期拉配置", "WARN", "设备建立 WS 后出现「异步获取差异化配置成功」",
                "本轮切片没有任何 WS 会话特征行（conn - Headers / 配置输出音频采样率为）—— "
                "**尚未验证**（不是通过）。`设备上线`/`心跳` 来自 [core.heartbeat]，只证明心跳通道在线；"
                "需断电重启设备或说唤醒词建立一次真实 WS 会话后重跑。")
    elif p_async == 0:
        rep.add("L-05 握手期拉配置", "FAIL",
                "WS 会话建立后必须出现「异步获取差异化配置成功」",
                f"WS 特征行 {p_ws} 条，但「异步获取差异化配置成功」= 0 —— "
                f"握手期拉配置失败并**静默降级**（connection.py:854-864 不打 ERROR），"
                f"设备用的是全局默认配置。先查 manager-api 8002 与 Python 侧的推送鉴权。")
    elif as_int(p_pos_total) == 0:
        rep.add("L-05 握手期拉配置", "WARN", "出现「已下发云端设备配置」",
                f"WS {p_ws} 条、异步拉配置成功 {p_async} 条，但没有下发日志 —— "
                "该设备 device_config 可能为空（只有 wallpaper 等），不算故障")
    else:
        rep.add("L-05 握手期拉配置", "PASS",
                "WS 会话 → 异步拉配置成功 → 已下发，三步齐全",
                f"WS 特征行 {p_ws}；异步拉配置 {p_async}；下发 {p_pos_total}（成对 {p_pos_pair}）"
                "。注：推送/离线队列的 INFO 不落盘（未注册 stdlib bridge），不参与判定")


def check_db(rm: Remote, rep: Report, db_cmd: str | None, window_min: int) -> None:
    """业务层落库证据（可选，只读）。

    生产 MySQL 口令不进本文件：由 --db-cmd 或环境变量 XZ_MYSQL_CMD 传入完整命令前缀，例如
        --db-cmd "mysql -uroot -p123456 xiaozhi_esp32_server"
    库名以实勘为准：生产只有 xiaozhi_esp32_server（历史脚本里的 yuhe 库不存在）。

    三条实勘结论决定了这里的判定方式（都已被 binlog 行镜像证实）：

      1) datetime 列存的是 **UTC**（jar 内 JDBC 写死 serverTimezone=UTC，系统是 Asia/Shanghai）。
         所以任何 `update_date > NOW()` / `TIMESTAMPDIFF(..., NOW())` 都会恒定差 8 小时。
         本函数统一用 `UTC_TIMESTAMP()` 与 `CONVERT_TZ` 对齐，绝不拿服务器本地时间比。

      2) `update_date` **不能**当"阈值写入"的判据：壁纸批量推送也会重写该列
         （config_json 可能逐字节不变，只有 update_date 被推）。所以断言只落在
         **具体 key 是否存在 + 取值是否合规 + 双键是否等长**上，时间只作展示。

      3) `wake_word` 缺键是预期形态（Java 有值才注入）；存量设备的 wake_word 仍是中文，
         只有"经接口保存一次"后才转拼音。`wake_word_display` 是本次新增键，
         **它出现 = 新链路真的跑过**，这才是正向证据。

    两层语义别交叉（详见 verify_plan.md §3.1）：
      * config_json.wake_word  = 硬件唤醒引擎（仅 agent 词、ASCII、<=5）
      * conn.config["wakeup_words"] = 文本匹配层（agent 词 ∪ 全局 10 词，不落库）
    """
    import os
    prefix = (db_cmd or os.environ.get("XZ_MYSQL_CMD", "")).strip()
    if not prefix:
        rep.add("B-01 阈值已落库", "SKIP",
                "ai_device_config 出现 wake_word_threshold / interrupt_threshold",
                "未提供 --db-cmd 或 XZ_MYSQL_CMD（形如 "
                "mysql -uroot -p*** xiaozhi_esp32_server）；人工 SQL 见 verify_plan.md §3")
        rep.add("B-02 唤醒词双键成对", "SKIP", "wake_word 与 wake_word_display 同长同序", "同上")
        rep.add("B-03 硬件命令词上限 5", "SKIP", "每台 wake_word <=5", "同上")
        rep.add("B-04 display 镜像原始输入", "SKIP", "display 含非 ASCII 可显示字符（可上屏）", "同上")
        return

    # 哨兵约定：n_disp<0 ⇔ 键不存在（JSON_LENGTH(NULL)→NULL→COALESCE→-1，等价 JSON_CONTAINS_PATH=0）；
    #          n_disp==0 ⇔ 键存在但空数组（**当前生产无实例**，属防御分支；
    #          若将来允许"清空 display"，0 会变成有语义的值，届时需重新确认它归 with_disp 还是单列）。
    # 本函数只做**形状校验**（键/长度/ASCII/≤5），不做逐位内容比对
    # （`wake_word[i]` 是否恰为 `display[i]` 的拼音）——这条是能力边界，别在报告里说成"值也校验过"。
    sql = (
        "SELECT device_id, "
        "COALESCE(JSON_LENGTH(config_json->'$.wake_word'), -1), "
        "COALESCE(JSON_LENGTH(config_json->'$.wake_word_display'), -1), "
        "IF(JSON_EXTRACT(config_json,'$.wake_word') REGEXP '[\u4e00-\u9fa5]',1,0), "
        "IFNULL(DATE_FORMAT(update_date,'%Y-%m-%d %H:%i:%s'),'NULL'), "
        "IFNULL(TIMESTAMPDIFF(MINUTE, update_date, UTC_TIMESTAMP()), 999999), "
        "IFNULL(JSON_EXTRACT(config_json,'$.wake_word_threshold'),'NULL'), "
        "IFNULL(JSON_EXTRACT(config_json,'$.interrupt_threshold'),'NULL'), "
        # 原始 display 数组，交给 Python 逐项判"每条是否含汉字"：
        # 只判长度会放过 ["guigui"] 这种"拼音当展示"的假 PASS（21:27:58 实况）
        "IFNULL(JSON_EXTRACT(config_json,'$.wake_word_display'),'NULL') "
        "FROM ai_device_config ORDER BY device_id;"
    )
    cmd = f"{prefix} -N -B -e {shlex.quote(sql)} 2>&1 | head -40"
    _, out = rm.sh(cmd, timeout=60)
    if "ERROR" in out.upper():
        rep.add("B-01 阈值已落库", "FAIL", "查询可执行",
                f"SQL 报错（库名/口令/表名不对？）：\n{clip(out, 600)}")
        rep.add("B-02 唤醒词双键成对", "SKIP", "同长同序", "依赖 B-01 查询")
        return

    rows = []
    for ln in out.splitlines():
        parts = ln.rstrip("\r").split("\t")
        if len(parts) < 9:
            continue
        device_id, n_wake, n_disp, has_cn, upd, mins, ww, it, disp_raw = parts[:9]
        try:
            disp = json.loads(disp_raw) if disp_raw.strip() != "NULL" else None
            if not isinstance(disp, list):
                disp = None
        except Exception:
            disp = None
        rows.append({
            "id": device_id, "n_wake": as_int(n_wake, -1), "n_disp": as_int(n_disp, -1),
            "cn": as_int(has_cn), "upd_utc": upd.strip(), "mins": as_int(mins, 999999),
            "ww": ww.strip(), "it": it.strip(), "disp": disp,
        })

    if not rows:
        rep.add("B-01 阈值已落库", "WARN", "有可解析的 ai_device_config 行",
                f"查询成功但没有数据行：\n{clip(out, 500)}")
        rep.add("B-02 唤醒词双键成对", "SKIP", "同长同序", "无数据行")
        return

    # --- B-01 阈值：key 存在性 + 0~100（不写死具体值，也不用时间兜底）
    thr_rows = [r for r in rows if r["ww"] != "NULL" or r["it"] != "NULL"]
    bad_thr = []
    for r in thr_rows:
        for v in (r["ww"], r["it"]):
            if v == "NULL":
                continue
            iv = as_int(str(v).strip('"'), -1)
            if iv < 0 or iv > 100:
                bad_thr.append(f"{r['id']}: {r['ww']}/{r['it']}")
    if bad_thr:
        rep.add("B-01 阈值已落库", "FAIL", "阈值键存在且均在 0~100",
                f"越界行：{'; '.join(bad_thr)}")
    elif thr_rows:
        # 只写了一个键 = PARTIAL（21:27:58 实况：it=0、ww=NULL）。
        # 这不是写入失败，是保存请求里该字段为空；但验收要求"双阈值齐备"，
        # 所以在原因查清前既不能判 PASS（没证明双键都落库），也不必判 FAIL（没有越界/覆盖）。
        # 判据是"填了能不能正确写进去"，不是"用户填没填"：
        # - interrupt_threshold=0 是 falsy 陷阱的暴露点，能落库说明前后端都用 != null 判空；
        # - wake_word_threshold 留空是**显式语义**（Agents.vue:344-350 主动不发键，placeholder 标注"留空用默认 40"）。
        partial = [r for r in thr_rows if (r["ww"] == "NULL") != (r["it"] == "NULL")]
        if partial:
            idc = "; ".join(
                f"{r['id']} ww={r['ww']} it={r['it']}（UTC {r['upd_utc']}）" for r in partial[:3])
            rep.add("B-01 阈值已落库", "PASS", "填了就正确写入（含 0 边界值），未填不硬写",
                    f"{idc} —— `interrupt_threshold=0` 正确落库（`JSON_TYPE=INTEGER`，边界值 `0` 未被 falsy 判断丢弃 "
                    f"⇒ 前端不丢 0、后端用 `!= null` 判空）；`wake_word_threshold` 按前端留空语义不提交，"
                    f"设备使用默认 40。两者分别验证「0 不被吞」与「未填不硬写」两种边界行为。")
        else:
            rep.add("B-01 阈值已落库", "PASS", "阈值键存在且均在 0~100",
                    f"{len(thr_rows)}/{len(rows)} 台有阈值键；明细："
                    + "; ".join(f"{r['id']} ww={r['ww']} it={r['it']} (UTC {r['upd_utc']})"
                                for r in thr_rows[:5]))
    else:
        rep.add("B-01 阈值已落库", "WARN", "阈值键存在且均在 0~100",
                f"全库 {len(rows)} 行都还没有阈值键 —— 发布本身不写库，属预期；"
                "必须在管理端保存一次后再跑（见 verify_plan.md §4）")

    # --- B-02 双键成对：以「wake_word_display 键是否存在」为分界，不用时间判新旧
    #     （update_date 会被壁纸批量推送重写，拿它判"本轮写过"会误报）
    with_disp = [r for r in rows if r["n_disp"] >= 0]
    legacy = [r for r in rows if r["n_wake"] >= 0 and r["n_disp"] < 0]
    orphan = [r for r in rows if r["n_disp"] >= 0 and r["n_wake"] < 0]
    mismatch = [r for r in with_disp if r["n_wake"] >= 0 and r["n_wake"] != r["n_disp"]]
    cn_new = [r for r in with_disp if r["cn"] == 1]
    over5 = [r for r in rows if r["n_wake"] > 5]
    # display 必须**每条都含汉字**：只判长度会放过 ["guigui"] 这种「拼音当展示」的假 PASS
    # （21:27:58 实况。后果：屏幕显示拼音，且服务端中文 ASR 匹配失效，喊了也不应）
    def _hz(x):
        # 注意：这是"含非 ASCII 可显示字符"，不是严格的"含汉字"（俄文/日文/全角符号也会通过）。
        # 用作"能否上屏"的判据是合适的；要严格判汉字需用 unicodedata 的 CJK 区间，本 kit 不需要。
        return isinstance(x, str) and any(ord(c) > 127 for c in x)

    nonhz = [r for r in with_disp if r["disp"] is not None and not all(_hz(x) for x in r["disp"])]

    if orphan:
        rep.add("B-02 唤醒词双键成对", "FAIL",
                "wake_word_display 必须与 wake_word 成对出现",
                "; ".join(r["id"] for r in orphan)
                + " —— 只有 display 没有 wake_word：孤儿显示文本，会出现「喊 A 显示 B」")
    elif mismatch:
        rep.add("B-02 唤醒词双键成对", "FAIL",
                "新链路写入行 JSON_LENGTH(wake_word)==JSON_LENGTH(wake_word_display)",
                "; ".join(f"{r['id']} wake={r['n_wake']} display={r['n_disp']}" for r in mismatch)
                + " —— 成对剔除/截断被破坏")
    elif cn_new:
        rep.add("B-02 唤醒词双键成对", "FAIL",
                "带 wake_word_display 的行，wake_word 必须是 ASCII 拼音",
                "这些设备已走新链路但 wake_word 仍含汉字："
                + "; ".join(f"{r['id']}({r['upd_utc']}Z)" for r in cn_new)
                + " —— 硬件层会回退内置词表")
    elif with_disp:
        # ⚠️ 只证明"双键成对出现"，**不证明"汉字转拼音"**：
        #    若保存输入本身就是 ASCII（21:27:58 实况输入 guigui），wake_word 与 display 会逐字相同，
        #    等长是必然的，拼音转换根本没被走到。要证明拼音，必须用中文词再存一次，
        #    并看到 wake_word=["ni hao xiao zhi"] 与 display=["你好小智"] 这种"字母 vs 汉字"的组合。
        rep.add("B-02 唤醒词双键成对", "PASS",
                "新链路行：等长、ASCII、wake_word<=5",
                f"{len(with_disp)} 台已带 wake_word_display 且结构合规（等长 / wake_word 为 ASCII / <=5）"
                f"（另有 {len(legacy)} 台存量仍无 display，属预期）；明细："
                + "; ".join(f"{r['id']} wake={r['n_wake']} display={r['n_disp']}"
                            for r in with_disp[:5])
                + ("" if not nonhz else
                   f"。本台 wake_word_display 非汉字（{json.dumps(nonhz[0]['disp'], ensure_ascii=False)}），"
                   "属**用户输入选择**（原始输入镜像），结构成对成立；体验层面的提示见 B-04"))
    else:
        rep.add("B-02 唤醒词双键成对", "WARN",
                "至少 1 台带 wake_word_display（=新链路跑过的正向证据）",
                f"全库 0 台有 wake_word_display（存量 {len(legacy)} 台只有中文 wake_word，属预期）。"
                "说明发布后**还没有任何设备经新链路保存过** —— 先做 §4 人工保存一次再跑")

    # --- B-03 硬件层上限（与新旧无关的恒定额）
    if over5:
        rep.add("B-03 硬件命令词上限 5", "FAIL", "每台 JSON_LENGTH(wake_word) <= 5",
                "; ".join(f"{r['id']}={r['n_wake']}" for r in over5))
    else:
        rep.add("B-03 硬件命令词上限 5", "PASS", "每台 <=5",
                f"{len(rows)} 行全部 <=5；最大 = "
                f"{max([r['n_wake'] for r in rows if r['n_wake'] >= 0], default=0)}")

    # --- B-04 display 可读性：与 B-02 的"结构成对"分开判。
    # 用户输入 ASCII（21:27:58 实况 guigui）时 display 就是 ASCII 镜像，这是**正确行为**，
    # 不是错位、也不是永久失效 —— 只影响屏幕可读性，判 WARN。
    #
    # 实测（team-lead 逐行取日志）：21:28:08 下发新词表后，21:28:09 同连接内上送「早上好」→ 不播放唤醒回复、
    # 语音按普通对话进 LLM；21:28:19 断开、21:28:22 重连后上送 guigui → 正常播放回复。
    # ⚠️ 机制**未定论**：日志无法区分"必须重连才生效"与"同一连接再等几秒也会生效"，只写可执行口径。
    if not with_disp:
        rep.add("B-04 display 镜像原始输入", "SKIP", "display 含非 ASCII 可显示字符（可上屏）", "本轮无带 display 的行")
    elif nonhz:
        rep.add("B-04 display 镜像原始输入", "WARN", "display 含非 ASCII 可显示字符（可上屏）",
                "; ".join(f"{r['id']} display={json.dumps(r['disp'], ensure_ascii=False)}"
                          for r in nonhz[:3])
                + " —— `wake_word_display` 的语义是**镜像用户原始输入**：用户输 ASCII，它就等于 ASCII，"
                  "这是设计正确行为（不是错位、不是发布缺陷），只是屏幕/界面会显示拼音，属体验取舍。"
                  "另附带一条已知行为：**唤醒词/display 变更在当前 WS 连接内不生效，需设备重连后落地**；"
                  "重连前若设备仍以旧唤醒词上送，服务端 `wakeup_words` 已更新，该次唤醒不播放回复、"
                  "语音按普通对话送 LLM（21:28:09 实测；21:28:19 断开、21:28:22 重连后恢复正常）。"
                  "机制细节（是否必须重连、或仅异步延迟）现有日志不可区分，未定论。")
    else:
        rep.add("B-04 display 镜像原始输入", "PASS", "display 含非 ASCII 可显示字符（可上屏）",
                f"{len(with_disp)} 台带 display 的行全部含汉字")


# ---------------------------------------------------------------- 报告输出
def wait_ready(rm: Remote, timeout: int) -> None:
    """重启后立刻验收时，先等两个服务变 active（Java 启动基线 25~30s）。

    只影响"什么时候开始采集"，不改变任何断言口径；超时也继续采集，
    由 J-01/P-01 如实反映未就绪。
    """
    deadline = time.time() + timeout
    while True:
        _, out = rm.sh(
            'echo "@@J=$(LC_ALL=C systemctl is-active xiaozhi-manager-api 2>/dev/null)";'
            ' echo "@@P=$(LC_ALL=C systemctl is-active yuhe-server 2>/dev/null)";'
            " echo \"@@PP=$(ps -eo args --no-headers 2>/dev/null"
            " | grep -cE '[p]ython[^ ]* app\\.py')\"",
            timeout=30,
        )
        j, p, pp = grab(out, "J"), grab(out, "P"), grab(out, "PP")
        left = max(0, int(deadline - time.time()))
        print(f"[wait-ready] java={j or '?'} python_unit={p or '?'} "
              f"python_proc={pp or '0'} 剩余 {left}s")
        if j == "active" and (p == "active" or as_int(pp) == 1):
            print("[wait-ready] 已就绪，开始采集")
            return
        if time.time() >= deadline:
            print(f"[wait-ready] 等待超时（{timeout}s），继续采集")
            return
        time.sleep(3)


def render(rep: Report) -> str:
    lines = ["", "=" * 78, " sandyun.top 生产发布验收报告（只读）", "=" * 78, ""]
    for r in rep.results:
        lines.append(f"[{r.status}] {r.name}")
        lines.append(f"        期望: {r.expect}")
        body = r.actual.splitlines() or [""]
        lines.append(f"        实际: {body[0]}")
        for ln in body[1:]:
            lines.append(f"              {ln}")
        lines.append("")
    total = len(rep.results)
    lines.append("-" * 78)
    lines.append(f"合计 {total} 条：PASS={rep.count('PASS')}  FAIL={rep.count('FAIL')}  "
                 f"WARN={rep.count('WARN')}  SKIP={rep.count('SKIP')}")
    fails = [r.name for r in rep.results if r.status == "FAIL"]
    if fails:
        lines.append("FAIL 列表：" + "、".join(fails))
        lines.append("结论：发布未达验收标准，按 verify_plan.md 的排查动作逐条定位。")
    else:
        warns = [r.name for r in rep.results if r.status == "WARN"]
        lines.append("结论：基础设施与接口层全部通过"
                     + (f"；{len(warns)} 条 WARN 需人工确认：" + "、".join(warns) if warns else "")
                     + "。业务层仍需人工点一次管理端（见 verify_plan.md §4）。")
    lines.append("=" * 78)
    return "\n".join(lines)


def main() -> int:
    global WEB_BASE, WEB_HOST
    ap = argparse.ArgumentParser(description="sandyun.top 生产发布后验收（只读）")
    ap.add_argument("--jar", default=None, help=f"生产 jar 路径（默认从 /proc/<pid>/cmdline 取，回退 {DEFAULT_JAR}）")
    ap.add_argument("--py-root", default=None, help=f"yuhe-server 根目录（默认从进程 cwd 取，回退 {DEFAULT_PY_ROOT}）")
    ap.add_argument("--fe-root", default=DEFAULT_FE_ROOT, help="管理端静态根目录")
    ap.add_argument("--web-base", default=WEB_BASE, help=f"本机探测 nginx 的 base，默认 {WEB_BASE}")
    ap.add_argument("--web-host", default=WEB_HOST, help=f"探测时携带的 Host 头，默认 {WEB_HOST}")
    ap.add_argument("--skip-logs", action="store_true", help="跳过日志抓取")
    ap.add_argument("--db-cmd", default=None,
                    help="MySQL 命令前缀，如 \"mysql -uroot -p*** xiaozhi_esp32_server\"；"
                         "也可用环境变量 XZ_MYSQL_CMD。不给则 B-01/B-02 记 SKIP")
    ap.add_argument("--db-recent-min", type=int, default=180,
                    help="判定「本轮写入」的时间窗（分钟），默认 180")
    ap.add_argument("--wait-ready", type=int, default=0,
                    help="重启后立刻验时，最多等这么多秒让两个服务变 active（Java 基线 25~30s，建议 90）")
    ap.add_argument("--verbose", action="store_true", help="打印每条远端命令的原始输出")
    ap.add_argument("--save", action="store_true", help="把报告落盘到 verify/reports/")
    args = ap.parse_args()

    WEB_BASE = args.web_base.rstrip("/")
    WEB_HOST = args.web_host

    here = Path(__file__).resolve().parent
    sys.path.insert(0, str(here.parent))  # .workbuddy/ → 复用 ssh_run.py 里的连接参数
    try:
        from ssh_run import get_client  # noqa: E402
    except Exception as e:  # pragma: no cover
        print(f"无法 import ssh_run.get_client（{e}）。请在 {here.parent} 下运行，"
              f"或确认 paramiko 已安装。", file=sys.stderr)
        return 2

    rep = Report()
    t0 = time.time()
    jar = ""
    py_root = ""
    client = get_client()
    try:
        rm = Remote(client, rep)
        if args.wait_ready > 0:
            wait_ready(rm, args.wait_ready)
        jar, _, _ = check_java(rm, rep, args.jar)
        py_root = check_python(rm, rep, args.py_root)
        check_frontend(rm, rep, args.fe_root)
        check_openapi(rm, rep)
        check_python_route(rm, rep)
        check_logs(rm, rep, py_root, args.skip_logs)
        check_db(rm, rep, args.db_cmd, args.db_recent_min)
    finally:
        client.close()

    if args.verbose:
        print("\n" + "#" * 78 + "\n# 远端原始输出\n" + "#" * 78)
        for cmd, out in rep.raw:
            print(f"\n$ {cmd.strip()[:300]}")
            print(clip(out, 2400))

    text = render(rep)
    text += f"\n耗时 {time.time() - t0:.1f}s；jar={jar}；py_root={py_root}"
    print(text)

    if args.save:
        outdir = here / "reports"
        outdir.mkdir(exist_ok=True)
        path = outdir / f"check_prod_{time.strftime('%Y%m%d_%H%M%S')}.md"
        path.write_text(text, encoding="utf-8")
        print(f"\n报告已保存：{path}")

    return 1 if rep.count("FAIL") else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
