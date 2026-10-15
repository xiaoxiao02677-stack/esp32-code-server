#!/usr/bin/env python3
"""在服务器上隔离实测补丁的 _ensure_device_playable_audio（不碰生产文件）。"""
import asyncio
import importlib.util
import os
import shutil
import sys

# 载入本地 fixed 文件（未部署）
spec = importlib.util.spec_from_file_location(
    "tg_fixed", "/tmp/deploy-test/topic_generator.py.fixed")
tg = importlib.util.module_from_spec(spec)
sys.modules["tg_fixed"] = tg
spec.loader.exec_module(tg)


async def main():
    gen = tg.TopicGenerator.__new__(tg.TopicGenerator)  # 只用方法，不走 __init__
    # 取一个真实损坏样本（生产 tmp 只读复制到 /tmp/deploy-test）
    src = "/root/xiaozhi-server/main/xiaozhi-server/tmp/topic-1792051947263-32ff63483c0e.mp3"
    work = "/tmp/deploy-test/work.mp3"
    shutil.copyfile(src, work)
    print("== 场景1：真实损坏样本（尾部0xAA垃圾）==")
    out = await gen._ensure_device_playable_audio(work)
    print("产物:", out, "size:", os.path.getsize(out))
    d = open(out, "rb").read()
    print("OggS:", d.count(b"OggS"), "OpusHead:", d[:64].count(b"OpusHead"))

    print("\n== 场景2：已是合法 ogg（应原样返回）==")
    out2 = await gen._ensure_device_playable_audio(out)
    print("产物:", out2, "未变:", out2 == out)

    print("\n== 场景3：坏文件（512B 垃圾）应抛错 ==")
    bad = "/tmp/deploy-test/garbage.mp3"
    open(bad, "wb").write(b"\xaa" * 512)
    try:
        await gen._ensure_device_playable_audio(bad)
        print("!! 未抛错（异常）")
    except RuntimeError as e:
        print("正确抛错:", str(e)[:80])

    print("\n== 场景4：空文件应抛错 ==")
    empty = "/tmp/deploy-test/empty.mp3"
    open(empty, "wb").close()
    try:
        await gen._ensure_device_playable_audio(empty)
        print("!! 未抛错（异常）")
    except RuntimeError as e:
        print("正确抛错:", str(e)[:80])


asyncio.run(main())
