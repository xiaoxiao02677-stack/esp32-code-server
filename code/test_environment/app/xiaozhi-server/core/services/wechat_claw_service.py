"""WeChat ClawBot core service.

Orchestrates user binding, message dispatch, conversation management,
and scheduled task execution for the WeChat integration layer.
"""
import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from core.services.database_manager import DatabaseManager
from core.services.message_processor import MessageProcessor, NormalisedMessage

logger = logging.getLogger(__name__)


# ── schedule expression helpers ──────────────────────────────

def _cron_next_fire(cron_expr: str, after_ts: Optional[float] = None) -> float:
    """Return the next fire timestamp for a simple cron expression.

    Supports 5-field standard cron (min hour dom month dow).
    Expanding to a full cron parser is left as future work.
    """
    if after_ts is None:
        after_ts = time.time()
    dt = datetime.fromtimestamp(after_ts)
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression: {cron_expr!r}")

    def _match(value: int, field: str) -> bool:
        if field == "*":
            return True
        if "/" in field:
            step = int(field.split("/")[1])
            return value % step == 0
        if "," in field:
            return int(value) in [int(x) for x in field.split(",")]
        if "-" in field:
            lo, hi = field.split("-")
            return int(lo) <= int(value) <= int(hi)
        return int(value) == int(field)

    # Simple brute-force scan up to 7 days ahead
    now = dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(7 * 24 * 60):
        if (_match(now.minute, parts[0]) and
                _match(now.hour, parts[1]) and
                _match(now.day, parts[2]) and
                _match(now.month, parts[3]) and
                _match(now.weekday(), parts[4])):
            return now.timestamp()
        now += timedelta(minutes=1)
    raise RuntimeError("Could not find next fire time within 7 days")


# ── WeChatClawService ────────────────────────────────────────

