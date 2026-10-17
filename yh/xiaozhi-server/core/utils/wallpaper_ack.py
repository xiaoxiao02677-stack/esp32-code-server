#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""壁纸下发回执落库

设备收到 ``{"type":"wallpaper","action":"set",...}`` 后回执：

    {"type":"wallpaper","action":"result","version":"3",
     "status":"ok"|"fail","reason":"..."}

服务端写入 Redis：``wallpaper:ack:{device_id}``
value 为 JSON 字符串 ``{"version":..,"status":..,"reason":..,"ts":..}``，
TTL 7 天（604800 秒）。``ts`` 为毫秒时间戳。

Redis 连接按需惰性建立，配置读取 ``config["redis"]``：::

    redis:
      host: 127.0.0.1
      port: 6379
      db: 0
      password: ""
      # 或直接给 url: redis://:pass@host:6379/0

未配置 / 未安装 redis 客户端 / 连接失败时仅记录日志，不影响设备主流程。
TODO(P1-3): xiaozhi-server 目前无 Redis 依赖，如需启用回执查询，
      在 requirements.txt 增加 ``redis>=5.0`` 并配置 config.redis。
"""
import json
import logging

from core.utils.stdlib_log_bridge import install_stdlib_log_bridge
import time

logger = logging.getLogger(__name__)
install_stdlib_log_bridge(__name__)

TAG = __name__

ACK_KEY_PREFIX = "wallpaper:ack:"
ACK_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 天

_redis_client = None
_redis_unavailable = False


def build_ack_key(device_id: str) -> str:
    return f"{ACK_KEY_PREFIX}{device_id}"


async def get_client(config: dict):
    """惰性创建 Redis 客户端；不可用时返回 None（只打一次告警）。

    供壁纸回执与壁纸待补投队列（wallpaper_service）共用同一连接。
    """
    global _redis_client, _redis_unavailable
    if _redis_client is not None:
        return _redis_client
    if _redis_unavailable:
        return None

    cfg = (config or {}).get("redis") or {}
    if not isinstance(cfg, dict) or not (cfg.get("url") or cfg.get("host")):
        logger.warning(
            f"[{TAG}] 未配置 config.redis（host/url），壁纸回执仅记录日志（TODO: 接入 Redis）"
        )
        _redis_unavailable = True
        return None

    try:
        import redis.asyncio as aioredis
    except ImportError:
        logger.warning(
            f"[{TAG}] 未安装 redis 客户端（pip install redis），壁纸回执仅记录日志（TODO: 接入 Redis）"
        )
        _redis_unavailable = True
        return None

    try:
        if cfg.get("url"):
            _redis_client = aioredis.Redis.from_url(
                cfg["url"], decode_responses=True, socket_connect_timeout=2
            )
        else:
            _redis_client = aioredis.Redis(
                host=cfg.get("host", "127.0.0.1"),
                port=int(cfg.get("port", 6379)),
                db=int(cfg.get("db", 0)),
                password=cfg.get("password") or None,
                decode_responses=True,
                socket_connect_timeout=2,
            )
    except Exception as e:
        logger.error(f"[{TAG}] 创建 Redis 客户端失败: {e}")
        _redis_unavailable = True
        return None

    logger.info(f"[{TAG}] 壁纸回执 Redis 客户端已创建")
    return _redis_client


async def save_ack(config: dict, device_id: str, ack: dict) -> bool:
    """写入壁纸回执，成功返回 True；Redis 不可用/写入失败返回 False。"""
    record = {
        "version": str(ack.get("version", "")),
        "status": ack.get("status", ""),
        "reason": ack.get("reason", ""),
        "ts": int(time.time() * 1000),
    }
    if not device_id:
        logger.warning(f"[{TAG}] 壁纸回执缺少 device_id，丢弃: {record}")
        return False

    value = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    client = await get_client(config)
    if client is None:
        logger.info(f"[{TAG}] 壁纸回执（未落 Redis）device={device_id} {value}")
        return False

    try:
        await client.set(build_ack_key(device_id), value, ex=ACK_TTL_SECONDS)
        logger.info(f"[{TAG}] 壁纸回执已写入 Redis: {build_ack_key(device_id)} {value}")
        return True
    except Exception as e:
        logger.error(f"[{TAG}] 壁纸回执写入 Redis 失败: {e}")
        return False
