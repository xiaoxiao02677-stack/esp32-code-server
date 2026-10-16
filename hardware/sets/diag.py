#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hardware/sets/diag.py — 设备侧回读诊断（只读，绝不写 flash）。

烧录后设备异常（例如无限重启）时，用它回答一个关键问题：
**芯片里存的，和本地编出来的，是不是一回事？**

据此把原因分成三类：
  1) 烧录没写全 / 写坏了   -> 回读内容与本地逐字节不一致（会指出首个不同的偏移）
  2) flash 容量与固件不符   -> flash-id 报的容量 < 固件配置的 16MB
                              （assets 在 0x800000，8MB 的板子上根本写不进去）
  3) 固件 / 硬件本身的问题  -> 回读完全一致，但设备依旧不启动
                              （这时该去打开 bootloader 日志看它到底卡在哪）

本脚本只读：不写、不擦、不改 eFuse。跑完会把设备复位回正常运行状态。

用法：
    python hardware/sets/diag.py                     # 自动探测串口 + 复位线序
    python hardware/sets/diag.py --port COM18        # 指定串口
    python hardware/sets/diag.py --board yh-154tft-wifi --full-app   # 连 app 全量比对
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

HERE = Path(__file__).resolve().parent
READ_BAUD = 460800
REEXEC_FLAG = "SETS_DIAG_REEXEC"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# 回读区间：一次把 bootloader + 分区表 + otadata + phy_init 都读回来
BOOT_BASE = 0x00000
BOOT_SIZE = 0x10000

# app 镜像头（先只看头部，`--full-app` 时读全量）
APP_BASE = 0x20000
APP_HEAD_SIZE = 0x2000