class WeChatClawService:
    """微信ClawBot服务，处理消息收发、对话管理、定时任务."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        db_cfg = config.get("database", {})
        db_path = db_cfg.get("path", "wechat_claw.db")
        self.db = DatabaseManager(db_path)
        self.msg_processor = MessageProcessor(config)

        # In-memory conversation handle (mirrors db for fast access)
        self.conversations: Dict[str, Any] = {}

        # Scheduled tasks: schedule_id -> asyncio.Task
        self._schedules: Dict[int, asyncio.Task] = {}
        self._schedule_lock = asyncio.Lock()
        self._running = False

        # Event loop for the scheduler tick
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # ── lifecycle ──────────────────────────────────────────────

    async def start(self) -> None:
        """启动服务，初始化数据库、加载定时任务."""
        await self.db.init()
        self._running = True
        self._loop = asyncio.get_event_loop()

        # Restore schedules from DB and recreate tasks
        users = await self.db.list_active_users()
        for user in users:
            schedules = await self.db.list_schedules(user["openid"])
            for sched in schedules:
                if sched["enabled"]:
                    await self._start_schedule_task(sched)

        logger.info("WeChatClawService started")

    async def stop(self) -> None:
        """停止服务，取消所有定时任务."""
        self._running = False
        async with self._schedule_lock:
            for task in list(self._schedules.values()):
                task.cancel()
            await asyncio.gather(*self._schedules.values(), return_exceptions=True)
            self._schedules.clear()
        logger.info("WeChatClawService stopped")

    # ── user binding ───────────────────────────────────────────

    async def bind_user(self, openid: str, qr_code: str) -> Dict[str, Any]:
        """用户扫码绑定 — qr_code 可携带 device_id 信息."""
        # Extract device_id from qr_code payload (format: "device:<device_id>")
        device_id = qr_code.strip()
        if device_id.startswith("device:"):
            device_id = device_id[len("device:"):]

        binding = await self.db.bind_user(openid, device_id)
        # Warm up conversation context
        if openid not in self.conversations:
            self.conversations[openid] = self.msg_processor._get_or_create_context(openid)
        logger.info(f"User {openid} bound to device {device_id}")
        return binding

    async def unbind_user(self, openid: str) -> bool:
        """解除绑定."""
        ok = await self.db.unbind_user(openid)
        # Close conversation context
        if openid in self.conversations:
            del self.conversations[openid]
        return ok

    async def get_user_device(self, openid: str) -> Optional[str]:
        """查询用户绑定的设备 ID."""
        return await self.db.get_user_device(openid)

    # ── message sending ────────────────────────────────────────

    async def send_message(
        self,
        openid: str,
        message: str,
        msg_type: str = "text",
    ) -> bool:
        """发送消息到微信（通过已有 API 或 webhook）.

        实际发送逻辑依赖底层 WeChat API（此处以日志占位，后续对接 aiohttp 调用）。
        """
        if not await self.db.get_user_device(openid):
            logger.warning(f"User {openid} is not bound, skip send")
            return False

        logger.debug(f"Sending {msg_type} message to {openid}: {message[:80]}")
        # TODO: integrate with real WeChat push channel
        return True

    # ── message receiving ──────────────────────────────────────

    async def receive_message(
        self,
        openid: str,
        content: str,
        msg_type: str = "text",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Optional[NormalisedMessage]:
        """接收微信消息并处理，返回 LLM 生成的回复消息."""
        device_id = await self.db.get_user_device(openid)
        if not device_id:
            logger.warning(f"User {openid} is not bound, ignoring message")
            return None

        raw = {
            "MsgType": msg_type,
            "Content": content,
            "FromUserName": openid,
            **(extra or {}),
        }

        # 持久化用户消息
        await self.db.save_message(openid, "user", content, {"type": msg_type})

        # LLM 生成回复
        reply = await self.msg_processor.process_user_message(openid, raw)

        # 持久化助手回复
        await self.db.save_message(
            openid, "assistant", reply.content,
            metadata={"source": "llm"},
        )

        # 回传消息到微信
        await self.send_message(openid, reply.content)

        return reply

    # ── conversation helpers ───────────────────────────────────

    async def get_conversations(self, openid: str) -> List[Dict[str, Any]]:
        """获取某用户的对话历史记录."""
        return await self.db.get_conversation_history(openid, last_n=20)

    async def clear_conversation(self, openid: str) -> int:
        """清空某用户的对话历史."""
        in_mem = await self.msg_processor.clear_context(openid)
        db_count = await self.db.clear_conversation(openid)
        return db_count

    # ── scheduled tasks ────────────────────────────────────────

    async def create_schedule(
        self,
        openid: str,
        task_name: str,
        cron_expr: str,
        payload: Dict[str, Any],
   ) -> Dict[str, Any]:
        """创建定时任务."""
        next_fire = _cron_next_fire(cron_expr)
        sid = await self.db.save_schedule(openid, task_name, cron_expr, payload, next_fire)

        sched = {
            "id": sid,
            "user_id": openid,
            "task_name": task_name,
            "cron_expr": cron_expr,
            "payload": payload,
            "next_fire": next_fire,
        }
        await self._start_schedule_task(sched)
        logger.info(f"Schedule '{task_name}' created for {openid}, next fire={next_fire}")
        return sched

    async def delete_schedule(self, openid: str, schedule_id: int) -> bool:
        """删除定时任务."""
        ok = await self.db.delete_schedule(schedule_id, openid)
        async with self._schedule_lock:
            task = self._schedules.pop(schedule_id, None)
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        return bool(ok)

    async def list_schedules(self, openid: str) -> List[Dict[str, Any]]:
        """列出定时任务."""
        return await self.db.list_schedules(openid)

    # ── internal scheduler ─────────────────────────────────────

    async def _start_schedule_task(self, sched: Dict[str, Any]) -> None:
        """注册一个 asyncio 定时任务."""
        task = asyncio.ensure_future(self._schedule_loop(sched))
        async with self._schedule_lock:
            self._schedules[sched["id"]] = task

    async def _schedule_loop(self, sched: Dict[str, Any]) -> None:
        """Periodic loop that fires when next_fire is reached."""
        while self._running:
            now = time.time()
            wait_secs = sched["next_fire"] - now
            if wait_secs > 0:
                try:
                    await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(None, time.sleep, wait_secs),
                        timeout=wait_secs + 5,
                    )
                except asyncio.TimeoutError:
                    pass
            if not self._running:
                break

            # Fire the task
            try:
                await self._execute_schedule(sched)
                # Compute next fire
                next_fire = _cron_next_fire(sched["cron_expr"])
                await self.db.update_next_fire(sched["id"], next_fire)
                sched["next_fire"] = next_fire
                await self.db.mark_last_run(sched["id"])
            except Exception as exc:
                logger.error(f"Schedule {sched['id']} execution failed: {exc}")
                # Back-off 1 minute before retry
                await asyncio.sleep(60)

    async def _execute_schedule(self, sched: Dict[str, Any]) -> None:
        """执行单次定时任务."""
        openid = sched["user_id"]
        payload = sched["payload"]
        logger.info(
            f"Firing schedule '{sched['task_name']}' for {openid}, "
            f"payload={json.dumps(payload, ensure_ascii=False)}"
        )
        # Default action: send a message
        message = payload.get("message", f"[定时提醒] {sched['task_name']}")
        await self.send_message(openid, message)
