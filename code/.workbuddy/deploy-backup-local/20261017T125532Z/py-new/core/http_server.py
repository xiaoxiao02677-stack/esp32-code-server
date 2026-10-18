import asyncio
import os
import re
from aiohttp import web
from config.logger import setup_logging
from core.api.ota_handler import OTAHandler
from core.api.vision_handler import VisionHandler
from core.api.memory_handler import MemoryManageHandler
from core.api.tts_preview_handler import TtsPreviewHandler
from core.api.asr_recognize_handler import AsrRecognizeHandler
from core.api.llm_preview_handler import LlmPreviewHandler
from core.api.model_test_handler import ModelTestHandler
from core.api.wake_word_handler import WakeWordHandler
from core.api.push_handler import PushHandler
from core.api.wallpaper_handler import WallpaperHandler
from core.api.timeline_handler import TimelineHandler
from core.api.entity_handler import EntityHandler
from core.api.wechat_claw_handler import WeChatClawHandler

TAG = __name__

# Loopback-only source addresses for the internal management APIs.
_LOOPBACK_ADDRS = frozenset({"127.0.0.1", "::1"})


@web.middleware
async def memory_loopback_middleware(request, handler):
    """Security gate for /api/memory/** and /api/tts/** (P0, security review):

    1. Loopback-only (403): port 8003 is public-facing for OTA/vision; the memory admin
       API and TTS preview API are manager-api → same-host loopback. Non-loopback
       source → 403.
    2. Bearer auth (401): even from localhost, every process must present
       ``Authorization: Bearer {server.secret}`` (constant-time compare in the
       handler's _verify_auth). OPTIONS is exempt (CORS preflight carries no
       credentials by design and must succeed for browser clients).

    Order matters: loopback 403 fires before auth 401 (cheaper, stricter check first).
    Other paths pass through untouched."""
    if request.path.startswith("/api/memory/"):
        if request.remote not in _LOOPBACK_ADDRS:
            return web.json_response({"code": 403, "msg": "禁止访问", "data": None}, status=403)
        if request.method != "OPTIONS" and not self_memory_handler()._verify_auth(request):
            return web.json_response({"code": 401, "msg": "无效的认证token", "data": None}, status=401)
    if request.path.startswith("/api/tts/"):
        if request.remote not in _LOOPBACK_ADDRS:
            return web.json_response({"code": 403, "msg": "禁止访问", "data": None}, status=403)
        if request.method != "OPTIONS" and not self_tts_preview_handler()._verify_auth(request):
            return web.json_response({"code": 401, "msg": "无效的认证token", "data": None}, status=401)
    if request.path.startswith("/api/llm/"):
        if request.remote not in _LOOPBACK_ADDRS:
            return web.json_response({"code": 403, "msg": "禁止访问", "data": None}, status=403)
        if request.method != "OPTIONS" and not self_llm_preview_handler()._verify_auth(request):
            return web.json_response({"code": 401, "msg": "无效的认证token", "data": None}, status=401)
    if request.path.startswith("/api/model/"):
        if request.remote not in _LOOPBACK_ADDRS:
            return web.json_response({"code": 403, "msg": "禁止访问", "data": None}, status=403)
        if request.method != "OPTIONS" and not self_model_test_handler()._verify_auth(request):
            return web.json_response({"code": 401, "msg": "无效的认证token", "data": None}, status=401)
    return await handler(request)


def self_memory_handler():
    """Late-bound access to the MemoryManageHandler instance owned by SimpleHttpServer.

    The middleware is registered at module scope before SimpleHttpServer.__init__ runs,
    so it cannot close over the instance; the global is set in __init__."""
    return _MEMORY_HANDLER


_MEMORY_HANDLER = None


def self_tts_preview_handler():
    """Late-bound access to the TtsPreviewHandler instance (same pattern as memory)."""
    return _TTS_PREVIEW_HANDLER


_TTS_PREVIEW_HANDLER = None


def self_llm_preview_handler():
    """Late-bound access to the LlmPreviewHandler instance (same pattern as tts)."""
    return _LLM_PREVIEW_HANDLER


_LLM_PREVIEW_HANDLER = None


def self_model_test_handler():
    """Late-bound access to the ModelTestHandler instance (same pattern as tts)."""
    return _MODEL_TEST_HANDLER


_MODEL_TEST_HANDLER = None


