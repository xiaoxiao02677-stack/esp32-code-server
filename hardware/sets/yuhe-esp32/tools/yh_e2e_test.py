#!/usr/bin/env python3
"""YH Device Protocol v1 - 对拍测试服务器（模拟 p19r_console 侧）。

用途：验证小智固件(ESP32)与屿禾工坊服务器之间的 YH Device Protocol v1。

    ESP32 (TCP client)  ----TCP 3333---->  本脚本 (TCP server)

协议：newline-delimited JSON
消息：HELLO / ADVERTISEMENT / HEARTBEAT / COMMAND / ACK

用法：
    python yh_e2e_test.py                    # 监听 0.0.0.0:3333, 自动对拍
    python yh_e2e_test.py --port 3333        # 指定端口
    python yh_e2e_test.py --no-auto          # 只监听, 不自动发命令 (手动交互)

交互命令（服务器 -> ESP32）：
    on                          SET_LED {"on": true}
    off                         SET_LED {"on": false}
    dup <command_id>            重放指定 command_id（触发 DUPLICATE_COMMAND）
    raw <json>                  发送任意原始 JSON（安全/边界测试）
    说明：服务器侧每收到一条设备消息会按 [DEVICE] 前缀打印。

与 p19r_console.py 的关系：本脚本实现了其 DeviceGate/DeviceCommand 侧
所需的 TCP 服务端点与消息回显，用于第一阶段验收对拍。
"""

import argparse
import json
import socket
import sys
import threading
import time
import uuid

PROTOCOL_VERSION = 1
DEVICE_ID_PREFIX = "yuhe-esp32s3-"


class DeviceSession:
    """单设备 TCP 会话（对应服务器侧 P17 Session）。"""

    def __init__(self, conn: socket.socket, addr):
        self.conn = conn
        self.addr = addr
        self.buffer = b""
        self.device_id = None
        self.session_id = None
        self.firmware = None
        self.operations = []
        self.hellos = 0
        self.heartbeats = 0
        self.last_heartbeat = 0.0
        self.last_cmd_id = None
        self.ack_count = 0
        self.nack_count = 0
        self.errors_seen = []

    def send(self, obj: dict):
        line = json.dumps(obj) + "\n"
        self.conn.sendall(line.encode("utf-8"))
        print(f"[SERVER] -> {json.dumps(obj, ensure_ascii=False)}")

    def handle_line(self, line: str):
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            print(f"[SERVER][ERR] malformed JSON from device: {line!r}")
            return

        mtype = msg.get("type")
        print(f"[DEVICE] <- {json.dumps(msg, ensure_ascii=False)}")

        if mtype == "HELLO":
            self.hellos += 1
            self.device_id = msg.get("device_id")
            self.session_id = msg.get("session_id")
            self.firmware = msg.get("firmware")
            if msg.get("protocol_version") != PROTOCOL_VERSION:
                print("[SERVER][ERR] HELLO protocol_version mismatch!")
        elif mtype == "ADVERTISEMENT":
            self.operations = msg.get("operations", [])
            print(f"[SERVER] device capabilities: {self.operations}")
        elif mtype == "HEARTBEAT":
            self.heartbeats += 1
            self.last_heartbeat = time.time()
        elif mtype == "ACK":
            if msg.get("status") == "ACKED":
                self.ack_count += 1
            else:
                self.nack_count += 1
                self.errors_seen.append((msg.get("command_id"), msg.get("error_code")))

    def send_command(self, operation: str, parameters: dict, command_id: str = None):
        if command_id is None:
            command_id = f"cmd_{uuid.uuid4().hex[:8]}"
        if self.device_id is None:
            print("[SERVER][ERR] no HELLO yet, cannot send COMMAND")
            return None
        self.last_cmd_id = command_id
        self.send({
            "type": "COMMAND",
            "protocol_version": PROTOCOL_VERSION,
            "command_id": command_id,
            "device_id": self.device_id,
            "operation": operation,
            "parameters": parameters,
        })
        return command_id


def serve_session(conn: socket.socket, addr, auto: bool):
    session = DeviceSession(conn, addr)
    print(f"[SERVER] TCP connected: {addr}")
    try:
        if auto:
            t = threading.Thread(target=auto_interact, args=(session,), daemon=True)
            t.start()
        while True:
            data = conn.recv(4096)
            if not data:
                break
            session.buffer += data
            while b"\n" in session.buffer:
                raw, session.buffer = session.buffer.split(b"\n", 1)
                line = raw.decode("utf-8", errors="replace").rstrip("\r")
                if line:
                    session.handle_line(line)
    except (ConnectionResetError, OSError) as e:
        print(f"[SERVER] connection lost: {e}")
    finally:
        print(f"[SERVER] TCP disconnected: {addr}, ACKs={session.ack_count}, "
              f"NACKs={session.nack_count}, errors={session.errors_seen}")
        conn.close()


