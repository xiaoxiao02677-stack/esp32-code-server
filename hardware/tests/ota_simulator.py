#!/usr/bin/env python3
"""OTA 固件升级链路验收模拟器（固件侧报文同构）。

复刻固件两处行为：
  * main/boards/common/board.cc  Board::GetSystemInfoJson()  —— POST /ota/ 的请求体
  * main/ota.cc                  Ota::CheckVersion()          —— Device-Id / Client-Id 头

按「设备已绑定 + auto_update + board.type 匹配 + 版本号比较」四要素覆盖全部判定分支，
并可选把返回的升级包真正下载回来比对 md5。

用法：
    python ota_simulator.py --base http://sandyun.top:8002/xiaozhi/ota \
        --mac AA:BB:CC:DD:EE:02 --board yh-cam --app-version 2.5.0 \
        --expect-url --verify-download --local-file ../sets/out/yh-cam/yh-cam-xiaozhi.bin

退出码：0=通过，1=失败
"""

from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import sys
import urllib.request

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# Constant.INVALID_FIRMWARE_URL 中的哨兵片段
INVALID_MARK = "NOT_ACTIVATED_FIRMWARE"


def report_payload(mac: str, board: str, app_version: str) -> dict:
    """对齐固件 GetSystemInfoJson() 的关键字段子集"""
    return {
        "version": 2,
        "language": "zh-CN",
        "flash_size": 16777216,
        "minimum_free_heap_size": "214720",
        "mac_address": mac,
        "uuid": "e0a1b2c3-d4e5-f607-8899-aabbccddeeff",
        "chip_model_name": "esp32s3",
        "chip_info": {"model": 9, "cores": 2, "revision": 0, "features": 18},
        "application": {
            "name": "xiaozhi",
            "version": app_version,
            "compile_time": "Oct 16 2026T19:33:25Z",
            "idf_version": "v6.1-dirty",
            "elf_sha256": "0" * 64,
        },
        "partition_table": [
            {"label": "app", "type": 0, "subtype": 0, "address": 65536, "size": 4194304}
        ],
        "ota": {"label": "ota_0"},
        "display": {"monochrome": False, "width": 240, "height": 240},
        "board": {"type": board, "name": board},
    }


def post_ota(base: str, mac: str, payload: dict):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(base.rstrip("/") + "/", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Device-Id", mac)
    req.add_header("Client-Id", "ota-simulator")
    with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
        return r.status, json.loads(r.read().decode())


def fetch(url: str):
    with urllib.request.urlopen(urllib.request.Request(url), timeout=120, context=CTX) as r:
        return r.status, r.read()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://sandyun.top:8002/xiaozhi/ota")
    ap.add_argument("--mac", required=True)
    ap.add_argument("--board", required=True, help="固件上报的 board.type")
    ap.add_argument("--app-version", required=True, help="设备当前固件版本，如 2.5.0")
    ap.add_argument("--expect-url", action="store_true", help="期望返回可下载的升级 URL")
    ap.add_argument("--verify-download", action="store_true")
    ap.add_argument("--local-file", help="本地固件文件，用于 md5 比对")
    args = ap.parse_args()

    payload = report_payload(args.mac, args.board, args.app_version)
    status, resp = post_ota(args.base, args.mac, payload)
    data = resp.get("data") if isinstance(resp.get("data"), dict) else resp
    fw = data.get("firmware") or {}
    print(f"POST /ota/  HTTP={status}  mac={args.mac} board={args.board} app_version={args.app_version}")
    print(f"  firmware.version = {fw.get('version')!r}")
    print(f"  firmware.url     = {fw.get('url')!r}")
    print(f"  websocket.url    = {(data.get('websocket') or {}).get('url')!r}")

    url = fw.get("url") or ""
    if args.expect_url:
        feasible = ("/otaMag/download/" in url) and (INVALID_MARK not in url)
        print(f"  >>> 期望可升级: {'PASS' if feasible else 'FAIL'}")
        if not feasible:
            return 1
        if args.verify_download:
            st, blob = fetch(url)
            digest = hashlib.md5(blob).hexdigest()
            print(f"  >>> 下载升级包: HTTP={st} bytes={len(blob)} md5={digest}")
            if args.local_file:
                local = open(args.local_file, "rb").read()
                lmd5 = hashlib.md5(local).hexdigest()
                same = lmd5 == digest
                print(
                    f"  >>> 与本地固件 {args.local_file} 比对: md5={lmd5} "
                    f"{'一致 PASS' if same else '不一致 FAIL'}"
                )
                if not same:
                    return 1
    else:
        ok = INVALID_MARK in url
        print(f"  >>> 期望不升级: {'PASS' if ok else 'FAIL'}")
        if not ok:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
