"""唤醒词推送 HTTP API。

端点：
- POST /api/wake_words/push   推送唤醒词给指定设备或 agent 下所有设备
- GET  /api/wake_words/devices  查询当前在线设备列表

鉴权：
- 走 loopback_middleware（仅本机回环可访问）+ Bearer token 校验。
- token 来源：config["server"]["auth_key"]（与 vision/OTA 接口共用）。
"""

import json
import logging
from aiohttp import web

from core.api.base_handler import BaseHandler

logger = logging.getLogger(__name__)
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


class WakeWordHandler(BaseHandler):
    def __init__(self, config: dict, wake_word_service=None):
        super().__init__(config)
        self.wake_word_service = wake_word_service
        self._auth_key = config.get("server", {}).get("auth_key", "")

    def _verify_auth(self, request: web.Request) -> bool:
        """Bearer token 校验（与 memory_loopback_middleware 风格一致）。"""
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
        else:
            token = auth
        if not token or token == self._auth_key:
            return True
        logger.bind(tag=TAG).warning("鉴权失败，token 不匹配")
        return False

    async def handle_push(self, request: web.Request) -> web.Response:
        """
        POST /api/wake_words/push
        Body JSON:
        {
            "agent_id": "<agent_id>",         # 可选，向该 agent 下所有绑定设备推送
            "device_id": "<device_id>",       # 可选，精确指定单台设备
            "wake_words": ["你好小智", "Hi XiaoZhi"],
            "tts_rate": 0                       # 可选，TTS 语速，默认 0
        }
        """
        try:
            if not self._verify_auth(request):
                return _json_response(401, "无效的认证token", status=401)

            body = await request.json()
            agent_id = body.get("agent_id")
            device_id = body.get("device_id")
            wake_words = body.get("wake_words", [])
            tts_rate = int(body.get("tts_rate", 0))

            if not wake_words:
                return _json_response(400, "wake_words 不能为空", status=400)
            if not isinstance(wake_words, list):
                return _json_response(400, "wake_words 必须是列表", status=400)
            if not agent_id and not device_id:
                return _json_response(
                    400, "agent_id 和 device_id 至少需要指定一个", status=400
                )

            if self.wake_word_service is None:
                return _json_response(503, "WakeWordService 未初始化", status=503)

            result = await self.wake_word_service.push_wake_words(
                agent_id=agent_id,
                device_id=device_id,
                wake_words=wake_words,
                tts_rate=tts_rate,
            )
            return _json_response(0, "success", data=result)

        except json.JSONDecodeError:
            return _json_response(400, "请求体 JSON 解析失败", status=400)
        except Exception as e:
            logger.bind(tag=TAG).error(f"推送唤醒词异常: {e}", exc_info=True)
            return _json_response(500, f"内部错误: {str(e)}", status=500)

    async def handle_list_devices(self, request: web.Request) -> web.Response:
        """
        GET /api/wake_words/devices
        Query 参数（可选）：
            agent_id: 过滤只返回该 agent 绑定的设备
        """
        try:
            if not self._verify_auth(request):
                return _json_response(401, "无效的认证token", status=401)

            if self.wake_word_service is None:
                return _json_response(503, "WakeWordService 未初始化", status=503)

            filter_agent = request.query.get("agent_id")
            online = self.wake_word_service.get_online_devices()
            if filter_agent:
                agent_devices = self.wake_word_service._agent_devices.get(
                    filter_agent, set()
                )
                online = [d for d in online if d in agent_devices]

            return _json_response(0, "success", data={"devices": online})
        except Exception as e:
            logger.bind(tag=TAG).error(
                f"查询设备列表异常: {e}", exc_info=True
            )
            return _json_response(500, f"内部错误: {str(e)}", status=500)
