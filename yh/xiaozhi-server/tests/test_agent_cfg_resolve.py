"""agent UUID -> MAC 反查修复验证：推送失败第二层根因。

生产失败路径：设备空闲（WS 断开、_connections 空），push_scheduler 经
_agent_devices 反查到 agent UUID 后传给 topic_generator；
_get_agent_cfg_from_api(UUID) 因 _agent_device_cache 未预热（鸡生蛋）、
_mac_from_plain 只认 12 位 hex 而 mac=None 直接 return None，
manager-api 根本没被调用 → TTS/记忆配置三级解析全空 → 推送判 failed。

修复：MAC 反查链补第三级 _mac_from_agent_devices（agent -> 设备集合，
unregister_connection 不清它，设备空闲期仍然可用）。
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

_ROOT = Path(__file__).resolve().parent.parent
_here = str(Path(__file__).resolve().parent)
sys.path = [p for p in sys.path if str(Path(p).resolve()) != _here]
sys.path.insert(0, str(_ROOT))

from core.services.topic_generator import TopicGenerator  # noqa: E402

AGENT_UUID = "97254a564446432cba4b21e8fbb6dd74"
DEVICE_MAC = "44:bd:8d:7b:3a:e4"

AGENT_CFG = {
    "agent_id": AGENT_UUID,
    "selected_module": {"TTS": "TTS_DoubaoV3", "Memory": "Memory_mem_hybrid"},
    "TTS": {"TTS_DoubaoV3": {"type": "doubao_v3", "voice": "zh_female"}},
    "Memory": {"Memory_mem_hybrid": {"type": "mem_hybrid"}},
}


def make_tg(agent_devices=None):
    """构造带 wake_word_service 桩的 TopicGenerator。

    agent_devices: dict[agent_uuid, set[mac]]，模拟设备 WS 断开后的
    残留映射（_connections 空、_agent_devices 保留）。
    """
    conn = type("C", (), {"client_ip": "1.2.3.4", "loop": None})()
    wws = type(
        "W",
        (),
        {"_connections": {}, "_agent_devices": agent_devices or {}},
    )()
    return TopicGenerator(config={}, conn=conn, wake_word_service=wws)


async def test_mac_from_agent_devices():
    """_agent_devices 有映射返回排序首个 MAC；无映射/无服务返回 None。"""
    tg = make_tg(agent_devices={AGENT_UUID: {"44:bd:8d:7b:3a:e4", "00:11:22:33:44:55"}})
    mac = tg._mac_from_agent_devices(AGENT_UUID)
    assert mac == "00:11:22:33:44:55", f"应返回排序首个 MAC，got {mac!r}"
    assert tg._mac_from_agent_devices("unknown-agent") is None
    tg_none = make_tg()
    tg_none._wake_word_service = None
    assert tg_none._mac_from_agent_devices(AGENT_UUID) is None
    print("  OK _mac_from_agent_devices 三分支")


async def test_agent_uuid_resolves_via_agent_devices():
    """核心修复路径：UUID 反查 MAC 后成功调 manager-api，三键缓存写入。"""
    tg = make_tg(agent_devices={AGENT_UUID: {DEVICE_MAC}})
    with patch(
        "config.manage_api_client.get_agent_models",
        AsyncMock(return_value=dict(AGENT_CFG)),
    ) as m:
        cfg = await tg._get_agent_cfg_from_api(AGENT_UUID)
    assert cfg is not None, "UUID 形态必须经 _agent_devices 反查到 MAC 并拿到配置"
    assert m.await_count == 1
    call_mac = m.await_args.args[0] if m.await_args.args else m.await_args.kwargs.get("mac_address")
    assert call_mac == DEVICE_MAC, f"manager-api 应收到 MAC，got {call_mac!r}"
    # 三键缓存：UUID / 原查询键（同 UUID）/ MAC
    assert tg._agent_cfg_cache.get(AGENT_UUID) is not None
    assert tg._agent_cfg_cache.get(DEVICE_MAC) is not None
    assert tg._agent_device_cache.get(AGENT_UUID) == DEVICE_MAC
    # 二次调用命中缓存不再发请求
    with patch(
        "config.manage_api_client.get_agent_models", AsyncMock()
    ) as m2:
        cfg2 = await tg._get_agent_cfg_from_api(AGENT_UUID)
    assert cfg2 is not None and m2.await_count == 0
    print("  OK UUID→_agent_devices→MAC→manager-api→三键缓存")


async def test_resolve_tts_config_idle_device():
    """端到端：设备空闲（无在线连接）时 UUID 也能解析出 TTS 配置。"""
    tg = make_tg(agent_devices={AGENT_UUID: {DEVICE_MAC}})
    with patch(
        "config.manage_api_client.get_agent_models",
        AsyncMock(return_value=dict(AGENT_CFG)),
    ):
        tts_cfg = await tg._resolve_tts_config(AGENT_UUID)
    assert tts_cfg is not None, "TTS 配置解析不应为空（修复前此处返回 None）"
    assert tts_cfg["selected_module"]["TTS"] == "TTS_DoubaoV3"
    assert "TTS_DoubaoV3" in tts_cfg["TTS"]
    print(f"  OK 空闲设备 TTS 解析: {tts_cfg['selected_module']['TTS']}")


async def test_resolve_memory_config_idle_device():
    """端到端：设备空闲时 UUID 也能解析出 Memory 配置（第一层修复的补全）。"""
    tg = make_tg(agent_devices={AGENT_UUID: {DEVICE_MAC}})
    with patch(
        "config.manage_api_client.get_agent_models",
        AsyncMock(return_value=dict(AGENT_CFG)),
    ):
        mt, sec = await tg._resolve_memory_config(AGENT_UUID)
    assert mt == "Memory_mem_hybrid", f"应解析出 mem_hybrid，got {mt!r}"
    assert "Memory_mem_hybrid" in sec
    print(f"  OK 空闲设备 Memory 解析: {mt}")


async def test_uuid_without_any_mapping_returns_none():
    """无任何映射时不发请求，保持原 return None 语义（不误报）。"""
    tg = make_tg(agent_devices={})
    with patch(
        "config.manage_api_client.get_agent_models", AsyncMock()
    ) as m:
        cfg = await tg._get_agent_cfg_from_api("ffffffffffffffffffffffffffffffff")
    assert cfg is None and m.await_count == 0
    print("  OK 无映射不发请求")


async def main():
    for name, fn in [
        ("_mac_from_agent_devices 三分支", test_mac_from_agent_devices),
        ("UUID 经 _agent_devices 反查成功", test_agent_uuid_resolves_via_agent_devices),
        ("空闲设备 TTS 配置解析", test_resolve_tts_config_idle_device),
        ("空闲设备 Memory 配置解析", test_resolve_memory_config_idle_device),
        ("无映射不发请求", test_uuid_without_any_mapping_returns_none),
    ]:
        print(f"== {name}")
        await fn()
    print("\nALL TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
