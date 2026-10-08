#!/usr/bin/env python3
"""原始帧探测：确认服务端 WebSocket 保活 Ping 真的在发。

在服务器上用裸 socket 完成 WS 握手，然后只解析帧头，统计收到的
控制帧（Ping=0x9 / Pong=0xA / Close=0x8），不依赖任何 WS 库。
"""
import sys

sys.path.insert(0, r"G:\demo\21_xiaozhi\code\.workbuddy")
from ssh_run import get_client  # noqa: E402

SCRIPT = r'''
import socket, base64, os, time, struct

HOST, PORT = "127.0.0.1", 8000
key = base64.b64encode(os.urandom(16)).decode()
req = (
    "GET /xiaozhi/v1/ HTTP/1.1\r\n"
    f"Host: {HOST}:{PORT}\r\n"
    "Upgrade: websocket\r\n"
    "Connection: Upgrade\r\n"
    f"Sec-WebSocket-Key: {key}\r\n"
    "Sec-WebSocket-Version: 13\r\n"
    "device-id: ws-ping-probe\r\n"
    "client-id: ws-ping-probe\r\n"
    "\r\n"
)

s = socket.create_connection((HOST, PORT), timeout=5)
s.sendall(req.encode())

# 读握手响应
buf = b""
while b"\r\n\r\n" not in buf:
    d = s.recv(4096)
    if not d:
        raise SystemExit("握手失败：连接被关闭")
    buf += d
status = buf.split(b"\r\n")[0].decode()
print("握手响应:", status)
assert "101" in status, status

s.settimeout(0.5)
start = time.time()
counts = {0x8: 0, 0x9: 0, 0xA: 0}
data_frames = 0
ping_times = []
OBSERVE = 75

while time.time() - start < OBSERVE:
    try:
        hdr = s.recv(2)
    except socket.timeout:
        continue
    if len(hdr) < 2:
        print("连接被关闭 (EOF)")
        break
    b0, b1 = hdr[0], hdr[1]
    opcode = b0 & 0x0F
    length = b1 & 0x7F
    if length == 126:
        length = struct.unpack(">H", s.recv(2))[0]
    elif length == 127:
        length = struct.unpack(">Q", s.recv(8))[0]
    payload = b""
    while len(payload) < length:
        payload += s.recv(length - len(payload))
    if opcode in counts:
        counts[opcode] += 1
        if opcode == 0x9:
            ping_times.append(round(time.time() - start, 1))
    else:
        data_frames += 1
        if len(payload) < 200:
            print(f"  [数据帧] {payload[:120].decode('utf-8', 'replace')}")

names = {0x8: "Close", 0x9: "Ping", 0xA: "Pong"}
print(f"\n观察 {OBSERVE}s 结果：")
for op, n in counts.items():
    print(f"  {names[op]:6s} x{n}")
print(f"  数据帧 x{data_frames}")
print("  Ping 到达时刻(s):", ping_times)
if ping_times:
    gaps = [round(ping_times[i+1] - ping_times[i], 1) for i in range(len(ping_times)-1)]
    print("  Ping 间隔(s):", gaps)
print("\n结论:", "服务端保活 Ping 已生效" if counts[0x9] >= 1 else "未收到 Ping（保活未生效!）")
try:
    s.close()
except Exception:
    pass
'''

client = get_client()
try:
    cmd = ("cd /root/xiaozhi-server/main/xiaozhi-server && "
           "cat > /tmp/_ping_probe.py <<'PYEOF'\n" + SCRIPT + "\nPYEOF\n"
           ".venv/bin/python /tmp/_ping_probe.py")
    _, out, err = client.exec_command(cmd, timeout=180)
    print(out.read().decode("utf-8", "replace"))
    e = err.read().decode("utf-8", "replace")
    if e.strip():
        print("[stderr]", e)
finally:
    client.close()
