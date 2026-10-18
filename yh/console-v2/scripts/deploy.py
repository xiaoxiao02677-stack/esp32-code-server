#!/usr/bin/env python3
"""部署 console-v2 到 sandyun.top（客户端 / + 管理端 /admincc/）。
tar 打包用 Git Bash；传输用 paramiko SFTP（绕开 argv 长度限制）。"""
import base64
import subprocess
import sys

sys.path.insert(0, r"G:\demo\21_xiaozhi\code\.workbuddy")

HOST = "sandyun.top"
PORT = 22222
USER = "root"
PASSWORD = "Ymm6088."

GIT_BASH = r"D:\INSTALL\Git\usr\bin\bash.exe"
LOCAL_TMP = r"G:\demo\21_xiaozhi\.workbuddy\v2_upload.tar.gz"


def make_tar(local_dir, out_path):
    posix_dir = local_dir.replace("\\", "/")
    posix_out = out_path.replace("\\", "/")
    # --force-local: Windows 盘符冒号（G:）会被 GNU tar 误认为远程主机
    r = subprocess.run(
        [GIT_BASH, "-c", f"tar --force-local -czf '{posix_out}' -C '{posix_dir}' ."],
        capture_output=True
    )
    if r.returncode != 0:
        raise RuntimeError("tar failed: " + r.stderr.decode(errors="ignore")[:300])


def ssh_exec(client, cmd):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=120)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    rc = stdout.channel.recv_exit_status()
    if out:
        print(out.rstrip()[-500:])
    if err and rc != 0:
        print("[stderr]", err.rstrip()[-300:])
    return out, rc


def upload_and_extract(client, local_tar, remote_dir, tag):
    remote_tar = f"/tmp/v2up/{tag}.tar.gz"
    ssh_exec(client, "mkdir -p /tmp/v2up " + remote_dir)
    sftp = client.open_sftp()
    sftp.put(local_tar, remote_tar)
    sftp.close()
    ssh_exec(client, f"rm -rf {remote_dir}/* && tar -xzf {remote_tar} -C {remote_dir} && ls {remote_dir} | head -4 && echo UPLOAD_{tag}_OK")


def main():
    import paramiko

    print("== 1. 打包 ==")
    make_tar(r"G:\demo\21_xiaozhi\yh\console-v2\dist", LOCAL_TMP)
    app_tar = LOCAL_TMP
    make_tar(r"G:\demo\21_xiaozhi\yh\console-v2\dist-admin", LOCAL_TMP)
    admin_tar = LOCAL_TMP
    print("打包完成")

    print("\n== 2. 连接服务器 ==")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=PASSWORD,
                   timeout=15, banner_timeout=15, auth_timeout=15,
                   look_for_keys=False, allow_agent=False)

    try:
        print("\n== 3. 上传 app（客户端 /）==")
        make_tar(r"G:\demo\21_xiaozhi\yh\console-v2\dist", LOCAL_TMP)
        upload_and_extract(client, LOCAL_TMP, "/var/www/console-v2/app", "app")

        print("\n== 4. 上传 admin（/admincc/）==")
        make_tar(r"G:\demo\21_xiaozhi\yh\console-v2\dist-admin", LOCAL_TMP)
        upload_and_extract(client, LOCAL_TMP, "/var/www/console-v2/admin", "admin")

        print("\n== 5. nginx 配置 ==")
        out, rc = ssh_exec(client, "grep -c console-v2 /etc/nginx/sites-enabled/xiaozhi-manager")
        already = "1" in out.strip().split("\n")[-1] if out.strip() else False
        if not already:
            ssh_exec(client, "cp /etc/nginx/sites-enabled/xiaozhi-manager /etc/nginx/xiaozhi-manager.bak-v2")
            py_code = """p='/etc/nginx/sites-enabled/xiaozhi-manager'
s=open(p).read()
anchor='    # 独立 API 控制台（全新项目，Kawaii + stylekit 动效）'
block=\"\"\"    # ===== console-v2 双端点（2026-10-08 部署）=====
    # 客户端 /
    location = / {
        root /var/www/console-v2/app;
        try_files /index.html =404;
    }
    location /assets/ {
        root /var/www/console-v2/app;
        try_files $uri =404;
    }
    # 管理端 /admincc/
    location /admincc/ {
        alias /var/www/console-v2/admin/;
        index index.html;
        try_files $uri $uri/ /admincc/index.html;
    }

\"\"\"
assert anchor in s, 'anchor missing'
s=s.replace(anchor, block+anchor)
open(p,'w').write(s)
print('patched')"""
            b = base64.b64encode(py_code.encode()).decode()
            ssh_exec(client, f"echo {b} | base64 -d > /tmp/patch.py && python3 /tmp/patch.py")

        print("\n== 6. 校验并重载 ==")
        ssh_exec(client, "nginx -t 2>&1 && nginx -s reload && echo NGINX_RELOADED")

        print("\n== 7. 验证 ==")
        ssh_exec(client, "curl -sk -o /dev/null -w 'root: %{http_code}\\n' https://127.0.0.1:9443/ -H 'Host: sandyun.top'")
        ssh_exec(client, "curl -sk -o /dev/null -w 'admincc: %{http_code}\\n' https://127.0.0.1:9443/admincc/ -H 'Host: sandyun.top'")
        ssh_exec(client, "curl -sk -o /dev/null -w 'cc-old: %{http_code}\\n' https://127.0.0.1:9443/cc/ -H 'Host: sandyun.top'")
        ssh_exec(client, "curl -sk https://127.0.0.1:9443/admincc/ -H 'Host: sandyun.top' | grep -o 'src=\\\"[^\\\"]*\\\"' | head -1")
        print("\nDEPLOY_DONE")
    finally:
        client.close()


if __name__ == "__main__":
    main()
