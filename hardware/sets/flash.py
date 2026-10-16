#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hardware/sets 专用烧录脚本 —— 与构建职责彻底分离。

分工：
  build.py  = 选版型 / 同步文件 / 幂等注册 / 编译 / 归档产物（不含任何烧录逻辑）
  flash.py  = 探测串口 / 把 <FW>/build 产物烧录到设备（本文件）

核心：**多线程并行探测 COM 口**。
宿主机「枚举到串口」并不等于「口上有设备」，也不等于「能打开」（可能被串口
监视器、另一个烧录会话占用）。逐个 open + 限时读数据的串行做法，N 个口就要等
N × 超时；这里用 ThreadPoolExecutor 一个口一个线程并行做，整体耗时 ≈ 单口超时，
而且哪个口先探完就先打印哪个口的结果，不必等最慢的那个。

探测分两级：
  1) 快速探测（默认）：以 DTR/RTS 均不激活的方式打开串口（**不会复位目标板**），
     限时读一小段数据。能打开 = 设备在线且未被占用；读到数据 = 设备在输出。
  2) 深度识别（--identify）：复刻 esptool 的 hard-reset 时序复位目标板并读 ROM
     启动日志，匹配 "ESP-ROM:" 判定是不是 Espressif 芯片、具体是哪一款。
     注意：该模式会复位目标板（复位后仍以正常运行模式启动，不会停在下载模式）。

pyserial / esptool 都取自 ESP-IDF 的 venv。当前解释器没有 pyserial 时，本脚本会
自动改用 IDF venv 的 python 重新执行自己（可用 --python 指定，或 --no-reexec 关闭）。

用法（完整示例见 --help）：
  python hardware/sets/flash.py                  # 探测串口并烧录 <FW>/build 产物
  python hardware/sets/flash.py --list           # 只探测列出，不烧录
  python hardware/sets/flash.py --identify       # 探测 + 复位识别芯片型号
  python hardware/sets/flash.py --json           # 探测结果输出 JSON（脚本调用）
  python hardware/sets/flash.py --port COM5 -y   # 指定串口直接烧录
