#!/usr/bin/env python3
"""Deploy xiaozhi-esp32-api.jar to sandyun.top (backup, upload, restart, verify)."""
import sys
import time
import paramiko

HOST = "sandyun.top"
PORT = 22222
USER = "root"
PASSWORD = "Ymm6088."
LOCAL_JAR = r"G:/demo/21_xiaozhi/code-server-mirror/manager-api/target/xiaozhi-esp32-api.jar"
REMOTE_DIR = "/opt/xiaozhi/"
REMOTE_JAR = REMOTE_DIR + "xiaozhi-esp32-api.jar"


def get_client():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=PASSWORD,
                   timeout=15, banner_timeout=15, auth_timeout=15,
                   look_for_keys=False, allow_agent=False)
    return client


def run(client, cmd, timeout=60):
    print(f"\n$ {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    rc = stdout.channel.recv_exit_status()
    if out:
        print(out.rstrip())
    if err:
        print("[stderr]", err.rstrip())
    print(f"[rc={rc}]")
    return rc, out, err


def main():
    client = get_client()
    try:
        # 1. backup
        ts = time.strftime("%Y%m%d-%H%M%S")
        rc, _, _ = run(client, f"cp {REMOTE_JAR} {REMOTE_JAR}.bak-{ts}")
        if rc != 0:
            print("!! backup failed, aborting")
            sys.exit(1)

        # 2. upload via SFTP
        print(f"\n# uploading {LOCAL_JAR} -> {REMOTE_JAR}")
        sftp = client.open_sftp()
        sftp.put(LOCAL_JAR, REMOTE_JAR)
        st = sftp.stat(REMOTE_JAR)
        print(f"uploaded, remote size = {st.st_size}")
        sftp.close()

        # 3. restart + check
        run(client, "systemctl restart xiaozhi-manager-api")
        time.sleep(15)
        rc, out, _ = run(client, "systemctl is-active xiaozhi-manager-api")
        if rc != 0 or "active" not in out:
            print("!! service not active, dumping status")
            run(client, "systemctl status xiaozhi-manager-api --no-pager -l | head -30")
            sys.exit(1)

        # 4. endpoint check
        rc, out, _ = run(client,
            "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8002/yuhe/user/pub-config",
            timeout=30)
        print(f"pub-config HTTP status: {out} (rc={rc})")

        # 5. verify wake_words inside new jar
        rc, out, _ = run(client,
            "cd /tmp && rm -rf jarcheck && mkdir jarcheck && cd jarcheck && "
            "unzip -o -q /opt/xiaozhi/xiaozhi-esp32-api.jar "
            "'BOOT-INF/classes/yuhe/modules/config/service/impl/ConfigServiceImpl.class' && "
            "strings BOOT-INF/classes/yuhe/modules/config/service/impl/ConfigServiceImpl.class | grep -i wake")
        if "wake_words" in out and "wakeup_words" in out:
            print("PASS: new jar contains wake_words + wakeup_words")
        else:
            print("FAIL: wake strings missing in jar")
            sys.exit(1)

        print("\nALL DEPLOY STEPS DONE")
    finally:
        client.close()


if __name__ == "__main__":
    main()
