#!/usr/bin/env python3
"""Deploy wake-word realtime push fix (device_config format) to sandyun.top.

Files (local code-server-mirror -> remote /root/xiaozhi-server/main/yuhe-server):
  1. core/services/wake_word_service.py  (push device_config payload, offline queue latest-only)
  2. core/connection.py                  (websocket/MQTT-gateway detection before wake service register)
  3. core/api/wake_word_handler.py       (allow empty wake_words list = clear semantics)

Local files are CRLF; remote uses LF -> normalize during upload.
Flow: backup -> upload -> remote AST check -> restart -> health check.
"""
import sys
import time
import paramiko

HOST = "sandyun.top"
PORT = 22222
USER = "root"

LOCAL_BASE = "G:/demo/21_xiaozhi/code-server-mirror/yuhe-server"
REMOTE_BASE = "/root/xiaozhi-server/main/yuhe-server"
FILES = [
    "core/services/wake_word_service.py",
    "core/connection.py",
    "core/api/wake_word_handler.py",
]
STAMP = "20261010T2030"


def get_client():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password="Ymm6088.",
                   timeout=15, banner_timeout=15, auth_timeout=15,
                   look_for_keys=False, allow_agent=False)
    return client


def run(client, cmd, timeout=120):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace").strip()
    err = stderr.read().decode("utf-8", "replace").strip()
    rc = stdout.channel.recv_exit_status()
    return rc, out, err


def main():
    client = get_client()
    try:
        # 0. 前置健康检查
        rc, out, err = run(client, "systemctl is-active yuhe-server")
        print(f"pre-check service: {out}")
        if out != "active":
            print("!! 服务当前非 active，中止部署")
            sys.exit(1)

        # 1. 备份远程原文件
        for f in FILES:
            rc, out, err = run(client,
                f"cp {REMOTE_BASE}/{f} {REMOTE_BASE}/{f}.bak-{STAMP}")
            print(f"backup {f}: rc={rc} {err[:100]}")

        # 2. 上传（CRLF -> LF 规范化）
        sftp = client.open_sftp()
        for f in FILES:
            local_path = f"{LOCAL_BASE}/{f}"
            remote_path = f"{REMOTE_BASE}/{f}"
            with open(local_path, "rb") as fh:
                data = fh.read().replace(b"\r\n", b"\n")
            with sftp.open(remote_path, "wb") as rf:
                rf.write(data)
            print(f"upload {f}: {len(data)} bytes (LF-normalized)")
        sftp.close()

        # 3. 远程 AST 语法校验
        files_list = ",".join(f"'{f}'" for f in FILES)
        rc, out, err = run(client,
            f"cd {REMOTE_BASE} && python3 -c \""
            f"import ast; [ast.parse(open(f, encoding='utf-8').read()) for f in [{files_list}]]; "
            "print('AST OK')\"")
        print(f"remote ast check: rc={rc} out={out} err={err[:200]}")
        if rc != 0:
            print("!! 远程语法校验失败，中止重启，恢复备份")
            for f in FILES:
                run(client, f"cp {REMOTE_BASE}/{f}.bak-{STAMP} {REMOTE_BASE}/{f}")
            sys.exit(1)

        # 4. 重启服务
        rc, out, err = run(client, "systemctl restart yuhe-server")
        print(f"restart yuhe-server: rc={rc} {err[:100]}")

        # 5. 等待启动 + 健康检查
        time.sleep(6)
        rc, out, err = run(client, "systemctl is-active yuhe-server")
        print(f"service status: {out}")
        if out != "active":
            print("!! 重启后服务异常，查看日志：")
            rc, out, err = run(client,
                "journalctl -u yuhe-server --since '2 minutes ago' --no-pager | tail -30")
            print(out)
            sys.exit(1)
        rc, out, err = run(client,
            "ss -tlnp | grep 8003 | head -3")
        print(f"port 8003: {out}")
        rc, out, err = run(client,
            "journalctl -u yuhe-server --since '1 minute ago' --no-pager | tail -15")
        print("recent log:")
        print(out)
    finally:
        client.close()


if __name__ == "__main__":
    main()
