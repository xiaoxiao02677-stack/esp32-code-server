#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""唤醒词推送服务"""
import asyncio
import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# device_config 允许下发的键（与 manager-api DeviceConfigServiceImpl.CONFIG_KEYS 同源）
DEVICE_CONFIG_ALLOWED_KEYS = {
    "wake_word",            # 唤醒词命令（无调拼音，或汉字走固件内置字表）
    "wake_word_display",    # 唤醒词显示文本（汉字），屏幕显示用，与 wake_word 索引对齐
    "wake_word_threshold",  # 唤醒词灵敏度 0~100（0=最灵敏）
    "interrupt_threshold",  # 实时打断灵敏度 0~100（0=最灵敏）
    "volume",               # 音量 0~100
    "brightness",           # 亮度 0~100
}

# wake_word / wake_word_display 的值约束（与 manager-api 侧一致）
WAKE_WORD_MAX_COUNT = 5
# 拼音单条长度：esp-sr 引擎硬上限 ESP_MN_MAX_PHRASE_LEN=63（可用 62），取 60 留余量。
# 不能沿用 32：5 音节最坏 34 字符（zhuang×5），会被静默丢弃
WAKE_WORD_PINYIN_MAX_LEN = 60
# 展示文本（汉字）单条长度
WAKE_WORD_DISPLAY_MAX_LEN = 32


