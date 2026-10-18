# -*- coding: utf-8 -*-
"""第三轮：只查 DB 当前值 + binlog 最新写入"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("sandyun.top", port=22222, username="root", timeout=30)
try:
    def run(cmd, label):
        print(f"\n===== {label} =====")
        _, out, err = ssh.exec_command(cmd, timeout=50)
        o = out.read().decode('utf-8', errors='replace')
        e = err.read().decode('utf-8', errors='replace')
        print(o[:3000] if o.strip() else "(无输出)")
        if e.strip(): print("[stderr]", e[:200])
    # 找 MySQL 凭据（Java yml 里 datasource 段）
    run("grep -B2 -A6 'datasource' /opt/xiaozhi/application-dev.yml | sed 's/password:.*/password: ***/' | head -12", "datasource 结构(密码打码)")
    # 用 python 读凭据再查（避免 shell 引号地狱），密码只在远端用
    run("""python3 - <<'EOF'
import re, subprocess
yml = open('/opt/xiaozhi/application-dev.yml', encoding='utf-8').read()
m = re.search(r'password:\s*(\S+)', yml)
user = re.search(r'username:\s*(\S+)', yml)
url = re.search(r'jdbc:mysql://([^/:]+)(?::(\d+))?/(\w+)', yml)
if not (m and url):
    print('凭据未找到'); raise SystemExit
pw, un, db = m.group(1), user.group(1) if user else 'root', url.group(3)
import pymysql
try:
    conn = pymysql.connect(host='127.0.0.1', user=un, password=pw, database=db)
except Exception:
    import subprocess as sp
    # 无 pymysql 就走 mysql cli
    q = "SELECT device_id, JSON_EXTRACT(config_json,'$.interrupt_threshold'), update_date FROM ai_device_config WHERE device_id='44:bd:8d:7b:3a:e4'"
    r = sp.run(['mysql','-h','127.0.0.1','-u',un,f'-p{pw}',db,'-N','-e',q], capture_output=True, text=True)
    print(r.stdout or r.stderr[:300]); raise SystemExit
cur = conn.cursor()
cur.execute("SELECT device_id, JSON_EXTRACT(config_json,'$.interrupt_threshold'), update_date FROM ai_device_config WHERE device_id='44:bd:8d:7b:3a:e4'")
print('44:bd device_config:', cur.fetchall())
cur.execute("SELECT interrupt_threshold FROM ai_agent WHERE id='97254a564446432cba4b21e8fbb6dd74'")
print('agent 表 threshold:', cur.fetchall())
conn.close()
EOF""", "DB 当前值")
finally:
    ssh.close()
    print("\n[done] 只读")
