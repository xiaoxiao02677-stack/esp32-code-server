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
  2) 深度识别（--identify）：复位目标板读 ROM 启动日志，匹配 "ESP-ROM:"
     判定是不是 Espressif 芯片、具体是哪一款。两种复位线序都会试（见下），
     识别完再把设备复位回正常运行状态。

烧录前还有一步 **复位线序识别（--reset auto，默认）**：
  Espressif 参考设计是 DTR->GPIO0、RTS->EN，esptool 的 ClassicReset 就按这个
  假定发时序。但**本项目部分板子是反相接线（DTR->EN、RTS->GPIO0）**，此时
  esptool 的 --before default-reset 只会让芯片正常运行并开始打日志，日志首字节
  'I'(0x49) 被 esptool 当成数据包包头，于是报：
      Failed to connect to ESP32-S3: Invalid head of packet (0x49)
  这块板「按住 BOOT 开机」也没用 —— esptool 在连接阶段会再复位一次。
  脚本因此自带线序识别：反相板由我们按镜像时序把芯片送进下载模式，再让 esptool
  用 --before no-reset 接管（实测一次连上，MAC/Flash ID 都能读）。

pyserial / esptool 都取自 ESP-IDF 的 venv。当前解释器没有 pyserial 时，本脚本会
自动改用 IDF venv 的 python 重新执行自己（可用 --python 指定，或 --no-reexec 关闭）。

写入策略（默认，2026-10-17 按实机断链问题加固）：
  · 逐段：一个镜像一个 esptool 会话；大镜像再按 1MB 切块，崩一次只重写这 1MB；
  · 探活：每段写之前先跑 flash-id（约 1.8 秒）—— 连接问题不能拖到写了一半才暴露；
  · 自愈：连接 / 写入失败 → 重试 3 次 → 降档波特率 → 换复位线序，全用完才报错；
  · 顺序：按地址升序（bootloader → 分区表 → otadata → app → assets），assets 垫底，
    它断了设备照样能启动，缺的只是字库 / 表情 / 唤醒词。

两种烧录方式（--mode，交互式终端会弹菜单让你选）：
  · idf  —— 直接用项目里的 build 目录：一条命令读完 build/flash_args 写完所有镜像
            （标准接线时就是真的 `idf.py flash`），连一次、最快、最省事；
  · staged —— 上面那套逐段 + 切块 + 自愈的加固流程，链路不稳时用（默认）。

烧录前后各有一道闸（默认开启）：
  · 烧录前核对 build 产物地址与分区表是否同源 —— 布局不一致直接拒烧。实机踩过的坑：
    分区表是 16MB 布局（ota_0@0x20000），app 却按 4MB 布局写到 0x10000，bootloader
    在 0x20000 找不到合法镜像（首字节不是 0xE9）就自杀重启 —— 屏幕不亮 + 无限重启。
  · 烧录后回读逐字节比对，再复位读串口，明确给出「已启动 / 在循环重启」的结论。
板子里是别的固件、或分区表被外来固件改过时，用 --clean 先整片擦除再全量重烧。

用法（完整示例见 --help）：
  python hardware/sets/flash.py                  # 探测串口并烧录 <FW>/build 产物
  python hardware/sets/flash.py --list           # 只探测列出，不烧录
  python hardware/sets/flash.py --identify       # 探测 + 复位识别芯片型号
  python hardware/sets/flash.py --json           # 探测结果输出 JSON（脚本调用）
  python hardware/sets/flash.py --port COM5 -y   # 指定串口直接烧录
  python hardware/sets/flash.py --port COM5 --clean   # 整片擦除后全量重烧
