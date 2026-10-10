#!/usr/bin/env python3
"""Deploy ASR fixes to sandyun.top (backup → upload → restart → verify).

Files to push (local code-server-mirror → remote /root/xiaozhi-server/main/xiaozhi-server):
  1. core/api/asr_recognize_handler.py   (X-Asr-Config-B64 头兼容 + ValueError 捕获)
  2. core/providers/asr/qwen3_asr_flash.py (asyncio.to_thread 防事件循环阻塞)
  3. core/http_server.py                 (client_max_size=8MB)
"""
import sys
import paramiko

HOST = "sandyun.top"
PORT = 22222
USER = "root"

LOCAL_BASE = "G:/demo/21_xiaozhi/code-server-mirror/xiaozhi-server"
REMOTE_BASE = "/root/xiaozhi-server/main/xiaozhi-server"
FILES = [
    "core/api/asr_recognize_handler.py",
    "core/providers/asr/qwen3_asr_flash.py",
    "core/http_server.py",
]
STAMP = "20261010T1910"


def get_client():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password="Ymm6088.",
                   timeout=15, banner_timeout=15, auth_timeout=15,
                   look_for_keys=False, allow_agent=False)
    return client


def run(client, cmd):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=120)
    out = stdout.read().decode("utf-8", "replace").strip()
    err = stderr.read().decode("utf-8", "replace").strip()
    rc = stdout.channel.recv_exit_status()
    return rc, out, err


def main():
    client = get_client()
    try:
        # 1. 备份远程原文件
        for f in FILES:
            rc, out, err = run(client,
                f"cp {REMOTE_BASE}/{f} {REMOTE_BASE}/{f}.bak-{STAMP}")
            print(f"backup {f}: rc={rc} {err[:100]}")

        # 2. 上传修复文件
        sftp = client.open_sftp()
        for f in FILES:
            local_path = f"{LOCAL_BASE}/{f}"
            remote_path = f"{REMOTE_BASE}/{f}"
            sftp.put(local_path.replace("/", "\\"), remote_path)
            print(f"upload {f}: done")
        sftp.close()

        # 3. 语法校验远程文件
        rc, out, err = run(client,
            f"cd {REMOTE_BASE} && python3 -c \""
            "import ast; [ast.parse(open(f, encoding='utf-8').read()) for f in "
            "['core/api/asr_recognize_handler.py', 'core/providers/asr/qwen3_asr_flash.py', 'core/http_server.py']]; "
            "print('AST OK')\"")
        print(f"remote ast check: rc={rc} out={out} err={err[:200]}")
        if rc != 0:
            print("!! 远程语法校验失败，中止重启，恢复备份")
            for f in FILES:
                run(client, f"cp {REMOTE_BASE}/{f}.bak-{STAMP} {REMOTE_BASE}/{f}")
            sys.exit(1)

        # 4. 重启服务
        rc, out, err = run(client, "systemctl restart xiaozhi-server")
        print(f"restart xiaozhi-server: rc={rc} {err[:100]}")

        # 5. 等待启动 + 健康检查
        import time
        time.sleep(6)
        rc, out, err = run(client, "systemctl is-active xiaozhi-server")
        print(f"service status: {out}")
        rc, out, err = run(client,
            "journalctl -u xiaozhi-server --since '1 minute ago' --no-pager | tail -15")
        print("recent log:")
        print(out)
    finally:
        client.close()


if __name__ == "__main__":
    main()
