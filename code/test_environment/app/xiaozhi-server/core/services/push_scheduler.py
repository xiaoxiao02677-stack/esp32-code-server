#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""随机推送调度器，支持即时/定时(cron)/延迟推送及频率限制。

设计说明：
- 本项目未引入 Redis，调度状态全部使用 asyncio 内存管理，重启后定时任务丢失（可接受）
- 依赖 WakeWordService 获取在线设备列表，避免重复维护连接映射
- cron 调度用 asyncio 周期任务模拟，避免引入 apscheduler 等新依赖
"""
import asyncio
import json
import logging
import random
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)
TAG = __name__

# 推送状态
PUSH_STATUS_PENDING = "pending"
PUSH_STATUS_SENT = "sent"
PUSH_STATUS_FAILED = "failed"

# 推送优先级（数值越小优先级越高）
PRIORITY_URGENT = 1    # 紧急推送 - 立即送达，不可延迟
PRIORITY_RANDOM = 5    # 普通推送 - 正常排队
PRIORITY_LOW = 10      # 低优先级 - 可延迟或被丢弃


class PushScheduler:
    """推送调度器，管理定时/随机推送任务队列。"""

    def __init__(self):
        # push_id -> PushTask
        self._tasks: Dict[str, dict] = {}
        # 活跃 cron 循环任务：push_id -> asyncio.Task
        self._cron_tasks: Dict[str, asyncio.Task] = {}
        # 频率限制：device_id -> {"count": int, "window_start": float}
        self._rate_limits: Dict[str, dict] = {}
        # 优先级队列：(priority, timestamp, push_id)
        self._priority_queue: List[tuple] = []
        # 执行中的任务 ID（防止重复执行同一优先级任务）
        self._executing: set = set()
        self._lock = asyncio.Lock()
        self._running = False
        self._wake_word_service = None  # 由 start() 注入
        # 并发度配置
        self._max_concurrent = 5  # 最大并发推送数
        # 话题生成独立并发信号量（与 _max_concurrent 区分）
        self._generation_semaphore = asyncio.Semaphore(3)
        self._topic_generator = None  # 由 set_topic_generator() 注入

    def set_wake_word_service(self, service) -> None:
        """注入 WakeWordService 实例，用于获取在线设备。"""
        self._wake_word_service = service

    def set_topic_generator(self, generator) -> None:
        """注入 TopicGenerator 实例，用于 topic_sources 自动生成。"""
        self._topic_generator = generator

    async def start(self) -> None:
        """启动调度器后台循环。"""
        if self._running:
            return
        self._running = True
        logger.info("PushScheduler 启动")
        # 启动优先级调度协程
        asyncio.create_task(self._priority_scheduler_loop())

    async def _priority_scheduler_loop(self) -> None:
        """优先级调度主循环：按优先级依次处理待执行任务。"""
        while self._running:
            await asyncio.sleep(0.1)  # 检查间隔
            executing_count = len(self._executing)
            if executing_count >= self._max_concurrent:
                continue

            # 找出所有待执行的一次性任务（非 cron，cron 由独立协程管理）
            pending_tasks = [
                (p, ts, pid)
                for (p, ts, pid) in self._priority_queue
                if pid in self._tasks and self._tasks[pid]["status"] == PUSH_STATUS_PENDING
                and self._tasks[pid]["schedule"].get("type") != "cron"
            ]
            if not pending_tasks:
                continue

            # 按优先级排序（数值小=高优先级）
            pending_tasks.sort(key=lambda x: x[0])

            # 执行最高优先级的任务（一次最多执行 max_concurrent - executing_count 个）
            budget = self._max_concurrent - executing_count
            for p, ts, pid in pending_tasks[:budget]:
                self._executing.add(pid)
                asyncio.create_task(self._run_pending_task(pid))

    async def _run_pending_task(self, push_id: str) -> None:
        """执行一个待执行的推送任务。"""
        try:
            async with self._lock:
                task = self._tasks.get(push_id)
            if task and task["status"] == PUSH_STATUS_PENDING:
                # P0 修复：delayed 类型实际等待 delay_seconds 后再执行
                push_type = task["schedule"].get("type", "immediate")
                if push_type == "delayed":
                    delay = task["schedule"].get("delay_seconds", 0)
                    if isinstance(delay, (int, float)) and delay > 0:
                        logger.info(f"推送任务 {push_id} 延迟 {delay}s 后执行")
                        await asyncio.sleep(delay)
                        # 重新检查状态（可能已被取消）
                        async with self._lock:
                            task = self._tasks.get(push_id)
                        if not task or task["status"] != PUSH_STATUS_PENDING:
                            return
                await self._deliver(task)
        finally:
            self._executing.discard(push_id)

    async def stop(self) -> None:
        """停止调度器，取消所有活跃的定时/延迟任务。"""
        self._running = False
        for pid, task in list(self._cron_tasks.items()):
            task.cancel()
        self._cron_tasks.clear()
        logger.info("PushScheduler 已停止")

    async def schedule_push(
        self,
        device_ids: List[str],
        content: dict,
        schedule: dict,
        rate_limit: Optional[dict] = None,
    ) -> str:
        """调度一次推送任务，返回 push_id。

        Args:
            device_ids: 目标设备 ID 列表
            content: 推送内容，需包含 audio_url、subtitles 等字段
            schedule: 调度配置，type 为 immediate/cron/delayed
            rate_limit: 频率限制配置，如 {"per_device": 3, "window_seconds": 300}
        """
        push_id = f"push_{int(time.time() * 1000)}"
        push_type = schedule.get("type", "immediate")
        default_rl = {"per_device": 3, "window_seconds": 300}
        rl = {**default_rl, **(rate_limit or {})}

        task = {
            "push_id": push_id,
            "device_ids": list(set(device_ids)),
            "content": content,
            "schedule": schedule,
            "rate_limit": rl,
            "status": PUSH_STATUS_PENDING,
            "created_at": time.time(),
            "sent_count": 0,
            "failed_count": 0,
        }

        async with self._lock:
            self._tasks[push_id] = task
            # 确定优先级并加入优先级队列
            priority = self._resolve_priority(push_type, content)
            timestamp = time.time()
            self._priority_queue.append((priority, timestamp, push_id))
            # 对优先级队列排序（保持堆有序）
            self._priority_queue.sort(key=lambda x: (x[0], x[1]))

        if push_type == "immediate" or push_type == "delayed" or push_type == "cron":
            # 任务已在优先级队列中，由 _priority_scheduler_loop 负责执行（immediate/delayed）
            # 或启动独立循环协程（cron）
            if push_type == "cron":
                asyncio.create_task(self._execute_cron(push_id))
            logger.info(
                f"推送任务已加入优先级队列: {push_id}, priority={priority}, type={push_type}, devices={len(task['device_ids'])}"
            )
        else:
            logger.warning(f"未知推送类型: {push_type}，按 immediate 处理")
            priority = self._resolve_priority("immediate", content)
            timestamp = time.time()
            self._priority_queue.append((priority, timestamp, push_id))
            self._priority_queue.sort(key=lambda x: (x[0], x[1]))

        logger.info(
            f"推送任务已创建: {push_id}, priority={priority}, type={push_type}, devices={len(task['device_ids'])}"
        )
        return push_id

    def _resolve_priority(self, push_type: str, content: dict) -> int:
        """根据 push_type 和内容解析优先级。"""
        push_type_value = content.get("push_type", "random")
        if push_type_value == "urgent":
            return PRIORITY_URGENT
        elif push_type_value == "low":
            return PRIORITY_LOW
        return PRIORITY_RANDOM

    async def _execute_immediate(self, push_id: str) -> None:
        """立即执行推送。"""
        async with self._lock:
            task = self._tasks.get(push_id)
        if not task:
            return
        await self._deliver(task)

    async def _execute_cron(self, push_id: str) -> None:
        """按 cron 表达式周期执行推送（用 asyncio 模拟）。

        支持表达式格式：
        - "every_Ns" : 每 N 秒执行一次
        - "every_Mm" : 每 N 分钟执行一次
        - "hourly"   : 每小时执行
        - "daily"    : 每天执行
        - 标准 cron 字符串如 "0 9 * * *" 暂不支持（需 apscheduler）
        """
        cron_expr = self._tasks.get(push_id, {}).get("schedule", {}).get("cron", "")
        interval = self._parse_cron_interval(cron_expr)

        if interval is None:
            logger.error(f"Cron 表达式无法解析: {cron_expr}")
            async with self._lock:
                if push_id in self._tasks:
                    self._tasks[push_id]["status"] = PUSH_STATUS_FAILED
            return

        async with self._lock:
            self._cron_tasks[push_id] = asyncio.current_task()

        try:
            while self._running and push_id in self._tasks:
                await self._deliver(self._tasks[push_id])
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info(f"Cron 推送任务已取消: {push_id}")
        finally:
            async with self._lock:
                self._cron_tasks.pop(push_id, None)

    def _parse_cron_interval(self, expr: str) -> Optional[int]:
        """解析 cron 表达式为间隔秒数。返回 None 表示无法解析。"""
        expr = expr.strip().lower()
        if expr.startswith("every_"):
            try:
                val_str = expr[6:]
                if val_str.endswith("s"):
                    return int(val_str[:-1])
                elif val_str.endswith("m"):
                    return int(val_str[:-1]) * 60
                elif val_str.endswith("h"):
                    return int(val_str[:-1]) * 3600
            except ValueError:
                pass
        # 简单关键词
        mapping = {
            "hourly": 3600,
            "daily": 86400,
            "every_minute": 60,
            "every_5_minutes": 300,
            "every_10_minutes": 600,
            "every_30_minutes": 1800,
        }
        return mapping.get(expr)

    async def _deliver(self, task: dict) -> None:
        """向目标设备投递推送消息，优先处理高优先级任务。"""
        push_id = task["push_id"]
        device_ids = task["device_ids"]
        content = task["content"]
        rl = task["rate_limit"]
        priority = self._resolve_priority(task["schedule"].get("type", "immediate"), content)
        now = time.time()

        # ---- 话题生成管线：content 含 topic_sources 且无 audio_url 时自动生成 ----
        topic_sources = content.get("topic_sources")
        if topic_sources and not content.get("audio_url") and self._topic_generator:
            # 反查：从 _agent_devices 找到包含任一 device_id 的 agent
            resolved_agent_id = None
            if self._wake_word_service and hasattr(self._wake_word_service, "_agent_devices"):
                for aid, devices in self._wake_word_service._agent_devices.items():
                    if any(did in devices for did in device_ids):
                        resolved_agent_id = aid
                        break
            try:
                async with self._generation_semaphore:
                    result = await self._topic_generator.generate_for_agent(
                        resolved_agent_id or device_ids[0],
                        topic_sources,
                        location=content.get("location"),
                    )
                # 写回 content（所有设备共用同一话题）
                content["text"] = result.get("text", "")
                content["audio_url"] = result.get("audio_url", "")
                content["subtitles"] = result.get("subtitles", [])
                meta = result.get("generation_meta", {})
                logger.info(
                    f"话题生成完成: {push_id}, source={meta.get('source')}, "
                    f"fallback={meta.get('fallback_used', False)}, audio_url={content.get('audio_url', '')}"
                )
            except Exception as e:
                logger.error(f"话题生成失败，降级为纯文本推送: {e}", exc_info=True)
                content["text"] = ""
                content["audio_url"] = ""
                content["subtitles"] = []
        elif topic_sources and not content.get("audio_url") and not self._topic_generator:
            logger.warning(
                f"[{TAG}] content 含 topic_sources 但 TopicGenerator 未注入，跳过生成"
            )

        sent = 0
        failed = 0
        skipped_rl = 0

        # 获取在线设备交集
        online_devices = set()
        if self._wake_word_service:
            online_devices = set(self._wake_word_service.get_online_devices())

        target_devices = set(device_ids) & online_devices if online_devices else set(device_ids)

        # 高优先级任务按随机顺序打散（避免同时推送同一设备）
        device_list = list(target_devices)
        if priority == PRIORITY_URGENT:
            # 紧急任务：按原始顺序，确保顺序性
            pass
        else:
            # 普通/低优先级：随机打散
            random.shuffle(device_list)

        for device_id in device_list:
            if not self._check_rate_limit(device_id, rl, now):
                skipped_rl += 1
                continue
            ok = await self._send_to_device(device_id, content)
            if ok:
                sent += 1
            else:
                failed += 1

        async with self._lock:
            task["sent_count"] = sent
            task["failed_count"] = failed
            task["priority"] = priority
            # cron 任务不改变状态；一次性任务标记完成
            if task["schedule"].get("type") != "cron":
                task["status"] = PUSH_STATUS_SENT if sent > 0 else PUSH_STATUS_FAILED
                # 从优先级队列中移除已完成任务
                self._priority_queue = [
                    item for item in self._priority_queue
                    if item[2] != push_id
                ]

        logger.info(
            f"推送完成: {push_id}, priority={priority}, sent={sent}, failed={failed}, rate_limit_skipped={skipped_rl}"
        )

    def _check_rate_limit(self, device_id: str, rate_limit: dict, now: float) -> bool:
        """检查设备是否超出频率限制。"""
        max_per_window = rate_limit.get("per_device", 3)
        window = rate_limit.get("window_seconds", 300)

        state = self._rate_limits.get(device_id)
        if state is None or (now - state["window_start"]) >= window:
            # 新窗口
            self._rate_limits[device_id] = {"count": 1, "window_start": now}
            return True

        state["count"] += 1
        if state["count"] > max_per_window:
            return False
        return True

    async def _send_to_device(self, device_id: str, content: dict) -> bool:
        """向单台设备发送推送消息。

        设备 WS 在线：直推 notify。
        设备仅心跳在线（WS 断开，空闲态）：notify 入离线队列，
        设备下次建立 WS（用户唤醒/对话）时由 register_connection 自动补推。
        """
        if not self._wake_word_service:
            logger.error(f"WakeWordService 未注入，无法推送: {device_id}")
            return False

        try:
            conn = self._wake_word_service._connections.get(device_id)
            if conn is None:
                # 心跳在线但 WS 断开：入离线队列，WS 重连时补推
                hb = getattr(self._wake_word_service, "heartbeat_server", None)
                hb_online = False
                if hb is not None:
                    try:
                        for hb_did, info in hb.devices.items():
                            normalized = str(hb_did)
                            if normalized.startswith("xiaozhi-") and ":" not in normalized:
                                raw = normalized[len("xiaozhi-"):].lower()
                                if len(raw) == 12 and all(c in "0123456789abcdef" for c in raw):
                                    normalized = ":".join(raw[i:i + 2] for i in range(0, 12, 2))
                            if normalized == device_id and info.get("online"):
                                hb_online = True
                                break
                    except Exception:
                        pass
                if hb_online:
                    msg = {
                        "type": "notify",
                        "push_type": content.get("push_type", "random"),
                        "audio_url": content.get("audio_url", ""),
                        "subtitles": content.get("subtitles", []),
                    }
                    async with self._wake_word_service._lock:
                        self._wake_word_service._offline_queue.setdefault(device_id, []).append(msg)
                    logger.info(f"设备 {device_id} 心跳在线但WS断开，notify 已入离线队列(设备WS重连时补推)")
                    return True
                logger.warning(f"设备 {device_id} 不在线")
                return False

            # 复用 WakeWordService 的推送逻辑（检查 websocket 有效性）
            if not hasattr(conn, "websocket") or conn.websocket is None:
                return False
            ws = conn.websocket
            closed = False
            if hasattr(ws, "closed") and ws.closed:
                closed = True
            elif hasattr(ws, "state") and ws.state.name == "CLOSED":
                closed = True
            if closed:
                return False

            msg = {
                "type": "notify",
                "push_type": content.get("push_type", "random"),
                "audio_url": content.get("audio_url", ""),
                "subtitles": content.get("subtitles", []),
            }
            await ws.send(json.dumps(msg))
            logger.info(f"推送已发送到设备 {device_id}")
            return True
        except Exception as e:
            logger.error(f"向设备 {device_id} 推送失败: {e}")
            return False

    def get_task(self, push_id: str) -> Optional[dict]:
        """查询推送任务状态。"""
        return self._tasks.get(push_id)

    def list_tasks(self) -> List[dict]:
        """列出所有推送任务（不含内部敏感字段）。"""
        result = []
        for t in self._tasks.values():
            result.append({
                "push_id": t["push_id"],
                "status": t["status"],
                "type": t["schedule"].get("type"),
                "priority": t.get("priority", PRIORITY_RANDOM),
                "device_count": len(t["device_ids"]),
                "sent_count": t["sent_count"],
                "failed_count": t["failed_count"],
                "created_at": t["created_at"],
            })
        # 按优先级排序返回
        result.sort(key=lambda x: x["priority"])
        return result
