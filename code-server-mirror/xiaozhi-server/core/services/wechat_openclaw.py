"""WeChat OpenClaw integration service.

Handles WeChat message receive, user binding, and command dispatch.
Supports both official WeChat (公众号) and WeCom (企业微信) APIs.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import time
from typing import Optional, Dict, Any
from datetime import datetime

import aiohttp
from aiohttp import web

logger = logging.getLogger(__name__)

# WeChat API config keys
_OPENID_KEY = "openid"
_USER_ID_KEY = "user_id"
_SESSION_KEY = "session_key"


class WeChatOpenClawService:
    """WeChat OpenClaw integration service."""

    def __init__(self, config: dict):
        self.config = config
        self.app_id = config.get("wechat", {}).get("app_id", "")
        self.app_secret = config.get("wechat", {}).get("app_secret", "")
        self.token = config.get("wechat", {}).get("token", "")
        self.encoding_aes_key = config.get("wechat", {}).get("encoding_aes_key", "")

        # In-memory user store (should use Redis in production)
        self._users: Dict[str, dict] = {}
        self._sessions: Dict[str, dict] = {}

        # WeChat API base URLs
        self._api_base = "https://api.weixin.qq.com"
        self._token_cache = None
        self._token_expire = 0

    async def get_access_token(self) -> str:
        """Get or refresh WeChat access token."""
        if self._token_cache and time.time() < self._token_expire:
            return self._token_cache

        url = f"{self._api_base}/cgi-bin/token"
        params = {
            "grant_type": "client_credential",
            "appid": self.app_id,
            "secret": self.app_secret,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                data = await resp.json()
                if "access_token" in data:
                    self._token_cache = data["access_token"]
                    self._token_expire = time.time() + data.get("expires_in", 7000) - 300
                    logger.info("WeChat access token refreshed")
                    return self._token_cache
                else:
                    logger.error(f"Failed to get access token: {data}")
                    raise Exception(f"WeChat token error: {data.get('errcode')}: {data.get('errmsg')}")

    def verify_signature(self, signature: str, timestamp: str, nonce: str, echostr: str = "") -> bool:
        """Verify WeChat message signature."""
        if not self.token:
            return True  # Skip verification if token not configured

        # Sort and concatenate parameters
        sorted_params = sorted([self.token, timestamp, nonce])
        string = "".join(sorted_params)

        # SHA1 hash
        sha1 = hashlib.sha1(string.encode()).hexdigest()

        return sha1 == signature

    def bind_user(self, openid: str, device_id: str) -> dict:
        """Bind WeChat user to device."""
        binding = {
            "openid": openid,
            "device_id": device_id,
            "bound_at": datetime.now().isoformat(),
        }
        self._users[openid] = binding
        logger.info(f"User {openid} bound to device {device_id}")
        return binding

    def get_user_device(self, openid: str) -> Optional[str]:
        """Get device ID for a WeChat user."""
        user = self._users.get(openid)
        return user.get("device_id") if user else None

    def get_user_openid(self, device_id: str) -> Optional[str]:
        """Get openid for a device."""
        for openid, user in self._users.items():
            if user.get("device_id") == device_id:
                return openid
        return None

    async def send_template_message(self, openid: str, template_id: str, data: dict) -> bool:
        """Send WeChat template message."""
        token = await self.get_access_token()
        url = f"{self._api_base}/cgi-bin/message/template/send?access_token={token}"

        payload = {
            "touser": openid,
            "template_id": template_id,
            "data": data,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                result = await resp.json()
                if result.get("errcode") == 0:
                    return True
                else:
                    logger.error(f"Failed to send template message: {result}")
                    return False

    async def create_handler(self) -> web.View:
        """Create aiohttp request handler for WeChat messages."""
        handler = self._handle_wechat_request
        return handler

    async def _handle_wechat_request(self, request: web.Request) -> web.Response:
        """Handle incoming WeChat requests."""
        if request.method == "GET":
            # URL verification
            signature = request.query.get("signature", "")
            timestamp = request.query.get("timestamp", "")
            nonce = request.query.get("nonce", "")
            echostr = request.query.get("echostr", "")

            if self.verify_signature(signature, timestamp, nonce, echostr):
                return web.Response(text=echostr)
            else:
                return web.Response(status=403, text="Forbidden")

        elif request.method == "POST":
            # Receive message
            body = await request.text()
            content_type = request.content_type

            if "xml" in content_type:
                return await self._handle_xml_message(body)
            else:
                return web.Response(status=400, text="Only XML messages supported")

        else:
            return web.Response(status=405, text="Method not allowed")

    async def _handle_xml_message(self, body: str) -> web.Response:
        """Handle XML message from WeChat."""
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(body)

            # Extract message fields
            to_username = root.findtext("ToUserName", "")
            from_username = root.findtext("FromUserName", "")
            msg_type = root.findtext("MsgType", "")
            content = root.findtext("Content", "")
            msg_id = root.findtext("MsgId", "")

            logger.debug(f"WeChat message: type={msg_type}, from={from_username}")

            # Route to device
            device_id = self.get_user_device(from_username)
            if device_id:
                # Send to device via WebSocket
                await self._dispatch_to_device(from_username, msg_type, content, msg_id)

            # Return empty response to acknowledge receipt
            return web.Response(text="success")

        except Exception as e:
            logger.error(f"Failed to handle WeChat message: {e}")
            return web.Response(status=500, text=str(e))

    async def _dispatch_to_device(self, openid: str, msg_type: str, content: str, msg_id: str):
        """Dispatch message to bound device."""
        # This would integrate with the existing WebSocket connection system
        # For now, log the message
        logger.info(f"Dispatching WeChat message to device: openid={openid}, type={msg_type}, content={content[:50]}")

        # Store in pending queue for device to pick up
        pending_key = f"wechat:{openid}:{msg_id}"
        self._sessions[pending_key] = {
            "openid": openid,
            "msg_type": msg_type,
            "content": content,
            "msg_id": msg_id,
            "created_at": datetime.now().isoformat(),
        }

        # TODO: Notify device via existing WebSocket channel
        # For now, just store for polling


def create_wechat_app(config: dict) -> web.Application:
    """Create aiohttp application for WeChat integration."""
    app = web.Application()

    # Initialize WeChat service
    wechat_service = WeChatOpenClawService(config)

    # Register routes
    app.router.add_get("/api/wechat", wechat_service.create_handler())
    app.router.add_post("/api/wechat", wechat_service.create_handler())

    # Webhook endpoint for WeChat callbacks
    app.router.add_get("/wechat/callback", wechat_service.create_handler())
    app.router.add_post("/wechat/callback", wechat_service.create_handler())

    return app
