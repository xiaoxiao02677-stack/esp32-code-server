#!/usr/bin/env python3
"""部署音色语气指令修复：备份 → SFTP 上传 → md5 校验 → 语法编译。

用法：python deploy_voice_instr.py
"""
import hashlib
import sys

import paramiko

HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."

LOCAL_ROOT = r"G:\demo\21_xiaozhi\code-server-mirror\xiaozhi-server"
REMOTE_ROOT = "/root/xiaozhi-server/main/xiaozhi-server"

FILES = [
    "core/connection.py",
    "core/providers/tts/base.py",
    "core/providers/tts/doubao_v3.py",
    "core/providers/tts/huoshan_double_stream.py",
]


def md5_local(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()


def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=PASSWORD,
                   timeout=20, look_for_keys=False, allow_agent=False)
    sftp = client.open_sftp()

    def sh(cmd, timeout=120):
        _, out, err = client.exec_command(cmd, timeout=timeout)
        o = out.read().decode("utf-8", "replace").strip()
        e = err.read().decode("utf-8", "replace").strip()
        rc = out.channel.recv_exit_status()
        return rc, o, e

    # 1. 备份
    rc, o, e = sh("date -u +%Y%m%dT%H%M%SZ")
    ts = o.strip() or "manual"
    print(f"[1/4] 备份时间戳 {ts}")
    for rel in FILES:
        rpath = f"{REMOTE_ROOT}/{rel}"
        sh(f"cp -f {rpath} {rpath}.bak-{ts}")
        rc, o, e = sh(f"ls -la {rpath}.bak-{ts}")
        if rc != 0:
            print(f"  !! 备份失败 {rpath}: {e}")
            sys.exit(1)
        print(f"  备份 OK  {rel}")

    # 2. 上传
    print("[2/4] 上传")
    for rel in FILES:
        local = f"{LOCAL_ROOT}\\{rel.replace('/', chr(92))}"
        remote = f"{REMOTE_ROOT}/{rel}"
        sftp.put(local, remote)
        print(f"  ↑ {rel}")

    # 3. md5 校验
    print("[3/4] md5 校验")
    ok = True
    for rel in FILES:
        want = md5_local(f"{LOCAL_ROOT}/{rel}")
        rc, o, e = sh(f"md5sum {REMOTE_ROOT}/{rel}")
        got = o.split()[0] if o else ""
        flag = "OK " if got == want else "MISMATCH"
        if got != want:
            ok = False
        print(f"  {flag} {rel}  local={want[:8]} remote={got[:8]}")

    # 4. 语法编译（用服务器自己的 venv，确保依赖与线上一致）
    print("[4/4] 服务器 py_compile")
    joined = " ".join(f"{REMOTE_ROOT}/{rel}" for rel in FILES)
    rc, o, e = sh(f"cd {REMOTE_ROOT} && .venv/bin/python -m py_compile {joined}")
    if rc != 0:
        print("  !! py_compile 失败:", e)
        ok = False
    else:
        print("  py_compile 通过")

    sftp.close()
    client.close()
    print("\n结果:", "全部就绪，可以重启" if ok else "存在问题，请勿重启")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
