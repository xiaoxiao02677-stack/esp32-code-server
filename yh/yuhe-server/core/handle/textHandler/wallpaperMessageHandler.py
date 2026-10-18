import time
from typing import Any, Dict

from core.handle.textMessageHandler import TextMessageHandler
from core.handle.textMessageType import TextMessageType
from core.utils.wallpaper_ack import save_ack

TAG = __name__


class WallpaperMessageHandler(TextMessageHandler):
    """壁纸回执处理器

    设备收到 ``{"type":"wallpaper","action":"set",...}`` 后回执：
    ``{"type":"wallpaper","action":"result","version":"3",
       "status":"ok"|"fail","reason":"..."}``

    回执写入 Redis ``wallpaper:ack:{device_id}``（TTL 7 天），
    Redis 不可用时仅记录日志，不阻塞设备主流程。
    """

    @property
    def message_type(self) -> TextMessageType:
        return TextMessageType.WALLPAPER

    async def handle(self, conn, msg_json: Dict[str, Any]) -> None:
        action = msg_json.get("action")
        if action != "result":
            conn.logger.bind(tag=TAG).debug(f"忽略壁纸消息（非回执）: {msg_json}")
            return

        device_id = getattr(conn, "device_id", None) or ""
        status = msg_json.get("status", "")
        reason = msg_json.get("reason", "")
        ack = {
            "version": msg_json.get("version", ""),
            "status": status,
            "reason": reason,
            "ts": int(time.time() * 1000),
        }
        if status not in ("ok", "fail"):
            conn.logger.bind(tag=TAG).warning(
                f"壁纸回执 status 异常（{status}），按原值记录: {msg_json}"
            )

        try:
            saved = await save_ack(conn.config, device_id, ack)
        except Exception as e:
            conn.logger.bind(tag=TAG).error(f"壁纸回执处理异常: {e}")
            return

        conn.logger.bind(tag=TAG).info(
            f"壁纸回执: device={device_id} version={ack['version']} "
            f"status={status} reason={reason} redis={saved}"
        )
