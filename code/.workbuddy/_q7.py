import paramiko
HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20, look_for_keys=False, allow_agent=False)
def sh(cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip()
print(sh("mysql -uroot -p123456 xiaozhi_esp32_server -e \"show tables;\" 2>&1 | grep -i -E 'model|config'"))
print("---")
print(sh("mysql -uroot -p123456 xiaozhi_esp32_server -e \"select id,name,model_type,config_json from ai_model_config where id='3248df0b7c0774f322ee0db56e8875d8';\" 2>&1 | head -20"))
c.close()
