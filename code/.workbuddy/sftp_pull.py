#!/usr/bin/env python3
import sys
import paramiko

HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
remote, local = sys.argv[1], sys.argv[2]

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, port=PORT, username=USER, password=PASSWORD,
               timeout=15, look_for_keys=False, allow_agent=False)
sftp = client.open_sftp()
print(f"pulling {remote} -> {local}")
sftp.get(remote, local)
sftp.close()
client.close()
print("done")
