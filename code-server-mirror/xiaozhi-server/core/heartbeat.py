import asyncio
import json
import time

from config.logger import setup_logging

TAG = __name__

# 与固件 main/yh/yh_protocol.cc 保持一致的协议参数：
# - TCP :12399，newline 分帧 JSON（HELLO / ADVERTISEMENT / HEARTBEAT / ACK / NACK）
# - 固件只处理 "COMMAND" 类型的下行消息，其余任何类型都会被固件回 NACK，
#   因此服务端对 JSON 上行消息保持静默（不回包），仅做日志记录与在线状态维护。
# - 非 JSON 的纯文本行（简单心跳客户端）回 "ok"。
MAX_FRAME_SIZE = 4096
# 固件每 25s 上报一次心跳，超过 35s 未收到视为掉线（留网络抖动余量）
HEARTBEAT_STALE_SECONDS = 35.0


class HeartbeatServer:
    """设备心跳监听服务（随 app.py 主服务一起启动、停止）。

    - TCP {port}（固件主协议）：newline 分帧 JSON。解析 HELLO / HEARTBEAT /
      ADVERTISEMENT，维护设备在线状态并输出日志；对已知消息不回包（回包会被
      固件 NACK）。非 JSON 文本行回 "ok"，兼容简单行协议客户端。
    - UDP {port}（保底兼容）：收到任意包回 b"ok"，并记录客户端地址；若包体
      是带 device_id 的 JSON，同样纳入设备在线状态。
    - 任一协议启动失败仅记录警告，不影响主服务；心跳端口被占用时另一协议
      仍可继续工作。

    配置项（config.yaml server 段，均可省略）：
      server.enable_heartbeat: true   # 心跳服务开关，默认 true
      server.heartbeat_port: 12399    # 心跳监听端口，默认 12399
    """

    def __init__(self, config: dict):
        self.config = config
        self.logger = setup_logging(config)
        server_config = config.get("server", {}) if isinstance(config, dict) else {}
        self.enabled = bool(server_config.get("enable_heartbeat", True))
        self.host = str(server_config.get("ip", "0.0.0.0"))
        try:
            self.port = int(server_config.get("heartbeat_port", 12399))
        except (TypeError, ValueError):
            self.port = 12399
        # device_id -> {ip, session_id, firmware, last_seen, online}
        self.devices = {}
        self._tcp_server = None
        self._udp_transport = None

    async def start(self):
        try:
            await self._start()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            # 异常隔离：心跳服务任何异常都不允许影响主服务
            self.logger.bind(tag=TAG).warning(f"心跳服务异常退出(不影响主服务): {e}")

    async def _start(self):
        if not self.enabled:
            self.logger.bind(tag=TAG).info(
                "心跳服务未启用(server.enable_heartbeat=false)"
            )
            return

        # TCP：固件主协议（newline 分帧 JSON）
        try:
            self._tcp_server = await asyncio.start_server(
                self._handle_tcp_client, self.host, self.port
            )
            self.logger.bind(tag=TAG).info(
                f"心跳服务(TCP)已启动\t{self.host}:{self.port}"
            )
        except Exception as e:
            self.logger.bind(tag=TAG).warning(
                f"心跳服务(TCP)启动失败(不影响主服务): {e}"
            )

        # UDP：保底兼容任意 UDP 心跳客户端（与 TCP 同端口号，互不冲突）
        try:
            loop = asyncio.get_running_loop()
            self._udp_transport, _ = await loop.create_datagram_endpoint(
                lambda: _UdpHeartbeatProtocol(self),
                local_addr=(self.host, self.port),
            )
            self.logger.bind(tag=TAG).info(
                f"心跳服务(UDP)已启动\t{self.host}:{self.port}"
            )
        except Exception as e:
            self.logger.bind(tag=TAG).warning(
                f"心跳服务(UDP)启动失败(不影响主服务): {e}"
            )

        if self._tcp_server is None and self._udp_transport is None:
            self.logger.bind(tag=TAG).warning(
                f"心跳服务 TCP/UDP 均启动失败(端口 {self.port})，放弃心跳监听"
            )
            return

        # 常驻运行：周期检查心跳超时的设备
        try:
            while True:
                await asyncio.sleep(10)
                self._check_stale_devices()
        finally:
            self.close()

    # ------------------------------------------------------------------
    # TCP 连接处理
    # ------------------------------------------------------------------

    async def _handle_tcp_client(self, reader, writer):
        peer = writer.get_extra_info("peername")
        peer_str = f"{peer[0]}:{peer[1]}" if peer else "unknown"
        device_id = None
        buffer = b""
        # 半开连接治理：设备 NAT 换源端口后旧连接无 FIN/RST，read 会永久阻塞。
        # 读超时 = 判死阈值×2（70s）：正常心跳 25~30s 间隔远小于此，超时即可判定
        # 半开，break 走 finally 关闭 socket，防止协程与 fd 泄漏线性累积。
        read_timeout = HEARTBEAT_STALE_SECONDS * 2
        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(reader.read(1024), timeout=read_timeout)
                except asyncio.TimeoutError:
                    self.logger.bind(tag=TAG).info(
                        f"心跳连接读超时({int(read_timeout)}s)视为半开，主动关闭 {peer_str}"
                    )
                    break
                if not chunk:
                    break
                buffer += chunk
                # newline 分帧（与固件 OnStreamData 一致：容忍 CRLF 与空行）
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    line = line.strip(b"\r \t")
                    if not line:
                        continue
                    if len(line) > MAX_FRAME_SIZE:
                        self.logger.bind(tag=TAG).warning(
                            f"心跳帧超长({len(line)}字节) 来自 {peer_str}，已丢弃"
                        )
                        continue
                    new_device_id = self._handle_frame(line, writer, peer_str)
                    if new_device_id:
                        device_id = new_device_id
                if len(buffer) > MAX_FRAME_SIZE:
                    self.logger.bind(tag=TAG).warning(
                        f"心跳半包数据超长 来自 {peer_str}，断开连接"
                    )
                    break
        except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
            pass
        except Exception as e:
            self.logger.bind(tag=TAG).warning(f"心跳连接异常 {peer_str}: {e}")
        finally:
            if device_id:
                self._mark_offline(device_id, "连接断开", peer_str)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            self.logger.bind(tag=TAG).info(f"心跳连接关闭 {peer_str}")

    def _handle_frame(self, line: bytes, writer, peer_str: str):
        """处理一行 TCP 消息，返回其中的 device_id（无则 None）。"""
        try:
            msg = json.loads(line.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            # 非 JSON 行：按简单文本心跳处理，回 ok
            self.logger.bind(tag=TAG).info(
                f"心跳(文本) 来自 {peer_str}: {line[:60]!r}"
            )
            self._tcp_send(writer, b"ok\n")
            return None
        if not isinstance(msg, dict):
            self.logger.bind(tag=TAG).warning(
                f"心跳消息格式非法 来自 {peer_str}: {line[:60]!r}"
            )
            return None

        msg_type = str(msg.get("type", ""))
        device_id = str(msg.get("device_id") or "")
        if msg_type in ("HELLO", "HEARTBEAT", "ADVERTISEMENT"):
            self._mark_online(device_id, peer_str, msg)
        else:
            # ACK / NACK / COMMAND 等：仅记录，不回包
            self.logger.bind(tag=TAG).debug(
                f"收到消息[{msg_type or '未知类型'}] 来自 {peer_str}"
            )
        return device_id or None

    def _tcp_send(self, writer, data: bytes):
        try:
            writer.write(data)
        except Exception as e:
            self.logger.bind(tag=TAG).warning(f"心跳回包失败: {e}")

    # ------------------------------------------------------------------
    # 设备在线状态
    # ------------------------------------------------------------------

    def _mark_online(self, device_id: str, peer_str: str, msg: dict):
        now = time.time()
        if not device_id:
            self.logger.bind(tag=TAG).info(f"心跳(无设备ID) 来自 {peer_str}")
            return
        device = self.devices.get(device_id)
        if device is None:
            self.devices[device_id] = {
                "ip": peer_str,
                "session_id": str(msg.get("session_id", "")),
                "firmware": str(msg.get("firmware", "")),
                "last_seen": now,
                "online": True,
            }
            self.logger.bind(tag=TAG).info(
                f"设备上线 [{device_id}] {peer_str} "
                f"firmware={msg.get('firmware', '')} session={msg.get('session_id', '')}"
            )
            return
        was_offline = not device.get("online", False)
        device["ip"] = peer_str
        device["last_seen"] = now
        device["online"] = True
        if msg.get("session_id"):
            device["session_id"] = str(msg["session_id"])
        if msg.get("firmware"):
            device["firmware"] = str(msg["firmware"])
        if was_offline:
            self.logger.bind(tag=TAG).info(f"设备恢复在线 [{device_id}] {peer_str}")
        elif msg.get("type") == "HEARTBEAT":
            self.logger.bind(tag=TAG).info(f"心跳 [{device_id}] {peer_str}")

    def _mark_offline(self, device_id: str, reason: str, peer_str: str = None):
        device = self.devices.get(device_id)
        if device and device.get("online"):
            # 半开连接治理的配套：同一设备可能换源端口建立了新连接（NAT 刷新），
            # 旧连接超时关闭属正常替换。仅当离线判定来源仍是设备当前活跃连接
            # （device["ip"] 与断开连接 peer 一致）时才判离线，避免误杀。
            if peer_str is not None and device.get("ip") != peer_str:
                self.logger.bind(tag=TAG).info(
                    f"旧连接关闭 [{device_id}] {peer_str}（设备已切换到 {device.get('ip', '')}，不判离线）"
                )
                return
            device["online"] = False
            self.logger.bind(tag=TAG).warning(
                f"设备离线 [{device_id}] {device.get('ip', '')} ({reason})"
            )

    def _check_stale_devices(self):
        now = time.time()
        for device_id, device in self.devices.items():
            if device.get("online") and (
                now - device.get("last_seen", now) > HEARTBEAT_STALE_SECONDS
            ):
                device["online"] = False
                self.logger.bind(tag=TAG).warning(
                    f"设备心跳超时判定离线 [{device_id}] {device.get('ip', '')} "
                    f"(超过{HEARTBEAT_STALE_SECONDS:.0f}s无心跳)"
                )

    # ------------------------------------------------------------------
    # 收包入口（UDP 协议对象回调）
    # ------------------------------------------------------------------

    def handle_udp_packet(self, data: bytes, addr):
        """UDP 收包处理：解析 JSON 心跳或记录原始包，并回 b"ok"。"""
        peer_str = f"{addr[0]}:{addr[1]}"
        try:
            try:
                msg = json.loads(data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                msg = None
            if isinstance(msg, dict) and msg.get("device_id"):
                self._mark_online(str(msg["device_id"]), peer_str, msg)
            else:
                self.logger.bind(tag=TAG).info(
                    f"心跳(UDP) 来自 {peer_str}: {data[:60]!r}"
                )
        except Exception as e:
            self.logger.bind(tag=TAG).warning(f"UDP心跳处理异常 {peer_str}: {e}")

    def close(self):
        for closer in (self._tcp_server, self._udp_transport):
            try:
                if closer:
                    closer.close()
            except Exception:
                pass


class _UdpHeartbeatProtocol(asyncio.DatagramProtocol):
    """UDP 心跳协议：收到任意包回 b"ok"，并记录客户端 ip:port。"""

    def __init__(self, server: HeartbeatServer):
        self.server = server
        self.logger = server.logger
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data: bytes, addr):
        self.server.handle_udp_packet(data, addr)
        try:
            if self.transport and not self.transport.is_closing():
                self.transport.sendto(b"ok", addr)
        except Exception as e:
            self.logger.bind(tag=TAG).warning(f"UDP心跳回包失败 {addr}: {e}")
