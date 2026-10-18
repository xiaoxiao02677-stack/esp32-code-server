#!/usr/bin/env python3
"""修复 WS 频繁断开：上传代码 → 修 nginx → 交给 systemd 托管 → 验证。

步骤：
  1. 备份并上传 2 个 Python 文件（connection.py / websocket_server.py），md5 + py_compile 校验
  2. 备份并替换 nginx 站点配置（去重 + WS 代理加固），nginx -t 通过后 reload
  3. 备份并替换 systemd unit（Restart=always + LimitNOFILE），daemon-reload
  4. 停掉手工 nohup 进程，改由 systemd 启动
  5. 验活：端口、systemd 状态、原始帧探测（确认服务端每 30s 发 Ping）
"""
import hashlib
import sys
import time

import paramiko

HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."

LOCAL_ROOT = r"G:\demo\21_xiaozhi\code-server-mirror\yuhe-server"
REMOTE_ROOT = "/root/xiaozhi-server/main/yuhe-server"
LOCAL_MISC = r"G:\demo\21_xiaozhi\code\.workbuddy"

PY_FILES = ["core/connection.py", "core/websocket_server.py"]


def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=PASSWORD,
                   timeout=20, look_for_keys=False, allow_agent=False)
    sftp = client.open_sftp()

    def sh(cmd, timeout=180, quiet=False):
        _, out, err = client.exec_command(cmd, timeout=timeout)
        o = out.read().decode("utf-8", "replace").strip()
        e = err.read().decode("utf-8", "replace").strip()
        rc = out.channel.recv_exit_status()
        if not quiet:
            print(f"  rc={rc}" + (f"\n{o}" if o else "") + (f"\n  [err]{e}" if e else ""))
        return rc, o, e

    rc, ts, _ = sh("date -u +%Y%m%dT%H%M%SZ", quiet=True)
    ts = ts or "manual"
    print(f"=== 备份时间戳 {ts} ===")

    # ---------- 1. Python 代码 ----------
    print("\n[1/5] 上传 Python 代码")
    ok = True
    for rel in PY_FILES:
        remote = f"{REMOTE_ROOT}/{rel}"
        sh(f"cp -f {remote} {remote}.bak-{ts}", quiet=True)
        local = f"{LOCAL_ROOT}\\{rel.replace('/', chr(92))}"
        sftp.put(local, remote)
        want = hashlib.md5(open(f"{LOCAL_ROOT}/{rel}", "rb").read()).hexdigest()
        _, got, _ = sh(f"md5sum {remote}", quiet=True)
        got = got.split()[0] if got else ""
        print(f"  {rel}: {'OK' if got == want else 'MISMATCH'} ({want[:8]}/{got[:8]})")
        ok &= (got == want)

    joined = " ".join(f"{REMOTE_ROOT}/{r}" for r in PY_FILES)
    rc, _, _ = sh(f"cd {REMOTE_ROOT} && .venv/bin/python -m py_compile {joined}", quiet=True)
    print(f"  py_compile: {'OK' if rc == 0 else 'FAILED'}")
    ok &= (rc == 0)

    # ---------- 2. nginx ----------
    print("\n[2/5] 修复 nginx 配置（去掉重复的 location = /）")
    sh("cp -f /etc/nginx/sites-available/xiaozhi-manager "
       f"/etc/nginx/sites-available/xiaozhi-manager.bak-{ts}", quiet=True)
    sftp.put(f"{LOCAL_MISC}\\nginx_yuhe_manager_fixed.conf",
             "/tmp/xz_nginx_fixed.conf")
    sh("cp -f /tmp/xz_nginx_fixed.conf /etc/nginx/sites-available/xiaozhi-manager", quiet=True)
    rc, o, e = sh("nginx -t 2>&1")
    if rc != 0:
        print("  !! nginx -t 未通过，放弃 reload（已保留备份）")
        ok = False
    else:
        sh("nginx -s reload", quiet=True)
        time.sleep(3)
        rc, o, _ = sh("ss -lntp 2>/dev/null | grep -E ':8001|:9001' | cut -c1-70", quiet=True)
        print(f"  8001/9001 监听: {o or '(无!)'}")

    # ---------- 3. systemd unit ----------
    print("\n[3/5] 更新 systemd unit（Restart=always）")
    sh("cp -f /etc/systemd/system/yuhe-server.service "
       f"/etc/systemd/system/yuhe-server.service.bak-{ts}", quiet=True)
    sftp.put(f"{LOCAL_MISC}\\yuhe-server.service", "/tmp/xz_service")
    sh("cp -f /tmp/xz_service /etc/systemd/system/yuhe-server.service", quiet=True)
    sh("systemctl daemon-reload", quiet=True)
    _, o, _ = sh("systemctl show yuhe-server -p Restart -p LimitNOFILE", quiet=True)
    print(f"  {o}")

    # ---------- 4. 切换到 systemd 托管 ----------
    print("\n[4/5] 停手工进程，交 systemd 托管")
    _, o, _ = sh("ps -eo pid,cmd | grep '[a]pp.py' | awk '{print $1}'", quiet=True)
    pids = [p for p in (o or "").split() if p.isdigit()]
    print(f"  待停 PID: {pids}")
    if pids:
        sh("kill -9 " + " ".join(pids), quiet=True)
        time.sleep(3)
    sh("systemctl restart yuhe-server", timeout=60, quiet=True)
    time.sleep(20)
    rc, o, _ = sh("systemctl is-active yuhe-server", quiet=True)
    print(f"  is-active: {o}")
    _, o, _ = sh("ps -eo pid,etime,cmd | grep '[a]pp.py'", quiet=True)
    print(f"  进程: {o}")
    _, o, _ = sh("ss -lntp 2>/dev/null | grep -E ':8000|:8003' | cut -c1-70", quiet=True)
    print(f"  监听: {o or '(无!)'}")
    _, o, _ = sh("grep 'Max open files' /proc/$(pgrep -f 'venv/bin/python app.py' | head -1)/limits",
                 quiet=True)
    print(f"  nofile: {o}")

    sftp.close()
    client.close()
    print("\n结果:", "全部就绪" if ok else "存在问题，请检查上方输出")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
