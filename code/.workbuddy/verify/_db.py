import paramiko
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("sandyun.top", port=22222, username="root", password="Ymm6088.", timeout=25, look_for_keys=False, allow_agent=False)
def sh(cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip(), e.read().decode("utf-8","replace").strip()
MY = 'mysql -uroot -p123456 xiaozhi_esp32_server -N -e'
q = lambda s: sh(f'{MY} "{s}"')[0]
print("=== 1) 44bd 的 device_config ===")
print(q("SELECT device_id, config_json FROM ai_device_config WHERE device_id LIKE '44:bd%' OR device_id LIKE 'yuhe-44bd%'"))
print("\n=== 2) 全表行数 / 含 wake_word_display 的行数 ===")
print("rows_total =", q("SELECT COUNT(*) FROM ai_device_config"))
print("n_display  =", q("SELECT COUNT(*) FROM ai_device_config WHERE config_json LIKE '%wake_word_display%'"))
print("\n=== 3) agent 侧 wake_word 值 ===")
print(q("SELECT id, wake_word FROM ai_agent WHERE id='97254a564446432cba4b21e8fbb6dd74'"))
print("\n=== 4) 表指纹 ===")
print(sh(f"{MY} \"SELECT MD5(GROUP_CONCAT(CONCAT_WS('|',device_id,COALESCE(config_json,''),COALESCE(update_date,'')) ORDER BY device_id)) FROM ai_device_config\"")[0])
print("\n=== 5) 44bd 最后上线时间 ===")
print(sh(f"{MY} \"SELECT device_id,last_connected_at,app_version FROM ai_device WHERE device_id LIKE '44:bd%'\"")[0])
c.close()