"""

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# 复用 build.py 的工具函数（输出降级 / 色彩 / IDF 环境探测 / 固件根定位）
#
# 这里刻意不重复实现：GBK 控制台降级、ESP-IDF venv 探测（约 200 行）如果各写
# 一份，迟早会走偏。build.py 只做「构建」，被当工具库加载不会触发任何构建行为。
# ---------------------------------------------------------------------------


def _load_build_module() -> Any:
    path = Path(__file__).resolve().parent / "build.py"
    spec = importlib.util.spec_from_file_location("sets_build", path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"无法加载 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["sets_build"] = module
    spec.loader.exec_module(module)
    return module


sets_build = _load_build_module()

say = sets_build.say
green = sets_build.green
red = sets_build.red
yellow = sets_build.yellow
bold = sets_build.bold
rule = sets_build.rule
notice_bad = sets_build.notice_bad
notice_warn = sets_build.notice_warn
notice_ok = sets_build.notice_ok

EXIT_OK = sets_build.EXIT_OK
EXIT_ERROR = sets_build.EXIT_ERROR
EXIT_ENV = sets_build.EXIT_ENV

# 自动切换到 IDF venv 解释器的标记（防止 exec 死循环）
_REEXEC_FLAG = "SETS_FLASH_REEXEC"
_REEXEC_DONE = os.environ.get(_REEXEC_FLAG) == "1"

try:  # pyserial 是探测串口的前提；缺失时会在 main() 里尝试换解释器
    import serial  # type: ignore  # noqa: F401
    from serial.tools import list_ports  # type: ignore  # noqa: F401

    _HAVE_PYSERIAL = True
except Exception:  # pragma: no cover - 环境相关
    _HAVE_PYSERIAL = False


# ---------------------------------------------------------------------------
# 烧录参数（与 <FW>/yh_flash.bat 保持一致）
# ---------------------------------------------------------------------------

CHIP = "esp32s3"
BAUD_DEFAULT = 460800
PROBE_BAUD = 115200
FLASH_MODE = "dio"
FLASH_SIZE = "16MB"
FLASH_FREQ = "80m"
PROBE_TIMEOUT_DEFAULT = 0.6
PROBE_JOBS_DEFAULT = 8

# 全量烧录地址表；assets 分区（0x800000）必须全量写入，OTA 之后只刷 app 分区
FLASH_FULL_IMAGE = [
    ("0x0", "build/bootloader/bootloader.bin"),
    ("0x8000", "build/partition_table/partition-table.bin"),
    ("0xd000", "build/ota_data_initial.bin"),
    ("0x20000", "build/xiaozhi.bin"),
    ("0x800000", "build/generated_assets.bin"),
]

# 优先认定「这是 USB 转串口」的描述关键字（排在选择菜单前面）
USB_SERIAL_HINTS = ("CP210", "CH340", "CH910", "USB Serial", "USB-SERIAL", "JTAG", "Silicon Labs")

# 蓝牙虚拟串口：宿主机一定会枚举出来、而且往往能「打开成功」，但后面根本没有
# 可烧录设备；其中一些驱动在 open() 时还会阻塞好几秒。默认直接跳过。
BLUETOOTH_HINTS = ("蓝牙", "bluetooth", "bthenum", "bthmodem")

# 判定 Espressif 芯片型号的 ROM 启动日志特征
ROM_PATTERNS = (
    (re.compile(rb"ESP-ROM:esp32s3", re.IGNORECASE), "esp32s3"),
    (re.compile(rb"ESP-ROM:esp32s2", re.IGNORECASE), "esp32s2"),
    (re.compile(rb"ESP-ROM:esp32c3", re.IGNORECASE), "esp32c3"),
    (re.compile(rb"ESP-ROM:esp32c6", re.IGNORECASE), "esp32c6"),
    (re.compile(rb"ESP-ROM:esp32c2", re.IGNORECASE), "esp32c2"),
    (re.compile(rb"ESP-ROM:esp32h2", re.IGNORECASE), "esp32h2"),
    (re.compile(rb"ESP-ROM:esp32", re.IGNORECASE), "esp32"),
)


# ---------------------------------------------------------------------------
# 1. 串口枚举
# ---------------------------------------------------------------------------


def _natural_key(device: str) -> tuple:
    """COM2 排在 COM10 前面（字符串排序会反过来）。"""
    match = re.fullmatch(r"([A-Za-z]+)(\d+)", device)
    if match:
        return (match.group(1).upper(), int(match.group(2)))
    return (device.upper(), 0)


def enumerate_ports() -> list[tuple[str, str, str]]:
    """枚举串口，返回 [(device, description, hwid), ...]。

    只做「枚举」，不代表口上有设备 —— 是否有设备由 probe_all() 并行确认。
    """
    if not _HAVE_PYSERIAL:
        return []
    ports: list[tuple[str, str, str]] = []
    try:
        for info in list_ports.comports():
            ports.append((info.device, (info.description or "").strip(), (info.hwid or "").strip()))
    except Exception as error:  # pragma: no cover - 环境相关
        notice_warn(f"枚举串口失败: {error}")
        return []
    ports.sort(key=lambda item: _natural_key(item[0]))
    return ports


# ---------------------------------------------------------------------------
# 2. 多线程并行探测
# ---------------------------------------------------------------------------


@dataclass
class PortProbe:
    """单个串口的探测结果。"""

    device: str
    description: str = ""
    hwid: str = ""
    state: str = "unknown"  # ok / occupied / error / unknown
    detail: str = ""
    bytes_seen: int = 0
    sample: str = ""
    chip: str = ""
    elapsed: float = 0.0

    @property
    def confirmed(self) -> bool:
        """能打开且未被占用 = 这个口后面确实挂着设备。"""
        return self.state == "ok"

    @property
    def is_bluetooth(self) -> bool:
        text = f"{self.description} {self.hwid}".lower()
        return any(hint.lower() in text for hint in BLUETOOTH_HINTS)

    @property
    def is_usb(self) -> bool:
        text = f"{self.description} {self.hwid}".upper()
        return "USB VID:PID" in text or any(hint.upper() in text for hint in USB_SERIAL_HINTS)

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["confirmed"] = self.confirmed
        data["is_usb"] = self.is_usb
        return data


def _pulse_reset(port: Any) -> None:
    """复刻 esptool 的 hard-reset 时序：RTS 拉低 EN 再放开，DTR(GPIO0) 全程保持高。

    这样目标板复位后仍以正常运行模式启动，不会停在下载模式。
    """
    port.dtr = False
    port.rts = True
    time.sleep(0.12)
    port.rts = False
    time.sleep(0.05)


def _read_window(port: Any, timeout: float, limit: int = 512) -> bytes:
    """在 timeout 内尽可能收集串口数据；已有可观数据就提前收手。"""
    deadline = time.monotonic() + timeout
    chunks = bytearray()
    while time.monotonic() < deadline and len(chunks) < limit:
        try:
            waiting = port.in_waiting
        except Exception:  # pragma: no cover - 驱动相关
            waiting = 0
        if waiting:
            try:
                chunks += port.read(min(waiting, limit - len(chunks)))
            except Exception:
                break
            if len(chunks) >= 64:
                break
        else:
            time.sleep(0.02)
    return bytes(chunks)


def _summarize(data: bytes, width: int = 72) -> str:
    """把原始字节压成一行可见文本，方便一眼看出设备在输出什么。"""
    if not data:
        return ""
    text = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in data[:width])
    text = re.sub(r"\.{3,}", "...", text).strip(". ")
    return text


def _match_chip(data: bytes) -> str:
    for pattern, name in ROM_PATTERNS:
        if pattern.search(data):
            return name
    return ""


def _probe_one(device: str, description: str, hwid: str, timeout: float, identify: bool) -> PortProbe:
    """在线程里执行：打开串口 →（可选复位）→ 限时读数据 → 关闭。"""
    probe = PortProbe(device=device, description=description, hwid=hwid)
    start = time.monotonic()
    if not _HAVE_PYSERIAL:
        probe.state = "unknown"
        probe.detail = "当前解释器没有 pyserial，无法确认设备是否在线"
        probe.elapsed = time.monotonic() - start
        return probe

    port = None
    try:
        port = serial.Serial()
        port.port = device
        port.baudrate = PROBE_BAUD
        port.timeout = 0.05
        port.write_timeout = 0.2
        # 关键：打开前就把 DTR/RTS 置为不激活。串口驱动打开端口时默认会拉高这两根
        # 线，经典自动复位电路上等于给目标板来一次复位 —— 单纯探测不该打扰设备。
        port.dtr = False
        port.rts = False
        port.open()
    except Exception as error:
        probe.elapsed = time.monotonic() - start
        text = str(error).strip()
        lowered = text.lower()
        denied = (
            isinstance(error, PermissionError)
            or "access is denied" in lowered
            or "permission" in lowered
            or "拒绝访问" in text
            or "被占用" in text
        )
        if denied:
            probe.state = "occupied"
            probe.detail = "被其它程序占用（串口监视器 / 另一个烧录会话？）"
        else:
            probe.state = "error"
            probe.detail = (text.splitlines()[0] if text else error.__class__.__name__)[:120]
        return probe

    try:
        if identify:
            _pulse_reset(port)
            try:
                port.reset_input_buffer()
            except Exception:
                pass
        data = _read_window(port, timeout + (0.8 if identify else 0.0))
        probe.bytes_seen = len(data)
        probe.sample = _summarize(data)
        probe.state = "ok"
        if identify:
            probe.chip = _match_chip(data)
            if not probe.chip:
                probe.detail = "已复位但未读到 ESP-ROM 启动日志（可能不是 Espressif 芯片，或控制台不在 115200）"
    except Exception as error:  # pragma: no cover - 驱动相关
        probe.state = "error"
        probe.detail = str(error)[:120]
    finally:
        try:
            if port is not None:
                port.close()
        except Exception:
            pass

    probe.elapsed = time.monotonic() - start
    return probe


def _format_probe(probe: PortProbe) -> str:
    tag = {
        "ok": green("[在线]"),
        "occupied": yellow("[被占用]"),
        "error": red("[打不开]"),
        "skipped": yellow("[跳过]"),
    }.get(probe.state, yellow("[未知]"))
    parts = [f"{probe.device:<7}", tag]
    if probe.description:
        parts.append(probe.description)
    if probe.chip:
        parts.append(green(f"芯片={probe.chip}"))
    if probe.bytes_seen:
        parts.append(f"数据={probe.bytes_seen}B")
    if probe.sample:
        parts.append(f"样本={probe.sample!r}")
    if probe.detail:
        parts.append(probe.detail)
    if probe.state == "ok" and not probe.bytes_seen and not probe.detail:
        parts.append("口可打开，未收到输出")
    if probe.state != "skipped":
        parts.append(f"{probe.elapsed * 1000:.0f}ms")
    return "  ".join(parts)


def probe_all(
    ports: list[tuple[str, str, str]],
    *,
    timeout: float,
    jobs: int,
    identify: bool,
    stream: bool = True,
    include_bluetooth: bool = False,
) -> list[PortProbe]:
    """并行探测全部串口；stream=True 时谁先探完先打印谁。

    蓝牙虚拟串口默认不探测（既不是可烧录目标，open() 还可能阻塞数秒）。
    """
    results: dict[str, PortProbe] = {}
    targets: list[tuple[str, str, str]] = []
    for device, description, hwid in ports:
        probe = PortProbe(device=device, description=description, hwid=hwid)
        if probe.is_bluetooth and not include_bluetooth:
            probe.state = "skipped"
            probe.detail = "蓝牙虚拟串口，默认跳过（--include-bluetooth 可强制探测）"
            results[device] = probe
        else:
            targets.append((device, description, hwid))

    if stream:
        say()
        window = timeout + (0.8 if identify else 0.0)
        thread_note = f" / {max(1, min(jobs, len(targets)))} 线程" if targets else "（无可探测目标）"
        say(bold(
            f"[探测] 枚举 {len(ports)} 个串口 → 并行探测 {len(targets)} 个{thread_note}"
            + ("，复位识别芯片" if identify else f"，单口超时 {window:.1f}s")
        ))
        for device, _, _ in ports:
            probe = results.get(device)
            if probe is not None and probe.state == "skipped":
                say("  " + _format_probe(probe))

    if targets:
        workers = max(1, min(jobs, len(targets)))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="probe") as pool:
            futures = {
                pool.submit(_probe_one, device, description, hwid, timeout, identify): device
                for device, description, hwid in targets
            }
            for future in as_completed(futures):
                device = futures[future]
                try:
                    probe = future.result()
                except Exception as error:  # pragma: no cover - 线程内异常兜底
                    probe = PortProbe(device=device, state="error", detail=str(error)[:120])
                results[device] = probe
                if stream:
                    say("  " + _format_probe(probe))

    return [results[device] for device, _, _ in ports if device in results]


def _selection_key(probe: PortProbe) -> tuple:
    """可用设备优先，非蓝牙次之，USB 转串口再次之，最后按端口号自然序。"""
    return (
        0 if probe.confirmed else 1,
        0 if probe.is_bluetooth else 1,
        0 if probe.is_usb else 1,
        _natural_key(probe.device),
    )


# ---------------------------------------------------------------------------
# 3. 选择串口
# ---------------------------------------------------------------------------


def select_port(probes: list[PortProbe], explicit: Optional[str]) -> Optional[str]:
    if explicit:
        known = {probe.device.upper(): probe for probe in probes}
        found = known.get(explicit.upper())
        if found is None:
            notice_warn(f"{explicit} 不在本次枚举结果里，仍按指定值尝试")
        elif not found.confirmed:
            notice_warn(f"{explicit} 的探测结果：{found.detail or found.state}")
        else:
            say(f"  使用指定串口：{explicit}    {found.description}"
                + (f"    芯片={found.chip}" if found.chip else ""))
        return explicit

    candidates = sorted((probe for probe in probes if probe.state != "skipped"), key=_selection_key)
    confirmed = [probe for probe in candidates if probe.confirmed]

    if not confirmed:
        notice_bad("没有检测到可用设备（串口枚举到 ≠ 口上有设备）")
        occupied = [probe for probe in candidates if probe.state == "occupied"]
        skipped = [probe for probe in probes if probe.state == "skipped"]
        if occupied:
            say("        以下串口已被其它程序占用，请先关闭串口监视器 / 另一个烧录会话：")
            for probe in occupied:
                say(f"          {probe.device}  {probe.description}")
        if skipped:
            say(f"        另有 {len(skipped)} 个蓝牙虚拟串口已跳过（它们不是可烧录目标）："
                + "、".join(probe.device for probe in skipped))
        if candidates and not occupied:
            say("        枚举到的串口都无法打开或不是可用设备；请检查 USB 线与串口驱动。")
        elif not candidates and not skipped:
            say("        一个串口都没有枚举到；请检查 USB 线（要能传数据，不是纯充电线）与驱动。")
        say("        也可以显式指定：--port COMx")
        return None

    if len(confirmed) == 1:
        probe = confirmed[0]
        say(f"  自动选择唯一可用设备：{probe.device}    {probe.description}"
            + (f"    芯片={probe.chip}" if probe.chip else ""))
        return probe.device

    if not sys.stdin.isatty():
        notice_bad(f"探测到 {len(confirmed)} 个可用设备，非交互式终端请用 --port 指定")
        for probe in confirmed:
            say(f"          {probe.device}  {probe.description}")
        return None

    say()
    say(bold(f"检测到 {len(confirmed)} 个可用设备，请选择要烧录的："))
    for index, probe in enumerate(confirmed, 1):
        mark = "  (USB 转串口)" if probe.is_usb else ""
        chip = f"  芯片={probe.chip}" if probe.chip else ""
        say(f"    [{index}] {probe.device}    {probe.description}{chip}{mark}")
    say("    [0] 取消烧录")
    try:
        raw = input("  请输入编号: ").strip()
    except EOFError:
        return None
    if not raw or raw == "0":
        return None
    if raw.isdigit() and 1 <= int(raw) <= len(confirmed):
        return confirmed[int(raw) - 1].device
    for probe in confirmed:
        if probe.device.upper() == raw.upper():
            return probe.device
    notice_bad(f"无效输入: {raw}")
    return None


# ---------------------------------------------------------------------------
# 4. 烧录
# ---------------------------------------------------------------------------


def check_build_ready(fw_root: Path) -> Optional[str]:
    """返回 None 表示产物齐备，否则返回不可烧录的原因。"""
    build_dir = fw_root / "build"
    if not build_dir.is_dir():
        return f"找不到编译目录: {build_dir}"
    if not (fw_root / "build" / "xiaozhi.bin").is_file():
        return f"缺少应用镜像: {build_dir / 'xiaozhi.bin'}"
    return None


def warn_board_mismatch(fw_root: Path, board: dict[str, Any]) -> None:
    """build/ 是全局共用目录，提醒产物其实属于别的版型。"""
    fragment = fw_root / "build" / "xiaozhi-build.sdkconfig.defaults"
    if not fragment.is_file():
        return
    try:
        text = fragment.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    previous = re.findall(r"^(CONFIG_BOARD_TYPE_[A-Za-z0-9_]+)=y$", text, re.MULTILINE)
    want = f"CONFIG_{board['kconfig_symbol']}"
    if not previous or want in previous:
        return
    notice_warn(f"build 产物属于 {previous[0]}，与 --board {board['id']}（{want}）不符")
    say("        继续烧录会把上一个版型的固件写进设备；如确认无误请加 --yes 或直接回车确认。")


def _esptool_ok(python: str) -> bool:
    try:
        completed = subprocess.run(
            [python, "-c", "import esptool"], capture_output=True, timeout=90, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def run_flash(fw_root: Path, port: str, baud: int) -> int:
    """按 build/flash_args 烧录；不含 assets 时退回显式全量烧录。"""
    build_dir = fw_root / "build"
    flash_args = build_dir / "flash_args"
    has_assets = False
    if flash_args.is_file():
        try:
            has_assets = "generated_assets" in flash_args.read_text(encoding="utf-8", errors="replace")
        except OSError:
            has_assets = False

    base = [
        sets_build._idf_python(), "-m", "esptool",
        "--chip", CHIP,
        "-p", port,
        "-b", str(baud),
        "--before", "default-reset",
        "--after", "hard-reset",
        "write-flash",
    ]

    if has_assets:
        command = base + [
            "@flash_args",
            "--flash-mode", FLASH_MODE,
            "--flash-size", FLASH_SIZE,
            "--flash-freq", FLASH_FREQ,
        ]
        cwd = build_dir
        mode_desc = "按 build/flash_args 烧录（已含 assets 分区）"
    else:
        command = base + [
            "--flash-mode", FLASH_MODE,
            "--flash-size", FLASH_SIZE,
            "--flash-freq", FLASH_FREQ,
        ]
        included = 0
        for offset, relative in FLASH_FULL_IMAGE:
            if not (fw_root / relative).is_file():
                notice_warn(f"缺少 {relative}，跳过该分区")
                continue
            command += [offset, relative]
            included += 1
        if included == 0:
            notice_bad("没有任何可烧录的镜像文件，请确认编译是否成功")
            return EXIT_ERROR
        cwd = fw_root
        mode_desc = "显式全量烧录（bootloader + 分区表 + ota_data + app + assets）"

    say()
    say(bold(f"[烧录] {mode_desc}"))
    say(f"  串口: {port}    波特率: {baud}")
    say(f"  工作目录: {cwd}")
    say("  " + " ".join(command))
    say("  烧录中，请勿拔线……")
    say(rule())
    try:
        completed = subprocess.run(
            command, cwd=str(cwd), check=False, env=sets_build._idf_env_vars()
        )
    except OSError as error:
        notice_bad(f"无法启动 esptool: {error}")
        say("        请用 --python 指定 IDF venv 的 python（esptool 随它一起安装）。")
        return EXIT_ERROR
    say(rule())
    if completed.returncode != 0:
        notice_bad(f"烧录失败（esptool 返回码 {completed.returncode}）")
        say("        常见原因：串口被占用（串口监视器 / 另一个烧录会话）、")
        say("                  设备未进入下载模式（按住 BOOT 再复位）、或 USB 线不支持数据传输。")
        return completed.returncode or EXIT_ERROR
    notice_ok(f"烧录完成，设备已复位（{port}）")
    say("  提示：可用 <FW>\\monitor.bat 或 <FW>\\yh_monitor.py 查看串口日志。")
    return EXIT_OK


# ---------------------------------------------------------------------------
# 5. 解释器自愈（pyserial 只在 IDF venv 里）
# ---------------------------------------------------------------------------


def reexec_with_idf_python(argv: list[str], allow_reexec: bool) -> Optional[int]:
    """当前解释器没有 pyserial 时，改用 IDF venv 的 python 重跑本脚本。

    返回子进程退出码表示「已重跑」（main 直接返回它）；返回 None 表示继续在本进程里跑。
    这里用 subprocess 而不是 os.execve：execve 会替换进程镜像，在 Git Bash 下配合
    重定向偶发段错误（实测过一次 exit 139），多一层进程换稳定性更划算。
    """
    if _HAVE_PYSERIAL:
        return None
    if _REEXEC_DONE or not allow_reexec:
        notice_warn("当前解释器没有 pyserial：只能枚举串口，无法确认「口上是否有设备」")
        say("        可用 --python <IDF venv>\\Scripts\\python.exe 指定解释器后重试。")
        return None
    python = sets_build._idf_python()
    try:
        same = Path(python).resolve() == Path(sys.executable).resolve()
    except OSError:  # pragma: no cover - 环境相关
        same = False
    if same:
        notice_warn(f"IDF venv 的 python 也缺 pyserial（{python}）")
        return None

    # 走 stderr，避免污染 --json 的 stdout
    print(f"[提示] 当前解释器（{sys.executable}）没有 pyserial，"
          f"改用 IDF venv 的 python 重新执行：{python}", file=sys.stderr, flush=True)
    env = dict(os.environ)
    env[_REEXEC_FLAG] = "1"
    command = [python, str(Path(__file__).resolve()), *argv]
    try:
        return subprocess.call(command, env=env)
    except OSError as error:  # pragma: no cover - 环境相关
        notice_warn(f"切换解释器失败（{error}），退化为只能枚举串口")
        return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: Optional[list[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="hardware/sets/flash.py",
        description="小智固件专用烧录脚本：多线程探测 COM 口 → 选择设备 → esptool 烧录 <FW>/build 产物",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python hardware/sets/flash.py                    # 探测串口并烧录（唯一设备时直接问一句）\n"
            "  python hardware/sets/flash.py --list             # 只探测列出串口状态，不烧录\n"
            "  python hardware/sets/flash.py --identify         # 探测 + 复位读 ROM 日志识别芯片型号\n"
            "  python hardware/sets/flash.py --json             # 探测结果输出 JSON（供脚本调用）\n"
            "  python hardware/sets/flash.py --port COM5 -y     # 指定串口，跳过确认直接烧录\n"
            "  python hardware/sets/flash.py --baud 921600      # 提高烧录波特率\n"
            "  python hardware/sets/flash.py --board yh-cam     # 指定版型（校验 build 产物是否对得上）\n"
            "\n"
            "不想先激活 ESP-IDF 环境时，直接用 IDF venv 的 python 跑本脚本：\n"
            "  D:\\INSTALL\\esp\\tools\\python\\v6.1\\venv\\Scripts\\python.exe hardware/sets/flash.py\n"
            "（缺 pyserial 时脚本也会自动切到 IDF venv，一般无需手动指定；可用 --python 覆盖）\n"
            "\n"
            "本脚本只烧录，不编译。产物不存在时请先执行 build.py。\n"
        ),
    )
    parser.add_argument("--port", metavar="COMx", help="指定串口（默认多线程探测后自动/交互选择）")
    parser.add_argument("--baud", type=int, default=BAUD_DEFAULT, metavar="N",
                        help=f"烧录波特率，默认 {BAUD_DEFAULT}")
    parser.add_argument("--list", action="store_true", help="只探测并列出串口状态，不烧录")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出探测结果（隐含 --list）")
    parser.add_argument("--identify", action="store_true",
                        help="深度识别：复位目标板并读 ROM 启动日志判定芯片型号（会复位设备）")
    parser.add_argument("--timeout", type=float, default=PROBE_TIMEOUT_DEFAULT, metavar="SEC",
                        help=f"单个串口的探测超时秒数，默认 {PROBE_TIMEOUT_DEFAULT}")
    parser.add_argument("--jobs", type=int, default=PROBE_JOBS_DEFAULT, metavar="N",
                        help=f"探测线程数上限，默认 {PROBE_JOBS_DEFAULT}")
    parser.add_argument("--include-bluetooth", action="store_true",
                        help="把蓝牙虚拟串口也纳入探测（默认跳过：它们不是可烧录目标，open() 还可能阻塞数秒）")
    parser.add_argument("-y", "--yes", action="store_true", help="跳过烧录确认（物理操作，默认要确认）")
    parser.add_argument("--board", metavar="ID", help="指定版型 id（仅用于提示与产物一致性校验）")
    parser.add_argument("--fw-root", metavar="DIR", help="固件源码根目录（默认用 sets 自带副本）")
    parser.add_argument("--python", metavar="EXE",
                        help="指定 IDF venv 的 python（探测与 esptool 都用它）")
    parser.add_argument("--no-reexec", action="store_true",
                        help="缺 pyserial 时不自动切换解释器（只枚举串口）")
    parser.add_argument("--no-color", action="store_true", help="关闭彩色输出")
    args = parser.parse_args(argv)

    if args.jobs < 1:
        parser.error("--jobs 至少为 1")
    if args.timeout <= 0:
        parser.error("--timeout 必须大于 0")
    return args


def _ask_flash(port: str, board: Optional[dict[str, Any]]) -> bool:
    if not sys.stdin.isatty():
        notice_bad("非交互式终端，请加 --yes 明确确认后重试")
        return False
    target = f"「{board['name']}」的产物" if board else "当前 build 产物"
    say()
    try:
        raw = input(f"是否把 {target} 烧录到 {port}？[y/N] ").strip().lower()
    except EOFError:
        return False
    return raw in ("y", "yes")


def _print_build_hint(fw_root: Path, board: Optional[dict[str, Any]]) -> None:
    say("        请先编译：")
    if board:
        say(f"          python hardware/sets/build.py --board {board['id']}")
    else:
        say("          python hardware/sets/build.py --board <版型id>")
    say("        （build.py 只编译 + 归档产物，烧录由本脚本负责）")


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(argv)
    sets_build._init_stdio()
    sets_build._USE_COLOR = not args.no_color and bool(getattr(sys.stdout, "isatty", lambda: False)())
    if sets_build._USE_COLOR:
        sets_build._enable_windows_ansi()

    if args.python:
        sets_build._PYTHON_OVERRIDE = args.python
        sets_build._IDF_ENV_CACHE = None

    rerun_code = reexec_with_idf_python(argv, allow_reexec=not args.no_reexec)
    if rerun_code is not None:
        return rerun_code

    json_mode = args.json
    list_mode = args.list or args.json

    if not json_mode:
        say(rule("="))
        say(bold("小智固件烧录 (hardware/sets/flash.py)"))
        say(rule("="))

    fw_root = sets_build.resolve_fw_root(args.fw_root)
    if fw_root is None:
        notice_bad("自动探测不到固件源码根目录（<FW>）")
        say("请用 --fw-root 指定，或设置环境变量 XIAOZHI_FW_ROOT。已尝试的位置：")
        for candidate in sets_build.FW_CANDIDATES:
            say(f"    {candidate}")
        return EXIT_ENV

    board: Optional[dict[str, Any]] = None
    if args.board:
        boards, broken = sets_build.discover_boards()
        board = next((item for item in boards if item["id"] == args.board), None)
        if board is None:
            notice_bad(f"未找到版型 {args.board!r}")
            say("可用版型: " + ", ".join(item["id"] for item in boards))
            for name, errors in broken:
                if name == args.board:
                    for message in errors:
                        say(f"  {name}: {message}")
            return EXIT_ENV

    if not json_mode:
        say(f"  固件根目录: {fw_root}")
        if board:
            say(f"  指定版型  : {board['id']} — {board['name']}")
        if not list_mode:
            if board:
                warn_board_mismatch(fw_root, board)
            reason = check_build_ready(fw_root)
            if reason:
                notice_bad(f"没有可烧录的产物：{reason}")
                _print_build_hint(fw_root, board)
                return EXIT_ERROR

    # ---- 1. 并行探测串口 ----
    ports = enumerate_ports()
    if not ports and not args.port:
        reason = "缺少 pyserial，无法枚举串口" if not _HAVE_PYSERIAL else "没有枚举到任何串口"
        if json_mode:
            print(json.dumps(
                {
                    "fw_root": str(fw_root),
                    "board": board["id"] if board else None,
                    "chip": CHIP,
                    "ports": [],
                    "confirmed": [],
                    "skipped_bluetooth": [],
                    "selected": None,
                    "error": reason,
                },
                ensure_ascii=False, indent=2,
            ))
            return EXIT_OK
        notice_bad(reason)
        if not _HAVE_PYSERIAL:
            say("        请用 --python <IDF venv>\\Scripts\\python.exe 指定解释器。")
            return EXIT_ENV
        say("        请检查 USB 线（要能传数据，不是纯充电线）与串口驱动是否安装。")
        return EXIT_ERROR if not list_mode else EXIT_OK

    if not ports:
        # 用户点名了串口，即使枚举不到也照他的意思试（有些驱动的口枚举不到但能开）
        notice_warn(f"没有枚举到任何串口，仍按 --port {args.port} 强制尝试")
        if json_mode:
            print(json.dumps(
                {
                    "fw_root": str(fw_root),
                    "board": board["id"] if board else None,
                    "chip": CHIP,
                    "ports": [],
                    "confirmed": [],
                    "skipped_bluetooth": [],
                    "selected": args.port,
                    "error": "没有枚举到任何串口，按 --port 强制使用",
                },
                ensure_ascii=False, indent=2,
            ))
            return EXIT_OK
        if list_mode:
            notice_warn("探测完成（--list，未烧录）：没有枚举到任何串口")
            return EXIT_OK
        probes = [PortProbe(device=args.port, state="unknown", detail="未枚举到，按用户指定强制使用")]
    else:
        probes = probe_all(
            ports,
            timeout=args.timeout,
            jobs=args.jobs,
            identify=args.identify,
            stream=not json_mode,
            include_bluetooth=args.include_bluetooth,
        )
    confirmed = [probe for probe in probes if probe.confirmed]
    skipped = [probe for probe in probes if probe.state == "skipped"]

    if json_mode:
        print(json.dumps(
            {
                "fw_root": str(fw_root),
                "board": board["id"] if board else None,
                "chip": CHIP,
                "ports": [probe.to_json() for probe in probes],
                "confirmed": [probe.device for probe in confirmed],
                "skipped_bluetooth": [probe.device for probe in skipped],
                "selected": None,
            },
            ensure_ascii=False,
            indent=2,
        ))
        return EXIT_OK

    # ---- 2. 只探测不烧录 ----
    if list_mode:
        if confirmed:
            notice_ok(f"探测完成（--list，未烧录）：{len(confirmed)} 个可用设备 —— "
                      + "、".join(probe.device for probe in confirmed))
        elif skipped:
            notice_warn(f"探测完成（--list，未烧录）：只枚举到 {len(skipped)} 个蓝牙虚拟串口，"
                        "没有检测到 USB 串口设备")
        else:
            notice_warn("探测完成（--list，未烧录）：没有检测到可用设备")
        return EXIT_OK

    # ---- 3. 选择串口 ----
    selected = select_port(probes, args.port)
    if selected is None:
        notice_warn("已取消烧录")
        return EXIT_OK

    # ---- 4. 确认并烧录 ----
    python = sets_build._idf_python()
    if not _esptool_ok(python):
        notice_bad(f"所用解释器里没有 esptool: {python}")
        say("        请用 --python 指定 IDF venv 的 python（esptool 随它一起安装）。")
        return EXIT_ENV

    if not args.yes and not _ask_flash(selected, board):
        say("已取消烧录。")
        return EXIT_OK

    return run_flash(fw_root, selected, args.baud)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        say("")
        notice_bad("已被用户中断 (Ctrl+C)")
        sys.exit(130)
