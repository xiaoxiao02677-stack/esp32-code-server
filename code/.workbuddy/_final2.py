import paramiko, time, re
HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20, look_for_keys=False, allow_agent=False)
def sh(cmd, t=120):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip(), e.read().decode("utf-8","replace").strip()
time.sleep(45)
out = sh(r"grep -E 'conn - Headers' /root/xiaozhi-server/main/yuhe-server/data/app.log")[0]
rows=[]
for line in out.splitlines():
    m = re.match(r"(\d{6} \d{2}:\d{2}:\d{2}).*?-INFO-(\S+) conn - Headers: (.*)", line)
    if not m: continue
    t, ip, hdr = m.groups()
    dm = re.search(r"'device-id': '([^']*)'", hdr)
    rows.append((t, ip, dm.group(1) if dm else "?"))
print(f"{'时间':10s} {'客户端IP':16s} {'device-id'}")
for t, ip, d in rows:
    mark = "  <- 探针" if d.startswith("pp") else ""
    print(f"{t:10s} {ip:16s} {d}{mark}")
print("\n结论：非探针连接是否已有真实 IP：",
      "是" if any(not d.startswith("pp") and ip != "127.0.0.1" for t,ip,d in rows) else "暂无真实设备重连（机制已由探针验证）")
c.close()
