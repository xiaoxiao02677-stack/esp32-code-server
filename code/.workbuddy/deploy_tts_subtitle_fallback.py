#!/usr/bin/env python3
"""部署 TTS 字幕保底修复（base.py）：
冲突检查(远程md5必须等于改前基线) → 备份.bak-ttsfix → SFTP上传 →
md5校验 → 服务器py_compile → 重启yuhe-server → is-active确认。

用法：python deploy_tts_subtitle_fallback.py
"""
import hashlib
import sys

import paramiko

HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."

LOCAL_FILE = r"G:\demo\21_xiaozhi\code-server-mirror\yuhe-server\core\providers\tts\base.py"
REMOTE_ROOT = "/root/xiaozhi-server/main/yuhe-server"
REMOTE_FILE = f"{REMOTE_ROOT}/core/providers/tts/base.py"

# 改前本地基线（部署前远程必须与此一致，否则说明有其他 agent 改过，放弃部署）
PRE_EDIT_MD5 = "3b4977092d78724402dd9205a1505751"
# 改后本地（上传后远程必须与此一致）
NEW_MD5 = "b3252a66cd592bf8cfaac31730eaf22c"


def md5_local(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()


def main():
    local_md5 = md5_local(LOCAL_FILE)
    if local_md5 != NEW_MD5:
        print(f"!! 本地文件与预期改后md5不一致({local_md5})，可能又被改动，中止")
        sys.exit(1)

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

    # 0. 冲突检查：远程 md5 必须等于改前基线
    print("[0/6] 冲突检查")
    rc, o, e = sh(f"md5sum {REMOTE_FILE}")
    remote_md5 = o.split()[0] if o else ""
    print(f"  remote={remote_md5}  expect(pre-edit)={PRE_EDIT_MD5}")
    if remote_md5 != PRE_EDIT_MD5:
        print("  !! 远程 base.py 与本地改前基线不一致（其他agent可能已改动），中止部署")
        sftp.close()
        client.close()
        sys.exit(2)
    print("  无冲突，继续")

    # 1. 备份 .bak-ttsfix
    print("[1/6] 备份")
    rc, o, e = sh(f"cp -f {REMOTE_FILE} {REMOTE_FILE}.bak-ttsfix && md5sum {REMOTE_FILE}.bak-ttsfix")
    if rc != 0 or PRE_EDIT_MD5 not in o:
        print(f"  !! 备份失败: {e or o}")
        sftp.close()
        client.close()
        sys.exit(3)
    print(f"  OK {REMOTE_FILE}.bak-ttsfix")

    # 2. 上传
    print("[2/6] 上传")
    sftp.put(LOCAL_FILE, REMOTE_FILE)
    print(f"  ↑ {REMOTE_FILE}")

    # 3. md5 校验
    print("[3/6] md5 校验")
    rc, o, e = sh(f"md5sum {REMOTE_FILE}")
    got = o.split()[0] if o else ""
    if got != NEW_MD5:
        print(f"  !! 上传后md5不一致 got={got}")
        sftp.close()
        client.close()
        sys.exit(4)
    print(f"  OK {got}")

    # 4. 服务器语法编译（AST/py_compile，用线上 venv）
    print("[4/6] 服务器 py_compile")
    rc, o, e = sh(f"cd {REMOTE_ROOT} && .venv/bin/python -m py_compile {REMOTE_FILE}")
    if rc != 0:
        print(f"  !! py_compile 失败: {e}")
        sftp.close()
        client.close()
        sys.exit(5)
    print("  OK")

    # 5. 重启 + 确认 active
    print("[5/6] 重启 yuhe-server")
    rc, o, e = sh("systemctl restart yuhe-server", timeout=90)
    if rc != 0:
        print(f"  !! restart 失败: {e}")
        sys.exit(6)
    rc, o, e = sh("systemctl is-active yuhe-server")
    print(f"  is-active: {o}")
    if o != "active":
        rc, o, e = sh("systemctl status yuhe-server --no-pager -l | head -30")
        print(o or e)
        sys.exit(7)

    # 6. 快速看启动日志有无报错
    print("[6/6] 启动日志检查")
    rc, o, e = sh("journalctl -u yuhe-server -n 20 --no-pager | tail -20")
    print(o or "(空)")

    sftp.close()
    client.close()
    print("\n结果: 部署成功，服务 active")
    sys.exit(0)


if __name__ == "__main__":
    main()