def _load_module(name: str, path: Path) -> Any:
    """按路径加载模块（同目录脚本互相复用，不依赖包结构）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - 环境相关
        raise RuntimeError(f"无法加载模块：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


flash = _load_module("sets_flash", HERE / "flash.py")


# ---------------------------------------------------------------------------
# esptool 调用（只读）
# ---------------------------------------------------------------------------


def _strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def esptool(python: str, port: str, extra: list[str]) -> tuple[int, str]:
    """在下载模式下调用 esptool（--before/--after 都不复位，芯片由我们负责）。"""
    command = [
        python, "-m", "esptool",
        "--chip", flash.CHIP,
        "-p", port,
        "-b", str(READ_BAUD),
        "--before", "no-reset",
        "--after", "no-reset",
        *extra,
    ]
    try:
        completed = subprocess.run(
            command, check=False, capture_output=True,
            env=flash.sets_build._idf_env_vars(),
        )
    except OSError as error:  # pragma: no cover - 环境相关
        return 1, f"无法启动 esptool: {error}"
    raw = (completed.stdout or b"") + (completed.stderr or b"")
    return completed.returncode, _strip_ansi(raw.decode("utf-8", errors="replace"))


def parse_flash_id(text: str) -> tuple[str, str]:
    """从 flash-id 输出里抠出 (型号, 容量)，抠不到就返回空串。"""
    chip_id = ""
    size = ""
    for line in text.splitlines():
        line = line.strip()
        low = line.lower()
        if "flash id" in low or "manufacturer" in low or "device id" in low:
            value = line.split(":", 1)[-1].strip()
            if value and not chip_id:
                chip_id = value
        if "flash size" in low or "detected flash size" in low:
            value = line.split(":", 1)[-1].strip()
            if value and not size:
                size = value
    # 新版 esptool 用表格输出，再兜一次正则
    if not size:
        match = re.search(r"(\d+)\s*MB", text)
        if match:
            size = f"{match.group(1)}MB"
    return chip_id, size


# ---------------------------------------------------------------------------
# 比对
# ---------------------------------------------------------------------------


def diff_detail(device: bytes, local: bytes) -> tuple[str, str]:
    """比对一段回读数据与本地文件，返回 (状态, 人话说明)。"""
    if device == local:
        return "ok", f"一致（{len(local)} 字节）"
    if len(device) < len(local):
        return "short", f"回读长度不足（设备 {len(device)} < 本地 {len(local)} 字节）"
    if device and all(byte == 0xFF for byte in device):
        return "blank", f"设备上是空白（全 0xFF，{len(local)} 字节）—— 这块区域根本没写进去"

    first = -1
    different = 0
    for index, (got, want) in enumerate(zip(device, local)):
        if got != want:
            different += 1
            if first < 0:
                first = index
    if first < 0:  # pragma: no cover - 已被上面的相等判断拦住
        return "ok", "一致"
    return "diff", (
        f"不一致：{different}/{len(local)} 字节不同，"
        f"首个不同在 +0x{first:x}（设备=0x{device[first]:02x} 本地=0x{local[first]:02x}）"
    )


def read_region(call: Any, base: int, size: int, label: str) -> Optional[bytes]:
    """回读一段 flash；失败返回 None。call = 每次调用前重新进下载模式的包装。"""
    handle, path = tempfile.mkstemp(prefix="sets_diag_", suffix=".bin")
    os.close(handle)
    try:
        code, output = call(["read-flash", hex(base), hex(size), path])
        if code != 0:
            flash.notice_bad(f"回读 {label} 失败（esptool 返回码 {code}）")
            tail = [line for line in output.splitlines() if line.strip()][-4:]
            for line in tail:
                flash.say("        " + line)
            return None
        data = Path(path).read_bytes()
        if len(data) != size:
            flash.notice_warn(f"回读 {label} 长度异常：{len(data)} != {size}")
        return data
    except OSError as error:  # pragma: no cover - 环境相关
        flash.notice_bad(f"回读 {label} 出错：{error}")
        return None
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# 解释器自愈（pyserial / esptool 只在 IDF venv 里）
# ---------------------------------------------------------------------------


def reexec_if_needed(argv: list[str]) -> Optional[int]:
    """当前解释器缺 pyserial 时，改用 IDF venv 的 python 重跑本脚本。"""
    if flash._HAVE_PYSERIAL:
        return None
    if os.environ.get(REEXEC_FLAG) == "1":
        flash.notice_warn("当前解释器没有 pyserial，且已重跑过一次：无法枚举串口")
        return None
    python = flash.sets_build._idf_python()
    try:
        same = Path(python).resolve() == Path(sys.executable).resolve()
    except OSError:  # pragma: no cover - 环境相关
        same = False
    if same:
        flash.notice_warn(f"IDF venv 的 python 也缺 pyserial（{python}）")
        return None
    print(f"[提示] 当前解释器（{sys.executable}）没有 pyserial，改用 IDF venv 重跑：{python}",
          file=sys.stderr, flush=True)
    env = dict(os.environ)
    env[REEXEC_FLAG] = "1"
    try:
        return subprocess.call(
            [python, str(Path(__file__).resolve()), *argv], env=env
        )
    except OSError as error:  # pragma: no cover - 环境相关
        flash.notice_warn(f"切换解释器失败（{error}）")
        return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: Optional[list[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="hardware/sets/diag.py",
        description="设备侧回读诊断：读回 flash 关键区域，与 <FW>/build 产物逐字节比对（只读）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python hardware/sets/diag.py                    # 自动探测串口\n"
            "  python hardware/sets/diag.py --port COM18\n"
            "  python hardware/sets/diag.py --board yh-154tft-wifi --full-app\n"
            "\n"
            "本脚本只读设备，不写不擦。\n"
        ),
    )
    parser.add_argument("--port", metavar="COMx", help="指定串口（默认多线程探测）")
    parser.add_argument("--board", metavar="ID", help="指定版型，用于校验产物与回读内容")
    parser.add_argument("--full-app", action="store_true",
                        help="连整个 app 镜像一起比对（2~3MB，慢十几秒）")
    parser.add_argument("--timeout", type=float, default=flash.PROBE_TIMEOUT_DEFAULT, metavar="SEC",
                        help=f"单口探测超时，默认 {flash.PROBE_TIMEOUT_DEFAULT}")
    parser.add_argument("--jobs", type=int, default=flash.PROBE_JOBS_DEFAULT, metavar="N",
                        help=f"探测线程数，默认 {flash.PROBE_JOBS_DEFAULT}")
    parser.add_argument("--fw-root", metavar="DIR", help="固件源码根目录（默认 sets 自带副本）")
    parser.add_argument("--python", metavar="EXE", help="指定 IDF venv 的 python")
    parser.add_argument("--no-color", action="store_true", help="关闭彩色输出")
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error("--jobs 至少为 1")
    return args


# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(argv)

    flash.sets_build._init_stdio()
    flash.sets_build._USE_COLOR = (
        not args.no_color and bool(getattr(sys.stdout, "isatty", lambda: False)())
    )
    if flash.sets_build._USE_COLOR:
        flash.sets_build._enable_windows_ansi()

    if args.python:
        flash.sets_build._PYTHON_OVERRIDE = args.python
        flash.sets_build._IDF_ENV_CACHE = None

    rerun = reexec_if_needed(argv)
    if rerun is not None:
        return rerun

    flash.say(flash.rule("="))
    flash.say(flash.bold("小智固件设备诊断 (hardware/sets/diag.py) —— 只读回读比对"))
    flash.say(flash.rule("="))

    fw_root = flash.sets_build.resolve_fw_root(args.fw_root)
    if fw_root is None:
        flash.notice_bad("自动探测不到固件源码根目录（<FW>），请用 --fw-root 指定")
        return flash.EXIT_ENV
    build_dir = fw_root / "build"
    flash.say(f"  固件根目录: {fw_root}")

    reason = flash.check_build_ready(fw_root)
    if reason:
        flash.notice_bad(f"本地没有可比对的产物：{reason}")
        flash.say("        先跑 build.py 编译，再来诊断。")
        return flash.EXIT_ERROR

    python = flash.sets_build._idf_python()
    if not flash._esptool_ok(python):
        flash.notice_bad(f"所用解释器里没有 esptool：{python}")
        flash.say("        请用 --python 指定 IDF venv 的 python。")
        return flash.EXIT_ENV
    flash.say(f"  解释器    : {python}")

    # ---- 1. 探测串口 ----
    flash.say()
    flash.say(flash.bold("[1/3] 探测串口"))
    ports = flash.enumerate_ports()
    if not ports and not args.port:
        flash.notice_bad("没有枚举到任何串口：请确认板子已插好、驱动正常")
        return flash.EXIT_ERROR
    probes = (
        flash.probe_all(ports, timeout=args.timeout, jobs=args.jobs,
                        identify=False, stream=True, include_bluetooth=False)
        if ports else []
    )
    port = flash.select_port(probes, args.port)
    if port is None:
        flash.notice_bad("没有选中串口，已退出")
        return flash.EXIT_ERROR

    # ---- 2. 进下载模式 ----
    flash.say()
    flash.say(flash.bold("[2/3] 把芯片送进下载模式"))
    order, evidence = flash.detect_reset_order(port)
    if order == "unknown":
        flash.notice_bad("识别不出本板复位线序（两种时序都没能让芯片重启）")
        if evidence:
            flash.say(f"        复位后串口输出：{evidence!r}")
        flash.say("        可先手动进下载模式：按住 BOOT → 点一下 RST → 松开 BOOT，")
        flash.say("        再跑本脚本（它会直接连，不需要再复位）。")
        return flash.EXIT_ERROR
    label = flash.RESET_ORDER_LABEL.get(order, order)
    flash.say(f"  复位线序: {label}")
    ok, detail = flash.enter_download_mode(port, order)
    if ok:
        flash.say(flash.green("  已进入下载模式") + (f"    {detail}" if detail else ""))
    else:
        flash.notice_warn(f"未确认进入下载模式：{detail or '复位后串口无输出'}")
        flash.say("        仍然继续尝试读取（有些适配器读不到回显）。")

    # ---- 3. 回读 + 比对 ----
    #
    # esptool 每次调用都是独立的一次「连接 -> 干活 -> 断开」。断开后芯片会离开
    # 下载模式（我们传了 --after no-reset，它也不会自己复位），所以**每一次**调用
    # 之前都得重新把芯片送进下载模式，否则第二次起就是
    # "Failed to connect: No serial data received"。
    def session_call(extra: list[str]) -> tuple[int, str]:
        flash.enter_download_mode(port, order)
        return esptool(python, port, extra)

    flash.say()
    flash.say(flash.bold("[3/3] 回读 flash 并与本地产物比对"))

    code, output = session_call(["flash-id"])
    if code == 0:
        chip_id, size = parse_flash_id(output)
        flash.say(f"  Flash ID : {chip_id or '（未解析出）'}")
        flash.say(f"  容量     : {size or '（未解析出）'}")
        if size and "16" not in size:
            flash.notice_warn(
                f"设备实际容量是 {size}，而固件按 16MB 配置编译（assets 分区在 0x800000）"
            )
            flash.say("        —— 容量不匹配时 assets 写不进去，且分区表越界会让 bootloader 起不来。")
    else:
        flash.notice_warn("读 flash-id 失败，跳过容量检查")

    local_app = (build_dir / "xiaozhi.bin").read_bytes()
    app_size = len(local_app) if args.full_app else APP_HEAD_SIZE
    boot_dump = read_region(session_call, BOOT_BASE, BOOT_SIZE, "bootloader/分区表区")
    app_dump = read_region(session_call, APP_BASE, app_size, "app 区")

    flash.say()
    rows: list[tuple[str, int, Path]] = [
        ("bootloader.bin", 0x0, build_dir / "bootloader" / "bootloader.bin"),
        ("partition-table.bin", 0x8000, build_dir / "partition_table" / "partition-table.bin"),
        ("ota_data_initial.bin", 0xD000, build_dir / "ota_data_initial.bin"),
    ]
    verdict: list[str] = []
    if boot_dump is not None:
        for name, offset, path in rows:
            if not path.is_file():
                continue
            local = path.read_bytes()
            start = offset - BOOT_BASE
            got = boot_dump[start:start + len(local)]
            state, detail = diff_detail(got, local)
            tag = {
                "ok": flash.green("[一致]"),
                "blank": flash.red("[空白]"),
                "diff": flash.red("[不一致]"),
                "short": flash.red("[长度不足]"),
            }.get(state, flash.yellow("[未知]"))
            flash.say(f"  {name:<22} 0x{offset:<7x} {tag}  {detail}")
            if state != "ok":
                verdict.append(f"{name}（0x{offset:x}）{detail}")
    else:
        verdict.append("bootloader/分区表区域回读失败，无法比对")

    if app_dump is not None:
        scope_len = min(len(app_dump), len(local_app))
        got = app_dump[:scope_len]
        state, detail = diff_detail(got, local_app[:scope_len])
        tag = {
            "ok": flash.green("[一致]"),
            "blank": flash.red("[空白]"),
            "diff": flash.red("[不一致]"),
            "short": flash.red("[长度不足]"),
        }.get(state, flash.yellow("[未知]"))
        scope = "全量" if args.full_app else f"头部 {APP_HEAD_SIZE // 1024}KB"
        flash.say(f"  {'xiaozhi.bin':<22} 0x{APP_BASE:<7x} {tag}  {detail}（{scope}）")
        if state != "ok":
            verdict.append(f"xiaozhi.bin（0x{APP_BASE:x}）{detail}")
    else:
        verdict.append("app 区域回读失败，无法比对")

    # ---- 收尾：把设备复位回运行状态 ----
    try:
        handle = flash._open_raw(port)
        try:
            flash._reset_and_sample(handle, "classic", 0.4)
        finally:
            flash._close_quietly(handle)
    except Exception:  # pragma: no cover - 驱动相关
        pass

    flash.say()
    flash.say(flash.rule())
    if not verdict:
        flash.notice_ok("flash 内容与本地编译产物完全一致")
        flash.say("        既然写进去的和编出来的一样，设备仍然不启动，就不是烧录/产物问题。")
        flash.say("        下一步该看 bootloader 到底卡在哪：把 bootloader 日志打开重编一次，")
        flash.say("        在 version/config.json 的 sdkconfig_append 里加：")
        flash.say("          CONFIG_BOOTLOADER_LOG_LEVEL_INFO=y")
        return flash.EXIT_OK

    flash.notice_bad("发现不一致，设备里的内容和本地产物不一样")
    for item in verdict:
        flash.say(f"        · {item}")
    flash.say("        结论：烧录没写全或写坏了。重新烧录一次：")
    flash.say(f"          python hardware/sets/flash.py --port {port}")
    return flash.EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
