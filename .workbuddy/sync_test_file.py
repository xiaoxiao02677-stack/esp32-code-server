#!/usr/bin/env python3
"""Upload fixed ConfigServiceImplTest.java (constructor mock updated)."""
import sys
import paramiko

HOST = "sandyun.top"
PORT = 22222
USER = "root"

LOCAL = "G:/demo/21_xiaozhi/code-server-mirror/manager-api/src/test/java/yuhe/modules/config/service/impl/ConfigServiceImplTest.java".replace("/", "\\")
REMOTE = "/root/xiaozhi-server/main/manager-api/src/test/java/yuhe/modules/config/service/impl/ConfigServiceImplTest.java"
STAMP = "20261010T2030"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, port=PORT, username=USER, password="Ymm6088.",
               timeout=15, banner_timeout=15, auth_timeout=15,
               look_for_keys=False, allow_agent=False)
try:
    stdin, stdout, stderr = client.exec_command(f"cp {REMOTE} {REMOTE}.bak-{STAMP}", timeout=60)
    rc = stdout.channel.recv_exit_status()
    print(f"backup: rc={rc}")
    sftp = client.open_sftp()
    sftp.put(LOCAL, REMOTE)
    sftp.close()
    print("upload: done")
    stdin, stdout, stderr = client.exec_command(f"grep -c 'DeviceConfigService' {REMOTE}", timeout=60)
    print(f"verify: {stdout.read().decode().strip()}")
finally:
    client.close()
