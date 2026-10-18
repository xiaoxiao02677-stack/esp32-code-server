#!/usr/bin/env python3
"""Sync wake_word minimal set (bd3e0d2d deps) to sandyun.top: backup -> upload -> verify.

Files:
  1. AgentEntity.java        (adds wakeWords field -> getWakeWords() for ConfigServiceImpl)
  2. 202610100930.sql        (ALTER ai_agent ADD wake_words, Liquibase changeSet)
  3. db.changelog-master.yaml(adds 202610100930 changeSet with MARK_RAN preCondition)
  (ConfigServiceImpl.java / DeviceConfigServiceImpl.java already uploaded earlier)
"""
import sys
import paramiko

HOST = "sandyun.top"
PORT = 22222
USER = "root"

LOCAL_BASE = "G:/demo/21_xiaozhi/code-server-mirror/manager-api"
REMOTE_BASE = "/root/xiaozhi-server/main/manager-api"
FILES = [
    "src/main/java/yuhe/modules/agent/entity/AgentEntity.java",
    "src/main/resources/db/changelog/202610100930.sql",
    "src/main/resources/db/changelog/db.changelog-master.yaml",
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
        # 1. 备份远程原文件（仅已存在的；新文件跳过备份）
        for f in FILES:
            rc, out, err = run(client,
                f"if [ -f {REMOTE_BASE}/{f} ]; then cp {REMOTE_BASE}/{f} {REMOTE_BASE}/{f}.bak-{STAMP}; echo BACKED_UP; else echo NEW_FILE; fi")
            print(f"backup {f.split('/')[-1]}: {out} {err[:80]}")
            if "BACKED_UP" not in out and "NEW_FILE" not in out:
                sys.exit(1)

        # 2. 上传
        sftp = client.open_sftp()
        for f in FILES:
            local_path = f"{LOCAL_BASE}/{f}".replace("/", "\\")
            remote_path = f"{REMOTE_BASE}/{f}"
            sftp.put(local_path, remote_path)
            print(f"upload {f.split('/')[-1]}: done")
        sftp.close()

        # 3. 校验：AgentEntity 含 wakeWords；master.yaml 含 202610100930；SQL 文件在位
        checks = [
            (f"grep -c wakeWords {REMOTE_BASE}/src/main/java/yuhe/modules/agent/entity/AgentEntity.java",
             "AgentEntity.wakeWords"),
            (f"grep -c 202610100930 {REMOTE_BASE}/src/main/resources/db/changelog/db.changelog-master.yaml",
             "master.yaml changeSet 202610100930"),
            (f"grep -c 'wake_words' {REMOTE_BASE}/src/main/resources/db/changelog/202610100930.sql",
             "0930.sql wake_words"),
        ]
        all_ok = True
        for cmd, name in checks:
            rc, out, err = run(client, cmd)
            ok = (rc == 0 and out.isdigit() and int(out) > 0)
            print(f"check {name}: rc={rc} count={out} -> {'OK' if ok else 'FAIL'}")
            if not ok:
                all_ok = False
        if not all_ok:
            print("!! 校验失败，恢复备份")
            for f in FILES:
                run(client, f"cp {REMOTE_BASE}/{f}.bak-{STAMP} {REMOTE_BASE}/{f}")
            sys.exit(1)
        print("SYNC OK")
    finally:
        client.close()


if __name__ == "__main__":
    main()
