#!/usr/bin/env python3
"""把 build.py 产出的固件发布到「固件升级管理」（ai_ota），打通设备 OTA 升级链路。

流程（与管理端页面完全同一条后端链路）：
  1. 读取 <out>/<board>/<board>-xiaozhi.bin，解析 ESP32 app 描述符拿到真实 version
  2. POST {server}/otaMag/upload              -> uploadfile/<md5>.bin
  3. POST {server}/otaMag  (同一 type 幂等 upsert) -> ai_ota 记录
  4. 可选：用 OTA 模拟器复验「低版本设备能拿到升级 URL」

关键约束（否则会造成设备 OTA 死循环）：
  ai_ota.version 必须与该 bin 内嵌的 app version **完全一致**；
  服务端只在 ai_ota.version > 设备上报版本 时才下发升级 URL。

用法：
    python ota_publish.py --board yh-cam                       # 用 out/yh-cam 的最新产物
    python ota_publish.py --board yh-cam --bin path/to.bin
    python ota_publish.py --all                                # 发布 out/ 下全部版型
    python ota_publish.py --board yh-cam --verify --mac AA:BB:CC:DD:EE:02

鉴权：
    --token <管理端 token>            # 推荐：浏览器 /admincc 登录后从请求头取
    或 --user/--password + --captcha-cmd（默认经 SSH 读 Redis 中的图形验证码）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import ssl
import struct
import subprocess
import sys
import urllib.request
import uuid as uuidlib
from pathlib import Path

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

SETS_ROOT = Path(__file__).resolve().parent
OUT_ROOT = SETS_ROOT / "out"

DEFAULT_SERVER = "http://sandyun.top:8002/xiaozhi"
DEFAULT_CAPTCHA_CMD = 'ssh -p 22222 root@sandyun.top "redis-cli -n 0 get sys:captcha:{uuid}"'

# 版型 -> 展示名 / 备注（可按需修改；type 必须等于固件上报的 board.type）
BOARD_META = {
    "yh-154tft-wifi": ("屿禾-1.54寸TFT-WiFi版", "ESP32-S3 / ST7789 + 直驱 I2S"),
    "yh-big-ili9341": ("屿禾-大屏ILI9341版", "ESP32-S3 / ILI9341 + ES8311（引脚待验证）"),
    "yh-cam": ("屿禾-CAM版", "ESP32-S3 / OV2640 + ES8311 + ES7210 + PCA9557 / 已启用回采(AEC)"),
    "yh-n16r8-st7789": ("屿禾-N16R8-ST7789版", "ESP32-S3 / ST7789 + MAX98357 + INMP441"),
}


# ---------------------------------------------------------------- 工具
def http(method: str, url: str, *, body=None, headers=None, raw=None, ctype=None, timeout=180):
    data = raw
    h = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode()
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in h.items():
        req.add_header(k, v)
    if ctype:
        req.add_header("Content-Type", ctype)
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        payload = r.read()
        try:
            return r.status, json.loads(payload.decode())
        except Exception:  # noqa: BLE001
            return r.status, payload


def read_app_version(bin_path: Path) -> str:
    """解析 ESP32 app 描述符（esp_app_desc_t）中的 version 字段"""
    data = bin_path.read_bytes()
    off = data.find(struct.pack("<I", 0xABCD5432))
    if off < 0:
        raise RuntimeError(f"{bin_path} 不是有效的 ESP32 app 镜像（未找到 app 描述符魔数）")
    return data[off + 16: off + 16 + 32].split(b"\0")[0].decode()


def multipart(fields: dict, files: dict):
    boundary = "----wbotapublish" + uuidlib.uuid4().hex
    buf = b""
    for k, v in fields.items():
        buf += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    for k, (fname, content) in files.items():
        buf += (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; "
            f"filename=\"{fname}\"\r\nContent-Type: application/octet-stream\r\n\r\n"
        ).encode()
        buf += content + b"\r\n"
    buf += f"--{boundary}--\r\n".encode()
    return buf, f"multipart/form-data; boundary={boundary}"


def login(server: str, user: str, password: str, captcha_cmd: str) -> str:
    try:
        from gmssl import sm2  # type: ignore
    except ImportError:
        raise SystemExit("自动登录需要 gmssl：pip install gmssl（或直接用 --token）")

    _, pub = http("GET", f"{server}/user/pub-config")
    pk = (pub.get("data") or {}).get("sm2PublicKey")
    if not pk:
        raise SystemExit(f"取公钥失败: {pub}")

    cap_uuid = str(uuidlib.uuid4())
    http("GET", f"{server}/user/captcha?uuid={cap_uuid}", raw=b"")
    cmd = captcha_cmd.format(uuid=cap_uuid)
    out = subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout
    code = (out.strip().splitlines() or [""])[-1].strip().strip('"')
    if not code:
        raise SystemExit(f"未能从 Redis 读取验证码（命令: {cmd}）")
    print(f"# 图形验证码 = {code}")

    raw_pk = pk[2:] if pk.startswith("04") and len(pk) == 130 else pk
    crypt = sm2.CryptSM2(public_key=raw_pk, private_key="", mode=1)
    enc = "04" + crypt.encrypt((code + password).encode()).hex()
    _, res = http("POST", f"{server}/user/login",
                  body={"username": user, "password": enc, "captchaId": cap_uuid})
    token = (res.get("data") or {}).get("token")
    if not token:
        raise SystemExit(f"登录失败: {res}")
    print(f"# 登录成功: {user}")
    return token


# ---------------------------------------------------------------- 主流程
def publish_one(server: str, token: str, board: str, bin_path: Path,
                name: str | None, remark: str | None, dry_run: bool) -> int:
    if not bin_path.is_file():
        print(f"!! 固件不存在: {bin_path}")
        return 1
    version = read_app_version(bin_path)
    size = bin_path.stat().st_size
    md5 = hashlib.md5(bin_path.read_bytes()).hexdigest()
    d_name, d_remark = BOARD_META.get(board, (f"{board} 固件", ""))

    print(f"## {board}")
    print(f"   bin      = {bin_path}")
    print(f"   version  = {version}   (必须与 bin 内嵌版本一致，否则设备会无限升级)")
    print(f"   size     = {size}")
    print(f"   md5      = {md5}")
    if dry_run:
        return 0

    auth = {"Authorization": f"Bearer {token}"}
    content = bin_path.read_bytes()
    body, ctype = multipart({}, {"file": (bin_path.name, content)})
    st, res = http("POST", f"{server}/otaMag/upload", raw=body, ctype=ctype, headers=auth)
    firmware_path = (res.get("data") if isinstance(res, dict) else None)
    if res.get("code") != 0 or not firmware_path:
        print(f"!! 上传失败 HTTP={st}: {res}")
        return 1
    print(f"   上传成功  -> {firmware_path}")

    entity = {
        "firmwareName": name or d_name,
        "type": board,
        "version": version,
        "size": size,
        "firmwarePath": firmware_path,
        "remark": remark or d_remark,
    }
    st, res = http("POST", f"{server}/otaMag", body=entity, headers=auth)
    if res.get("code") != 0:
        print(f"!! 注册 ai_ota 失败 HTTP={st}: {res}")
        return 1
    print(f"   注册成功  -> ai_ota type={board} version={version}")
    return 0


def verify(server: str, board: str, version: str, mac: str, bin_path: Path) -> int:
    sys.path.insert(0, str(SETS_ROOT.parent / "tests"))
    from ota_simulator import report_payload, post_ota  # type: ignore

    # 造一个比当前版本低一位的"老设备"版本号
    parts = version.split(".")
    parts[-1] = str(max(0, int(parts[-1]) - 1))
    old = ".".join(parts)
    _, resp = post_ota(server + "/ota" if not server.endswith("/ota") else server,
                       mac, report_payload(mac, board, old))
    fw = (resp.get("data") if isinstance(resp.get("data"), dict) else resp).get("firmware") or {}
    url = fw.get("url") or ""
    ok = "/otaMag/download/" in url and "NOT_ACTIVATED" not in url
    print(f"   复验: 设备版本 {old} -> firmware.version={fw.get('version')!r} "
          f"url={'有' if ok else '无'}  {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", help="版型 id（如 yh-cam）")
    ap.add_argument("--all", action="store_true", help="发布 out/ 下全部版型")
    ap.add_argument("--bin", help="直接指定固件文件（默认取 out/<board>/<board>-xiaozhi.bin）")
    ap.add_argument("--out-root", default=str(OUT_ROOT))
    ap.add_argument("--server", default=os.environ.get("XIAOZHI_SERVER", DEFAULT_SERVER))
    ap.add_argument("--token", default=os.environ.get("XIAOZHI_TOKEN"))
    ap.add_argument("--user", default=os.environ.get("XIAOZHI_USER"))
    ap.add_argument("--password", default=os.environ.get("XIAOZHI_PASSWORD"))
    ap.add_argument("--captcha-cmd", default=DEFAULT_CAPTCHA_CMD)
    ap.add_argument("--name", help="固件展示名（默认按版型表）")
    ap.add_argument("--remark", help="备注（默认按版型表）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify", action="store_true", help="发布后模拟低版本设备复验")
    ap.add_argument("--mac", help="复验用的已登记设备 MAC")
    args = ap.parse_args()

    out_root = Path(args.out_root)
    if args.all:
        boards = sorted(
            p.name for p in out_root.iterdir()
            if p.is_dir() and (p / f"{p.name}-xiaozhi.bin").is_file()
        )
    elif args.board:
        boards = [args.board]
    else:
        ap.error("需要 --board 或 --all")

    if not boards:
        print(f"!! {out_root} 下没有可发布的产物（先跑 build.py 编译）")
        return 1

    token = args.token
    if not token and not args.dry_run:
        if not (args.user and args.password):
            print("!! 需要 --token，或 --user + --password（可自动过验证码登录）")
            return 1
        token = login(args.server, args.user, args.password, args.captcha_cmd)

    rc = 0
    for board in boards:
        bin_path = Path(args.bin) if args.bin else out_root / board / f"{board}-xiaozhi.bin"
        rc |= publish_one(args.server, token or "", board, bin_path,
                          args.name, args.remark, args.dry_run)
        if args.verify and not args.dry_run and args.mac:
            rc |= verify(args.server, board, read_app_version(bin_path), args.mac, bin_path)
    print("\n# 完成" if rc == 0 else "\n# 存在失败项")
    return rc


if __name__ == "__main__":
    sys.exit(main())