class WakeWordService:
    """唤醒词管理服务，作为单例挂在 WebSocketServer 上。"""

    def __init__(self):
        self._connections: Dict[str, object] = {}
        self._agent_devices: Dict[str, set] = {}
        self._offline_queue: Dict[str, List[dict]] = {}
        self._lock = asyncio.Lock()
        # 心跳服务引用：由 app.py 注入。心跳在线=设备可达（WS 可能未建），
        # 在线设备列表 = WS 连接 ∪ 心跳在线，供推送调度页展示真实可达设备。
        self.heartbeat_server = None
        logger.info("WakeWordService 初始化完成")

    def set_heartbeat_server(self, heartbeat_server) -> None:
        self.heartbeat_server = heartbeat_server

    def set_wallpaper_service(self, wallpaper_service) -> None:
        """注入壁纸服务：设备文本通道建立时回调其离线补投钩子。"""
        self._wallpaper_service = wallpaper_service

    async def register_connection(self, device_id: str, conn: object) -> None:
        async with self._lock:
            self._connections[device_id] = conn
            pending = self._offline_queue.pop(device_id, [])
        if pending:
            # 对齐推送策略：未绑定设备、MQTT 网关设备不下发
            if getattr(conn, "need_bind", False) or getattr(conn, "conn_from_mqtt_gateway", False):
                logger.info(f"设备 {device_id} 未绑定或来自MQTT网关，丢弃 {len(pending)} 条离线唤醒词")
                return
            logger.info(f"设备 {device_id} 上线，尝试下发 {len(pending)} 条离线唤醒词")
            failed = []
            for msg in pending:
                if not await self._push_to_conn(device_id, conn, msg):
                    failed.append(msg)
            if failed:
                # 发送失败的重新入队，等待下次上线或重试
                async with self._lock:
                    self._offline_queue.setdefault(device_id, []).extend(failed)
        # 壁纸离线补投钩子（失败自处理，不影响唤醒词流程）
        wallpaper = getattr(self, "_wallpaper_service", None)
        if wallpaper is not None:
            try:
                await wallpaper.on_connection_registered(device_id, conn)
            except Exception as e:
                logger.warning(f"壁纸补投钩子异常（不影响设备上线流程）: {e}")

    async def unregister_connection(self, device_id: str) -> None:
        async with self._lock:
            self._connections.pop(device_id, None)

    def register_agent_device(self, agent_id: str, device_id: str) -> None:
        if agent_id not in self._agent_devices:
            self._agent_devices[agent_id] = set()
        self._agent_devices[agent_id].add(device_id)
        logger.debug(f"设备 {device_id} 绑定到 agent {agent_id}")

    async def push_wake_words(self, agent_id: Optional[str], device_id: Optional[str],
                              wake_words: List[str], tts_rate: int = 0,
                              display_words: Optional[List[str]] = None) -> dict:
        """推送唤醒词到目标设备（在线直推 / 离线缓存）。

        设备端消息固件 application.cc 只认 device_config 等 10 种 type，
        wake_word 消息会被静默丢弃；因此对在线设备改发：
        {"type":"device_config","payload":{"wake_word":[...],"wake_word_display":[...]}}
        → board.cc ApplyDeviceConfig → MultiNet UpdateWakeWordCommands 热更新。
        wake_words 现由 manager-api 转成无调拼音下发（任意中文词可用，不受固件内置
        字表限制）；display_words 为原汉字，屏幕显示与老服务端兼容（缺省回落 wake_words）。
        空数组配合固件 ClearWakeWordCommands 语义可清空唤醒词。
        """
        # 保留位置：非法/空项留空串占位，不能直接 filter——两侧各自 filter 会压缩下标，
        # 导致"喊 A 显示 B"（display 是按原始下标对齐的）
        raw_words = [str(w).strip() if w is not None else "" for w in (wake_words or [])]
        # display_words 三语义（不能混成一锅）：
        #   None   —— 老链路（manager-api 只传 wake_words，值为汉字）：display 用 wake_words
        #   []     —— 显式空：不可信，绝不用它覆盖服务端匹配词表（否则拼音串会挤掉
        #             中文匹配词，导致"喊醒了却没反应"）
        #   非空   —— 汉字展示文本（可信，用它同步连接态 conn.config["wakeup_words"]）
        if display_words is None:
            raw_display = None
        else:
            raw_display = [str(d).strip() if d is not None else "" for d in display_words]

        # 成对构建：命令词为空的位置整条丢弃（连 display 一起），保证两数组同长同序
        pairs: list = []
        for i, word in enumerate(raw_words):
            if not word:
                continue
            if raw_display is None:
                pairs.append((word, ""))
            else:
                pairs.append((word, raw_display[i] if i < len(raw_display) else ""))
        if len(pairs) > WAKE_WORD_MAX_COUNT:
            logger.warning("唤醒词 %d 个超过设备上限 %d，截断", len(pairs), WAKE_WORD_MAX_COUNT)
            pairs = pairs[:WAKE_WORD_MAX_COUNT]

        payload = {"wake_word": [w for w, _ in pairs]}
        if pairs and any(d for _, d in pairs):
            if any(not d for _, d in pairs):
                logger.debug("部分唤醒词缺显示文本，回落命令词自身以保持两数组等长")
            payload["wake_word_display"] = [d or w for w, d in pairs]

        def _on_sent(conn) -> None:
            # 同步服务端匹配词表（helloTalk/文本匹配用）：必须是汉字，中文 ASR 结果
            # 才匹配得上；拿不到可信汉字（display 为空或是拼音）时宁可不动旧词表
            if not pairs:
                sync_words = []                                  # 清空：服务端也清
            elif all(d for _, d in pairs):
                # 判定与取值必须同口径：原来用 any() 判定、d or w 取值，会在
                # display 参差时把拼音塞进 wakeup_words（如 ['你好小禾','gui gui']），
                # 而 listenMessageHandler/helloHandle 拿中文 ASR 文本做 in 判断，
                # 拼音永远匹配不上 → 设备唤醒了却被当普通对话，属极难排查的故障。
                # 全组 display 齐备才用它覆盖；缺一个就整组不动（下个分支兜老链路）。
                sync_words = [d for _, d in pairs]               # 可信汉字
            elif display_words is None:
                sync_words = [w for w, _ in pairs]               # 老链路：wake_words 本身是汉字
            else:
                sync_words = None                                # 显式空 display：不可信，不动
            if sync_words is None:
                return
            try:
                conn.config["wakeup_words"] = list(sync_words)
            except Exception:
                pass

        return await self._push_device_config(
            agent_id, device_id, payload, "唤醒词", on_sent=_on_sent)

    async def push_device_config(self, agent_id: Optional[str] = None,
                                 device_id: Optional[str] = None,
                                 payload: Optional[dict] = None,
                                 log_tag: str = "设备配置") -> dict:
        """通用 device_config 下发（manager-api 内部调用，唤醒词/阈值/打断阈值共用）。

        payload 白名单 + 值域校验在此再做一遍（纵深防御）：即使 manager-api 的
        B 线写入口被绕过，脏键也不会到达设备。未知键丢弃、数值键必须 0~100 整数。
        """
        if not isinstance(payload, dict) or not payload:
            raise ValueError("payload 不能为空")
        clean: dict = {}
        for key, value in payload.items():
            if key not in DEVICE_CONFIG_ALLOWED_KEYS:
                logger.warning(f"忽略未知 device_config 键: {key}")
                continue
            if key == "wake_word":
                words = None
                if isinstance(value, str) and value.strip():
                    words = [value.strip()]
                elif isinstance(value, list):
                    # 保留位置：非法项留空串占位。直接 filter 会压缩下标，
                    # 与 wake_word_display 脱节 ⇒ "喊 A 显示 B"（见下方成对剔除）
                    words = [w.strip() if isinstance(w, str) else "" for w in value]
                    if not any(words):
                        words = None
                if words is None:
                    logger.warning(f"忽略非法唤醒词值: {value!r}")
                    continue
                # 上限截断不在这里做：此时数组还含空占位，先截断会把"坏项后面的
                # 有效词"一起砍掉（['a','x'*70,'b','c','d','e'] 截 5 再剔除只剩 4 个，
                # e 无声消失）。统一挪到下方成对剔除之后。
                # 长度按形态：拼音（ASCII）60 / 汉字 32。超长同样留空串占位，
                # 由下方成对剔除同步删掉对应的 display
                kept = [
                    w if w and len(w) <= (WAKE_WORD_PINYIN_MAX_LEN if w.isascii()
                                          else WAKE_WORD_DISPLAY_MAX_LEN) else ""
                    for w in words
                ]
                if not any(kept):
                    logger.warning("唤醒词全部超长，忽略: %r", words)
                    continue
                clean["wake_word"] = kept
                continue
            if key == "wake_word_display":
                # 显示文本（汉字）：字符串或字符串数组，上限与唤醒词一致
                cleaned = self._sanitize_wake_word_display(value)
                if cleaned is not None:
                    clean[key] = cleaned
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                logger.warning(f"忽略非数值配置: {key}={value!r}")
                continue
            if isinstance(value, float) and not float(value).is_integer():
                logger.warning(f"忽略非整数配置: {key}={value!r}")
                continue
            int_value = int(value)
            if int_value < 0 or int_value > 100:
                logger.warning(f"忽略越界配置: {key}={int_value}（0~100）")
                continue
            clean[key] = int_value
        # 孤儿 display：wake_word 缺席时（未下发、或全部非法被上面 continue 掉），
        # 单独存在的 wake_word_display 没有意义。固件只在 wake_word 是字符串/数组时
        # 才进解析块（board.cc L249），所以不会误用；但契约上不允许单发，
        # 且 manager-api 侧可能把它当有效配置回写。此处删除；
        # 若删完没有别的键，下面会按"payload 无合法配置键"拒绝，语义正确。
        if "wake_word_display" in clean and "wake_word" not in clean:
            logger.warning("wake_word_display 缺少配对的 wake_word，丢弃")
            clean.pop("wake_word_display", None)
        if not clean:
            raise ValueError("payload 无合法配置键")
        # 配对归一 + 成对剔除：display 与 wake_word 必须按下标严格对应。
        #   ① 两侧各自 filter 会压缩下标 ⇒ "喊 A 显示 B"。
        #      例：['a','x'*70,'c'] + ['甲','乙','丙'] → wake 压成 ['a','c']、
        #      display 仍是 ['甲','乙','丙']，截断后 c 显示成"乙"（应为"丙"）。
        #      故两侧都保留位置占位，在此统一下标剔除。
        #   ② display 是字符串但命令词多个 → 无法对齐，丢弃 display（回落命令词自身）。
        #   ③ 命令词是字符串而 display 是数组 → 只取第一条。
        wake_list = clean.get("wake_word")
        display_list = clean.get("wake_word_display")
        if isinstance(wake_list, list):
            if isinstance(display_list, str):
                if len(wake_list) == 1:
                    display_list = [display_list]
                else:
                    logger.warning("display 为字符串但命令词 %d 个，无法对齐，忽略 display", len(wake_list))
                    # 必须从 clean 里真正删掉：只把局部变量置 None，原字符串仍会被下发
                    clean.pop("wake_word_display", None)
                    display_list = None
            if isinstance(display_list, list):
                if len(display_list) > len(wake_list):
                    logger.debug("唤醒词显示文本多于命令词，已截断到 %d 条", len(wake_list))
                paired_wake: list = []
                paired_display: list = []
                for i, word in enumerate(wake_list):
                    if not word:
                        # 命令词为空：这条没有意义，display 同步丢弃（成对剔除）
                        continue
                    paired_wake.append(word)
                    text = display_list[i] if i < len(display_list) else ""
                    # display 缺失时回落命令词自身，保持两数组等长
                    paired_display.append(text or word)
                clean["wake_word"] = paired_wake
                if paired_display:
                    clean["wake_word_display"] = paired_display
                else:
                    clean.pop("wake_word_display", None)
            else:
                # 没传 display（或上面已判为不可对齐）：清掉空占位，不凭空造 display
                clean["wake_word"] = [w for w in wake_list if w]
            # 上限截断放在成对剔除之后：剔干净了再数条数，才不会误砍有效词
            final_wake = clean.get("wake_word") or []
            if len(final_wake) > WAKE_WORD_MAX_COUNT:
                logger.warning("唤醒词 %d 个超过设备上限 %d，截断",
                               len(final_wake), WAKE_WORD_MAX_COUNT)
                clean["wake_word"] = final_wake[:WAKE_WORD_MAX_COUNT]
                final_display = clean.get("wake_word_display")
                if isinstance(final_display, list):
                    clean["wake_word_display"] = final_display[:WAKE_WORD_MAX_COUNT]
        return await self._push_device_config(agent_id, device_id, clean, log_tag)

    @staticmethod
    def _sanitize_wake_word_display(value):
        """唤醒词显示文本校验：≤5 项。数组<b>保留位置</b>（非法项留空串占位）——
        与 wake_word 按下标配对，压缩会让"喊 A 显示 B"。"""
        if isinstance(value, str):
            text = value.strip()
            if not text or len(text) > WAKE_WORD_DISPLAY_MAX_LEN:
                logger.warning(f"忽略非法唤醒词显示文本: len={len(text)}")
                return None
            return text
        if isinstance(value, list):
            if len(value) > WAKE_WORD_MAX_COUNT:
                logger.warning(f"唤醒词显示文本超上限 {WAKE_WORD_MAX_COUNT}，已截断")
                value = value[:WAKE_WORD_MAX_COUNT]
            texts = []
            any_valid = False
            for item in value:
                if isinstance(item, str) and item.strip() and len(item.strip()) <= WAKE_WORD_DISPLAY_MAX_LEN:
                    texts.append(item.strip())
                    any_valid = True
                else:
                    texts.append("")  # 保留位置占位
            if not any_valid:
                return None
            return texts
        logger.warning(f"忽略非法唤醒词显示文本类型: {type(value).__name__}")
        return None

    async def push_wake_word_threshold(self, agent_id: Optional[str] = None,
                                       device_id: Optional[str] = None,
                                       threshold: int = 40) -> dict:
        """唤醒词阈值下发（0~100，0=最灵敏）。

        帧：{"type":"device_config","payload":{"wake_word_threshold":N}}
        → board.cc ApplyDeviceConfig → NVS("wake_word_config") 持久
          + AudioService.SetWakeWordThreshold 热生效（固件重启后从 NVS 恢复）。
        """
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            raise ValueError(f"唤醒词阈值必须为数值: {threshold!r}")
        if isinstance(threshold, float) and not float(threshold).is_integer():
            raise ValueError(f"唤醒词阈值必须为整数: {threshold}")
        threshold = int(threshold)
        if threshold < 0 or threshold > 100:
            raise ValueError(f"唤醒词阈值超出 0~100 区间: {threshold}")
        return await self.push_device_config(
            agent_id, device_id, {"wake_word_threshold": threshold}, "唤醒词阈值")

    async def push_interrupt_threshold(self, agent_id: Optional[str] = None,
                                       device_id: Optional[str] = None,
                                       threshold: int = 15) -> dict:
        """实时打断灵敏度下发（0~100，0=最灵敏、100=最难打断）。

        帧：{"type":"device_config","payload":{"interrupt_threshold":N}}
        → board.cc ApplyDeviceConfig → NVS("interrupt_config") 持久
          + AudioService.SetInterruptThreshold 热生效（映射 VAD 人声确认窗 0~2000ms）。
        """
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            raise ValueError(f"打断阈值必须为数值: {threshold!r}")
        if isinstance(threshold, float) and not float(threshold).is_integer():
            raise ValueError(f"打断阈值必须为整数: {threshold}")
        threshold = int(threshold)
        if threshold < 0 or threshold > 100:
            raise ValueError(f"打断阈值超出 0~100 区间: {threshold}")
        return await self.push_device_config(
            agent_id, device_id, {"interrupt_threshold": threshold}, "实时打断阈值")

    async def _push_device_config(self, agent_id: Optional[str], device_id: Optional[str],
                                  payload: dict, log_tag: str, on_sent=None) -> dict:
        """device_config 直投公共路径：在线直推 / 离线缓存。

        所有"改设备本地配置"类消息（wake_word / wake_word_threshold / ...）统一走这里，
        保证调度策略一致：need_bind/MQTT 网关跳过、离线队列每设备只保留最新一条。
        on_sent(conn)：推送成功后的服务端状态同步钩子（可选）。
        """
        msg = {
            "type": "device_config",
            "payload": payload,
        }
        result = {"sent": 0, "offline": 0, "failed": 0, "skipped": 0}
        target_ids: set = set()
        if agent_id and agent_id in self._agent_devices:
            target_ids |= self._agent_devices[agent_id]
        if device_id:
            target_ids.add(device_id)
        if not target_ids:
            logger.warning(f"无目标设备可推送: agent_id={agent_id}, device_id={device_id}")
            return result
        async with self._lock:
            snapshot = dict(self._connections)
        offline_updates: Dict[str, List[dict]] = {}
        for did in target_ids:
            conn = snapshot.get(did)
            if conn is not None:
                # 对齐 connection.py 云端配置下发策略：未绑定设备、MQTT 网关设备不下发
                if getattr(conn, "need_bind", False) or getattr(conn, "conn_from_mqtt_gateway", False):
                    logger.info(f"设备 {did} 未绑定或来自MQTT网关，跳过{log_tag}推送")
                    result["skipped"] += 1
                    continue
                ok = await self._push_to_conn(did, conn, msg, log_tag=log_tag)
                if ok:
                    if on_sent is not None:
                        on_sent(conn)
                    result["sent"] += 1
                else:
                    # 发送失败同样入离线队列：下次上线自动重试
                    offline_updates[did] = [msg]
                    result["failed"] += 1
            else:
                # 配置语义：离线队列每设备只保留最新一条，避免历史堆积
                offline_updates[did] = [msg]
                result["offline"] += 1
        if offline_updates:
            async with self._lock:
                self._offline_queue.update(offline_updates)
            logger.info(f"{log_tag}已缓存至 {len(offline_updates)} 个离线设备")
        return result

    def get_connections(self) -> Dict[str, object]:
        """返回 WS 连接快照 {device_id: conn}（供壁纸下发等服务按设备直投）。"""
        return dict(self._connections)

    def get_online_devices(self) -> List[str]:
        """在线设备 = WS 连接中的设备 ∪ 心跳在线的设备。

        固件 2.5.x 起心跳常驻、WS 按需建立：设备心跳在线但 WS 已断时，
        单看 WS 会误判离线（推送调度页显示 0 台在线）。合并两个来源，
        心跳在线代表设备网络可达，可与推送目标选择共用。
        """
        online = set(self._connections.keys())
        hb = getattr(self, "heartbeat_server", None)
        if hb is not None:
            try:
                for device_id, info in hb.devices.items():
                    if not info.get("online"):
                        continue
                    # 心跳上报 ID 形如 yuhe-14c19fd13348（前缀+无冒号MAC），
                    # WS/设备库用 14:c1:9f:d1:33:48 冒号格式；归一化后合并，
                    # 保证推送目标与 WS 连接键一致。
                    normalized = str(device_id)
                    if normalized.startswith("yuhe-") and ":" not in normalized:
                        raw = normalized[len("yuhe-"):].lower()
                        if len(raw) == 12 and all(c in "0123456789abcdef" for c in raw):
                            normalized = ":".join(raw[i:i + 2] for i in range(0, 12, 2))
                    online.add(normalized)
            except Exception as e:
                logger.warning(f"合并心跳在线设备失败: {e}")
        return list(online)

    async def _push_to_conn(self, device_id: str, conn: object, msg: dict, log_tag: str = "唤醒词") -> bool:
        try:
            if not hasattr(conn, "websocket") or conn.websocket is None:
                logger.warning(f"设备 {device_id} 的 websocket 为 None，跳过推送")
                return False
            ws = conn.websocket
            closed = False
            if hasattr(ws, "closed") and ws.closed:
                closed = True
            elif hasattr(ws, "state") and ws.state.name == "CLOSED":
                closed = True
            if closed:
                logger.warning(f"设备 {device_id} 连接已关闭，跳过推送")
                return False
            await ws.send(json.dumps(msg))
            logger.info(f"向设备 {device_id} 推送{log_tag}")
            return True
        except Exception as e:
            logger.error(f"向设备 {device_id} 推送唤醒词失败: {e}")
            return False
