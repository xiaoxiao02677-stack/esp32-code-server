#!/usr/bin/env python3
"""部署 doubao_v3 情感合成改造：备份 → 上传 → 校验 → 重启 → 线上实测。"""
import hashlib
import time

import paramiko

HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."

LOCAL_ROOT = r"G:\demo\21_xiaozhi\code-server-mirror\xiaozhi-server"
REMOTE_ROOT = "/root/xiaozhi-server/main/xiaozhi-server"
LOCAL_MISC = r"G:\demo\21_xiaozhi\code\.workbuddy"
PY_FILE = "core/providers/tts/doubao_v3.py"

STAMP = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def md5(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


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
        if not quiet:
            if o:
                print(o)
            if e:
                print("[ERR]", e)
        return o, e

    print("=" * 60)
    print("步骤 1: 备份 + 上传 doubao_v3.py")
    print("=" * 60)
    local = f"{LOCAL_ROOT}\\{PY_FILE.replace('/', chr(92))}"
    remote = f"{REMOTE_ROOT}/{PY_FILE}"
    sh(f"cp -a {remote} {remote}.bak-{STAMP}")
    sh(f"ls -l {remote}.bak-{STAMP}")
    sftp.put(local, remote)
    lm, rm = md5(local), sh(f"md5sum {remote}", quiet=True)[0].split()[0]
    print(f"local md5 = {lm}")
    print(f"remote md5= {rm}")
    assert lm == rm, "md5 不一致，上传失败"
    print("md5 一致 ✔")

    print()
    print("=" * 60)
    print("步骤 2: 语法校验")
    print("=" * 60)
    o, e = sh(f"cd {REMOTE_ROOT} && python3 -m py_compile {PY_FILE} && echo COMPILE_OK")
    assert "COMPILE_OK" in o, "py_compile 失败"

    print()
    print("=" * 60)
    print("步骤 3: 线上实测（服务器网络，真实 API）")
    print("=" * 60)
    sftp.put(f"{LOCAL_MISC}\\server_tts_probe.py", "/tmp/server_tts_probe.py")
    sh(f"cd {REMOTE_ROOT} && python3 /tmp/server_tts_probe.py", timeout=180)

    print()
    print("=" * 60)
    print("步骤 4: 重启服务并验活")
    print("=" * 60)
    sh("systemctl restart xiaozhi-server")
    time.sleep(12)
    sh("systemctl is-active xiaozhi-server")
    sh("ss -lntp | grep -E ':8000|:8003' | head")
    sh("journalctl -u xiaozhi-server -n 15 --no-pager")

    sftp.close()
    client.close()
    print("\n部署完成。")


if __name__ == "__main__":
    main()
