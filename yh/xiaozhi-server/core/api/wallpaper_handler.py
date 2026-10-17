#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""壁纸即时下发 HTTP API

端点：
    POST /api/wallpaper/dispatch   向在线设备下发壁纸设置指令
    GET  /api/wallpaper/queue      查看待补投队列（?flush=1 立即补投一轮）
"""
import json
import logging

from core.utils.stdlib_log_bridge import install_stdlib_log_bridge

from aiohttp import web

from core.api.base_handler import BaseHandler

logger = logging.getLogger(__name__)
install_stdlib_log_bridge(__name__)
TAG = __name__


def _json_response(code: int, msg: str, data=None, status: int = 200) -> web.Response:
    body = json.dumps(
        {"code": code, "msg": msg, "data": data},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    resp = web.Response(text=body, content_type="application/json", status=status)
    resp.headers["Access-Control-Allow-Headers"] = (
        "client-id, content-type, device-id, authorization"
    )
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


class WallpaperHandler(BaseHandler):
    def __init__(self, config: dict, wallpaper_service=None):
        super().__init__(config)
        self.wallpaper_service = wallpaper_service
        self._auth_key = config.get("server", {}).get("auth_key", "")

    def _verify_auth(self, request: web.Request) -> bool:
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else auth
        if not self._auth_key or not token:
            logger.warning("[%s] 鉴权失败（token为空或服务端未配置auth_key）", TAG)
            return False
        import hmac as _hmac

        return _hmac.compare_digest(token, self._auth_key)

    async def handle_dispatch(self, request: web.Request) -> web.Response:
        """下发壁纸。

        请求体：
            {
                "device_ids": ["AA:BB:CC:DD:EE:FF"],
                "wallpaper": {
                    "version": "3",
                    "url": "https://...",
                    "md5": "...",
                    "size": 115200,
                    "format": "rgb565"
                }
            }

        响应 data：
            {"sent": ["AA:BB:..."], "offline": ["..."]}
        """
        try:
            if not self._verify_auth(request):
                return _json_response(401, "无效的认证token", status=401)

            body = await request.json()

            device_ids = body.get("device_ids")
            wallpaper = body.get("wallpaper")

            if not isinstance(device_ids, list) or not device_ids:
                return _json_response(400, "device_ids 必须为非空列表", status=400)
            if not all(isinstance(d, str) and d for d in device_ids):
                return _json_response(400, "device_ids 元素必须为非空字符串", status=400)
            if not isinstance(wallpaper, dict):
                return _json_response(400, "wallpaper 必须为对象", status=400)
            if not wallpaper.get("url"):
                return _json_response(400, "wallpaper.url 不能为空", status=400)
            if wallpaper.get("size") is not None and not isinstance(
                wallpaper.get("size"), int
            ):
                return _json_response(400, "wallpaper.size 必须为整数", status=400)
            if not wallpaper.get("version"):
                return _json_response(400, "wallpaper.version 不能为空", status=400)

            if self.wallpaper_service is None:
                return _json_response(503, "WallpaperService 未初始化", status=503)

            result = await self.wallpaper_service.dispatch(
                device_ids=list(device_ids), wallpaper=wallpaper
            )
            return _json_response(
                0,
                "success",
                data={
                    "sent": result["sent"],
                    "queued": result.get("queued", []),
                    "offline": result["offline"],
                },
            )
        except json.JSONDecodeError:
            return _json_response(400, "请求体 JSON 解析失败", status=400)
        except Exception as e:
            logger.error("[%s] 壁纸下发异常: %s", TAG, e, exc_info=True)
            return _json_response(500, f"内部错误: {str(e)}", status=500)

    async def handle_queue(self, request: web.Request) -> web.Response:
        """查看待补投队列；``?flush=1`` 时先立即补投一轮再返回结果。

        响应 data：
            {"pending": {"<device_id>": "<version>"}, "flushed": <本轮成功条数>}
        """
        try:
            if not self._verify_auth(request):
                return _json_response(401, "无效的认证token", status=401)
            if self.wallpaper_service is None:
                return _json_response(503, "WallpaperService 未初始化", status=503)

            flushed = None
            if request.query.get("flush", "") in ("1", "true", "yes"):
                flushed = await self.wallpaper_service.sweep_once()
            return _json_response(
                0,
                "success",
                data={
                    "pending": self.wallpaper_service.queue_snapshot(),
                    "flushed": flushed,
                },
            )
        except Exception as e:
            logger.error("[%s] 查询壁纸队列异常: %s", TAG, e, exc_info=True)
            return _json_response(500, f"内部错误: {str(e)}", status=500)
