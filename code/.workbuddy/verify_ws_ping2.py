#!/usr/bin/env python3
"""第二次验证：模拟真实固件（收到 Ping 立即回 Pong），确认
  a) Ping 每 30s 一次持续不断
  b) 连接不会被误杀（观察 100s 仍 OPEN）
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
    "device-id: ws-pong-probe\r\n"
    "client-id: ws-pong-probe\r\n"
    "\r\n"
)
s = socket.create_connection((HOST, PORT), timeout=5)
s.sendall(req.encode())
buf = b""
while b"\r\n\r\n" not in buf:
    buf += s.recv(4096)
print("握手:", buf.split(b"\r\n")[0].decode())


def send_frame(opcode, payload=b""):
    """客户端->服务端帧必须掩码"""
    hdr = bytes([0x80 | opcode])
    n = len(payload)
    if n < 126:
        hdr += bytes([0x80 | n])
    elif n < 65536:
        hdr += bytes([0x80 | 126]) + struct.pack(">H", n)
    else:
        hdr += bytes([0x80 | 127]) + struct.pack(">Q", n)
    mask = os.urandom(4)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    s.sendall(hdr + mask + masked)


s.settimeout(0.5)
start = time.time()
ping_times, pong_sent, closed = [], 0, False
OBSERVE = 100
while time.time() - start < OBSERVE:
    try:
        hdr = s.recv(2)
    except socket.timeout:
        continue
    if len(hdr) < 2:
        closed = True
        print("!! 服务端关闭了连接")
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
    if opcode == 0x9:                      # Ping -> 立即回 Pong（固件行为）
        send_frame(0xA, payload)
        pong_sent += 1
        ping_times.append(round(time.time() - start, 1))
    elif opcode == 0x8:
        closed = True
        print("!! 收到 Close 帧")
        break

gaps = [round(ping_times[i+1] - ping_times[i], 1) for i in range(len(ping_times) - 1)]
print(f"\n观察 {OBSERVE}s（每收到 Ping 立即回 Pong）")
print(f"  收到 Ping x{len(ping_times)}  发出 Pong x{pong_sent}")
print("  Ping 到达时刻(s):", ping_times)
print("  Ping 间隔(s):", gaps)
print(f"  连接是否仍 OPEN: {'是' if not closed else '否 —— 被误杀!'}")
print("\n结论:", "保活正常且不会误杀健康连接" if (not closed and len(ping_times) >= 2)
      else "异常：健康连接被断开或 Ping 未持续")
try:
    s.close()
except Exception:
    pass
'''

client = get_client()
try:
    cmd = ("cd /root/xiaozhi-server/main/xiaozhi-server && "
           "cat > /tmp/_pong_probe.py <<'PYEOF'\n" + SCRIPT + "\nPYEOF\n"
           ".venv/bin/python /tmp/_pong_probe.py")
    _, out, err = client.exec_command(cmd, timeout=200)
    print(out.read().decode("utf-8", "replace"))
    e = err.read().decode("utf-8", "replace")
    if e.strip():
        print("[stderr]", e)
finally:
    client.close()
