import paramiko
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("sandyun.top", port=22222, username="root", password="Ymm6088.", timeout=25, look_for_keys=False, allow_agent=False)
def sh(cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip()
MY = 'mysql -uroot -p123456 xiaozhi_esp32_server -N -e'
q = lambda s: sh(f'{MY} "{s}"')
print("=== 1) ai_device_config 44bd ===")
print(q("SELECT config_json FROM ai_device_config WHERE device_id='44:bd:8d:7b:3a:e4'"))
print("\n=== 2) 全表 n_display ===")
print("rows=", q("SELECT COUNT(*) FROM ai_device_config"), "n_display=", q("SELECT COUNT(*) FROM ai_device_config WHERE config_json LIKE '%wake_word_display%'"))
print("\n=== 3) ai_agent 表结构里的唤醒词字段 ===")
print(sh(f"{MY} \"SHOW COLUMNS FROM ai_agent LIKE '%wake%'\""))
print("\n=== 4) ai_agent 全表唤醒词相关值 ===")
print(q("SELECT id, nick_name, wake_word FROM ai_agent") or "(无该列)")
print("\n=== 5) ai_agent_wake_word（死代码表，看是否被写）===")
print(q("SELECT COUNT(*) FROM ai_agent_wake_word") or "(表不存在)")
c.close()
