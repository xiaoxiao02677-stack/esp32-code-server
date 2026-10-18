import paramiko
HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20, look_for_keys=False, allow_agent=False)
def sh(cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip()
print(sh("grep -n -A10 'datasource' /root/xiaozhi-server/main/manager-api/target/classes/application-dev.yml | head -25"))
print("--- config_from_api TTS ---")
print(sh("grep -n -A30 '^  TTS' /root/xiaozhi-server/main/yuhe-server/config_from_api.yaml | head -60"))
c.close()
