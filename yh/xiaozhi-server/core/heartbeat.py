import asyncio
import json
import os
import time
import uuid

from config.logger import setup_logging

TAG = __name__

# 与固件 main/yh/yh_protocol.cc 保持一致的协议参数：
# - TCP :12399，newline 分帧 JSON（HELLO / ADVERTISEMENT / HEARTBEAT / ACK / NACK）
# - 固件只处理 "COMMAND" 类型的下行消息，其余任何类型都会被固件回 NACK，
#   因此服务端对 JSON 上行消息保持静默（不回包），仅做日志记录与在线状态维护。
# - 服务端下行推送：COMMAND 帧（protocol_version=1 + device_id + command_id +
#   operation=SEND_NOTIFY + parameters.audio_url），固件校验后播放并回 ACK。
# - 非 JSON 的纯文本行（简单心跳客户端）回 "ok"。
MAX_FRAME_SIZE = 4096
# 固件每 25s 上报一次心跳，超过 35s 未收到视为掉线（留网络抖动余量）
HEARTBEAT_STALE_SECONDS = 35.0
# 下行协议版本（固件 HandleCommand 严格校验 protocol_version==1）
YH_PROTOCOL_VERSION = 1


class HeartbeatServer:
    """设备心跳监听服务（随 app.py 主服务一起启动、停止）。

    - TCP {port}（固件主协议）：newline 分帧 JSON。解析 HELLO / HEARTBEAT /
      ADVERTISEMENT，维护设备在线状态并输出日志；对已知消息不回包（回包会被
      固件 NACK）。非 JSON 文本行回 "ok"，兼容简单行协议客户端。
    - 下行推送：记录每个设备的 TCP writer 与 ADVERTISEMENT 能力列表，
      send_to_device() 经心跳通道直接下发 COMMAND（SET_LED / SEND_NOTIFY），
      固件执行后回 ACK/NACK（仅记录）。
    - UDP {port}（保底兼容）：收到任意包回 b"ok"，并记录客户端地址；若包体
      是带 device_id 的 JSON，同样纳入设备在线状态（无下行能力）。
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
        # device_id -> {ip, session_id, firmware, last_seen, online, operations}
        self.devices = {}
        # device_id -> asyncio StreamWriter（仅 TCP 连接；设备换连接/断开时更新/清理）
        # 用于下行推送：COMMAND SEND_NOTIFY 等直接经心跳 TCP 通道下发
        self.writers = {}
        # 壁纸回执落库回调：由 app.py 注入，签名 (device_id, payload) -> Awaitable|None
        # 固件执行 SET_WALLPAPER 后经本通道回 {"type":"wallpaper","action":"result",...}
        self.wallpaper_ack_sink = None
        self._tcp_server = None
        self._udp_transport = None
        # WebSocket 通道旁的 UDP 心跳端口：固件 websocket_protocol.cc 中
        # OpenUdpChannel() 固定向 host:8002 发 {"type":"udp_heartbeat"}（15s 一次）。
        # 该端口与 12399 互不相干，历史上无任何服务监听，固件每次发包都会收到
        # ICMP 端口不可达，等于白跑一条心跳。此处补齐监听，收到即回 ack。
        # 置 0 可关闭。
        # 取值优先级：环境变量 XIAOZHI_WS_UDP_HEARTBEAT_PORT > 配置 > 默认 8002
        try:
            ws_udp_env = os.environ.get("XIAOZHI_WS_UDP_HEARTBEAT_PORT")
            if ws_udp_env is not None and str(ws_udp_env).strip() != "":
                self.ws_udp_port = int(ws_udp_env)
            else:
                self.ws_udp_port = int(server_config.get("ws_udp_heartbeat_port", 8002) or 0)
        except (TypeError, ValueError):
            self.ws_udp_port = 8002
        self._ws_udp_transport = None
        # ip -> {"count": n, "last_seen": ts}，仅用于观测固件是否真的在发心跳
        self.ws_udp_stats = {}

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

        # UDP：固件 WebSocket 通道旁的独立心跳端口（默认 8002）
        # 与上面的 12399 是两个互不相同的协议端口，故单独监听。
        if self.ws_udp_port and self.ws_udp_port != self.port:
            try:
                loop = asyncio.get_running_loop()
                self._ws_udp_transport, _ = await loop.create_datagram_endpoint(
                    lambda: _WsUdpHeartbeatProtocol(self),
                    local_addr=(self.host, self.ws_udp_port),
                )
                self.logger.bind(tag=TAG).info(
                    f"WebSocket UDP心跳已启动\t{self.host}:{self.ws_udp_port}"
                )
            except Exception as e:
                self.logger.bind(tag=TAG).warning(
                    f"WebSocket UDP心跳({self.ws_udp_port})启动失败(不影响主服务): {e}"
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
                # 清理下行通道：仅当该设备当前 writer 就是本连接时才移除
                # （设备已换新连接时保留新 writer）
                if self.writers.get(device_id) is writer:
                    self.writers.pop(device_id, None)
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
            self._mark_online(device_id, peer_str, msg, writer=writer)
        elif msg_type in ("ACK", "NACK"):
            # 固件对下行 COMMAND 的执行结果回执：记录 command_id/status/error_code
            status = str(msg.get("status", ""))
            error_code = str(msg.get("error_code", ""))
            command_id = str(msg.get("command_id", ""))
            level = "info" if status == "ACKED" else "warning"
            log = self.logger.bind(tag=TAG)
            getattr(log, level)(
                f"收到{msg_type} [{device_id or peer_str}] status={status} "
                f"error={error_code} command_id={command_id}"
            )
        elif msg_type == "wallpaper":
            # 固件经本常连通道回壁纸执行结果（设备空闲时 WS 不保持，只能走这里）
            self._handle_wallpaper_result(device_id or peer_str, msg)
        else:
            # 其他类型：仅记录，不回包
            self.logger.bind(tag=TAG).debug(
                f"收到消息[{msg_type or '未知类型'}] 来自 {peer_str}"
            )
        return device_id or None

    def _handle_wallpaper_result(self, device_id: str, msg: dict) -> None:
        """壁纸执行结果（TCP 通道）→ 落 Redis 回执，供 manager-api 任务详情汇总。"""
        payload = {
            "version": str(msg.get("version", "")),
            "status": str(msg.get("status", "")),
            "reason": str(msg.get("reason", "")),
            "ts": int(time.time() * 1000),
        }
        self.logger.bind(tag=TAG).info(
            f"收到壁纸回执 [{device_id}] version={payload['version']} "
            f"status={payload['status']} reason={payload['reason']}"
        )
        sink = self.wallpaper_ack_sink
        if sink is None:
            self.logger.bind(tag=TAG).info(
                f"壁纸回执未落库（未注入 sink）: {payload}"
            )
            return
        try:
            result = sink(device_id, payload)
            if asyncio.iscoroutine(result):
                asyncio.create_task(result)
        except Exception as e:
            self.logger.bind(tag=TAG).warning(f"壁纸回执落库失败: {e}")

    def _tcp_send(self, writer, data: bytes):
        try:
            writer.write(data)
        except Exception as e:
            self.logger.bind(tag=TAG).warning(f"心跳回包失败: {e}")

    # ------------------------------------------------------------------
    # 设备在线状态
    # ------------------------------------------------------------------

    def _mark_online(self, device_id: str, peer_str: str, msg: dict, writer=None):
        now = time.time()
        if not device_id:
            self.logger.bind(tag=TAG).info(f"心跳(无设备ID) 来自 {peer_str}")
            return
        # 记录/更新下行通道与能力声明
        if writer is not None:
            self.writers[device_id] = writer
        device = self.devices.get(device_id)
        if device is None:
            self.devices[device_id] = {
                "ip": peer_str,
                "session_id": str(msg.get("session_id", "")),
                "firmware": str(msg.get("firmware", "")),
                "last_seen": now,
                "online": True,
                "operations": self._parse_operations(msg),
            }
            self.logger.bind(tag=TAG).info(
                f"设备上线 [{device_id}] {peer_str} "
                f"firmware={msg.get('firmware', '')} session={msg.get('session_id', '')} "
                f"operations={self.devices[device_id]['operations']}"
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
        # ADVERTISEMENT 的能力列表（SET_LED / SEND_NOTIFY）更新
        ops = self._parse_operations(msg)
        if ops:
            device["operations"] = ops
        if was_offline:
            self.logger.bind(tag=TAG).info(f"设备恢复在线 [{device_id}] {peer_str}")
        elif msg.get("type") == "HEARTBEAT":
            self.logger.bind(tag=TAG).info(f"心跳 [{device_id}] {peer_str}")

    @staticmethod
    def _parse_operations(msg: dict) -> list:
        """从 ADVERTISEMENT 提取 operations 能力列表（其他消息类型返回空）。"""
        if str(msg.get("type", "")) != "ADVERTISEMENT":
            return []
        ops = msg.get("operations")
        if not isinstance(ops, list):
            return []
        return [str(o) for o in ops if isinstance(o, (str, int))]

    # ------------------------------------------------------------------
    # 下行推送（心跳 TCP 通道）
    # ------------------------------------------------------------------

    def supports_operation(self, device_id: str, operation: str) -> bool:
        """设备是否在 ADVERTISEMENT 中声明了指定下行能力。"""
        device = self.devices.get(device_id)
        if not device:
            return False
        ops = device.get("operations") or []
        return operation in ops

    async def send_to_device(self, device_id: str, operation: str,
                             parameters: dict, timeout: float = 5.0) -> bool:
        """经心跳 TCP 通道向设备下发 COMMAND，返回是否写入成功。

        帧格式与固件 yh_protocol.cc HandleCommand 严格对齐：
          {"type":"COMMAND","protocol_version":1,"device_id":...,
           "command_id":<uuid>,"operation":...,"parameters":{...}}
        幂等：command_id 由固件 64 槽环形缓存去重（重发同 id 会 DUPLICATE_COMMAND）。
        写入成功不代表设备执行成功——设备执行后回 ACK，由 _handle_frame 记录。
        """
        writer = self.writers.get(device_id)
        if writer is None:
            return False
        try:
            if writer.is_closing():
                self.writers.pop(device_id, None)
                return False
        except Exception:
            pass
        command = {
            "type": "COMMAND",
            "protocol_version": YH_PROTOCOL_VERSION,
            "device_id": device_id,
            "command_id": str(uuid.uuid4()),
            "operation": operation,
            "parameters": parameters,
        }
        try:
            payload = json.dumps(command, ensure_ascii=False,
                                 separators=(",", ":")) + "\n"
            await asyncio.wait_for(
                self._send_and_drain(writer, payload.encode("utf-8")), timeout
            )
            self.logger.bind(tag=TAG).info(
                f"下行 COMMAND 已发送 [{device_id}] operation={operation} "
                f"command_id={command['command_id']}"
            )
            return True
        except Exception as e:
            self.logger.bind(tag=TAG).warning(
                f"下行 COMMAND 发送失败 [{device_id}] operation={operation}: {e}"
            )
            return False

    async def _send_and_drain(self, writer, data: bytes):
        writer.write(data)
        await writer.drain()

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
            # 判定离线：清理下行通道（writer 的最终清理由连接 finally 兜底，
            # 这里先移除避免向已死连接推送）
            self.writers.pop(device_id, None)
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
                # 心跳超时判死：下行通道一并作废（半开连接写入只会假成功）
                self.writers.pop(device_id, None)
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

    def handle_ws_udp_packet(self, data: bytes, addr):
        """WebSocket 旁路 UDP 心跳处理：固件仅要求发得出去，服务端收到即回 ack。

        报文为 {"type":"udp_heartbeat"}，不含 device_id（固件侧只带类型），
        因此这里只做「到达性 + 频次」观测，不参与设备在线判定。
        """
        peer_ip = addr[0] if addr else "unknown"
        entry = self.ws_udp_stats.get(peer_ip)
        if entry is None:
            self.ws_udp_stats[peer_ip] = {"count": 1, "last_seen": time.time()}
            self.logger.bind(tag=TAG).info(
                f"WebSocket UDP心跳首次收到来自 {peer_ip}: {data[:60]!r}"
            )
        else:
            entry["count"] += 1
            entry["last_seen"] = time.time()
            self.logger.bind(tag=TAG).debug(
                f"WebSocket UDP心跳 来自 {peer_ip} (累计 {entry['count']} 次)"
            )

    def close(self):
        for closer in (self._tcp_server, self._udp_transport, self._ws_udp_transport):
            try:
                if closer:
                    closer.close()
            except Exception:
                pass


class _WsUdpHeartbeatProtocol(asyncio.DatagramProtocol):
    """固件 WebSocket 通道旁路 UDP 心跳（默认 8002）：收到即回 JSON ack。"""

    def __init__(self, server: HeartbeatServer):
        self.server = server
        self.logger = server.logger
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data: bytes, addr):
        self.server.handle_ws_udp_packet(data, addr)
        try:
            if self.transport and not self.transport.is_closing():
                self.transport.sendto(b'{"type":"udp_heartbeat_ack"}', addr)
        except Exception as e:
            self.logger.bind(tag=TAG).warning(f"WebSocket UDP心跳回包失败 {addr}: {e}")


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
