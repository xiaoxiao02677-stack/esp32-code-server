"""契约测试：device_config 上报拦截钩子 on_tool_call 的 gate 行为

覆盖 Kawaii 控制台 B 线安全契约（design-kawaii-console-v1 §1.2 链路②）：
- P0 gate：need_bind / read_config_from_api（regression）
- 裁决 b（2026-10）：conn_from_mqtt_gateway=True 时上报跳过，与下发侧对齐
"""
from unittest.mock import patch

from core.providers.tools import device_config_sync
from core.providers.tools.device_config_sync import (
    DEVICE_CONFIG_TOOL_RULES,
    on_tool_call,
)

_VALID_TOOL = "self_audio_speaker_set_volume"


class FakeConn:
    """最小连接替身：只暴露 on_tool_call 用到的属性"""

    def __init__(
        self,
        need_bind=False,
        read_config_from_api=True,
        conn_from_mqtt_gateway=False,
        device_id="AA:BB:CC:DD:EE:FF",
    ):
        self.need_bind = need_bind
        self.read_config_from_api = read_config_from_api
        self.conn_from_mqtt_gateway = conn_from_mqtt_gateway
        self.headers = {"device-id": device_id} if device_id else {}


def _run_on_tool_call(conn, tool, args):
    """执行 on_tool_call 并捕获被调度的上报协程（不真正执行网络上报）"""
    scheduled = []

    def _fake_create_task(coro, *a, **k):
        scheduled.append(coro)
        coro.close()  # 避免 "coroutine never awaited" 警告
        return None

    with patch("asyncio.create_task", side_effect=_fake_create_task):
        on_tool_call(conn, tool, args)
    return scheduled


def test_gateway_connection_skips_report():
    """裁决 b：MQTT 网关透传连接即使已绑定 + API 模式也跳过上报"""
    conn = FakeConn(need_bind=False, read_config_from_api=True, conn_from_mqtt_gateway=True)
    scheduled = _run_on_tool_call(conn, _VALID_TOOL, {"volume": 50})
    assert scheduled == [], "网关连接下不应调度任何设备配置上报"


def test_bound_non_gateway_connection_schedules_report():
    """基线：普通已绑定 + API 模式连接命中白名单工具时正常调度上报"""
    conn = FakeConn(need_bind=False, read_config_from_api=True)
    scheduled = _run_on_tool_call(conn, _VALID_TOOL, {"volume": 50})
    assert len(scheduled) == 1


def test_need_bind_still_skips_report():
    """regression：未绑定设备不记账（P0 gate）"""
    conn = FakeConn(need_bind=True, read_config_from_api=True)
    scheduled = _run_on_tool_call(conn, _VALID_TOOL, {"volume": 50})
    assert scheduled == []


def test_non_api_mode_still_skips_report():
    """regression：非 API 配置模式（本地 config.yaml 部署）不上报"""
    conn = FakeConn(need_bind=False, read_config_from_api=False)
    scheduled = _run_on_tool_call(conn, _VALID_TOOL, {"volume": 50})
    assert scheduled == []


def test_invalid_argument_dropped_without_report():
    """regression：白名单命中但参数越界（volume=150 > max 100）丢弃不上报"""
    conn = FakeConn(need_bind=False, read_config_from_api=True)
    scheduled = _run_on_tool_call(conn, _VALID_TOOL, {"volume": 150})
    assert scheduled == []


def test_missing_device_id_skips_report():
    """regression：连接缺少 device-id（MAC）时不上报"""
    conn = FakeConn(device_id=None)
    scheduled = _run_on_tool_call(conn, _VALID_TOOL, {"volume": 50})
    assert scheduled == []


def test_non_whitelisted_tool_noop():
    """regression：非白名单工具零开销直通，不上报"""
    conn = FakeConn(need_bind=False, read_config_from_api=True)
    scheduled = _run_on_tool_call(conn, "some_other_tool", {"volume": 50})
    assert scheduled == []
    assert "some_other_tool" not in DEVICE_CONFIG_TOOL_RULES


def test_bool_value_not_reported_as_int():
    """regression：bool 是 int 子类，True/False 不得被当作 1/0 记账"""
    conn = FakeConn(need_bind=False, read_config_from_api=True)
    scheduled = _run_on_tool_call(conn, _VALID_TOOL, {"volume": True})
    assert scheduled == []
