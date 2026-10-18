# -*- coding: utf-8 -*-
"""第二轮取证：21:51 后的下发记录 + DB 当前值（密码从配置文件取）"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import paramiko

HOST, PORT, USER = "sandyun.top", 22222, "root"
LOG = "/root/xiaozhi-server/main/yuhe-server/data/app.log"

def run(ssh, cmd, label, maxlen=5000):
    print(f"\n===== {label} =====")
    _, out, err = ssh.exec_command(cmd, timeout=60)
    o = out.read().decode('utf-8', errors='replace')
    e = err.read().decode('utf-8', errors='replace')
    print((o[:maxlen] + ("\n...[截断]" if len(o) > maxlen else "")) if o.strip() else "(无输出)")
    if e.strip(): print("[stderr]", e[:300])

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, port=PORT, username=USER, timeout=30)
try:
    # 1) 只提取「已下发云端设备配置」的精简行（避免大 payload 淹没）
    run(ssh, f"grep -n '已下发云端设备配置' {LOG} | tail -15", "下发记录精简行(尾部15)", 3000)
    # 2) 21:50 后全部 conn 事件（用户保存后设备有没有重连）
    run(ssh, f"awk '/^261017 21:5[0-9]/,0' {LOG} | grep -c 'device-id.: .44:bd'", "21:50后 44:bd 连接次数", 500)
    run(ssh, f"awk '/^261017 21:5[0-9]/,0' {LOG} | grep 'conn - Headers' | tail -3 | cut -c1-200", "21:50后最后3次连接头", 1000)
    # 3) 1.5 那条 WARNING 的上下文（前后各5行）
    run(ssh, f"grep -n -B5 -A5 '忽略非整数配置' {LOG} | cut -c1-250", "1.5 WARNING 上下文", 4000)
    # 4) MySQL 密码（从 Java 配置取）
    run(ssh, "grep -A3 'datasource' /opt/xiaozhi/application-dev.yml 2>/dev/null | head -8; ls /opt/xiaozhi/*.yml 2>/dev/null", "Java 配置位置", 1500)
    # 5) 用配置里的凭据查 DB（在远端执行，密码不过网到本地）
    run(ssh, r"""PW=$(grep -oP 'password:\s*\K\S+' /opt/xiaozhi/application-dev.yml | head -1); mysql -h127.0.0.1 -uroot -p"$PW" -N -e "SELECT device_id, JSON_EXTRACT(config_json,'$.interrupt_threshold') AS it, JSON_EXTRACT(config_json,'$.wake_word') AS ww, update_date FROM ai_yuhe.ai_device_config WHERE device_id='44:bd:8d:7b:3a:e4'" 2>&1 | grep -v Warning""",
        "DB 当前值(44:bd)", 2000)
    run(ssh, r"""PW=$(grep -oP 'password:\s*\K\S+' /opt/xiaozhi/application-dev.yml | head -1); mysql -h127.0.0.1 -uroot -p"$PW" -N -e "SELECT id, agent_name, interrupt_threshold FROM ai_yuhe.ai_agent WHERE id='97254a564446432cba4b21e8fbb6dd74'" 2>&1 | grep -v Warning""",
        "DB agent 表阈值", 2000)
finally:
    ssh.close()
    print("\n[done] 只读")
