#!/usr/bin/env python3
"""批次3 Java 部署：jar 上传 + systemctl restart + 验活。"""
import sys
import time

sys.path.insert(0, r"G:\demo\21_xiaozhi\code\.workbuddy")
from ssh_run import get_client  # noqa: E402

JAR_LOCAL = r"G:\demo\21_xiaozhi\code-server-mirror\manager-api\target\xiaozhi-esp32-api.jar"
JAR_REMOTE = "/opt/xiaozhi/xiaozhi-esp32-api.jar"
STAMP = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def sh(client, cmd, timeout=120):
    _, out, err = client.exec_command(cmd, timeout=timeout)
    o = out.read().decode("utf-8", "replace").strip()
    e = err.read().decode("utf-8", "replace").strip()
    rc = out.channel.recv_exit_status()
    if o:
        print(o[-500:])
    if e and rc != 0:
        print("[stderr]", e[-300:])
    return rc, o


def main():
    client = get_client()
    try:
        print("== 1. 备份 ==")
        sh(client, f"cp {JAR_REMOTE} {JAR_REMOTE}.bak-{STAMP}")
        print("\n== 2. 上传 ==")
        sftp = client.open_sftp()
        sftp.put(JAR_LOCAL, JAR_REMOTE)
        sftp.close()
        print("上传完成")
        print("\n== 3. 重启 ==")
        sh(client, "systemctl restart xiaozhi-manager-api")
        time.sleep(22)
        sh(client, "systemctl is-active xiaozhi-manager-api")
        print("\n== 4. 验活 ==")
        sh(client, "curl -s -o /dev/null -w 'manager-api: %{http_code}\\n' http://127.0.0.1:8002/yuhe/user/pub-config")
        sh(client, "unzip -p /opt/xiaozhi/xiaozhi-esp32-api.jar BOOT-INF/classes/yuhe/common/config/SwaggerConfig.class | strings | grep -c 屿禾 || echo 0")
        print("\nDEPLOY_JAVA_DONE")
    finally:
        client.close()


if __name__ == "__main__":
    main()
