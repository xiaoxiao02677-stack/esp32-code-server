import paramiko
HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20, look_for_keys=False, allow_agent=False)
def sh(cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip()
print("=== models ===")
print(sh("mysql -uroot -p123456 xiaozhi_esp32_server -e 'select id,name,type,config_json from ai_tts_model;' 2>&1 | head -40"))
print("=== voices ===")
print(sh("mysql -uroot -p123456 xiaozhi_esp32_server -e 'select id,name,tts_model_id,voice_id,instruction,dynamic_instruction,instruction_llm_id from ai_tts_voice;' 2>&1 | head -40"))
c.close()
