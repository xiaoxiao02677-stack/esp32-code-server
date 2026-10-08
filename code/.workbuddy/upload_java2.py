#!/usr/bin/env python3
"""上传试听链路修复的 2 个 Java 文件"""
import sys
sys.path.insert(0, r"G:\demo\21_xiaozhi\code\.workbuddy")
from ssh_run import get_client

PAIRS = [
    (r"G:\demo\21_xiaozhi\code-server-mirror\manager-api\src\main\java\xiaozhi\modules\model\controller\TtsPreviewController.java",
     "/root/xiaozhi-server/main/manager-api/src/main/java/xiaozhi/modules/model/controller/TtsPreviewController.java"),
    (r"G:\demo\21_xiaozhi\code-server-mirror\manager-api\src\main\java\xiaozhi\modules\timbre\service\impl\TimbreServiceImpl.java",
     "/root/xiaozhi-server/main/manager-api/src/main/java/xiaozhi/modules/timbre/service/impl/TimbreServiceImpl.java"),
]
client = get_client()
sftp = client.open_sftp()
for local, remote in PAIRS:
    sftp.put(local, remote)
    print(f"OK {remote}")
sftp.close()
client.close()
print("DONE")
