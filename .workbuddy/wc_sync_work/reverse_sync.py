import paramiko, os, hashlib

HOST, PORT, USER, PWD = "sandyun.top", 22222, "root", "Ymm6088."
REMOTE_BASE = "/root/xiaozhi-server/main/xiaozhi-server"
LOCAL_BASE = "G:/demo/21_xiaozhi/code-server-mirror/xiaozhi-server"

FILES = [
    "core/providers/tts/base.py",
    "core/utils/modules_initialize.py",
    "core/api/wake_word_handler.py",
    "core/connection.py",
    "core/websocket_server.py",
    "app.py",
    "core/http_server.py",
    "core/services/wake_word_service.py",
]

cli = paramiko.SSHClient(); cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
cli.connect(HOST, port=PORT, username=USER, password=PWD, timeout=15,
            banner_timeout=15, auth_timeout=15, look_for_keys=False, allow_agent=False)
sftp = cli.open_sftp()

for rel in FILES:
    rpath = f"{REMOTE_BASE}/{rel}"
    lpath = os.path.join(LOCAL_BASE, rel)
    # local md5 before (normalized)
    def nmd5(path):
        try:
            with open(path, "rb") as f:
                return hashlib.md5(f.read().replace(b"\r\n", b"\n")).hexdigest()
        except FileNotFoundError:
            return None
    before = nmd5(lpath)
    sftp.get(rpath, lpath)
    after = nmd5(lpath)
    # remote md5 normalized via bash
    stdin, stdout, stderr = cli.exec_command(f"md5sum <(tr -d '\r' < {rpath}) | awk '{{print $1}}'", timeout=15)
    rmd5 = stdout.read().decode().strip()
    status = "SAME" if before == after else "UPDATED"
    match = "OK" if after == rmd5 else "MISMATCH!"
    print(f"{status:8s} {match:9s} {rel}  (before={before}, after={after}, remote={rmd5})")

sftp.close(); cli.close()
print("REVERSE_SYNC_DONE")
