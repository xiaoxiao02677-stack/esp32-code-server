#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""随机推送调度 HTTP API

端点：
    POST /api/push/schedule   调度推送任务
    GET  /api/push/tasks      查询所有推送任务列表
    GET  /api/push/tasks/{push_id}  查询单个推送任务状态
"""
import json
import logging
from typing import Optional
from aiohttp import web
from core.api.base_handler import BaseHandler

logger = logging.getLogger(__name__)
TAG = __name__


def _json_response(code: int, msg: str, data=None, status: int = 200) -> web.Response:
    body = json.dumps({"code": code, "msg": msg, "data": data}, ensure_ascii=False, separators=(",", ":"))
    resp = web.Response(text=body, content_type="application/json", status=status)
    resp.headers["Access-Control-Allow-Headers"] = "client-id, content-type, device-id, authorization"
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


class PushHandler(BaseHandler):
    def __init__(self, config: dict, push_scheduler=None):
        super().__init__(config)
        self.push_scheduler = push_scheduler
        self._auth_key = config.get("server", {}).get("auth_key", "")

    def _verify_auth(self, request: web.Request) -> bool:
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else auth
        if not self._auth_key or not token:
            logger.warning("[%s] 鉴权失败（token为空或服务端未配置auth_key）", TAG)
            return False
        import hmac as _hmac
        return _hmac.compare_digest(token, self._auth_key)

    async def handle_schedule(self, request: web.Request) -> web.Response:
        """调度推送任务。

        请求体：
            {
                "device_ids": ["dev1", "dev2"],
                "content": {
                    "push_type": "random",   // random | urgent
                    "audio_url": "https://...",
                    "subtitles": [{"text": "..."}]
                },
                "schedule": {
                    "type": "immediate",    // immediate | delayed | cron
                    "cron": null,           // "every_30s" / "hourly" / "daily"
                    "delay_seconds": 0
                },
                "rate_limit": {"per_device": 3, "window_seconds": 300}
            }
        """
        try:
            if not self._verify_auth(request):
                return _json_response(401, "无效的认证token", status=401)

            body = await request.json()

            device_ids = body.get("device_ids")
            content = body.get("content")
            schedule = body.get("schedule", {})

            if not isinstance(device_ids, list) or not device_ids:
                return _json_response(400, "device_ids 必须为非空列表", status=400)
            if not isinstance(content, dict) or not content.get("audio_url"):
                return _json_response(400, "content 必须包含 audio_url", status=400)

            # 校验 push_type
            push_type_value = content.get("push_type", "random")
            valid_push_types = {"random", "urgent", "low"}
            if push_type_value not in valid_push_types:
                return _json_response(400, f"content.push_type 非法，允许值: {valid_push_types}", status=400)
            if not isinstance(schedule, dict):
                return _json_response(400, "schedule 必须为对象", status=400)

            valid_types = {"immediate", "delayed", "cron"}
            push_type = schedule.get("type", "immediate")
            if push_type not in valid_types:
                return _json_response(400, f"schedule.type 非法，允许值: {valid_types}", status=400)

            if push_type == "delayed":
                delay = schedule.get("delay_seconds", 0)
                if not isinstance(delay, (int, float)) or delay < 0:
                    return _json_response(400, "delay_seconds 必须为非负数", status=400)
            if push_type == "cron":
                cron_expr = schedule.get("cron", "")
                if not cron_expr:
                    return _json_response(400, "cron 表达式不能为空", status=400)

            if self.push_scheduler is None:
                return _json_response(503, "PushScheduler 未初始化", status=503)

            rate_limit = body.get("rate_limit")
            if rate_limit is not None:
                if not isinstance(rate_limit, dict):
                    return _json_response(400, "rate_limit 必须为对象", status=400)

            push_id = await self.push_scheduler.schedule_push(
                device_ids=list(device_ids),
                content=content,
                schedule=schedule,
                rate_limit=rate_limit,
            )
            return _json_response(0, "success", data={"push_id": push_id})
        except json.JSONDecodeError:
            return _json_response(400, "请求体 JSON 解析失败", status=400)
        except Exception as e:
            logger.error("[%s] 调度推送异常: %s", TAG, e, exc_info=True)
            return _json_response(500, f"内部错误: {str(e)}", status=500)

    async def handle_list_tasks(self, request: web.Request) -> web.Response:
        """查询所有推送任务列表。"""
        try:
            if not self._verify_auth(request):
                return _json_response(401, "无效的认证token", status=401)
            if self.push_scheduler is None:
                return _json_response(503, "PushScheduler 未初始化", status=503)
            tasks = self.push_scheduler.list_tasks()
            return _json_response(0, "success", data={"tasks": tasks})
        except Exception as e:
            logger.error("[%s] 查询任务列表异常: %s", TAG, e, exc_info=True)
            return _json_response(500, f"内部错误: {str(e)}", status=500)

    async def handle_get_task(self, request: web.Request) -> web.Response:
        """查询单个推送任务状态。"""
        try:
            if not self._verify_auth(request):
                return _json_response(401, "无效的认证token", status=401)
            push_id = request.match_info["push_id"]
            if self.push_scheduler is None:
                return _json_response(503, "PushScheduler 未初始化", status=503)
            task = self.push_scheduler.get_task(push_id)
            if task is None:
                return _json_response(404, "任务不存在", status=404)
            return _json_response(0, "success", data=task)
        except Exception as e:
            logger.error("[%s] 查询任务异常: %s", TAG, e, exc_info=True)
            return _json_response(500, f"内部错误: {str(e)}", status=500)