"""

import argparse
import importlib.util
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
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
BAUD_DEFAULT = 230400       # 460800 在长线/劣质线材 + 4MB 大镜像时会断链；稳优先
PROBE_BAUD = 115200
FLASH_MODE = "dio"
FLASH_SIZE = "16MB"
FLASH_FREQ = "80m"
PROBE_TIMEOUT_DEFAULT = 0.6
PROBE_JOBS_DEFAULT = 8

# 烧录方式（交互式菜单 / --mode）
METHOD_IDF = "idf"          # 直接吃 build/flash_args，一条命令写完（最省事）
METHOD_STAGED = "staged"    # 逐段 + 切块 + 双端校验（链路不稳时用）
METHOD_DIAG = "diag"        # 只回读体检，不写 flash
DEFAULT_MODE = METHOD_STAGED  # 非交互式（脚本 / -y / 管道）时的默认，保持旧行为

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

# --- 复位线序 / 下载模式 ---------------------------------------------------
RESET_HOLD = 0.12         # 复位线保持时长
RESET_SETTLE = 0.12       # 放开复位到开始采样之间的等待
RESET_READ_WINDOW = 1.6   # 复位后读启动日志的窗口
RESET_ORDER_LABEL = {"classic": "标准（DTR=GPIO0 / RTS=EN）", "reversed": "反相（DTR=EN / RTS=GPIO0）"}

# ROM 启动日志横幅：只要出现它，就说明这次复位真的生效了
ROM_BANNER = re.compile(rb"ESP-ROM:esp32", re.IGNORECASE)
# 停在下载模式的特征
DOWNLOAD_MARKERS = (
    re.compile(rb"waiting for download", re.IGNORECASE),
    re.compile(rb"DOWNLOAD\(UART", re.IGNORECASE),
    re.compile(rb"DOWNLOAD\(USB", re.IGNORECASE),
)
# 正常启动应用的特征
APP_BOOT_MARKERS = (re.compile(rb"SPI_FAST_FLASH_BOOT", re.IGNORECASE),)
# 应用运行日志（"I (1234) Tag: ..."）—— 报 0x49 时看到的就是它
APP_LOG_HINT = re.compile(rb"[IWEDV] \(\d+\) ")


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
    reset_order: str = ""  # identify 模式下命中的复位线序：classic / reversed
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


def _reset_lines(port: Any, order: str = "classic") -> None:
    """按指定线序复位目标板，最后把两根控制线都放开。

    order="classic"  ：DTR=GPIO0、RTS=EN —— 与 esptool ClassicReset 完全一致。
    order="reversed" ：DTR=EN、RTS=GPIO0 —— 本项目部分板子的实际接线。
    复位后芯片以什么模式启动取决于「放开 EN 那一刻 GPIO0 的电平」：
    镜像时序让 GPIO0 保持低 -> 进下载模式；标准时序让 GPIO0 回高 -> 正常运行。
    """
    if order == "reversed":
        port.dtr = True   # EN 拉低，芯片进入复位
        port.rts = False
        time.sleep(RESET_HOLD)
        port.rts = True   # GPIO0 拉低
        port.dtr = False  # 放开 EN -> 带着 GPIO0=L 启动
    else:
        port.dtr = False  # GPIO0 保持高
        port.rts = True   # EN 拉低，芯片进入复位
        time.sleep(RESET_HOLD)
        port.dtr = True   # GPIO0 拉低
        port.rts = False  # 放开 EN -> 带着 GPIO0=L 启动
    time.sleep(RESET_SETTLE)
    port.dtr = False
    port.rts = False


def _classify_reset(data: bytes) -> str:
    """判断复位后芯片落在哪种状态：download / app / none（没复位成功）。"""
    if not ROM_BANNER.search(data):
        return "none"
    if any(pattern.search(data) for pattern in DOWNLOAD_MARKERS):
        return "download"
    if any(pattern.search(data) for pattern in APP_BOOT_MARKERS):
        return "app"
    return "app"


def _open_raw(device: str) -> Any:
    """以 DTR/RTS 均不激活的方式打开串口（打开动作本身不会打扰目标板）。"""
    port = serial.Serial()
    port.port = device
    port.baudrate = PROBE_BAUD
    port.timeout = 0.05
    port.write_timeout = 0.2
    port.dtr = False
    port.rts = False
    port.open()
    return port


def _reset_and_sample(port: Any, order: str, window: float = RESET_READ_WINDOW) -> tuple[str, bytes]:
    """复位一次并读启动日志，返回（状态分类, 原始数据）。"""
    try:
        port.reset_input_buffer()
    except Exception:  # pragma: no cover - 驱动相关
        pass
    try:
        _reset_lines(port, order)
    except (OSError, ValueError) as error:
        # 少数 USB 转串口适配器不支持控制 DTR/RTS（esptool 同样会给出 ENOTTY 提示）
        return "unsupported", str(error).encode("utf-8", "replace")
    data = _read_window(port, window)
    return _classify_reset(data), data


def _close_quietly(port: Any) -> None:
    try:
        if port is not None:
            port.dtr = False
            port.rts = False
            port.close()
    except Exception:  # pragma: no cover - 驱动相关
        pass


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
    if len(data) > width:
        # 复位采样的开头常混着上一轮启动的残留日志：让可见片段从最后一次 ROM 横幅开始
        index = data.rfind(b"ESP-ROM:")
        if 0 <= index < len(data) - 8:
            data = data[index:]
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
            # 两种线序都试：命中判据是「真的落进下载模式」。只读到 ROM 横幅不算 ——
            # 那是复位成功了，但芯片可能正常运行了应用（本项目的反相板就是这样）。
            data = b""
            for candidate in ("classic", "reversed"):
                status, sample = _reset_and_sample(port, candidate, timeout + 0.8)
                data = sample
                if status == "unsupported":
                    probe.detail = "该适配器不支持控制 DTR/RTS，无法复位识别"
                    break
                if not probe.chip:
                    probe.chip = _match_chip(sample)
                if any(pattern.search(sample) for pattern in DOWNLOAD_MARKERS):
                    probe.reset_order = candidate
                    break
        else:
            data = _read_window(port, timeout)
        probe.bytes_seen = len(data)
        probe.sample = _summarize(data)
        probe.state = "ok"
        if identify:
            probe.chip = _match_chip(data)
            if not probe.chip:
                if any(p.search(data) for p in DOWNLOAD_MARKERS):
                    probe.detail = "已复位并停在下载模式（控制台不在 115200 时读不到 ROM 横幅）"
                elif APP_LOG_HINT.search(data):
                    probe.detail = "复位后读到的是应用运行日志 —— 本板复位线序与 esptool 假定相反"
                else:
                    probe.detail = "已复位但未读到 ESP-ROM 启动日志（可能不是 Espressif 芯片，或控制台不在 115200）"
            if probe.reset_order:
                # 命中的那次复位会把芯片留在下载模式；识别完用相反时序复位回正常运行
                restore = "classic" if probe.reset_order == "reversed" else "reversed"
                try:
                    _reset_and_sample(port, restore, 0.4)
                except Exception:  # pragma: no cover - 驱动相关
                    pass
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
    if probe.reset_order:
        label = "反相" if probe.reset_order == "reversed" else "标准"
        parts.append(f"复位线序={label}")
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
# 3. 下载模式（复位线序识别 / 送进下载模式）
#
# 背景：esptool 的 ClassicReset 假定 DTR=GPIO0、RTS=EN（Espressif 参考设计）。
# 本项目部分板子是**反相**接线（DTR=EN、RTS=GPIO0），结果：
#   * --before default-reset 只会让芯片正常运行，随后应用日志的首字节 'I'(0x49)
#     被 esptool 当成数据包包头 -> "Invalid head of packet (0x49)"；
#   * 「按住 BOOT 开机」也救不了，因为 esptool 在连接阶段还会自己再复位一次。
# 对策：烧录前先识别线序；反相板由脚本按镜像时序送进下载模式，再用
# --before no-reset 交给 esptool（已实测一次连上，能读 MAC / Flash ID）。
# ---------------------------------------------------------------------------


@dataclass
class ResetPlan:
    """烧录前如何让芯片进入下载模式。"""

    before: str = "default-reset"  # 传给 esptool 的 --before 取值
    our_reset: bool = False        # True = 由本脚本负责把芯片送进下载模式
    order: str = ""                # our_reset 时使用的线序：classic / reversed
    note: str = ""


def detect_reset_order(device: str) -> tuple[str, str]:
    """识别本板复位线序，返回 (order, evidence)，order ∈ reversed / classic / unknown。

    判据是「复位后芯片落在下载模式、还是正常运行应用」：镜像时序先试（本项目
    反相板就是这一种），命中即返回；否则再按标准时序试一次。两次都没能让芯片
    重启（读不到 ESP-ROM 横幅）则视为识别失败。
    """
    try:
        port = _open_raw(device)
    except Exception as error:
        return "unknown", f"无法打开串口：{error}"
    evidence = ""
    try:
        for order in ("reversed", "classic"):
            status, data = _reset_and_sample(port, order)
            if data:
                evidence = _summarize(data, 108)
            if status == "unsupported":
                return "unknown", evidence or "该适配器不支持控制 DTR/RTS"
            if status == "download":
                return order, evidence
    finally:
        _close_quietly(port)
    return "unknown", evidence


def enter_download_mode(device: str, order: str, window: float = 0.9) -> tuple[bool, str]:
    """按指定线序把芯片送进下载模式，并回读一段日志确认。"""
    try:
        port = _open_raw(device)
    except Exception as error:
        return False, f"无法打开串口：{error}"
    try:
        status, data = _reset_and_sample(port, order, window)
    except Exception as error:  # pragma: no cover - 驱动相关
        return False, f"复位失败：{error}"
    finally:
        _close_quietly(port)
    return status == "download", _summarize(data, 108)


def _manual_plan(port: str) -> ResetPlan:
    """打印手动进下载模式的步骤、等用户回车，再回读串口做个确认。"""
    if not sys.stdin.isatty():
        notice_bad("--manual 需要交互式终端：请在真实终端里执行，或改用 --reset none")
        return ResetPlan("no-reset", False, "", "--manual（非交互式终端，未等待）")
    say()
    say(bold("[手动] 请让设备进入下载模式："))
    say("        1) 按住 BOOT 键不放")
    say("        2) 点一下 RST 键（没有 RST 键就拔插一次 USB 供电）")
    say("        3) 松开 BOOT 键")
    say("        4) 回到这里按回车，脚本立刻用 --before no-reset 连接")
    try:
        input("        > ")
    except (EOFError, KeyboardInterrupt):
        say()
        notice_warn("已取消")
        return ResetPlan("no-reset", False, "", "--manual（已取消）")
    try:
        handle = _open_raw(port)
        try:
            data = _read_window(handle, 0.8)
        finally:
            _close_quietly(handle)
        if APP_LOG_HINT.search(data):
            notice_warn("设备看起来仍在运行应用（读到运行日志），可能没进下载模式；先试一次，失败可重来")
        elif data:
            say(f"        串口输出：{_summarize(data, 100)!r}")
        else:
            say(green("        串口安静 —— 符合下载模式的表现"))
    except Exception:  # pragma: no cover - 驱动相关
        pass
    return ResetPlan("no-reset", False, "", "--manual：已由用户手动进入下载模式")


def resolve_reset_plan(port: str, args: argparse.Namespace) -> ResetPlan:
    """决定烧录前怎么让芯片进下载模式。"""
    if args.manual:
        return _manual_plan(port)
    if args.before:
        return ResetPlan(args.before, False, "", f"按 --before {args.before} 原样交给 esptool")
    if args.reset == "none":
        return ResetPlan("no-reset", False, "",
                         "--reset none：不复位、直接连接（用于设备已手动进下载模式）")
    if args.reset == "esptool":
        return ResetPlan("default-reset", False, "", "--reset esptool：完全交给 esptool 自己复位")
    if args.reset == "reversed":
        return ResetPlan("no-reset", True, "reversed", "--reset reversed：按镜像时序送进下载模式")

    # auto（默认）：先识别本板线序
    say()
    say(bold("[复位] 识别本板复位线序（最多复位两次，约 3~5 秒）"))
    order, evidence = detect_reset_order(port)
    if order == "reversed":
        return ResetPlan(
            "no-reset", True, "reversed",
            f"检测到本板为反相接线（{RESET_ORDER_LABEL['reversed']}）：esptool 的 "
            "--before default-reset 对这块板无效，改由脚本送进下载模式",
        )
    if order == "classic":
        return ResetPlan("default-reset", False, "classic",
                         f"检测到标准接线（{RESET_ORDER_LABEL['classic']}）：交给 esptool 自己复位")
    notice_warn("未能识别复位线序：两种时序都没能让芯片重启（读不到 ESP-ROM 横幅）")
    if evidence:
        say(f"        复位后串口输出：{evidence!r}")
    say("        可能原因：适配器不支持控制 DTR/RTS、EN/GPIO0 没接到串口，或设备本就不输出日志。")
    say("        建议手动进入下载模式后重跑：按住 BOOT → 点一下 RST → 松开 BOOT，")
    say("              再加 --reset none（或直接用 --manual 让脚本带你走一遍）。")
    return ResetPlan("default-reset", False, "", "")


def diagnose_after_failure(port: str) -> None:
    """烧录失败后回读一小段串口，判断设备此刻到底在干什么（不依赖 esptool 的 stdout）。"""
    try:
        handle = _open_raw(port)
    except Exception:
        return
    try:
        data = _read_window(handle, 1.2)
    finally:
        _close_quietly(handle)
    if not data:
        say("        回读串口：没有数据（口可用，但设备没有任何输出）")
        return
    sample = _summarize(data, 120)
    if any(pattern.search(data) for pattern in DOWNLOAD_MARKERS):
        say(f"        回读串口：设备停在下载模式（{sample!r}）")
        say("        esptool 却连不上 → 多半是波特率或线材问题：先试 --baud 115200。")
    elif APP_LOG_HINT.search(data):
        say(f"        回读串口：设备正在运行应用（{sample!r}）")
        say("        即它压根没进下载模式 —— 这类板子的复位时序与 esptool 的假定不符。")
        say("        手动进下载模式后重跑：按住 BOOT → 点一下 RST → 松开 BOOT，再加 --reset none。")
    else:
        say(f"        回读串口：{sample!r}")


# ---------------------------------------------------------------------------
# 4. 选择串口
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
# 5. 烧录
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


def show_build_server_env(fw_root: Path) -> None:
    """烧录前展示当前 build 产物连的是哪个服务器环境（生产/测试）。"""
    fragment = fw_root / "build" / "xiaozhi-build.sdkconfig.defaults"
    if not fragment.is_file():
        return
    try:
        text = fragment.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    ota = re.search(r'^CONFIG_OTA_URL="([^"]*)"$', text, re.MULTILINE)
    yh_port = re.search(r"^CONFIG_YH_SERVER_PORT=(\d+)$", text, re.MULTILINE)
    if not ota and not yh_port:
        return
    matched = None
    for env_key, env in sets_build.SERVER_ENVS.items():
        env_ota = re.search(r'CONFIG_OTA_URL="([^"]*)"', "\n".join(env["sdkconfig"]))
        env_port = re.search(r"CONFIG_YH_SERVER_PORT=(\d+)", "\n".join(env["sdkconfig"]))
        if ota and env_ota and ota.group(1) == env_ota.group(1):
            matched = env_key
            break
        if yh_port and env_port and yh_port.group(1) == env_port.group(1):
            matched = env_key
            break
    say(f"  产物环境  : {sets_build.bold(matched or '未知')}（OTA {ota.group(1) if ota else '?'}"
        + (f"，YH 端口 {yh_port.group(1)}" if yh_port else "") + "）")
    if matched == "test":
        say(sets_build.yellow("        这是连测试服务器的固件（--server test 编译产物），勿刷到生产设备。"))
    elif matched is None and ota:
        say(sets_build.yellow("        产物里的服务器地址不在已知环境表内，请人工确认。"))


def _esptool_ok(python: str) -> bool:
    try:
        completed = subprocess.run(
            [python, "-c", "import esptool"], capture_output=True, timeout=90, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def _extra_flash_flags(text: str) -> list[str]:
    """flash_args 里已经写明的烧录参数不再重复追加（让命令保持干净）。"""
    extra: list[str] = []
    for flag, value in (
        ("--flash-mode", FLASH_MODE),
        ("--flash-freq", FLASH_FREQ),
        ("--flash-size", FLASH_SIZE),
    ):
        if not re.search(rf"{flag}[= ]{re.escape(value)}\b", text):
            extra += [flag, value]
    return extra


def build_flash_command(
    fw_root: Path, port: str, baud: int, plan: ResetPlan, after: str
) -> tuple[list[str], Path, str]:
    """拼装 esptool 命令，返回 (命令, 工作目录, 模式说明)；命令为空表示产物缺失。"""
    build_dir = fw_root / "build"
    flash_args = build_dir / "flash_args"
    text = ""
    if flash_args.is_file():
        try:
            text = flash_args.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""

    base = [
        sets_build._idf_python(), "-m", "esptool",
        "--chip", CHIP,
        "-p", port,
        "-b", str(baud),
        "--before", plan.before,
        "--after", after,
        "write-flash",
    ]

    if "generated_assets" in text:
        # 用 @flash_args 时工作目录必须是 build/（文件里的路径是相对的）
        command = base + ["@flash_args", *_extra_flash_flags(text)]
        return command, build_dir, "按 build/flash_args 烧录（已含 assets 分区）"

    command = base + _extra_flash_flags("")
    included = 0
    for offset, relative in FLASH_FULL_IMAGE:
        if not (fw_root / relative).is_file():
            notice_warn(f"缺少 {relative}，跳过该分区")
            continue
        command += [offset, relative]
        included += 1
    if included == 0:
        return [], fw_root, "没有任何可烧录的镜像文件"
    return command, fw_root, "显式全量烧录（bootloader + 分区表 + ota_data + app + assets）"


# ---------------------------------------------------------------------------
# 5a-2. 分段烧录：一次 esptool 会话只写一个镜像
#
# 血泪教训（2026-10-17 实机）：一次性 write-flash 写 5 个镜像、其中 assets 有
# 3.9MB 时，只要中途链路断一次，**整条命令**就作废 —— 已写进去的还在，但后面
# 的镜像一个都没写；而 esptool 只会甩一句
#     A fatal error occurred: No more data to read from the serial port.
# 看起来像「连不上芯片」，实际是「写到一半掉线」，于是很容易误判。
#
# 分段后：每段独立「进下载模式 → 连接 → 写 → 断开」，某段断了只重写那一段，
# 还能顺带自动降速重试。assets 单独成段，慢但不再拖累前面四个关键镜像。
# ---------------------------------------------------------------------------

BAUD_LADDER = (460800, 230400, 115200)
OTADATA_NAME = "ota_data_initial.bin"

# 大镜像切块阈值：超过 1.5MB 就切，块大小 1MB（与 4KB sector 对齐，互不擦除）。
# 单次传输越长越容易中途断链；切块后崩一次只重写 1MB，而不是从头再来 4MB。
CHUNK_THRESHOLD = 0x180000
CHUNK_SIZE_DEFAULT = 0x100000

CONNECT_TRIES = 3           # 每次连接的探活次数
CONNECT_RETRY_DELAY = 0.4   # 两次探活之间的间隔（秒）

# 这些字样出现就说明是「连不上」，而不是「写到一半坏了」—— 两者处置完全不同。
CONNECT_ERROR_HINTS = (
    "Failed to connect",
    "Invalid head of packet",
    "No serial data received",
    "Timed out waiting for packet",
    "Wrong boot mode",
    "could not open port",
    "PermissionError",
    "Access is denied",
    "拒绝访问",
)


def describe_otadata(data: bytes) -> str:
    """解析 otadata（两个 4KB 记录）给出人话。

    `ota_data_initial.bin` 是全 0xFF，含义是「从未通过 OTA 启动过」；而设备只要成功
    启动过一次，bootloader 就会把 `ota_seq=1` 写进记录里表示「正在用 ota_0」。
    所以它**天然不等于**本地产物 —— 按逐字节比对，每次启动后再校验都会误报。
    """
    def seq_of(base: int) -> Optional[int]:
        if len(data) < base + 4:
            return None
        value = struct.unpack("<I", data[base:base + 4])[0]
        return None if value == 0xFFFFFFFF else value

    values = [item for item in (seq_of(0), seq_of(0x1000)) if item is not None]
    if not values:
        return "未使用（全 0xFF）—— bootloader 会默认启动 ota_0"
    active = max(values)
    slot = "ota_0" if active % 2 == 1 else "ota_1"
    return f"已选中 {slot}（ota_seq={active}）—— 设备启动过，属正常状态"


def baud_candidates(baud: int) -> list[int]:
    """从给定波特率往下退到 115200，用于失败后自动降速重试。"""
    ladder = [baud]
    for item in BAUD_LADDER:
        if item < baud and item not in ladder:
            ladder.append(item)
    if ladder[-1] != 115200:
        ladder.append(115200)
    return ladder


def _last_error_line(text: str) -> str:
    """从 esptool 输出里挑一行最能说明问题的话。"""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(lines):
        lowered = line.lower()
        if any(hint.lower() in lowered for hint in CONNECT_ERROR_HINTS) or "fatal error" in lowered:
            return line
    return lines[-1] if lines else ""


def stage_command(
    port: str, baud: int, plan: ResetPlan, after: str, offset: int, path: Path
) -> list[str]:
    """拼装「只写一段」的 esptool 命令。"""
    return [
        sets_build._idf_python(), "-m", "esptool",
        "--chip", CHIP,
        "-p", port,
        "-b", str(baud),
        "--before", plan.before,
        "--after", after,
        "write-flash",
        "--flash-mode", FLASH_MODE,
        "--flash-freq", FLASH_FREQ,
        "--flash-size", FLASH_SIZE,
        hex(offset), str(path),
    ]


def probe_connection(port: str, plan: ResetPlan, baud: int, tries: int) -> tuple[bool, str]:
    """轻量探活（`esptool flash-id`，1~2 秒）：先确认连得上，再开始写。

    不再拿 `write-flash` 去当探针 —— 连接问题必须暴露在传输 4MB 之前，而不是
    写了一半才报 "No more data to read"。探活失败会重试，并把复位线序也换一遍
    （自动识别偶尔会认错，认对的那条会沿用到后续所有段）。
    """
    python = sets_build._idf_python()
    last = ""
    orders = [plan.order]
    if plan.our_reset:
        orders.append("classic" if plan.order == "reversed" else "reversed")

    for order in orders:
        for attempt in range(1, max(1, tries) + 1):
            if plan.our_reset:
                enter_download_mode(port, order)
            command = [
                python, "-m", "esptool",
                "--chip", CHIP,
                "-p", port,
                "-b", str(baud),
                "--before", plan.before,
                "--after", "no-reset",
                "flash-id",
            ]
            try:
                completed = subprocess.run(
                    command, check=False, capture_output=True, env=sets_build._idf_env_vars()
                )
            except OSError as error:  # pragma: no cover - 环境相关
                return False, f"无法启动 esptool: {error}"
            if completed.returncode == 0:
                if plan.our_reset and order != plan.order:
                    notice_ok(f"  换用 {order} 线序才连上（自动识别认错了，本次沿用这条）")
                    plan.order = order
                return True, ""
            raw = (completed.stdout or b"") + (completed.stderr or b"")
            last = _last_error_line(raw.decode("utf-8", "replace"))
            if attempt < tries:
                time.sleep(CONNECT_RETRY_DELAY)
        if plan.our_reset:
            notice_warn(f"  连不上（{order} 线序 @ {baud}）：{last or '无输出'} → 换另一种线序")
    return False, last or "连接没有建立"


def slice_chunk(path: Path, start: int, length: int) -> Optional[Path]:
    """把文件的 [start, start+length) 切到临时文件（esptool 只能整文件写）。"""
    handle, name = tempfile.mkstemp(prefix="sets_chunk_", suffix=".bin")
    temp = Path(name)
    try:
        with os.fdopen(handle, "wb") as out, path.open("rb") as source:
            source.seek(start)
            remaining = length
            while remaining > 0:
                block = source.read(min(0x40000, remaining))
                if not block:
                    break
                out.write(block)
                remaining -= len(block)
    except OSError:
        try:
            temp.unlink()
        except OSError:
            pass
        return None
    return temp


def write_chunk(
    port: str, baud: int, plan: ResetPlan,
    base_offset: int, path: Path, start: int, length: int,
) -> tuple[bool, str]:
    """把文件的 [start, start+length) 写到 `base_offset + start`。"""
    temp: Optional[Path] = None
    try:
        total = path.stat().st_size
    except OSError:
        return False, f"文件不存在：{path}"

    if start == 0 and length == total:
        source = path                       # 整段就是整个文件，不必切
    else:
        temp = slice_chunk(path, start, length)
        if temp is None:
            return False, "切分镜像失败（磁盘不可写？）"
        source = temp

    try:
        command = stage_command(port, baud, plan, "no-reset", base_offset + start, source)
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:  # pragma: no cover - 环境相关
            pass
        try:
            completed = subprocess.run(command, check=False, env=sets_build._idf_env_vars())
        except OSError as error:  # pragma: no cover - 环境相关
            return False, f"无法启动 esptool: {error}"
    finally:
        if temp is not None:
            try:
                temp.unlink()
            except OSError:
                pass

    if completed.returncode == 0:
        return True, ""
    return False, f"esptool 返回码 {completed.returncode}"


def run_stage(
    port: str, plan: ResetPlan, offset: int, name: str, path: Path,
    bauds: list[int], chunk_size: int, attempts: int,
) -> tuple[bool, str]:
    """写一个镜像（大文件切块），失败按「降速 → 重试 → 换线序」自愈。

    每一块都：探活 → 写入。探活失败降速；写入失败降速并重写**这一块**（不是整段）。
    """
    try:
        size = path.stat().st_size
    except OSError:
        return False, f"文件不存在：{path}"

    chunks: list[tuple[int, int, int]] = []      # (flash 地址, 文件内偏移, 长度)
    if chunk_size > 0 and size > CHUNK_THRESHOLD:
        for start in range(0, size, chunk_size):
            chunks.append((offset + start, start, min(chunk_size, size - start)))
        say(f"        {size} 字节 → 切成 {len(chunks)} 块（每块 {chunk_size // 1024}KB）")
    else:
        chunks.append((offset, 0, size))

    baud_index = 0
    index = 0
    while index < len(chunks):
        baud = bauds[baud_index]
        ok, detail = probe_connection(port, plan, baud, attempts)
        if not ok:
            if baud_index + 1 < len(bauds):
                notice_warn(f"  连接失败（{baud}）：{detail} → 降到 {bauds[baud_index + 1]}")
                baud_index += 1
                continue
            return False, f"连不上芯片：{detail}"

        chunk_offset, start, length = chunks[index]
        label = f"块 {index + 1}/{len(chunks)}" if len(chunks) > 1 else "整段"
        say(f"        0x{chunk_offset:<9x} {label:<9} {length:>9} 字节   @ {baud}")
        ok, detail = write_chunk(port, baud, plan, offset, path, start, length)
        if ok:
            index += 1
            continue

        if baud_index + 1 < len(bauds):
            notice_warn(f"  {label} 写入失败（{baud}）：{detail} → 降到 {bauds[baud_index + 1]} 重写这一块")
            baud_index += 1
            time.sleep(0.4)
            continue
        return False, detail
    return True, ""


def run_staged_flash(
    port: str, plan: ResetPlan, targets: list[tuple[int, str, Path]],
    baud: int, chunk_size: int, attempts: int,
) -> tuple[bool, str, str]:
    """逐段烧录。返回 (是否全部成功, 失败说明, 出问题的镜像名)。

    **顺序按地址升序**，不是 flash_args 里的书写顺序 —— flash_args 把 assets（8MB）
    排在 app（0x20000）前面，照它写就会「先啃最慢的 3.9MB，断了 app 还没写」。
    升序后关键的四段先落盘，assets 垫底：它断了设备也能启动（只是没字库/唤醒词）。
    """
    targets = sorted(targets, key=lambda item: item[0])
    bauds = baud_candidates(baud)
    if len(bauds) > 1:
        say(f"  连接/写入失败自动降速: {' → '.join(str(item) for item in bauds)}")

    failed_name = ""
    failed_detail = ""
    total = len(targets)
    for index, (offset, name, path) in enumerate(targets, start=1):
        say()
        say(bold(f"  [{index}/{total}] {name}"))
        ok, detail = run_stage(port, plan, offset, name, path, bauds, chunk_size, attempts)
        if ok:
            say(green("        OK"))
            continue
        notice_bad(f"{name} 写入失败：{detail}")
        failed_name, failed_detail = name, detail
        break

    if failed_name:
        return False, failed_detail, failed_name
    return True, "", ""


# ---------------------------------------------------------------------------
# 5b. 烧录前自检 / 烧录后校验
#
# 血泪教训：**分区表与 app 必须是同一套布局**。实机出现过的死机形态：
#   设备里的分区表是 16MB 布局（ota_0 @ 0x20000），而 app 却按 4MB 布局写到了
#   0x10000 —— bootloader 在 0x20000 找不到合法镜像（首字节不是 0xE9），于是走
#   bootloader_utility.c 的 bootloader_reset() 自杀重启，表现为「刷完屏幕不亮 /
#   无限重启」。所以这里补三道闸：烧录前核对地址、烧录后回读核对内容、最后复位
#   一次看它到底起没起来。
# ---------------------------------------------------------------------------

VERIFY_HEAD_SIZE = 0x1000     # 大镜像回读头部 4KB：能发现「写到了别处 / 写错文件」
VERIFY_TAIL_SIZE = 0x1000     # 大镜像再回读尾部 4KB：app 末尾是整段 SHA256，能发现「写一半断链」
VERIFY_FULL_LIMIT = 0x20000   # 小于这个尺寸的镜像（bootloader/分区表/otadata）全量回读
BOOT_CHECK_SECONDS = 8.0      # 烧完复位后读串口的时长

# 固定区域：不在分区表里，但也必须写。其余目标地址**必须**落在某个分区起始处，
# 否则就是「布局不同源」（例如 app 按 4MB 布局写到 0x10000，而分区表是 16MB 布局）。
FIXED_REGIONS = {0x0: "bootloader", 0x8000: "partition-table"}


def read_partition_offsets(table: Path) -> list[dict[str, Any]]:
    """解析分区表二进制，返回 [{name, type, subtype, offset, size}]。"""
    entries: list[dict[str, Any]] = []
    try:
        data = table.read_bytes()
    except OSError:
        return entries
    for index in range(0, len(data) - 31, 32):
        raw = data[index:index + 32]
        if raw[:2] != b"\xaa\x50":
            break
        name = raw[12:28].split(b"\x00")[0].decode("utf-8", "replace")
        if not name:
            break
        offset, size = struct.unpack("<II", raw[4:12])
        entries.append(
            {"name": name, "type": raw[2], "subtype": raw[3], "offset": offset, "size": size}
        )
    return entries


def parse_write_targets(fw_root: Path) -> list[tuple[int, str, Path]]:
    """列出真正会被写进 flash 的 (地址, 名字, 文件)，顺序与烧录顺序一致。

    build/flash_args 里是 `0xXXXX <相对路径>` 交替出现的 token 流（前面还有
    --flash-mode 之类的参数）；没有 flash_args 时按 FLASH_FULL_IMAGE 全量表推。
    """
    build_dir = fw_root / "build"
    args_file = build_dir / "flash_args"
    text = ""
    if args_file.is_file():
        try:
            text = args_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""

    targets: list[tuple[int, str, Path]] = []
    tokens = text.split()
    index = 0
    while index + 1 < len(tokens):
        if tokens[index].lower().startswith("0x"):
            try:
                offset = int(tokens[index], 16)
            except ValueError:
                index += 1
                continue
            relative = tokens[index + 1]
            targets.append((offset, Path(relative).name, build_dir / relative))
            index += 2
            continue
        index += 1
    if targets:
        return targets

    for offset, relative in FLASH_FULL_IMAGE:
        targets.append((int(offset, 16), Path(relative).name, fw_root / relative))
    return targets


ONLY_ALIASES = {
    "bootloader": "bootloader.bin",
    "pt": "partition-table.bin",
    "partition-table": "partition-table.bin",
    "otadata": "ota_data_initial.bin",
    "app": "xiaozhi.bin",
    "xiaozhi": "xiaozhi.bin",
    "assets": "generated_assets.bin",
}


def filter_targets(
    targets: list[tuple[int, str, Path]], only: str
) -> tuple[list[tuple[int, str, Path]], list[str]]:
    """把 `--only app,assets` 解析成要写的镜像清单，返回 (选中, 不认识的名字)。"""
    wanted: set[str] = set()
    unknown: list[str] = []
    available = {name for _offset, name, _path in targets}
    for raw in only.replace(";", ",").replace(" ", ",").split(","):
        token = raw.strip().lower()
        if not token:
            continue
        name = ONLY_ALIASES.get(token, token)
        if name not in available:
            unknown.append(raw.strip())
            continue
        wanted.add(name)
    return [item for item in targets if item[1] in wanted], unknown


def check_layout_consistency(fw_root: Path, targets: list[tuple[int, str, Path]]) -> list[str]:
    """核对「要写的地址」与「正被写进去的那张分区表」是不是同一套布局。"""
    problems: list[str] = []
    for offset, name, path in targets:
        if not path.is_file():
            problems.append(f"{name}（0x{offset:x}）文件不存在：{path}")

    table = fw_root / "build" / "partition_table" / "partition-table.bin"
    entries = read_partition_offsets(table)
    if not entries:
        problems.append(f"读不出分区表 {table}，无法核对烧录地址")
        return problems

    by_offset = {entry["offset"]: entry for entry in entries}
    for offset, name, path in targets:
        if offset in FIXED_REGIONS:  # bootloader @0x0、分区表 @0x8000：固定位置，不在表里
            continue
        entry = by_offset.get(offset)
        if entry is None:
            listed = "、".join(f"{item['name']}@0x{item['offset']:x}" for item in entries)
            problems.append(
                f"{name} 要写到 0x{offset:x}，但分区表里没有任何分区起始于该地址（{listed}）"
            )
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > entry["size"]:
            problems.append(f"{name} 有 {size} 字节，超过分区 {entry['name']} 的 {entry['size']} 字节")

    app_offsets = [entry["offset"] for entry in entries if entry["type"] == 0]
    app_target = next((item for item in targets if item[1] == "xiaozhi.bin"), None)
    if app_target is None:
        problems.append("这份烧录计划里没有 app 镜像（xiaozhi.bin）：设备必然起不来")
    elif app_target[0] not in app_offsets:
        listed = "、".join(f"0x{item:x}" for item in app_offsets) or "（一个都没有）"
        problems.append(
            f"app 要写到 0x{app_target[0]:x}，而分区表里的 app 分区在 {listed} —— 布局不同源"
        )
    return problems


def _esptool_read(
    python: str, port: str, plan: ResetPlan, baud: int, offset: int, size: int, target: Path
) -> tuple[int, str]:
    """回读一段 flash 到 target；反相板由调用方负责先把芯片送进下载模式。"""
    if plan.our_reset:
        enter_download_mode(port, plan.order)
    command = [
        python, "-m", "esptool",
        "--chip", CHIP,
        "-p", port,
        "-b", str(baud),
        "--before", "no-reset" if plan.our_reset else plan.before,
        "--after", "no-reset",
        "read-flash", hex(offset), hex(size), str(target),
    ]
    try:
        completed = subprocess.run(
            command, check=False, capture_output=True, env=sets_build._idf_env_vars()
        )
    except OSError as error:  # pragma: no cover - 环境相关
        return 1, str(error)
    raw = (completed.stdout or b"") + (completed.stderr or b"")
    return completed.returncode, raw.decode("utf-8", "replace")


def verify_written_regions(
    fw_root: Path, port: str, plan: ResetPlan, baud: int, targets: list[tuple[int, str, Path]]
) -> list[str]:
    """回读刚写好的区域逐字节比对本地产物，返回不一致清单（空 = 全部一致）。

    小镜像全量比对；大镜像比对**头部 + 尾部**两段：
      · 头部能发现「写到了别处 / 写错文件」；
      · 尾部能发现「写到一半断链」—— app 镜像末尾就是整段镜像的 SHA256，
        最后 4KB 对得上基本等于整段写完了（不做全量回读，省一半时间）。
    """
    python = sets_build._idf_python()
    bad: list[str] = []
    say()
    say(bold("[校验] 回读刚写入的区域，与本地产物逐字节比对"))
    for offset, name, path in targets:
        if not path.is_file():
            continue
        data = path.read_bytes()
        size = len(data)
        if size <= VERIFY_FULL_LIMIT:
            regions = [(offset, 0, size, "全量")]
        else:
            tail_start = max(0, size - VERIFY_TAIL_SIZE)
            regions = [
                (offset, 0, VERIFY_HEAD_SIZE, f"头部 {VERIFY_HEAD_SIZE // 1024}KB"),
                (offset + tail_start, tail_start, VERIFY_TAIL_SIZE, "尾部校验和"),
            ]

        for read_offset, file_start, read_size, label in regions:
            handle, temp_name = tempfile.mkstemp(prefix="sets_verify_", suffix=".bin")
            os.close(handle)
            temp = Path(temp_name)
            try:
                code, text = _esptool_read(
                    python, port, plan, baud, read_offset, read_size, temp
                )
                if code != 0:
                    tail = [line for line in text.splitlines() if line.strip()][-3:]
                    notice_warn(f"{name} 回读失败（esptool 返回码 {code}），跳过比对")
                    for line in tail:
                        say("        " + line)
                    bad.append(f"{name}（0x{read_offset:x}）回读失败")
                    break
                got = temp.read_bytes()
                if name == OTADATA_NAME:
                    # otadata 被 bootloader 改写属正常，只报状态、不判对错
                    say(f"  {name:<26} 0x{offset:<9x} {green('[信息]')} {describe_otadata(got)}")
                    break
                want = data[file_start:file_start + read_size]
                if got == want:
                    say(f"  {name:<26} 0x{read_offset:<9x} {green('[一致]')} {label}（{read_size} 字节）")
                    continue
                first = next(
                    (i for i in range(min(len(got), len(want))) if got[i] != want[i]), -1
                )
                if first >= 0:
                    detail = (
                        f"{sum(1 for a, b in zip(got, want) if a != b)}/{read_size} 字节不同，"
                        f"首个不同在 +0x{file_start + first:x}"
                        f"（设备=0x{got[first]:02x} 本地=0x{want[first]:02x}）"
                    )
                else:
                    detail = f"长度不符：设备 {len(got)} 字节 / 本地 {read_size} 字节"
                notice_bad(f"{name} 0x{read_offset:x} 与本地不一致（{label}）：{detail}")
                bad.append(f"{name}（0x{read_offset:x}，{label}）{detail}")
                break
            finally:
                try:
                    temp.unlink()
                except OSError:
                    pass
    return bad


def _sample_window(port: Any, seconds: float, limit: int = 8192) -> bytes:
    """在 seconds 内尽量收数据（给启动检查用：要够长才看得出是不是在循环重启）。"""
    deadline = time.monotonic() + seconds
    chunks = bytearray()
    while time.monotonic() < deadline and len(chunks) < limit:
        try:
            waiting = port.in_waiting
        except Exception:  # pragma: no cover - 驱动相关
            waiting = 0
        if waiting:
            try:
                chunks += port.read(min(waiting, limit - len(chunks)))
            except Exception:  # pragma: no cover - 驱动相关
                break
        else:
            time.sleep(0.05)
    return bytes(chunks)


def boot_check(port: str, plan: ResetPlan, seconds: float) -> str:
    """复位一次并读串口，判断设备到底起没起来。

    返回 started / loop / download / silent / unknown。
    ROM 的 "ESP-ROM:" 横幅一定会打（ROM 代码，不受 sdkconfig 影响），应用日志
    受 CONFIG_LOG_LEVEL 影响；因此「窗口里出现两次以上横幅」就能判定在循环重启。
    """
    if seconds <= 0:
        return "skipped"
    say()
    say(bold(f"[启动检查] 复位设备并读 {seconds:.0f} 秒串口日志"))
    try:
        handle = _open_raw(port)
    except Exception as error:
        notice_warn(f"打不开串口做启动检查：{error}")
        return "unknown"
    order = plan.order if plan.our_reset else "classic"
    try:
        try:
            handle.reset_input_buffer()
        except Exception:  # pragma: no cover - 驱动相关
            pass
        try:
            _reset_lines(handle, order)
        except (OSError, ValueError) as error:
            notice_warn(f"复位失败（{error}）：跳过启动检查")
            return "unknown"
        data = _sample_window(handle, seconds)
    finally:
        _close_quietly(handle)

    sample = _summarize(data, 150)
    if not data:
        notice_warn("复位后串口没有任何输出")
        return "silent"
    if any(pattern.search(data) for pattern in DOWNLOAD_MARKERS):
        say(f"  串口日志: {sample!r}")
        notice_warn("设备停在下载模式（没有被复位回应用）")
        return "download"
    banners = data.count(b"ESP-ROM:")
    if banners >= 2:
        say(f"  串口日志: {sample!r}")
        notice_bad(f"{seconds:.0f} 秒内出现了 {banners} 次 ROM 启动横幅：设备在**循环重启**")
        return "loop"
    if APP_LOG_HINT.search(data):
        say(f"  串口日志: {sample!r}")
        notice_ok("设备已正常启动（读到了应用运行日志）")
        return "started"
    say(f"  串口日志: {sample!r}")
    notice_warn("既没读到应用日志，也没看到反复重启：判定不了（可能日志级别被关掉）")
    return "unknown"


def erase_flash(port: str, plan: ResetPlan, baud: int) -> int:
    """整片擦除（--clean 用）：把外来的分区表 / 固件残骸清干净，避免布局混用。"""
    python = sets_build._idf_python()
    if plan.our_reset:
        enter_download_mode(port, plan.order)
    command = [
        python, "-m", "esptool",
        "--chip", CHIP,
        "-p", port,
        "-b", str(baud),
        "--before", "no-reset" if plan.our_reset else plan.before,
        "--after", "no-reset",
        "erase-flash",
    ]
    say()
    say(bold("[清空] 整片擦除 flash（erase-flash，16MB 大约要几十秒）"))
    say("  " + " ".join(command))
    try:
        completed = subprocess.run(command, check=False, env=sets_build._idf_env_vars())
    except OSError as error:
        notice_bad(f"无法启动 esptool: {error}")
        return EXIT_ERROR
    if completed.returncode != 0:
        notice_bad(f"整片擦除失败（esptool 返回码 {completed.returncode}）")
    return completed.returncode


def _write_all_at_once(
    fw_root: Path, port: str, baud: int, plan: ResetPlan,
    args: argparse.Namespace, targets: list[tuple[int, str, Path]],
) -> tuple[bool, str, str]:
    """一次性把全部镜像交给同一条 esptool 命令（--single）。

    这么做有风险：中途一旦断链，整条命令作废、后面的镜像一个都不写。留着它是因为
    连接稳定时它最快（一次连接写完）。日常用默认的分段模式。
    """
    command = [
        sets_build._idf_python(), "-m", "esptool",
        "--chip", CHIP,
        "-p", port,
        "-b", str(baud),
        "--before", plan.before,
        "--after", args.after,
        "write-flash",
        "--flash-mode", FLASH_MODE,
        "--flash-freq", FLASH_FREQ,
        "--flash-size", FLASH_SIZE,
    ]
    # 按地址升序写：app 先落盘，3.9MB 的 assets 垫底 —— 中途断了也更可能留下能启动的板子
    for offset, _name, path in sorted(targets, key=lambda item: item[0]):
        command += [hex(offset), str(path)]

    attempts = max(1, args.attempts) if plan.our_reset else 1
    detail = ""
    say("  " + " ".join(command))
    say("  烧录中，请勿拔线……")
    say(rule())
    for attempt in range(1, attempts + 1):
        if plan.our_reset:
            ok, evidence = enter_download_mode(port, plan.order)
            label = "反相" if plan.order == "reversed" else "标准"
            if ok:
                say(green(f"  已按{label}时序送进下载模式") + f"    {evidence}")
            elif evidence:
                notice_warn(f"送进下载模式未确认（{label}时序）：{evidence}")
            else:
                notice_warn(f"送进下载模式未确认（{label}时序）：复位后串口无输出")
        if attempt > 1:
            say(f"  重试 {attempt}/{attempts}……")
        # esptool 直接写继承来的控制台句柄；日志重定向到文件时先刷新，
        # 免得它的输出跑到我们前面去
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:  # pragma: no cover - 环境相关
            pass
        try:
            completed = subprocess.run(command, check=False, env=sets_build._idf_env_vars())
        except OSError as error:
            return False, f"无法启动 esptool: {error}", ""
        say(rule())
        if completed.returncode == 0:
            return True, "", ""
        detail = f"esptool 返回码 {completed.returncode}"
        if attempt < attempts:
            say()
            say(f"  第 {attempt} 次失败（{detail}），重新复位后再试一次……")
    return False, detail, ""


def _report_flash_failure(
    port: str, plan: ResetPlan, failed_name: str, detail: str
) -> int:
    """把「哪一段坏的」翻译成人话 —— 别再把写到一半掉线说成「连不上芯片」。"""
    say()
    if failed_name in ("bootloader.bin", "partition-table.bin"):
        notice_bad(f"烧录在最早的一段「{failed_name}」就失败了：{detail}")
        say("        已经试过：3 次探活 × 2 种复位线序 × 2~3 档波特率，都没连上。")
        say("        设备现在在干什么：")
        diagnose_after_failure(port)
        say("        人工排查顺序：")
        say("          1) 换一根短一点的 USB 数据线（很多线只有充电线芯，传数据必失败）；")
        say("          2) 关掉串口监视器 / 另一个烧录窗口（串口独占，被占用时连不上）；")
        say("          3) 手动进下载模式：按住 BOOT → 点一下 RST → 松开 BOOT，再 --reset none 重跑；")
        say("          4) 报 Invalid head of packet (0x49)：0x49 是字符 'I'（应用日志首字节），")
        say("             说明芯片在跑应用没进下载模式 —— 上面的 --reset none 就是解这个的。")
        return EXIT_ERROR

    notice_bad(f"写到「{failed_name}」时断链了：{detail}")
    say("        这不是「连不上芯片」—— 芯片是连上过的（连接前已探活），是传输中途断了。")
    if failed_name == "generated_assets.bin":
        say("        好消息：assets 是最后一段，bootloader / 分区表 / otadata / app 都已写好 ——")
        say("        设备已经能启动，缺的只是唤醒词 / 字库 / 表情。单独补这一段：")
        say(f"          python hardware/sets/flash.py --port {port} --chunk-size 512K")
        say("        要先把应用跑通、暂时不要资源，就加 --skip-assets 重烧一遍。")
    else:
        say("        前面几段已经写进芯片，重跑会逐段补写并校验：")
        say(f"          python hardware/sets/flash.py --port {port}")
        say("        还断就再往下退：")
        say(f"          python hardware/sets/flash.py --port {port} --baud 115200")
        say(f"          python hardware/sets/flash.py --port {port} --chunk-size 512K")
    say("        反复断更可能是供电不足：换 USB 口 / 拔掉外设 / 用带供电的 HUB，")
    say("        或把背光调暗——写 4MB 时电流冲击最大。")
    if plan.our_reset:
        say("        另外：这块板 EN/GPIO0 是反相接线，esptool 收尾那句")
        say("        「Hard resetting via RTS pin / No more data to read」是它把复位拉成了 GPIO0 造成的假故障，")
        say("        本脚本收尾已改成由自己复位（--after no-reset）。")
    diagnose_after_failure(port)
    return EXIT_ERROR


def _preflight(fw_root: Path) -> Optional[list[tuple[int, str, Path]]]:
    """烧录前闸门：build 里的写入地址必须与分区表同源。返回 None = 拒绝烧录。

    实机踩过的坑：分区表是 16MB 布局（ota_0@0x20000），app 却按 4MB 布局写到
    0x10000 —— bootloader 在 0x20000 找不到合法镜像（首字节不是 0xE9）就自杀重启，
    表现是「屏幕不亮 + 无限重启」，而且日志一句话都不打。
    """
    targets = parse_write_targets(fw_root)
    problems = check_layout_consistency(fw_root, targets)
    if problems:
        say()
        say(bold("[自检] 烧录地址与分区表对不上"))
        for problem in problems:
            say(f"        · {problem}")
        notice_bad("已阻止烧录：照这样写下去，app 会落在分区表不认识的地方，刷完必然起不来")
        say("        请确认 <FW>/build 里各项产物来自同一次编译（build.py 一次只编一个版型）。")
        return None
    say()
    say(bold("[自检] 烧录地址与分区表一致"))
    for offset, name, path in targets:
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        say(f"  0x{offset:<9x} {name:<26} {size:>9} 字节")
    return targets


def _post_flash_checks(
    fw_root: Path, port: str, plan: ResetPlan, baud: int,
    args: argparse.Namespace, targets: list[tuple[int, str, Path]],
) -> int:
    """烧录后两道闸：内容对不对（回读比对）→ 起没起来（复位读串口）。"""
    # ---- 烧录后校验：内容对不对 ----
    if not args.no_verify:
        mismatches = verify_written_regions(fw_root, port, plan, baud, targets)
        if mismatches:
            notice_bad("回读校验没通过：设备里的内容和本地产物不一样")
            for item in mismatches:
                say(f"        · {item}")
            say("        多半是写一半被打断了（拔线 / 复位 / 串口被抢）。整片重烧一次：")
            say(f"          python hardware/sets/flash.py --port {port} --clean")
            return EXIT_ERROR
        notice_ok("回读校验通过：设备内容与本地产物完全一致")

    # ---- 烧录后校验：起没起来 ----
    state = boot_check(port, plan, args.boot_check)
    if state == "loop":
        say("        设备在循环重启。最常见的原因是分区表与 app 不同源")
        say("        （例如分区表写的是 16MB 布局 ota_0@0x20000，而 app 落在 4MB 布局的 0x10000）——")
        say("        bootloader 在 ota_0 找不到合法镜像就自杀重启，屏幕自然一直不亮。")
        say("        排查：python hardware/sets/diag.py  （回读设备与产物逐字节比对）")
        say(f"        处置：python hardware/sets/flash.py --port {port} --clean  （整片擦除后全量重烧）")
        return EXIT_ERROR
    if state in ("silent", "download"):
        say("        设备没有进入应用。若确认写进去的内容一致，就该去看 bootloader 卡在哪：")
        say("        在 version/config.json 的 sdkconfig_append 里加 CONFIG_BOOTLOADER_LOG_LEVEL_INFO=y 重编，")
        say("        再烧一次就能看到它到底为什么退出。")
    say("  提示：可用 <FW>\\monitor.bat 或 <FW>\\yh_monitor.py 看串口日志。")
    return EXIT_OK


# ---------------------------------------------------------------------------
# 5c. idf.py 快速烧录（直接吃 build/ 里的 flash_args）
#
# 「用项目里的 build 目录烧录」就是让它读 build/flash_args：写哪些镜像、写到哪个
# 地址，全由这次编译的产物决定，脚本不再自己拼地址表 —— 少一层手写就少一处错。
#
# 但 idf.py 的 --before 是**编译期**从 sdkconfig 的 CONFIG_ESPTOOLPY_BEFORE 固化的，
# 命令行改不了（实测 `write-flash --before no-reset` 会被 esptool 拒绝：
# No such option '--before'），所以 EN/GPIO0 反相接线的板子没法直接用 idf.py flash：
# 它那次 default-reset 会把芯片留在应用态，必然报 Invalid head of packet (0x49)。
# 这种板子改用「同一份 flash_args + 一条 esptool 命令」，差别只有那一次复位。
# ---------------------------------------------------------------------------


def idf_script() -> Optional[Path]:
    """定位 <IDF_PATH>/tools/idf.py；找不到返回 None（不影响分段烧录）。"""
    resolved = sets_build.discover_idf_env()
    idf_path = resolved.get("idf_path")
    if not idf_path:
        return None
    script = Path(idf_path) / "tools" / "idf.py"
    return script if script.is_file() else None


def build_idf_command(
    script: Path, port: str, baud: int, build_name: str = "build", all_data: bool = False
) -> list[str]:
    """idf.py flash 的完整命令（端口 / 波特率 / 构建目录，其余交给 flash_args）。"""
    command = [
        sets_build._idf_python(), str(script),
        "-p", port,
        "-b", str(baud),
        "-B", build_name,
        "flash",
    ]
    if all_data:
        # --all 关掉 IDF 的快速重烧（只写与上次成功烧录不同的扇区），每次都全量写
        command.append("--all")
    return command


def _idf_env() -> dict[str, str]:
    """idf.py 的子进程环境：补齐 IDF 变量，并去掉 Git Bash 的 MSYSTEM。

    idf.py 见到 MSYSTEM 会打「MSys/Mingw is no longer supported」的警告；而本机
    在 Git Bash 下启动 idf.py 出现过「只打印提示就退出、退出码 0」的假成功，
    去掉这个变量最省事。真退出码不可信时，后面的回读校验会兜住。
    """
    env = sets_build._idf_env_vars()
    for key in ("MSYSTEM", "MSYS2_ENV_CONV_EXCL"):
        env.pop(key, None)
    env.setdefault("PYTHONUTF8", "1")
    return env


def _report_idf_failure(port: str, plan: ResetPlan, code: int) -> int:
    say()
    notice_bad(f"idf.py flash 失败（返回码 {code}）")
    say("        idf.py 的复位方式固化在 sdkconfig 的 CONFIG_ESPTOOLPY_BEFORE 里，命令行改不了：")
    say("        反相接线的板子（DTR=EN / RTS=GPIO0）在这一步必然报 Invalid head of packet (0x49)，")
    say("        因为它的 default-reset 会把芯片留在应用态、继续跑应用。换个方式重烧：")
    say(f"          python hardware/sets/flash.py --port {port} --mode staged")
    say("        分段模式会自己按正确时序把芯片送进下载模式，大镜像还会降速 + 切块重试。")
    diagnose_after_failure(port)
    return EXIT_ERROR


def run_idf_flash(fw_root: Path, port: str, baud: int, plan: ResetPlan, args: argparse.Namespace) -> int:
    """idf.py 快速烧录：一条命令写完 build/flash_args 里的全部镜像。

    标准接线的板子用真正的 `idf.py flash`（它还负责先跑一次增量编译）；
    反相接线或找不到 idf.py 时，退到等价的单会话 esptool 写入，并说明原因。
    """
    targets = _preflight(fw_root)
    if targets is None:
        return EXIT_ERROR

    if args.only or args.skip_assets:
        say()
        notice_warn("idf.py 快速烧录按 build/flash_args 写全部镜像：本次忽略 --only / --skip-assets")

    if args.clean:
        if erase_flash(port, plan, baud) != 0:
            notice_bad("整片擦除没成功，已中止（继续烧录只会留下半套内容）")
            return EXIT_ERROR

    script = idf_script()
    if script is not None and not plan.our_reset:
        command = build_idf_command(script, port, baud, all_data=args.idf_all)
        say()
        say(bold("[烧录] idf.py flash：用 build/flash_args 一次写完所有镜像"))
        say(f"  串口: {port}    波特率: {baud}")
        say("  idf.py 会先跑一次增量编译（产物没变时几秒），再交给 esptool 写入")
        say("  " + " ".join(command))
        say(rule())
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:  # pragma: no cover - 环境相关
            pass
        try:
            completed = subprocess.run(
                command, cwd=str(fw_root), env=_idf_env(), check=False
            )
        except OSError as error:
            notice_bad(f"无法启动 idf.py: {error}")
            return EXIT_ENV
        say(rule())
        if completed.returncode != 0:
            return _report_idf_failure(port, plan, completed.returncode)
        notice_ok(f"idf.py flash 完成（{port}）")
        return _post_flash_checks(fw_root, port, plan, baud, args, targets)

    # ---- 等价替代：同一份 flash_args，只换掉那次错误复位 ----
    say()
    say(bold("[烧录] idf.py 快速烧录（等价的单会话写法）"))
    if plan.our_reset:
        say("  这块板的复位线是反相接的：idf.py 的 --before 固化在 sdkconfig 里改不了，")
        say("  它那次复位会把芯片留在应用态（然后报 Invalid head of packet 0x49）。")
    else:
        say("  没找到 idf.py（IDF_PATH 未探测到）：用等价的 esptool 单会话写入。")
    say("  用的是同一份 build/flash_args、同一条 write-flash，只是复位由脚本负责。")

    ok, detail, failed_name = _write_all_at_once(fw_root, port, baud, plan, args, targets)
    if not ok:
        if failed_name:
            return _report_flash_failure(port, plan, failed_name, detail)
        notice_bad("烧录失败：" + (detail or "未知原因"))
        return EXIT_ERROR
    notice_ok(f"烧录完成（{port}）")
    return _post_flash_checks(fw_root, port, plan, baud, args, targets)


def run_flash(fw_root: Path, port: str, baud: int, plan: ResetPlan, args: argparse.Namespace) -> int:
    """分段烧录入口：默认逐段写（每段一个独立 esptool 会话），--single 退回一次性写。

    plan.our_reset=True 时，每段开始前都由本脚本把芯片送进下载模式。
    """
    command, cwd, mode_desc = build_flash_command(fw_root, port, baud, plan, args.after)
    if not command:
        notice_bad(mode_desc + "：请确认编译是否成功（先跑 build.py）")
        return EXIT_ERROR

    # ---- 烧录前自检：地址必须与分区表同源 ----
    targets = _preflight(fw_root)
    if targets is None:
        return EXIT_ERROR

    if args.skip_assets:
        targets = [item for item in targets if item[1] != "generated_assets.bin"]
        say()
        notice_warn("--skip-assets：本次不写 assets 分区（唤醒词 / 字库 / 表情沿用设备里已有的那份）")

    if args.only:
        selected, unknown = filter_targets(targets, args.only)
        if unknown:
            notice_bad(f"--only 里有不认识的镜像名：{'、'.join(unknown)}")
            say("        可用：bootloader / partition-table / otadata / app / assets")
            return EXIT_ERROR
        if not selected:
            notice_bad("--only 过滤之后没有剩下任何镜像")
            return EXIT_ERROR
        targets = selected
        say()
        notice_warn(f"--only {args.only}：只写 {len(targets)} 段（{', '.join(t[1] for t in targets)}）")

    say()
    if args.single:
        say(bold(f"[烧录] {mode_desc}"))
    else:
        say(bold("[烧录] 逐段写入：一个镜像一个 esptool 会话，某段断了只补这一段"))
    say(f"  串口: {port}    波特率: {baud}")
    say(f"  复位: {plan.note or f'--before {plan.before}'}")
    if not args.single:
        say("  每段写完都留在下载模式，全部写完后统一复位并检查启动")

    if args.clean:
        if erase_flash(port, plan, baud) != 0:
            notice_bad("整片擦除没成功，已中止（继续烧录只会留下半套内容）")
            return EXIT_ERROR

    # ---- 写：默认逐段，--single 一次性 ----
    if args.single:
        ok, detail, failed_name = _write_all_at_once(fw_root, port, baud, plan, args, targets)
    else:
        ok, detail, failed_name = run_staged_flash(
            port, plan, targets, baud, args.chunk_size, args.attempts
        )
    if not ok:
        if failed_name:
            return _report_flash_failure(port, plan, failed_name, detail)
        notice_bad("烧录失败：" + (detail or "未知原因"))
        return EXIT_ERROR

    notice_ok(f"烧录完成（{port}）")
    return _post_flash_checks(fw_root, port, plan, baud, args, targets)


# ---------------------------------------------------------------------------
# 6. 解释器自愈（pyserial 只在 IDF venv 里）
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


def _size_arg(text: str) -> int:
    """把 `512K` / `1M` / `1048576` 解析成字节数（切块参数用）。"""
    raw = text.strip().lower()
    multiplier = 1
    if raw.endswith("k"):
        multiplier, raw = 1024, raw[:-1]
    elif raw.endswith("m"):
        multiplier, raw = 1024 * 1024, raw[:-1]
    try:
        value = int(raw, 0) * multiplier
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"看不懂的大小：{text}") from error
    if value < 0x1000:
        raise argparse.ArgumentTypeError("切块至少 4KB（必须与 flash sector 对齐）")
    return value


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
            "  python hardware/sets/flash.py --manual           # 手动进下载模式（按住 BOOT + 点 RST）\n"
            "  python hardware/sets/flash.py --reset none -y    # 设备已手动进下载模式，不再复位\n"
            "  python hardware/sets/flash.py --port COM18 --clean   # 先整片擦除再全量重烧\n"
            "  python hardware/sets/flash.py --port COM18 --skip-assets  # 跳过 3.9MB assets，先确认 app 能起来\n"
            "  python hardware/sets/flash.py --port COM18 --baud 460800   # 想快点（默认 230400，稳优先）\n"
            "  python hardware/sets/flash.py --port COM18 --chunk-size 512K  # 大镜像还断就用更小的块\n"
            "  python hardware/sets/flash.py --port COM18 --mode idf   # 用 build/flash_args 一次写完（最省事）\n"
            "  python hardware/sets/flash.py --port COM18 --mode staged   # 强制走逐段加固流程\n"
            "  python hardware/sets/flash.py --port COM18 --mode diag   # 只回读体检，不写 flash\n"
            "\n"
            "烧录方式（--mode；交互式终端不给 --mode 时会弹菜单，回车 = 1）：\n"
            "  1) idf    —— 直接用项目里的 build 目录：读 build/flash_args 一次写完所有镜像。\n"
            "              标准接线时就是真的 idf.py flash；反相板（本项目的 1.54 寸板）改用等价的\n"
            "              单会话 esptool —— idf.py 的 --before 固化在 sdkconfig 里改不了，\n"
            "              它那次复位会把芯片留在应用态（Invalid head of packet 0x49）。\n"
            "  2) staged —— 逐段写 + 切块 + 双端校验（默认；链路不稳时用）。\n"
            "  d) diag   —— 只回读比对，不改 flash。\n"
            "\n"
            "默认**逐段写入**：一个镜像一个 esptool 会话（bootloader → 分区表 → otadata → app → assets），\n"
            "每段写之前先 flash-id 探活（约 1.8 秒）：失败重试 3 次 → 降速 → 换复位线序，全做完才报错。\n"
            "大镜像再按 1MB 切块（app 3 块、assets 4 块），崩一次只重写这 1MB，不用从头再来。\n"
            "assets 排在最后：它断了设备照样能启动，只是没字库 / 唤醒词。\n"
            "（--single 可退回「一次会话写完所有镜像」的旧行为。）\n"
            "\n"
            "烧录前后各有一道闸（默认开启，--no-verify 可关）：\n"
            "  · 烧录前：核对 build 产物地址与分区表是否同源，不同源直接拒烧\n"
            "    （app 与分区表布局不一致时，刷完一定是「屏幕不亮 + 无限重启」）；\n"
            "  · 烧录后：回读逐字节比对，再复位读串口，明确告诉你「已启动 / 在循环重启」。\n"
            "  板子里是别的固件、或分区表被外来固件改过时，加 --clean 先整片擦除。\n"
            "\n"
            "复位线序（--reset，默认 auto）：本项目部分板子的 EN/GPIO0 是反相接线\n"
            "（DTR=EN、RTS=GPIO0），esptool 的 default-reset 对它们无效，会报\n"
            "\"Invalid head of packet (0x49)\"（0x49 就是应用日志首字节 'I'）。\n"
            "auto 会先复位探测线序：反相板由脚本送进下载模式 + esptool --before no-reset；\n"
            "标准板维持原样交给 esptool。可用 --reset {auto,esptool,reversed,none} 或\n"
            "--before 手动指定。\n"
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
                        help=f"烧录波特率，默认 {BAUD_DEFAULT}；连不上时可降到 115200 排查")
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

    reset_group = parser.add_argument_group("复位 / 下载模式")
    reset_group.add_argument(
        "--reset", choices=("auto", "esptool", "reversed", "none"), default="auto",
        help="烧录前如何让芯片进下载模式：auto=先识别线序（默认）；esptool=完全交给 esptool "
             "的 default-reset（标准接线）；reversed=按镜像时序（DTR=EN/RTS=GPIO0）由脚本送进下载模式；"
             "none=不复位直接连接（设备已手动进下载模式）",
    )
    reset_group.add_argument(
        "--manual", action="store_true",
        help="打印手动进下载模式的步骤并等待回车，随后按 --reset none 连接（适配器无法控制 DTR/RTS 时用）",
    )
    reset_group.add_argument(
        "--before", metavar="MODE",
        help="直接指定 esptool 的 --before（default-reset/usb-reset/no-reset/no-reset-no-sync），"
             "覆盖 --reset 的自动判断",
    )
    reset_group.add_argument(
        "--after", choices=("auto", "hard-reset", "soft-reset", "no-reset", "no-reset-stub", "watchdog-reset"),
        default="auto",
        help="烧录完成后 esptool 的 --after，默认 auto：反相板用 no-reset（esptool 的 "
             "hard-reset 在反相板上拉的是 GPIO0，只会换来一句 No more data to read），"
             "标准板用 hard-reset",
    )
    reset_group.add_argument(
        "--attempts", type=int, default=CONNECT_TRIES, metavar="N",
        help=f"每段连接的探活次数，默认 {CONNECT_TRIES}；用完就降速再来一轮（仍未成会换复位线序）",
    )

    write_group = parser.add_argument_group("写入方式")
    write_group.add_argument(
        "--single", action="store_true",
        help="一次性写完所有镜像（默认是逐段写：一个镜像一个会话，断了只补那一段）",
    )
    write_group.add_argument(
        "--skip-assets", action="store_true",
        help="不写 assets 分区（3.9MB，唤醒词 / 字库 / 表情）。排查启动问题时用它跳过最慢的一段",
    )
    write_group.add_argument(
        "--only", metavar="NAME",
        help="只写指定镜像（逗号分隔）。可用名：bootloader / partition-table / otadata / app / assets，"
             "例：--only assets 只补写资源分区，不碰前面的镜像",
    )
    write_group.add_argument(
        "--chunk-size", type=_size_arg, default=CHUNK_SIZE_DEFAULT, metavar="BYTES",
        help=f"大镜像切块大小，默认 {CHUNK_SIZE_DEFAULT // 1024}KB（可写 512K / 1M）；"
             "单次传输越短越不容易中途断链，断了也只重写这一块",
    )
    write_group.add_argument(
        "--no-chunk", action="store_true",
        help="关掉切块（大镜像整段写）。只在链路非常稳、想省连接开销时用",
    )
    write_group.add_argument(
        "--idf-all", action="store_true",
        help="idf 模式强制全量写（idf.py flash --all）：关掉 IDF 的快速重烧（只写变化扇区）",
    )

    verify_group = parser.add_argument_group("校验 / 清空")
    verify_group.add_argument(
        "--clean", action="store_true",
        help="烧录前先整片擦除 flash（erase-flash）：板子里是别的固件、或分区布局混用时用",
    )
    verify_group.add_argument(
        "--no-verify", action="store_true",
        help="跳过烧录后的回读比对与启动检查（默认都做）",
    )
    verify_group.add_argument(
        "--boot-check", type=float, default=BOOT_CHECK_SECONDS, metavar="SEC",
        help=f"烧完复位并读串口的时长（秒），默认 {BOOT_CHECK_SECONDS:.0f}；0 = 不做启动检查",
    )

    parser.add_argument("-y", "--yes", action="store_true",
                        help="跳过烧录确认（物理操作，默认要确认）；同时不再弹方式选择菜单")
    parser.add_argument(
        "--mode", choices=(METHOD_IDF, METHOD_STAGED, METHOD_DIAG), default=None,
        help="烧录方式：idf=直接用 build/flash_args 一次写完（最省事）；"
             "staged=逐段写 + 切块 + 双端校验（默认，链路不稳时用）；"
             "diag=只回读体检、不写 flash。不指定且是交互式终端时会让你选",
    )
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
    if args.attempts < 1:
        parser.error("--attempts 至少为 1")
    if args.timeout <= 0:
        parser.error("--timeout 必须大于 0")
    if args.no_chunk:
        args.chunk_size = 0
    elif args.chunk_size % 0x1000:
        # 必须与 4KB sector 对齐，否则相邻块擦除时会互相吃掉尾巴
        args.chunk_size -= args.chunk_size % 0x1000
    return args


METHOD_LABEL = {
    METHOD_IDF: "idf.py 快速烧录",
    METHOD_STAGED: "分段加固烧录",
    METHOD_DIAG: "只体检不烧录",
}


def ask_method() -> Optional[str]:
    """交互式选择烧录方式；返回 None = 用户取消。

    stdin 不是终端时（脚本 / 管道 / 重定向）不提问，直接返回默认方式，
    免得自动化流程卡在 input() 上。
    """
    if not sys.stdin.isatty():
        return DEFAULT_MODE
    say()
    say(bold("请选择烧录方式（直接回车 = 1）："))
    say("  1) idf.py 快速烧录   —— 直接用 build/flash_args 一次写完，最省事")
    say("  2) 分段加固烧录      —— 逐段写 + 1MB 切块 + 双端校验，链路不稳时用")
    say("  d) 只体检不烧录      —— 回读设备内容与产物逐字节比对（不改 flash）")
    while True:
        try:
            raw = input("  选择 [1/2/d] > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            say()
            return None
        if raw in ("", "1", "i", "idf"):
            return METHOD_IDF
        if raw in ("2", "s", "staged"):
            return METHOD_STAGED
        if raw in ("d", "diag", "0"):
            return METHOD_DIAG
        notice_warn("请输入 1、2 或 d")


def run_diag(port: str, board: Optional[dict[str, Any]], fw_root: Path) -> int:
    """走 diag.py 做只读体检（不改 flash）。"""
    script = Path(__file__).resolve().parent / "diag.py"
    if not script.is_file():
        notice_bad("找不到 diag.py（只读体检工具），已跳过")
        return EXIT_ENV
    command = [sets_build._idf_python(), str(script), "--port", port, "--fw-root", str(fw_root)]
    if board:
        command += ["--board", board["id"]]
    say()
    say(bold("[体检] 回读设备内容与 build 产物逐字节比对（只读，不写 flash）"))
    say("  " + " ".join(command))
    say(rule())
    try:
        completed = subprocess.run(command, check=False, env=_idf_env())
    except OSError as error:
        notice_bad(f"无法启动 diag.py: {error}")
        return EXIT_ENV
    return completed.returncode


def _ask_flash(port: str, board: Optional[dict[str, Any]], method: str = "") -> bool:
    if not sys.stdin.isatty():
        notice_bad("非交互式终端，请加 --yes 明确确认后重试")
        return False
    target = f"「{board['name']}」的产物" if board else "当前 build 产物"
    label = METHOD_LABEL.get(method)
    via = f"用{label}" if label else "烧录"
    say()
    try:
        raw = input(f"是否{via}把 {target} 写到 {port}？[y/N] ").strip().lower()
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
            show_build_server_env(fw_root)
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

    # ---- 4. 选烧录方式（--mode 指定 / -y 或非交互式走默认，否则菜单）----
    method = args.mode
    if method is None:
        method = DEFAULT_MODE if args.yes else ask_method()
        if method is None:
            say("已取消。")
            return EXIT_OK
    if method == METHOD_DIAG:
        return run_diag(selected, board, fw_root)

    # ---- 5. 确认并烧录 ----
    python = sets_build._idf_python()
    if not _esptool_ok(python):
        notice_bad(f"所用解释器里没有 esptool: {python}")
        say("        请用 --python 指定 IDF venv 的 python（esptool 随它一起安装）。")
        return EXIT_ENV

    if not args.yes and not _ask_flash(selected, board, method):
        say("已取消烧录。")
        return EXIT_OK

    # ---- 6. 决定复位方式（反相板由脚本送进下载模式）----
    plan = resolve_reset_plan(selected, args)
    # --after auto：反相板上 esptool 的 hard-reset 实际拉的是 GPIO0（不是 EN），
    # 收尾必然报 "No more data to read from the serial port"；这种板子改用 no-reset，
    # 写完由脚本自己按正确时序复位。
    if args.after == "auto":
        args.after = "no-reset" if plan.our_reset else "hard-reset"
    if method == METHOD_IDF:
        return run_idf_flash(fw_root, selected, args.baud, plan, args)
    return run_flash(fw_root, selected, args.baud, plan, args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        say("")
        notice_bad("已被用户中断 (Ctrl+C)")
        sys.exit(130)
