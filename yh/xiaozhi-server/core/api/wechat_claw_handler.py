"""WeChat ClawBot HTTP API Handler.

Endpoints:
- GET    /api/wechat/claw/users          - 列出已绑定用户
- POST   /api/wechat/claw/bind           - 绑定用户
- DELETE /api/wechat/claw/unbind/{openid} - 解除绑定
- GET    /api/wechat/claw/conversations/{openid} - 获取对话历史
- POST   /api/wechat/claw/messages/{openid}       - 发送消息
- GET    /api/wechat/claw/schedules/{openid}      - 获取定时任务列表
- POST   /api/wechat/claw/schedules/{openid}      - 创建定时任务
- DELETE /api/wechat/claw/schedules/{openid}/{id} - 删除定时任务
- PUT    /api/wechat/claw/schedules/{openid}/{id}/toggle - 启用/禁用
"""
import json
import logging
from aiohttp import web
from core.api.base_handler import BaseHandler
from core.services.wechat_claw_service import WeChatClawService

TAG = __name__
logger = logging.getLogger(TAG)


class WeChatClawHandler(BaseHandler):
    """微信ClawBot HTTP API处理器."""

    def __init__(self, config: dict, claw_service: WeChatClawService):
        super().__init__(config)
        self.claw = claw_service
        # 内部服务密钥（与 server.secret 相同）
        self._auth_key = (config.get("server", {}) or {}).get("auth_key") or ""

    def _verify_auth(self, request) -> bool:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return False
        token = auth[7:]
        return bool(self._auth_key) and token == self._auth_key

    def _json(self, code: int, msg: str, data=None, status: int = 200) -> web.Response:
        body = json.dumps(
            {"code": code, "msg": msg, "data": data},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        resp = web.Response(text=body, content_type="application/json", status=status)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp

    async def handle_options(self, request) -> web.Response:
        resp = web.Response(status=204)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        return resp

    # ── 用户绑定 ────────────────────────────────────────────────

    async def handle_list_users(self, request) -> web.Response:
        """GET /api/wechat/claw/users"""
        if not self._verify_auth(request):
            return self._json(401, "未授权")
        try:
            users = await self.claw.db.list_active_users()
            result = []
            for u in users:
                result.append({
                    "openid": u["openid"],
                    "device_id": u["device_id"],
                    "bound_at": u["bound_at"],
                    "conversation_count": await self.claw.db.get_conversation_count(u["openid"]),
                })
            return self._json(0, "success", {"users": result, "total": len(result)})
        except Exception as e:
            logger.error(f"List users failed: {e}", exc_info=True)
            return self._json(500, f"查询失败: {str(e)}")

    async def handle_bind(self, request) -> web.Response:
        """POST /api/wechat/claw/bind
        Body: {"openid": "xxx", "device_id": "xxx"}
        """
        if not self._verify_auth(request):
            return self._json(401, "未授权")
        try:
            body = await request.json()
            openid = body.get("openid", "").strip()
            device_id = body.get("device_id", "").strip()
            if not openid or not device_id:
                return self._json(400, "openid 和 device_id 必填")
            binding = await self.claw.bind_user(openid, device_id)
            return self._json(0, "绑定成功", binding)
        except Exception as e:
            logger.error(f"Bind failed: {e}", exc_info=True)
            return self._json(500, f"绑定失败: {str(e)}")

    async def handle_unbind(self, request) -> web.Response:
        """DELETE /api/wechat/claw/unbind/{openid}"""
        if not self._verify_auth(request):
            return self._json(401, "未授权")
        openid = request.match_info.get("openid", "")
        if not openid:
            return self._json(400, "openid 必填")
        try:
            ok = await self.claw.unbind_user(openid)
            return self._json(0, "解绑成功" if ok else "用户不存在", {"ok": ok})
        except Exception as e:
            logger.error(f"Unbind failed: {e}", exc_info=True)
            return self._json(500, f"解绑失败: {str(e)}")

    # ── 对话管理 ────────────────────────────────────────────────

    async def handle_get_conversations(self, request) -> web.Response:
        """GET /api/wechat/claw/conversations/{openid}"""
        if not self._verify_auth(request):
            return self._json(401, "未授权")
        openid = request.match_info.get("openid", "")
        if not openid:
            return self._json(400, "openid 必填")
        try:
            msgs = await self.claw.get_conversations(openid)
            return self._json(0, "success", {"messages": msgs, "total": len(msgs)})
        except Exception as e:
            logger.error(f"Get conversations failed: {e}", exc_info=True)
            return self._json(500, f"查询失败: {str(e)}")

    async def handle_clear_conversation(self, request) -> web.Response:
        """DELETE /api/wechat/claw/conversations/{openid}"""
        if not self._verify_auth(request):
            return self._json(401, "未授权")
        openid = request.match_info.get("openid", "")
        if not openid:
            return self._json(400, "openid 必填")
        try:
            count = await self.claw.clear_conversation(openid)
            return self._json(0, f"已清除 {count} 条消息", {"cleared": count})
        except Exception as e:
            logger.error(f"Clear conversation failed: {e}", exc_info=True)
            return self._json(500, f"清除失败: {str(e)}")

    async def handle_send_message(self, request) -> web.Response:
        """POST /api/wechat/claw/messages/{openid}
        Body: {"content": "xxx", "type": "text"}
        """
        if not self._verify_auth(request):
            return self._json(401, "未授权")
        openid = request.match_info.get("openid", "")
        if not openid:
            return self._json(400, "openid 必填")
        try:
            body = await request.json()
            content = body.get("content", "").strip()
            msg_type = body.get("type", "text")
            if not content:
                return self._json(400, "content 必填")
            reply = await self.claw.receive_message(openid, content, msg_type)
            if reply is None:
                return self._json(400, "用户未绑定")
            return self._json(0, "发送成功", reply.to_dict())
        except Exception as e:
            logger.error(f"Send message failed: {e}", exc_info=True)
            return self._json(500, f"发送失败: {str(e)}")

    # ── 定时任务 ────────────────────────────────────────────────

    async def handle_list_schedules(self, request) -> web.Response:
        """GET /api/wechat/claw/schedules/{openid}"""
        if not self._verify_auth(request):
            return self._json(401, "未授权")
        openid = request.match_info.get("openid", "")
        if not openid:
            return self._json(400, "openid 必填")
        try:
            schedules = await self.claw.list_schedules(openid)
            return self._json(0, "success", {"schedules": schedules, "total": len(schedules)})
        except Exception as e:
            logger.error(f"List schedules failed: {e}", exc_info=True)
            return self._json(500, f"查询失败: {str(e)}")

    async def handle_create_schedule(self, request) -> web.Response:
        """POST /api/wechat/claw/schedules/{openid}
        Body: {"task_name": "xxx", "cron": "0 9 * * *", "message": "xxx"}
        """
        if not self._verify_auth(request):
            return self._json(401, "未授权")
        openid = request.match_info.get("openid", "")
        if not openid:
            return self._json(400, "openid 必填")
        try:
            body = await request.json()
            task_name = body.get("task_name", "").strip()
            cron_expr = body.get("cron", "").strip()
            message = body.get("message", "").strip()
            if not task_name or not cron_expr:
                return self._json(400, "task_name 和 cron 必填")
            payload = {"message": message or f"[定时提醒] {task_name}"}
            sched = await self.claw.create_schedule(openid, task_name, cron_expr, payload)
            return self._json(0, "创建成功", sched)
        except Exception as e:
            logger.error(f"Create schedule failed: {e}", exc_info=True)
            return self._json(500, f"创建失败: {str(e)}")

    async def handle_delete_schedule(self, request) -> web.Response:
        """DELETE /api/wechat/claw/schedules/{openid}/{id}"""
        if not self._verify_auth(request):
            return self._json(401, "未授权")
        openid = request.match_info.get("openid", "")
        schedule_id = request.match_info.get("id", "")
        if not openid or not schedule_id:
            return self._json(400, "openid 和 id 必填")
        try:
            ok = await self.claw.delete_schedule(openid, int(schedule_id))
            return self._json(0, "删除成功" if ok else "任务不存在", {"ok": ok})
        except Exception as e:
            logger.error(f"Delete schedule failed: {e}", exc_info=True)
            return self._json(500, f"删除失败: {str(e)}")

    async def handle_toggle_schedule(self, request) -> web.Response:
        """PUT /api/wechat/claw/schedules/{openid}/{id}/toggle"""
        if not self._verify_auth(request):
            return self._json(401, "未授权")
        openid = request.match_info.get("openid", "")
        schedule_id = request.match_info.get("id", "")
        if not openid or not schedule_id:
            return self._json(400, "openid 和 id 必填")
        try:
            # 重新加载任务列表获取当前状态
            schedules = await self.claw.list_schedules(openid)
            target = next((s for s in schedules if str(s["id"]) == schedule_id), None)
            if not target:
                return self._json(404, "任务不存在")
            # 切换状态
            new_enabled = not bool(target.get("enabled", 1))
            # 更新数据库
            import sqlite3, time
            db_path = self.claw.db._db_path
            conn = sqlite3.connect(db_path, timeout=10)
            conn.execute(
                "UPDATE schedules SET enabled = ? WHERE id = ? AND user_id = ?",
                (1 if new_enabled else 0, int(schedule_id), openid),
            )
            conn.commit()
            conn.close()
            # 启动或取消任务
            if new_enabled:
                target["enabled"] = 1
                await self.claw._start_schedule_task(target)
            else:
                target["enabled"] = 0
                async with self.claw._schedule_lock:
                    task = self.claw._schedules.pop(int(schedule_id), None)
                    if task:
                        task.cancel()
            return self._json(0, "success", {"enabled": new_enabled})
        except Exception as e:
            logger.error(f"Toggle schedule failed: {e}", exc_info=True)
            return self._json(500, f"操作失败: {str(e)}")
