#!/usr/bin/env python3
"""sftp 上传文件到服务器"""
import sys
sys.path.insert(0, r"G:\demo\21_xiaozhi\code\.workbuddy")
from ssh_run import get_client

local, remote = sys.argv[1], sys.argv[2]
client = get_client()
sftp = client.open_sftp()
sftp.put(local, remote)
st = sftp.stat(remote)
print(f"UPLOADED {local} -> {remote} ({st.st_size} bytes)")
sftp.close()
client.close()
