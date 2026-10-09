#!/usr/bin/env python3
"""批次2 后端部署：jar + Python 4 文件 + 双服务重启 + 验活。

用法：python deploy_batch2_backend.py
"""
import sys
import time

sys.path.insert(0, r"G:\demo\21_xiaozhi\code\.workbuddy")
from ssh_run import get_client  # noqa: E402

JAR_LOCAL = r"G:\demo\21_xiaozhi\code-server-mirror\manager-api\target\xiaozhi-esp32-api.jar"
JAR_REMOTE = "/opt/xiaozhi/xiaozhi-esp32-api.jar"

PY_FILES = [
    (r"G:\demo\21_xiaozhi\code-server-mirror\xiaozhi-server\core\heartbeat.py",
     "/root/xiaozhi-server/main/xiaozhi-server/core/heartbeat.py"),
    (r"G:\demo\21_xiaozhi\code-server-mirror\xiaozhi-server\core\connection.py",
     "/root/xiaozhi-server/main/xiaozhi-server/core/connection.py"),
    (r"G:\demo\21_xiaozhi\code-server-mirror\xiaozhi-server\core\utils\wakeup_word.py",
     "/root/xiaozhi-server/main/xiaozhi-server/core/utils/wakeup_word.py"),
    (r"G:\demo\21_xiaozhi\code-server-mirror\xiaozhi-server\app.py",
     "/root/xiaozhi-server/main/xiaozhi-server/app.py"),
]
STAMP = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def sh(client, cmd, timeout=120):
    _, out, err = client.exec_command(cmd, timeout=timeout)
    o = out.read().decode("utf-8", "replace").strip()
    e = err.read().decode("utf-8", "replace").strip()
    rc = out.channel.recv_exit_status()
    if o:
        print(o[-600:])
    if e and rc != 0:
        print("[stderr]", e[-300:])
    return rc, o


def main():
    client = get_client()
    try:
        print("== 1. 备份 ==")
        sh(client, f"cp {JAR_REMOTE} {JAR_REMOTE}.bak-{STAMP}")
        for _, remote in PY_FILES:
            sh(client, f"cp {remote} {remote}.bak-{STAMP}")

        print("\n== 2. 上传（SFTP）==")
        sftp = client.open_sftp()
        sftp.put(JAR_LOCAL, JAR_REMOTE)
        for local, remote in PY_FILES:
            sftp.put(local, remote)
        sftp.close()
        print("上传完成")

        print("\n== 3. Python 语法检查（服务器 venv）==")
        rc, _ = sh(client,
                   "cd /root/xiaozhi-server/main/xiaozhi-server && "
                   ".venv/bin/python -m py_compile core/heartbeat.py core/connection.py "
                   "core/utils/wakeup_word.py app.py && echo PY_COMPILE_OK")

        print("\n== 4. 重启 Java（Liquibase 迁移随启动执行）==")
        sh(client, "systemctl restart xiaozhi-manager-api && echo JAVA_RESTARTED")
        time.sleep(18)
        sh(client, "systemctl is-active xiaozhi-manager-api")

        print("\n== 5. 重启 Python ==")
        sh(client, "pkill -f 'xiaozhi-server/main/xiaozhi-server'; pkill -f 'venv/bin/python app.py'; sleep 3; true")
        sh(client, "cd /root/xiaozhi-server/main/xiaozhi-server && "
                   "setsid nohup .venv/bin/python app.py > /tmp/xiaozhi-server.log 2>&1 < /dev/null & echo PY_STARTED",
            timeout=20)
        time.sleep(12)
        sh(client, "ps -eo pid,etime,cmd | grep '[a]pp.py' | head -3")

        print("\n== 6. 验活 ==")
        sh(client, "curl -s -o /dev/null -w 'manager-api 8002: %{http_code}\\n' http://127.0.0.1:8002/xiaozhi/user/pub-config")
        sh(client, "ss -lnt | grep -E ':(8000|8003|12399)' || echo '端口未监听!'")
        sh(client, "journalctl -u xiaozhi-manager-api -n 8 --no-pager | tail -8")

        print("\nDEPLOY_BACKEND_DONE")
    finally:
        client.close()


if __name__ == "__main__":
    main()
