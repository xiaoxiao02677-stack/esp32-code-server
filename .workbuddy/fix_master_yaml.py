#!/usr/bin/env python3
"""Upload fixed master.yaml (only 0930 changeSet appended) and restart service."""
import sys
import time
import paramiko

HOST = "sandyun.top"
PORT = 22222
USER = "root"

LOCAL = "C:/Users/34808/AppData/Local/Temp/java-sync/fixed_master.yaml"
REMOTE = "/root/xiaozhi-server/main/manager-api/src/main/resources/db/changelog/db.changelog-master.yaml"


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
        # 上传修复版（当前坏版本已随 2030 备份过，无需再备）
        sftp = client.open_sftp()
        sftp.put(LOCAL, REMOTE)
        sftp.close()
        rc, out, err = run(client,
            f"grep -c '202610100930' {REMOTE}; grep -c '202610090130\\|202610101030\\|202610101100' {REMOTE} || echo 0")
        print(f"master.yaml check: 0930 present, stale refs = {out.splitlines()[-1]}")

        # 重新打包（resources 变更需重新构建 jar）
        rc, out, err = run(client,
            "cd /root/xiaozhi-server/main/manager-api && mvn package -DskipTests -q 2>&1 | tail -3; echo MVN_RC=${PIPESTATUS[0]}",
            timeout=600)
        print(f"rebuild: {out}")
        if "MVN_RC=0" not in out:
            print("!! rebuild failed")
            sys.exit(1)

        # 部署 + 重启
        rc, out, err = run(client,
            "cp /root/xiaozhi-server/main/manager-api/target/xiaozhi-esp32-api.jar /opt/xiaozhi/xiaozhi-esp32-api.jar && systemctl restart xiaozhi-manager-api")
        print(f"deploy+restart: rc={rc} {err[:100]}")

        # 等待启动（Spring Boot + Liquibase 需时间）
        time.sleep(25)
        rc, out, err = run(client, "systemctl is-active xiaozhi-manager-api")
        print(f"service: {out}")
        rc, out, err = run(client, "systemctl show xiaozhi-manager-api -p NRestarts")
        print(f"restarts: {out}")
        rc, out, err = run(client,
            "curl -s -o /dev/null -w 'HTTP=%{http_code}' http://127.0.0.1:8002/yuhe/")
        print(f"health: {out}")
        rc, out, err = run(client,
            "tail -30 /opt/xiaozhi/logs/error.log | grep -E 'Caused by|Exception|ERROR' | tail -5")
        print(f"recent errors: {out if out else '(none)'}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
