# -*- coding: utf-8 -*-
"""只读取证：interrupt_threshold 的下发记录 + 设备连接状态 + DB 当前值。
生产 sandyun.top:22222 / 日志 /root/xiaozhi-server/main/yuhe-server/data/app.log
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import paramiko

HOST, PORT, USER = "sandyun.top", 22222, "root"
LOG = "/root/xiaozhi-server/main/yuhe-server/data/app.log"

def run(ssh, cmd, label, maxlen=4000):
    print(f"\n===== {label} =====")
    _, out, err = ssh.exec_command(cmd, timeout=60)
    o = out.read().decode('utf-8', errors='replace')
    e = err.read().decode('utf-8', errors='replace')
    if o.strip():
        print(o[:maxlen] + ("\n...[截断]" if len(o) > maxlen else ""))
    else:
        print("(无输出)")
    if e.strip():
        print("[stderr]", e[:500])

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, port=PORT, username=USER, timeout=30)
try:
    run(ssh, f"date '+%F %T %z'", "服务器当前时间")
    # 1) 今天全部 interrupt_threshold 相关行
    run(ssh, f"grep -n 'interrupt_threshold' {LOG} | tail -40", "app.log 全部 interrupt_threshold 行(尾部40)", 8000)
    # 2) 21:28 之后 44:bd 的连接事件
    run(ssh, f"grep -n '44:bd' {LOG} | grep -E 'conn|Headers|device-id|close|断开' | tail -25", "设备 44:bd 连接事件(尾部25)", 6000)
    # 3) Java 侧：journalctl 实时打断
    run(ssh, "journalctl -u xiaozhi-manager-api --since '21:25' --no-pager 2>/dev/null | grep -iE 'interrupt|打断|device.config|applyDevice' | tail -30", "Java journalctl 打断相关(21:25后)", 6000)
    # 4) Python 侧 21:28 后的 device_config 下发
    run(ssh, f"awk '/^261017 21:2[89]/,0' {LOG} | grep -E '已下发云端设备配置|异步获取差异化配置成功|离线|缓存' | tail -25", "21:28后 下发/离线队列 活动", 6000)
    # 5) DB 当前值
    run(ssh, """mysql -N -e "SELECT device_id, JSON_UNQUOTE(JSON_EXTRACT(config_json,'$.interrupt_threshold')), update_date FROM `ai_yuhe`.`ai_device_config` WHERE device_id='44:bd:8d:7b:3a:e4'" 2>/dev/null || mysql -N -e 'SELECT 1' 2>&1 | head -3""", "DB 尝试(可能需密码,失败则跳过)", 2000)
finally:
    ssh.close()
    print("\n[done] 只读，未写远端")
