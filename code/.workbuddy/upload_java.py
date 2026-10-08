#!/usr/bin/env python3
"""批量 sftp 上传（Java 源码镜像 → 服务器 manager-api）"""
import sys
sys.path.insert(0, r"G:\demo\21_xiaozhi\code\.workbuddy")
from ssh_run import get_client

PAIRS = [
    (r"G:\demo\21_xiaozhi\code-server-mirror\manager-api\src\main\java\xiaozhi\modules\model\dto\VoiceDTO.java",
     "/root/xiaozhi-server/main/manager-api/src/main/java/xiaozhi/modules/model/dto/VoiceDTO.java"),
    (r"G:\demo\21_xiaozhi\code-server-mirror\manager-api\src\main\java\xiaozhi\modules\timbre\entity\TimbreEntity.java",
     "/root/xiaozhi-server/main/manager-api/src/main/java/xiaozhi/modules/timbre/entity/TimbreEntity.java"),
    (r"G:\demo\21_xiaozhi\code-server-mirror\manager-api\src\main\java\xiaozhi\modules\timbre\dto\TimbreDataDTO.java",
     "/root/xiaozhi-server/main/manager-api/src/main/java/xiaozhi/modules/timbre/dto/TimbreDataDTO.java"),
    (r"G:\demo\21_xiaozhi\code-server-mirror\manager-api\src\main\java\xiaozhi\modules\timbre\vo\TimbreDetailsVO.java",
     "/root/xiaozhi-server/main/manager-api/src/main/java/xiaozhi/modules/timbre/vo/TimbreDetailsVO.java"),
    (r"G:\demo\21_xiaozhi\code-server-mirror\manager-api\src\main\java\xiaozhi\modules\timbre\service\impl\TimbreServiceImpl.java",
     "/root/xiaozhi-server/main/manager-api/src/main/java/xiaozhi/modules/timbre/service/impl/TimbreServiceImpl.java"),
    (r"G:\demo\21_xiaozhi\code-server-mirror\manager-api\src\main\java\xiaozhi\modules\config\service\impl\ConfigServiceImpl.java",
     "/root/xiaozhi-server/main/manager-api/src/main/java/xiaozhi/modules/config/service/impl/ConfigServiceImpl.java"),
]

client = get_client()
sftp = client.open_sftp()
for local, remote in PAIRS:
    sftp.put(local, remote)
    print(f"OK {remote}")
sftp.close()
client.close()
print("ALL_UPLOADED")