def auto_interact(session: DeviceSession):
    """对拍主流程：等 HELLO -> 命令序列 -> 校验 ACK（对应 §三十 对拍测试）。"""
    # 等 HELLO/ADVERTISEMENT
    for _ in range(100):
        if session.device_id is not None and session.operations:
            break
        time.sleep(0.2)
    if session.device_id is None:
        print("[SERVER] timeout waiting HELLO")
        return
    print(f"[SERVER] 对拍开始: device={session.device_id}, firmware={session.firmware}")

    # 1) SET_LED ON -> 期望 ACKED
    cid = session.send_command("SET_LED", {"on": True}, command_id="cmd_001")
    time.sleep(1.0)
    # 2) SET_LED OFF -> 期望 ACKED
    session.send_command("SET_LED", {"on": False}, command_id="cmd_002")
    time.sleep(1.0)
    # 3) 重复 command_id -> 期望 DUPLICATE_COMMAND
    session.send_command("SET_LED", {"on": True}, command_id=cid)
    time.sleep(1.0)
    # 4) 安全/边界用例
    bad_cases = [
        ("cmd_wrong_device", {"type": "COMMAND", "protocol_version": 1,
                              "command_id": "cmd_wrong_device",
                              "device_id": "another-device",
                              "operation": "SET_LED", "parameters": {"on": True}}),
        ("cmd_bad_version", {"type": "COMMAND", "protocol_version": 2,
                             "command_id": "cmd_bad_version",
                             "device_id": session.device_id,
                             "operation": "SET_LED", "parameters": {"on": True}}),
        ("cmd_unknown_op", {"type": "COMMAND", "protocol_version": 1,
                            "command_id": "cmd_unknown_op",
                            "device_id": session.device_id,
                            "operation": "SET_GPIO", "parameters": {"on": True}}),
        ("cmd_bad_param", {"type": "COMMAND", "protocol_version": 1,
                           "command_id": "cmd_bad_param",
                           "device_id": session.device_id,
                           "operation": "SET_LED", "parameters": {"on": "true"}}),
        ("cmd_extra_param", {"type": "COMMAND", "protocol_version": 1,
                             "command_id": "cmd_extra_param",
                             "device_id": session.device_id,
                             "operation": "SET_LED",
                             "parameters": {"on": True, "gpio": 2}}),
        ("cmd_missing_id", {"type": "COMMAND", "protocol_version": 1,
                            "device_id": session.device_id,
                            "operation": "SET_LED", "parameters": {"on": True}}),
    ]
    for name, obj in bad_cases:
        session.send(obj)
        time.sleep(0.5)
    print("[SERVER] 自动对拍命令已全部下发, 观察 [DEVICE] ACK 回显")


def main():
    parser = argparse.ArgumentParser(description="YH Device Protocol v1 对拍测试服务器")
    parser.add_argument("--port", type=int, default=3333)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--no-auto", action="store_true",
                        help="不自动下发对拍命令, 进入交互模式")
    args = parser.parse_args()

    if args.no_auto:
        print("[SERVER] 交互模式: 输入 on/off/dup <id>/raw <json> 发送命令")
        auto = False
    else:
        auto = True

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((args.host, args.port))
    srv.listen(4)
    print(f"[SERVER] YH Device Protocol v1 对拍服务器已启动: {args.host}:{args.port}")

    def stdin_loop():
        while True:
            try:
                cmd = input()
            except EOFError:
                return
            parts = cmd.strip().split()
            if not parts:
                continue
            if parts[0] == "on":
                sessions[-1].send_command("SET_LED", {"on": True}) if sessions else print("[SERVER] no device")
            elif parts[0] == "off":
                sessions[-1].send_command("SET_LED", {"on": False}) if sessions else print("[SERVER] no device")
            elif parts[0] == "dup" and len(parts) > 1:
                sessions[-1].send_command("SET_LED", {"on": True}, command_id=parts[1]) if sessions else print("[SERVER] no device")
            elif parts[0] == "raw" and len(parts) > 1:
                obj = json.loads(" ".join(parts[1:]))
                sessions[-1].send(obj) if sessions else print("[SERVER] no device")
            else:
                print("[SERVER] 可用: on | off | dup <id> | raw <json>")

    sessions = []
    threading.Thread(target=stdin_loop, daemon=True).start()

    while True:
        conn, addr = srv.accept()
        session_thread = threading.Thread(
            target=serve_session, args=(conn, addr, auto), daemon=True)
        session_thread.start()


if __name__ == "__main__":
    main()