class SimpleHttpServer:
    def __init__(self, config: dict):
        self.config = config
        self.logger = setup_logging()
        self.ota_handler = OTAHandler(config)
        self.vision_handler = VisionHandler(config)
        self.memory_handler = MemoryManageHandler(config)
        self.tts_preview_handler = TtsPreviewHandler(config)
        self.asr_recognize_handler = AsrRecognizeHandler(config)
        self.llm_preview_handler = LlmPreviewHandler(config)
        self.model_test_handler = ModelTestHandler(config)
        self.wake_word_handler = None
        self.push_handler = None
        self.wallpaper_handler = None
        self.timeline_handler = TimelineHandler(config)
        self.entity_handler = EntityHandler(config)
        self.wechat_claw_handler = None
        # Expose the instances to the module-scope middlewares (auth check).
        global _MEMORY_HANDLER, _TTS_PREVIEW_HANDLER, _LLM_PREVIEW_HANDLER, _MODEL_TEST_HANDLER
        _MEMORY_HANDLER = self.memory_handler
        _TTS_PREVIEW_HANDLER = self.tts_preview_handler
        _LLM_PREVIEW_HANDLER = self.llm_preview_handler
        _MODEL_TEST_HANDLER = self.model_test_handler
        _WAKE_WORD_HANDLER = None

    def set_wake_word_service(self, wake_word_service):
        self.wake_word_handler = WakeWordHandler(self.config, wake_word_service)
        global _WAKE_WORD_HANDLER
        _WAKE_WORD_HANDLER = self.wake_word_handler
        self.logger.bind(tag=TAG).info("WakeWordHandler 已绑定")

    def set_push_scheduler(self, push_scheduler):
        """绑定 PushScheduler 实例，用于 HTTP API 端点。"""
        self.push_handler = PushHandler(self.config, push_scheduler)
        self.logger.bind(tag=TAG).info("PushHandler 已绑定")

    def set_wallpaper_service(self, wallpaper_service):
        """绑定 WallpaperService 实例，用于壁纸下发 HTTP API。"""
        self.wallpaper_handler = WallpaperHandler(self.config, wallpaper_service)
        self.logger.bind(tag=TAG).info("WallpaperHandler 已绑定")

    def set_wechat_claw_service(self, claw_service):
        """绑定 WeChatClawService 实例，用于 HTTP API 端点。"""
        self.wechat_claw_handler = WeChatClawHandler(self.config, claw_service)
        self.logger.bind(tag=TAG).info("WeChatClawHandler 已绑定")

    async def _handle_tmp_options(self, request: web.Request) -> web.Response:
        """OPTIONS 预检，返回 CORS 头。"""
        resp = web.Response(status=204)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "client-id, content-type, device-id, authorization"
        return resp

    async def _handle_tmp_download(self, request: web.Request) -> web.Response:
        """静态文件服务：从 tmp/ 目录提供 TTS 合成音频。

        URL: /tmp/{filename}
        - filename 只允许安全字符（字母、数字、点、下划线、横线）
        - 路径须落在项目根目录下的 tmp/ 子目录内（防路径穿越）
        """
        return await self._serve_tmp_audio(request, allow_prefix=None)

    async def _handle_topic_audio_download(self, request: web.Request) -> web.Response:
        """受限静态文件服务：仅提供 tmp/ 下 topic- 前缀的推送音频。

        URL: /audio/{filename}
        - 与 _handle_tmp_download 的区别：无条件注册（不依赖
          read_config_from_api 开关），且强制 topic- 前缀白名单，
          绝不放行 tmp/server.log 等日志文件。
        - 面向设备公网下载推送通知音频（http_port 8003）。
        """
        return await self._serve_tmp_audio(request, allow_prefix="topic-")

    async def _serve_tmp_audio(
        self, request: web.Request, allow_prefix: str = None
    ) -> web.Response:
        """tmp/ 目录静态音频的公共实现（防穿越 + 可选前缀白名单）。"""
        try:
            fname = request.match_info.get("filename", "")
            if not fname:
                return web.Response(text="filename required", status=400)
            fname = os.path.basename(fname)
            if not re.match(r"^[A-Za-z0-9.\-_]+$", fname):
                return web.Response(text="invalid filename", status=400)
            if allow_prefix is not None and not fname.startswith(allow_prefix):
                return web.Response(text="forbidden prefix", status=403)

            tmp_dir = os.path.join(os.getcwd(), "tmp")
            file_path = os.path.join(tmp_dir, fname)
            file_real = os.path.realpath(file_path)
            tmp_dir_real = os.path.realpath(tmp_dir)
            if not file_real.startswith(tmp_dir_real + os.sep) and file_real != tmp_dir_real:
                return web.Response(text="forbidden", status=403)
            if not os.path.isfile(file_real):
                return web.Response(text="file not found", status=404)

            # 推断 MIME 类型
            ext = os.path.splitext(fname)[1].lower()
            content_type = {
                ".mp3": "audio/mpeg",
                ".wav": "audio/wav",
                ".ogg": "audio/ogg",
                ".opus": "audio/opus",
                ".flac": "audio/flac",
            }.get(ext, "application/octet-stream")

            resp = web.FileResponse(path=file_real, headers={
                "Cache-Control": "no-cache",
                "Access-Control-Allow-Origin": "*",
            })
            resp.content_type = content_type
            return resp
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"tmp 文件下载异常: {e}")
            return web.Response(text="download error", status=500)

    def _get_websocket_url(self, local_ip: str, port: int) -> str:
        """获取websocket地址

        Args:
            local_ip: 本地IP地址
            port: 端口号

        Returns:
            str: websocket地址
        """
        server_config = self.config["server"]
        websocket_config = server_config.get("websocket")

        if websocket_config and "你" not in websocket_config:
            return websocket_config
        else:
            return f"ws://{local_ip}:{port}/yuhe/v1/"

    async def start(self):
        try:
            server_config = self.config["server"]
            read_config_from_api = self.config.get("read_config_from_api", False)
            host = server_config.get("ip", "0.0.0.0")
            port = int(server_config.get("http_port", 8003))

            if port:
                # client_max_size：与 manager-api asrRecognize 的 2MB 音频上限对齐
                # （aiohttp 默认 1MB，超过直接 413 Request Entity Too Large）
                app = web.Application(client_max_size=8 * 1024 * 1024)

                # 安全前置：/api/memory/** 仅允许本机回环访问（manager-api 与 yuhe-server
                # 同机部署，经 127.0.0.1 互调）。8003 同时承载 OTA/vision 面向公网，若不拦截，
                # 公网可直达记忆管理端点。覆盖所有方法（含 OPTIONS）；必须先于路由注册。
                app.middlewares.append(memory_loopback_middleware)

                if not read_config_from_api:
                    # 如果没有开启智控台，只是单模块运行，就需要再添加简单OTA接口，用于下发websocket接口
                    app.add_routes(
                        [
                            web.get("/yuhe/ota/", self.ota_handler.handle_get),
                            web.post("/yuhe/ota/", self.ota_handler.handle_post),
                            web.options(
                                "/yuhe/ota/", self.ota_handler.handle_options
                            ),
                            web.options(
                                "/yuhe/ota/download/{filename}",
                                self.ota_handler.handle_options,
                            ),
                            # 下载接口，仅提供 data/bin/*.bin 下载
                            web.get(
                                "/yuhe/ota/download/{filename}",
                                self.ota_handler.handle_download,
                            ),
                            web.options(
                                "/yuhe/ota/download/{filename}",
                                self.ota_handler.handle_options,
                            ),
                            # TTS 临时音频静态暴露：/tmp/{filename}
                            web.get(
                                "/tmp/{filename}",
                                self._handle_tmp_download,
                            ),
                            web.options(
                                "/tmp/{filename}",
                                self._handle_tmp_options,
                            ),
                        ]
                    )
                # 添加路由
                app.add_routes(
                    [
                        web.get("/mcp/vision/explain", self.vision_handler.handle_get),
                        web.post(
                            "/mcp/vision/explain", self.vision_handler.handle_post
                        ),
                        web.options(
                            "/mcp/vision/explain", self.vision_handler.handle_options
                        ),
                    ]
                )

                # 推送通知音频（受限静态路由，无条件注册）
                # /audio/{filename} 仅放行 tmp/topic-* 前缀，供设备下载
                # 推送 TTS 音频；不依赖 read_config_from_api 开关。
                app.add_routes(
                    [
                        web.get(
                            "/audio/{filename}",
                            self._handle_topic_audio_download,
                        ),
                        web.options(
                            "/audio/{filename}",
                            self._handle_tmp_options,
                        ),
                    ]
                )

                # 内部记忆管理 API（manager-api 经 server.secret 鉴权代理转发，design §3.1）
                app.add_routes(
                    [
                        web.get("/api/memory/agents", self.memory_handler.dispatch(self.memory_handler.handle_agents)),
                        web.options(
                            "/api/memory/agents", self.memory_handler.handle_options
                        ),
                        web.get(
                            "/api/memory/{agent_id}/facts",
                            self.memory_handler.dispatch(self.memory_handler.handle_list_facts),
                        ),
                        web.post(
                            "/api/memory/{agent_id}/facts",
                            self.memory_handler.dispatch(self.memory_handler.handle_create_fact),
                        ),
                        web.options(
                            "/api/memory/{agent_id}/facts",
                            self.memory_handler.handle_options,
                        ),
                        web.get(
                            "/api/memory/{agent_id}/facts/{fact_id}",
                            self.memory_handler.dispatch(self.memory_handler.handle_get_fact),
                        ),
                        web.put(
                            "/api/memory/{agent_id}/facts/{fact_id}",
                            self.memory_handler.dispatch(self.memory_handler.handle_update_fact),
                        ),
                        web.delete(
                            "/api/memory/{agent_id}/facts/{fact_id}",
                            self.memory_handler.dispatch(self.memory_handler.handle_delete_fact),
                        ),
                        web.post(
                            "/api/memory/{agent_id}/facts/{fact_id}/feedback",
                            self.memory_handler.dispatch(self.memory_handler.handle_feedback),
                        ),
                        web.post(
                            "/api/memory/{agent_id}/facts/{fact_id}/review",
                            self.memory_handler.dispatch(self.memory_handler.handle_review),
                        ),
                    ]
                )

                # 记忆时间查询 API（manager-api 经 server.secret 鉴权代理转发）
                app.add_routes(
                    [
                        web.get(
                            "/api/memory/{agent_id}/timeline",
                            self.timeline_handler.handle_list_timeline,
                        ),
                        web.options(
                            "/api/memory/{agent_id}/timeline",
                            self.timeline_handler.handle_options,
                        ),
                        web.get(
                            "/api/memory/{agent_id}/timeline/by-date/{date}",
                            self.timeline_handler.handle_list_by_date,
                        ),
                        web.options(
                            "/api/memory/{agent_id}/timeline/by-date/{date}",
                            self.timeline_handler.handle_options,
                        ),
                        web.post(
                            "/api/memory/{agent_id}/facts/{fact_id}/times",
                            self.timeline_handler.handle_add_times,
                        ),
                        web.delete(
                            "/api/memory/{agent_id}/facts/{fact_id}/times",
                            self.timeline_handler.handle_remove_times,
                        ),
                        web.get(
                            "/api/memory/{agent_id}/timeline/chart",
                            self.timeline_handler.handle_chart,
                        ),
                        web.options(
                            "/api/memory/{agent_id}/timeline/chart",
                            self.timeline_handler.handle_options,
                        ),
                    ]
                )

                # 实体图谱 API（manager-api 经 Bearer auth 代理转发）
                app.add_routes(
                    [
                        web.post(
                            "/api/memory/{agent_id}/entities/extract",
                            self.entity_handler.handle_extract_entities,
                        ),
                        web.get(
                            "/api/memory/{agent_id}/entities",
                            self.entity_handler.handle_list_entities,
                        ),
                        web.get(
                            "/api/memory/{agent_id}/entities/graph",
                            self.entity_handler.handle_get_entity_graph,
                        ),
                    ]
                )

                # 运行服务
                runner = web.AppRunner(app)

                # 内部 TTS 试听 API（manager-api 经 server.secret 鉴权代理转发）
                app.add_routes(
                    [
                        web.post(
                            "/api/tts/preview",
                            self.tts_preview_handler.handle_preview,
                        ),
                        web.options(
                            "/api/tts/preview",
                            self.tts_preview_handler.handle_options,
                        ),
                    ]
                )

                # 内部 LLM 试聊 API（manager-api 经 server.secret 鉴权代理转发）
                app.add_routes(
                    [
                        web.get(
                            "/api/llm/preview",
                            self.llm_preview_handler.handle_preview,
                        ),
                        web.post(
                            "/api/llm/preview",
                            self.llm_preview_handler.handle_preview,
                        ),
                        web.options(
                            "/api/llm/preview",
                            self.llm_preview_handler.handle_options,
                        ),
                    ]
                )

                # 内部模型测试 API（manager-api 经 server.secret 鉴权代理转发）
                app.add_routes(
                    [
                        web.post(
                            "/api/model/test",
                            self.model_test_handler.handle_test,
                        ),
                        web.options(
                            "/api/model/test",
                            self.model_test_handler.handle_options,
                        ),
                    ]
                )

                # 内部 ASR 识别 API（cc-console 链路模拟器真实 ASR；manager-api 代理转发）
                app.add_routes(
                    [
                        web.post(
                            "/api/asr/recognize",
                            self.asr_recognize_handler.handle_recognize,
                        ),
                    ]
                )

                # 内部唤醒词推送 API（manager-api 经 server.secret 鉴权代理转发）
                if self.wake_word_handler is not None:
                    app.add_routes(
                        [
                            web.post(
                                "/api/wake-word/push",
                                self.wake_word_handler.handle_push,
                            ),
                            web.post(
                                "/api/device-config/push",
                                self.wake_word_handler.handle_push_device_config,
                            ),
                            web.get(
                                "/api/wake-word/devices",
                                self.wake_word_handler.handle_list_devices,
                            ),
                        ]
                    )

                # 随机推送调度 API（manager-api 经 server.secret 鉴权代理转发）
                if self.push_handler is not None:
                    app.add_routes(
                        [
                            web.post(
                                "/api/push/schedule",
                                self.push_handler.handle_schedule,
                            ),
                            web.get(
                                "/api/push/tasks",
                                self.push_handler.handle_list_tasks,
                            ),
                            web.get(
                                "/api/push/tasks/{push_id}",
                                self.push_handler.handle_get_task,
                            ),
                        ]
                    )

                # 壁纸即时下发 API（manager-api 经 server.secret 鉴权代理转发）
                if self.wallpaper_handler is not None:
                    app.add_routes(
                        [
                            web.post(
                                "/api/wallpaper/dispatch",
                                self.wallpaper_handler.handle_dispatch,
                            ),
                            web.get(
                                "/api/wallpaper/queue",
                                self.wallpaper_handler.handle_queue,
                            ),
                        ]
                    )

                # 微信 ClawBot API（manager-api 经 server.secret 鉴权代理转发）
                if self.wechat_claw_handler is not None:
                    app.add_routes(
                        [
                            # 用户绑定管理
                            web.get(
                                "/api/wechat/claw/users",
                                self.wechat_claw_handler.handle_list_users,
                            ),
                            web.post(
                                "/api/wechat/claw/bind",
                                self.wechat_claw_handler.handle_bind,
                            ),
                            web.delete(
                                "/api/wechat/claw/unbind/{openid}",
                                self.wechat_claw_handler.handle_unbind,
                            ),
                            # 对话管理
                            web.get(
                                "/api/wechat/claw/conversations/{openid}",
                                self.wechat_claw_handler.handle_get_conversations,
                            ),
                            web.delete(
                                "/api/wechat/claw/conversations/{openid}",
                                self.wechat_claw_handler.handle_clear_conversation,
                            ),
                            web.post(
                                "/api/wechat/claw/messages/{openid}",
                                self.wechat_claw_handler.handle_send_message,
                            ),
                            # 定时任务管理
                            web.get(
                                "/api/wechat/claw/schedules/{openid}",
                                self.wechat_claw_handler.handle_list_schedules,
                            ),
                            web.post(
                                "/api/wechat/claw/schedules/{openid}",
                                self.wechat_claw_handler.handle_create_schedule,
                            ),
                            web.delete(
                                "/api/wechat/claw/schedules/{openid}/{id}",
                                self.wechat_claw_handler.handle_delete_schedule,
                            ),
                            web.put(
                                "/api/wechat/claw/schedules/{openid}/{id}/toggle",
                                self.wechat_claw_handler.handle_toggle_schedule,
                            ),
                        ]
                    )

                await runner.setup()
                site = web.TCPSite(runner, host, port)
                await site.start()

                # 保持服务运行
                while True:
                    await asyncio.sleep(3600)  # 每隔 1 小时检查一次
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"HTTP服务器启动失败: {e}")
            import traceback

            self.logger.bind(tag=TAG).error(f"错误堆栈: {traceback.format_exc()}")
            raise
