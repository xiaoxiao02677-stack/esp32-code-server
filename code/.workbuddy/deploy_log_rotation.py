#!/usr/bin/env python3
"""部署日志追加 + logrotate：上传配置 → 演练 → 强制跑一次 → 验证。"""
import time
import paramiko

HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
STAMP = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=PASSWORD,
              timeout=20, look_for_keys=False, allow_agent=False)
    sftp = c.open_sftp()

    def sh(cmd, t=180):
        _, o, e = c.exec_command(cmd, timeout=t)
        return (o.read().decode("utf-8", "replace").strip(),
                e.read().decode("utf-8", "replace").strip())

    print("=" * 62)
    print("步骤 0: 现状确认（是否还有覆盖写）")
    print("=" * 62)
    print(sh("grep -H -E 'StandardOutput|StandardError' "
             "/etc/systemd/system/xiaozhi-server.service "
             "/etc/systemd/system/xiaozhi-manager-api.service")[0])
    print("\n轮转前大小:")
    print(sh("du -h /root/xiaozhi-server/main/xiaozhi-server/data/app.log "
             "/opt/xiaozhi/manager-api.log")[0])
    print("\ncron.daily 是否存在:")
    print(sh("ls -l /etc/cron.daily/logrotate")[0])

    print()
    print("=" * 62)
    print("步骤 1: 上传 logrotate 配置")
    print("=" * 62)
    sh("test -f /etc/logrotate.d/xiaozhi && cp -a /etc/logrotate.d/xiaozhi "
       f"/etc/logrotate.d/xiaozhi.bak-{STAMP} || true")
    sftp.put(r"G:\demo\21_xiaozhi\code\.workbuddy\logrotate_xiaozhi.conf",
             "/etc/logrotate.d/xiaozhi")
    sh("chmod 644 /etc/logrotate.d/xiaozhi")
    print(sh("cat /etc/logrotate.d/xiaozhi")[0])

    print()
    print("=" * 62)
    print("步骤 2: 语法/演练（logrotate -d，不实际操作）")
    print("=" * 62)
    o, e = sh("logrotate -d /etc/logrotate.d/xiaozhi 2>&1 | tail -25")
    print(o)
    if e:
        print("[ERR]", e)

    print()
    print("=" * 62)
    print("步骤 3: 强制轮转一次，验证 copytruncate 生效")
    print("=" * 62)
    print(sh("logrotate -f /etc/logrotate.d/xiaozhi 2>&1")[0])
    print("\n轮转后:")
    print(sh("ls -la /root/xiaozhi-server/main/xiaozhi-server/data/app.log* "
             "/opt/xiaozhi/manager-api.log*")[0])

    print()
    print("=" * 62)
    print("步骤 4: 确认服务仍在往原文件写（fd 没断）")
    print("=" * 62)
    print(sh("systemctl is-active xiaozhi-server xiaozhi-manager-api")[0])
    print(sh("sleep 8; tail -2 /root/xiaozhi-server/main/xiaozhi-server/data/app.log")[0])

    sftp.close(); c.close()
    print("\n完成。")


if __name__ == "__main__":
    main()
