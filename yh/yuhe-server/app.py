import sys
import uuid
import signal
import asyncio
from aioconsole import ainput
from config.settings import load_config
from config.logger import setup_logging
from core.utils.util import get_local_ip, validate_mcp_endpoint
from core.http_server import SimpleHttpServer
from core.websocket_server import WebSocketServer
from core.heartbeat import HeartbeatServer
from core.utils.util import check_ffmpeg_installed
from core.utils.gc_manager import get_gc_manager

TAG = __name__
logger = setup_logging()


async def wait_for_exit() -> None:
    """
    阻塞直到收到 Ctrl‑C / SIGTERM。
    - Unix: 使用 add_signal_handler
    - Windows: 依赖 KeyboardInterrupt
    """
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    if sys.platform != "win32":  # Unix / macOS
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)
        await stop_event.wait()
    else:
        # Windows：await一个永远pending的fut，
        # 让 KeyboardInterrupt 冒泡到 asyncio.run，以此消除遗留普通线程导致进程退出阻塞的问题
        try:
            await asyncio.Future()
        except KeyboardInterrupt:  # Ctrl‑C
            pass


async def monitor_stdin():
    """监控标准输入，消费回车键"""
    while True:
        await ainput()  # 异步等待输入，消费回车


async def main():
    check_ffmpeg_installed()
    config = await load_config()

    # auth_key优先级：配置文件server.auth_key > manager-api.secret > 自动生成
    # auth_key用于jwt认证，比如视觉分析接口的jwt认证、ota接口的token生成与websocket认证
    # 获取配置文件中的auth_key
    auth_key = config["server"].get("auth_key", "")
    
    # 验证auth_key，无效则尝试使用manager-api.secret
    if not auth_key or len(auth_key) == 0 or "你" in auth_key:
        auth_key = config.get("manager-api", {}).get("secret", "")
        # 验证secret，无效则生成随机密钥
        if not auth_key or len(auth_key) == 0 or "你" in auth_key:
            auth_key = str(uuid.uuid4().hex)
    
    config["server"]["auth_key"] = auth_key

    # 添加 stdin 监控任务
    stdin_task = asyncio.create_task(monitor_stdin())

    # 启动全局GC管理器（5分钟清理一次）
    gc_manager = get_gc_manager(interval_seconds=300)
    await gc_manager.start()

    # 启动 WebSocket 服务器
    ws_server = WebSocketServer(config)
    ws_task = asyncio.create_task(ws_server.start())
    # 启动 Simple http 服务器
    ota_server = SimpleHttpServer(config)
    # 绑定唤醒词服务（必须在使用路由前完成）
    ota_server.set_wake_word_service(ws_server.wake_word_service)
    # 初始化推送调度器并绑定 wake_word_service，启动后台处理器
    from core.services.push_scheduler import PushScheduler
    push_scheduler = PushScheduler()
    push_scheduler.set_wake_word_service(ws_server.wake_word_service)
    await push_scheduler.start()
    ota_server.set_push_scheduler(push_scheduler)
    # 壁纸即时下发服务：复用设备 WS 连接注册表按 device_id 直投
    from core.services.wallpaper_service import WallpaperService
    wallpaper_service = WallpaperService()
    wallpaper_service.bind_connections_provider(ws_server.wake_word_service.get_connections)
    # 待补投队列落 Redis（重启不丢），配置不可用时自动降级为内存队列
    wallpaper_service.bind_config(config)
    # 壁纸离线补投：设备文本通道建立（hello）时自动补投排队指令
    ws_server.wake_word_service.set_wallpaper_service(wallpaper_service)
    ota_server.set_wallpaper_service(wallpaper_service)
    # 注入 TopicGenerator（话题源随机聊天功能）
    from core.services.topic_generator import TopicGenerator
    topic_generator = TopicGenerator(config, ws_server, wake_word_service=ws_server.wake_word_service)
    # wake_word_service already passed to constructor
    push_scheduler.set_topic_generator(topic_generator)
    # 心跳服务注入唤醒词服务：在线设备列表 = WS连接 ∪ 心跳在线
    # （固件2.5.x心跳常驻、WS按需建立，单看WS会漏掉心跳在线的设备）

    # 初始化微信ClawBot服务
    from core.services.wechat_claw_service import WeChatClawService
    claw_service = WeChatClawService(config)
    await claw_service.start()
    ota_server.set_wechat_claw_service(claw_service)
    ota_task = asyncio.create_task(ota_server.start())

    # 启动心跳监听服务（12399，TCP/UDP；失败不影响主服务）
    heartbeat_server = HeartbeatServer(config)
    heartbeat_task = asyncio.create_task(heartbeat_server.start())
    ws_server.wake_word_service.set_heartbeat_server(heartbeat_server)

    # 壁纸：无 WS 时经心跳 TCP 通道兜底下发；固件经该通道回的 result 落 Redis 回执
    # sink 第三参 kind 为槽位（idle/boot），按槽位分键落 Redis（互不覆盖）
    wallpaper_service.bind_wake_word_service(ws_server.wake_word_service)
    try:
        from core.utils.wallpaper_ack import save_ack as _save_wallpaper_ack

        heartbeat_server.wallpaper_ack_sink = (
            lambda device_id, payload, kind="idle": _save_wallpaper_ack(
                config, device_id, payload, kind
            )
        )
    except Exception as e:  # 回执落库不可用不影响下发
        logger.bind(tag=TAG).warning(f"壁纸回执 sink 注入失败: {e}")

    # 壁纸补投的两个自动触发点：设备心跳上线即时补投 + 后台巡检兜底
    heartbeat_server.on_device_online = wallpaper_service.on_device_online
    try:
        await wallpaper_service.start_sweeper()
    except Exception as e:
        logger.bind(tag=TAG).warning(f"壁纸补投巡检启动失败（不影响下发）: {e}")

    read_config_from_api = config.get("read_config_from_api", False)
    port = int(config["server"].get("http_port", 8003))
    if not read_config_from_api:
        logger.bind(tag=TAG).info(
            "OTA接口是\t\thttp://{}:{}/yuhe/ota/",
            get_local_ip(),
            port,
        )
    logger.bind(tag=TAG).info(
        "视觉分析接口是\thttp://{}:{}/mcp/vision/explain",
        get_local_ip(),
        port,
    )
    mcp_endpoint = config.get("mcp_endpoint", None)
    if mcp_endpoint is not None and "你" not in mcp_endpoint:
        # 校验MCP接入点格式
        if validate_mcp_endpoint(mcp_endpoint):
            logger.bind(tag=TAG).info("mcp接入点是\t{}", mcp_endpoint)
            # 将mcp计入点地址转成调用点
            mcp_endpoint = mcp_endpoint.replace("/mcp/", "/call/")
            config["mcp_endpoint"] = mcp_endpoint
        else:
            logger.bind(tag=TAG).error("mcp接入点不符合规范")
            config["mcp_endpoint"] = "你的接入点 websocket地址"

    # 获取WebSocket配置，使用安全的默认值
    websocket_port = 8000
    server_config = config.get("server", {})
    if isinstance(server_config, dict):
        websocket_port = int(server_config.get("port", 8000))

    logger.bind(tag=TAG).info(
        "Websocket地址是\tws://{}:{}/yuhe/v1/",
        get_local_ip(),
        websocket_port,
    )

    logger.bind(tag=TAG).info(
        "=======上面的地址是websocket协议地址，请勿用浏览器访问======="
    )
    logger.bind(tag=TAG).info(
        "如想测试websocket请启动digital-human模块，打开浏览器交互测试"
    )
    logger.bind(tag=TAG).info(
        "=============================================================\n"
    )

    try:
        await wait_for_exit()  # 阻塞直到收到退出信号
    except asyncio.CancelledError:
        print("任务被取消，清理资源中...")
    finally:
        # 停止全局GC管理器
        await gc_manager.stop()

        # 停止推送调度器
        if push_scheduler:
            await push_scheduler.stop()

        # 停止微信ClawBot服务
        if claw_service:
            await claw_service.stop()

        # 取消所有任务（关键修复点）
        stdin_task.cancel()
        ws_task.cancel()
        if ota_task:
            ota_task.cancel()
        if heartbeat_task:
            heartbeat_task.cancel()

        # 等待任务终止（必须加超时）
        wait_tasks = [stdin_task, ws_task]
        if ota_task:
            wait_tasks.append(ota_task)
        if heartbeat_task:
            wait_tasks.append(heartbeat_task)
        await asyncio.wait(
            wait_tasks,
            timeout=3.0,
            return_when=asyncio.ALL_COMPLETED,
        )
        print("服务器已关闭，程序退出。")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("手动中断，程序终止。")
