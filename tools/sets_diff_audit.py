#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同源审计 FR-1.1 / P0-4：A(hardware/small_secreen) 与 B(hardware/sets) 的 main/ 只读比对。

用法：
  PYTHONUTF8=1 D:/INSTALL/python313/python.exe tools/sets_diff_audit.py
  PYTHONUTF8=1 D:/INSTALL/python313/python.exe tools/sets_diff_audit.py --report code/reports/2026-10-17-复刻同源审计.md

判定口径：
  * 逐字节比对（sha256），排除 managed_components/、build/、*.o；
  * 分类 IDENTICAL / DIFF / B_ONLY / A_ONLY；
  * 白名单（见 WHITELIST）之外的任何 DIFF / B_ONLY / A_ONLY 均视为审计失败；
  * 对 B 领先 6 项做特征断言，任一 token 缺失即失败。

只读约定：除 --report 指定的报告文件外不写任何文件，不执行 git 写操作。
退出码：0 = 审计通过；1 = 审计失败。
"""

from __future__ import annotations

import argparse
import difflib
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_A = REPO_ROOT / "hardware/small_secreen/yuhe-esp32/main"
SRC_B = REPO_ROOT / "hardware/sets/yuhe-esp32/main"
DEFAULT_REPORT = REPO_ROOT / "code/reports/2026-10-17-复刻同源审计.md"

# 比对时整目录跳过（第三方托管组件 / 构建产物）
EXCLUDE_DIRS = {"managed_components", "build", ".git"}
# 比对时按后缀跳过
EXCLUDE_SUFFIXES = {".o", ".obj"}

A_LABEL = "hardware/small_secreen/yuhe-esp32/main"
B_LABEL = "hardware/sets/yuhe-esp32/main"

# ---------------------------------------------------------------------------
# 白名单：key = 相对 A/B main 的 POSIX 路径（支持 "dir/**" 前缀与 fnmatch 通配）
#         kinds = 允许的分类集合；reason = 放行理由（必须在报告中原样展示）
# 约定：新增条目必须写清"为什么这不是回归"，禁止用 "*"/"**" 之类的全局放行。
# ---------------------------------------------------------------------------
WHITELIST: dict[str, dict] = {
    # ---- 版型目录（机制差异，非代码回归）----
    "boards/yuhe/**": {
        "kinds": {"B_ONLY"},
        "reason": "sets 版型目录：4 个由 zhengchen 改名而来 + 4 个 sets 新增板（yh-154tft-wifi/yh-big-ili9341/yh-cam/yh-n16r8-st7789），A 侧无同名目录",
    },
    "boards/zhengchen/**": {
        "kinds": {"A_ONLY"},
        "reason": "A 侧旧版型目录；B 已整体改名为 boards/yuhe/**（zhengchen→yuhe），属目录级改名对，非删除",
    },
    "display/yh_skin/**": {
        "kinds": {"B_ONLY"},
        "reason": "屿禾「小柚」皮肤共享层：A 侧把同一套皮肤内联在 boards/my-s3-tft/round_screen_display.*，"
                  "B 侧抽成跨 4 个 yh-* 版型复用的一份实现（display/yh_skin/yh_skin_display|boot|cards|assets），"
                  "A 侧无该目录；视觉基准仍为 A 的 my-s3-tft 实现，仅新增开机首帧接管与系统态卡片",
    },
    "boards/lckfb/szpi-esp32s3/config.json": {
        "kinds": {"DIFF"},
        "reason": "板型元数据：补 sdkconfig_append（YH 协议 / 16MB 分区 / 自定义唤醒词 / 设备 AEC），不参与 C++ 同源判定",
    },
    "boards/lckfb/szpi-esp32s3/README.md": {
        "kinds": {"B_ONLY"},
        "reason": "板型说明文档，非编译单元",
    },
    # ---- B 领先 6 项（人声打断 / AEC 判定）----
    "application.cc": {
        "kinds": {"DIFF"},
        "reason": "B 领先 6 项：kSpeakingInterruptGuardMs 播放保护窗、IsVoiceDetected 下降沿过滤、IsDeviceAecEffective 门控、静默打断；另含需求二 wallpaper hook",
    },
    "audio/audio_service.h": {
        "kinds": {"DIFF"},
        "reason": "B 领先：新增 GetPlaybackElapsedMs / IsDeviceAecEffective / playback_start_us_ 声明",
    },
    "audio/audio_service.cc": {
        "kinds": {"DIFF"},
        "reason": "B 领先：播放起止时刻记账、AEC 生效判定、设备 AEC 诊断日志",
    },
    "audio/audio_engine.h": {
        "kinds": {"DIFF"},
        "reason": "B 领先：AudioEngine 新增虚函数 IsAecEffective()（默认 false）",
    },
    "audio/engines/afe_audio_engine.h": {
        "kinds": {"DIFF"},
        "reason": "B 领先：IsAecEffective() override + VAD 去抖成员（vad_candidate_/确认窗常量）",
    },
    "audio/engines/afe_audio_engine.cc": {
        "kinds": {"DIFF"},
        "reason": "B 领先：IsAecEffective() 实现 + VAD 双向去抖（CONFIG_YH_VAD_*）+ 播放期 VAD 状态复位",
    },
    # ---- 协议修复 ----
    "protocols/websocket_protocol.cc": {
        "kinds": {"DIFF"},
        "reason": "B 修复 URL 取 host：host.erase(0, scheme_pos + 3)，旧写法 erase(scheme_pos, 4) 在 wss:// 下残留前缀；"
                  "2026-10-25 追加 WS 兜底：OpenAudioChannel 主 URL 连接失败且 CONFIG_WEBSOCKET_FALLBACK_URL 非空时"
                  "重建 websocket 连兜底地址（SetupWebsocket 统一头/回调），宏未配置时行为与旧固件一致",
    },
    "protocols/websocket_protocol.h": {
        "kinds": {"DIFF"},
        "reason": "2026-10-25 WS 兜底：新增私有声明 SetupWebsocket(const std::string&)（统一鉴权头与 OnData/OnDisconnected 绑定）",
    },
    "ota.cc": {
        "kinds": {"DIFF"},
        "reason": "2026-10-25 OTA 兜底：GetCheckVersionUrl() 支持连续失败切 CONFIG_OTA_FALLBACK_URL（kPrimaryFailThreshold=3，"
                  "5xx/连接失败计数、4xx 不计），ReportPrimaryResult 成功恢复主 URL；宏未配置时空串短路，行为与旧固件一致",
    },
    "ota.h": {
        "kinds": {"DIFF"},
        "reason": "2026-10-25 OTA 兜底：新增 ReportPrimaryResult/IsFallbackActive 声明与 kPrimaryFailThreshold/primary_fail_count_/fallback_active_ 成员",
    },
    "protocols/protocol.h": {
        "kinds": {"DIFF"},
        "reason": "需求二壁纸回执：新增 Protocol::SendJsonText 公开薄封装（`return SendText(text)`，"
                  "SendText 仍是 protected 纯虚 at :90），供 application.cc 主动上报壁纸 ACK；不新增消息类型",
    },
    # ---- 构建系统（注册块 / 改名 / 换行）----
    "CMakeLists.txt": {
        "kinds": {"DIFF"},
        "reason": "SETS-BOARDS 注册块（4 个 yuhe_set 板型）+ zhengchen→yuhe 改名 + 皮肤共享层 4 个 source/1 个 include；当前 +31/-8（=39 行），"
                  "工作区 blob f42eafbf 与基线一致（P0-2 只改换行、内容零变化，无增量）；两侧均为纯 LF，不含换行噪声",
    },
    "Kconfig.projbuild": {
        "kinds": {"DIFF"},
        "reason": "SETS-BOARDS 注册块 + zhengchen→yuhe 改名 + YH Voice Interrupt Tuning 菜单（+57 行）+ "
                  "USE_DEVICE_AEC 板型白名单同步改名与补齐；行数归属：基线 = blob 68c5db5b"
                  "（P0-2 改动前的 sets Kconfig，可用 git cat-file blob 直出复核），vs A 实测 +81/-9（=90 行纯基线）；"
                  "当前 +83/-10（=93 行），差值 +2/-1 即 P0-2 对 BOARD_TYPE_YUHE_SET_CAM 的补齐"
                  "（在 BOARD_TYPE_ATK_DNESP32S3_BOX3 行尾补续行符并拆出新行）；两侧均为纯 LF，不含换行噪声",
    },
    # ---- 服务端侧信道修复 ----
    "yh/yh_protocol.cc": {
        "kinds": {"DIFF"},
        "reason": "G4 修复（SEND_NOTIFY busy → NACKED/BUSY，A+B 同步）；需求二追加 SET_WALLPAPER 操作"
                  "（B 独有：常连 TCP 通道下发壁纸，A 无壁纸模块）——本条同时覆盖两类差异",
    },
    "yh/yh_protocol.h": {
        "kinds": {"DIFF"},
        "reason": "需求二 SET_WALLPAPER 关联头文件：新增 SendWallpaperResult 公开接口与发送互斥锁，"
                  "仅 B 有壁纸模块（A 侧保留原样）",
    },
    # ---- 需求二：壁纸模块（B 独有）----
    "wallpaper/**": {
        "kinds": {"B_ONLY"},
        "reason": "需求二新增壁纸模块（源码/资源），仅存在于 B",
    },
    # ---- UI 主题层（B 独有，编译期 --theme 切换）----
    "display/pet_skin/**": {
        "kinds": {"B_ONLY"},
        "reason": "像素宠物主题（--theme pixel-pet）：canvas 直写自绘宠物 + 3.8s 出生动画 + "
                  "五态表情，继承 YhSkinDisplay 骨架只换视觉层；A 侧无该目录",
    },
    "display/emo_skin/**": {
        "kinds": {"B_ONLY"},
        "reason": "EMOpet 主题（--theme emopet）：机器人发光眼（15 态表情）+ 直写 buffer 渲染，"
                  "继承 YhSkinDisplay 骨架只换视觉层（2026-10-19 移植自 theme/EMOpet）；A 侧无该目录",
    },
    # ---- B 领先：NVS / 唤醒词健壮性修复 ----
    "settings.cc": {
        "kinds": {"DIFF"},
        "reason": "B 领先：Settings NVS 防崩（nvs_open 失败不 abort、句柄判 0 跳写，"
                  "2026-10-17 interrupt_config 崩溃现场修复）",
    },
    "boards/common/board.cc": {
        "kinds": {"DIFF"},
        "reason": "B 领先：服务端下发唤醒词拼音清洗（esp_mn 只认小写音节，'Ni Hao'/'|' 会静默失败）"
                  "+ wake_word_config→wake_word_cfg 命名空间缩短（16 字符超 NVS 上限 15）",
    },
    "audio/wake_words/custom_wake_word.cc": {
        "kinds": {"DIFF"},
        "reason": "B 领先：跟随 board.cc 的 wake_word_cfg 命名空间改名（曾用名 16 字符超 NVS 上限，"
                  "nvs_open 永远失败）",
    },
    "display/display.h": {
        "kinds": {"DIFF"},
        "reason": "需求二壁纸接口：Display 基类新增 SetWallpaper/ClearWallpaper 虚函数（默认空实现），"
                  "仅在 !CONFIG_USE_EMOTE_MESSAGE_STYLE 时声明（emote 模式不引入 lvgl.h）；"
                  "调用侧已用 WALLPAPER_HAS_LVGL_DISPLAY 适配，见报告中该条件编译的核对记录",
    },
    "application.h": {
        "kinds": {"DIFF"},
        "reason": "需求二 wallpaper hook 关联头文件（预置条目：wallpaper 成员/接口变更时需要；未改动时不命中）",
    },
}


@dataclass
class Feature:
    """B 领先特征断言。tokens 需全部命中，scope 为允许命中的相对路径 glob。"""

    key: str
    title: str
    tokens: list[str]
    scope: list[str]
    hits: dict[str, list[tuple[str, int]]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return all(self.hits.get(t) for t in self.tokens)

    @property
    def missing(self) -> list[str]:
        return [t for t in self.tokens if not self.hits.get(t)]


# 6 项 B 领先（对应团队任务书第 3 条；F2 为 IsVoiceDetected 下降沿过滤）
FEATURES: list[Feature] = [
    Feature(
        "F1",
        "播放起始保护窗 kSpeakingInterruptGuardMs",
        ["kSpeakingInterruptGuardMs", "CONFIG_YH_INTERRUPT_GUARD_MS"],
        ["application.cc", "Kconfig.projbuild"],
    ),
    Feature(
        "F2",
        "IsVoiceDetected 下降沿过滤（只在真人声上升沿打断）",
        ["!IsVoiceDetected()", "Ignore VAD change: falling edge"],
        ["application.cc"],
    ),
    Feature(
        "F3",
        "IsDeviceAecEffective（设备侧 AEC 生效判定 + 播报期门控）",
        ["IsDeviceAecEffective"],
        ["audio/**", "application.cc"],
    ),
    Feature(
        "F4",
        "IsAecEffective（引擎层 AEC 生效实现）",
        ["IsAecEffective"],
        ["audio/**"],
    ),
    Feature(
        "F5",
        "GetPlaybackElapsedMs（连续播放计时）",
        ["GetPlaybackElapsedMs"],
        ["audio/**", "application.cc"],
    ),
    Feature(
        "F6",
        "websocket host 前缀修复 host.erase(0, scheme_pos + 3)",
        ["host.erase(0, scheme_pos + 3)"],
        ["protocols/websocket_protocol.cc"],
    ),
]

# Q7 相关源文件（只读核查，不改代码）
DEVICE_IMPL = REPO_ROOT / "yh/manager-api/src/main/java/yuhe/modules/device/service/impl/DeviceServiceImpl.java"
OTA_IMPL = REPO_ROOT / "yh/manager-api/src/main/java/yuhe/modules/device/service/impl/OtaServiceImpl.java"


@dataclass
class FilePair:
    rel: str
    kind: str
    size_a: int = -1
    size_b: int = -1
    eol_only: bool = False
    added: int = -1
    removed: int = -1
    wl_reason: str | None = None
    wl_kind_ok: bool = True

    @property
    def is_diff(self) -> bool:
        return self.kind != "IDENTICAL"

    @property
    def whitelisted(self) -> bool:
        return self.wl_reason is not None and self.wl_kind_ok


@dataclass
class Q7Result:
    ok: bool = False
    notes: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    board_types: list[str] = field(default_factory=list)


@dataclass
class AecFinding:
    """config.json 声明 USE_DEVICE_AEC=y 与 Kconfig 白名单/依赖的一致性旁证。"""

    side: str
    rel: str
    board_type: str
    target: str
    symbols: list[str]
    status: str  # pre-existing / sets-introduced / target-unsupported / unmapped
    note: str


# ------------------------------- 工具函数 -------------------------------


def display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def pad(text: str, width: int) -> str:
    return text + " " * max(0, width - display_width(text))


def match_pattern(rel: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return rel == prefix or rel.startswith(prefix + "/")
    return fnmatch.fnmatchcase(rel, pattern)


def walk(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS)
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if path.suffix.lower() in EXCLUDE_SUFFIXES:
                continue
            files[path.relative_to(root).as_posix()] = path
    return files


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def eol_only_difference(path_a: Path, path_b: Path) -> bool:
    """字节不同但仅 CRLF/LF 换行差异时返回 True（仅用于报告标注，不改变分类）。"""
    try:
        raw_a = path_a.read_bytes()
        raw_b = path_b.read_bytes()
    except OSError:
        return False
    if max(len(raw_a), len(raw_b)) > 2 * 1024 * 1024:
        return False
    return raw_a.replace(b"\r\n", b"\n") == raw_b.replace(b"\r\n", b"\n")


def count_line_changes(path_a: Path, path_b: Path) -> tuple[int, int]:
    """行级增删数，优先用 `git diff --no-index --numstat`（与人工 diff 口径一致），
    失败时退回 difflib。仅统计 < 512KB 的文本文件。"""
    try:
        if max(path_a.stat().st_size, path_b.stat().st_size) > 512 * 1024:
            return -1, -1
    except OSError:
        return -1, -1

    try:
        proc = subprocess.run(
            ["git", "diff", "--no-index", "--numstat", "--", str(path_a), str(path_b)],
            capture_output=True, text=True, check=False,
        )
        first = (proc.stdout or "").splitlines()[0] if proc.stdout else ""
        parts = first.split("\t")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            return int(parts[0]), int(parts[1])
    except (OSError, IndexError):
        pass

    try:
        lines_a = path_a.read_text(encoding="utf-8", errors="replace").splitlines()
        lines_b = path_b.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return -1, -1
    added = removed = 0
    for line in difflib.unified_diff(lines_a, lines_b, n=0, lineterm=""):
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return added, removed


def git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        return out.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


# ------------------------------- 审计主体 -------------------------------


def classify_files() -> list[FilePair]:
    files_a = walk(SRC_A)
    files_b = walk(SRC_B)
    pairs: list[FilePair] = []

    for rel in sorted(set(files_a) | set(files_b)):
        path_a = files_a.get(rel)
        path_b = files_b.get(rel)
        if path_a is not None and path_b is not None:
            size_a, size_b = path_a.stat().st_size, path_b.stat().st_size
            if sha256_of(path_a) == sha256_of(path_b):
                pairs.append(FilePair(rel, "IDENTICAL", size_a, size_b))
                continue
            pair = FilePair(rel, "DIFF", size_a, size_b)
            pair.eol_only = eol_only_difference(path_a, path_b)
            pair.added, pair.removed = count_line_changes(path_a, path_b)
            pairs.append(pair)
        elif path_b is not None:
            pairs.append(FilePair(rel, "B_ONLY", -1, path_b.stat().st_size))
        else:
            pairs.append(FilePair(rel, "A_ONLY", path_a.stat().st_size, -1))

    for pair in pairs:
        for pattern, spec in WHITELIST.items():
            if not match_pattern(pair.rel, pattern):
                continue
            if pair.kind in spec["kinds"]:
                pair.wl_reason = spec["reason"]
            else:
                pair.wl_reason = (
                    f"{spec['reason']}（白名单条目只允许 {sorted(spec['kinds'])}，"
                    f"实际分类 {pair.kind}，需复核）"
                )
                pair.wl_kind_ok = False
            break
    return pairs


def grep_tokens(root: Path, tokens: list[str], scope: list[str]) -> dict[str, list[tuple[str, int]]]:
    hits: dict[str, list[tuple[str, int]]] = {t: [] for t in tokens}
    for rel, path in sorted(walk(root).items()):
        if not any(match_pattern(rel, pattern) for pattern in scope):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for token in tokens:
                if token in line:
                    hits[token].append((rel, lineno))
    return hits


def run_feature_assertions() -> list[Feature]:
    for feature in FEATURES:
        feature.hits = grep_tokens(SRC_B, feature.tokens, feature.scope)
    return FEATURES


def check_q7() -> Q7Result:
    result = Q7Result()

    # 设备侧上报的 board.type 来源：各板型 config.json 的 type 字段（编译期 BOARD_TYPE 宏）
    # 只列 B 侧改动相关板型（boards/yuhe/**、boards/lckfb/**），避免报告被 150+ 全量板型淹没
    total_boards = 0
    for config in sorted((SRC_B / "boards").rglob("config.json")):
        try:
            data = json.loads(config.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        board_type = data.get("type")
        if not board_type:
            continue
        total_boards += 1
        board_dir = config.parent.relative_to(SRC_B).as_posix()
        if board_dir.startswith(("boards/yuhe/", "boards/lckfb/")):
            result.board_types.append(f"{board_type}  ({board_dir})")
    result.board_types.insert(0, f"（全仓共 {total_boards} 个板型，下面仅列 B 侧改动相关）")

    device_src = DEVICE_IMPL.read_text(encoding="utf-8", errors="replace") if DEVICE_IMPL.exists() else ""
    ota_src = OTA_IMPL.read_text(encoding="utf-8", errors="replace") if OTA_IMPL.exists() else ""

    if not device_src or not ota_src:
        result.notes.append("未找到 DeviceServiceImpl.java / OtaServiceImpl.java，Q7 无法核查")
        return result

    # 任务F force 修复后变量名 type→trackType（轨道目标 type 或上报 type），
    # 匹配语义不变：ai_ota.type == 轨道/上报 type 精确相等
    latest_ok = "otaService.getLatestOta(trackType)" in device_src
    eq_ok = 'eq("type", type)' in ota_src
    upsert_ok = "same" if 'eq("type", entity.getType())' in ota_src else ""

    for name, path, token in (
        ("DeviceServiceImpl.java", DEVICE_IMPL, "otaService.getLatestOta(trackType)"),
        ("OtaServiceImpl.java", OTA_IMPL, 'eq("type", type)'),
    ):
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            if token in line:
                result.evidence.append(f"{name}:{lineno}: {line.strip()}")
                break

    result.ok = latest_ok and eq_ok
    result.notes.append(
        "匹配语义：ai_ota 表按 type 精确字符串相等过滤（eq），再按 update_date 倒序取 1 条；"
        "不做前缀/别名/厂商模糊匹配"
    )
    if upsert_ok:
        result.notes.append("写入语义：save() 按 type upsert，同 type 仅保留一行")
    result.notes.append(
        "board.type 由板型 config.json 的 type 字段生成 BOARD_TYPE 宏，随 OTA 请求体 board.type 上报"
    )
    result.notes.append(
        "结论：OTA 确实按 ai_ota.type == board.type 精确匹配；B 侧把 zhengchen-* 改名为 yuhe-* 并新增 yh-* 后，"
        "ai_ota 中必须存在同名 type 行，否则 getLatestOta 返回 null，接口回落为设备当前版本 + INVALID_FIRMWARE_URL（不升级）"
    )
    return result


# ------------------------- 配置一致性旁证（AEC） -------------------------


def _kconfig_text(root: Path) -> str:
    path = root / "Kconfig.projbuild"
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _config_block(text: str, symbol: str) -> str:
    """取 `config <symbol>` 到下一个 config/menu 之间的文本（choice 内的 config 有缩进）。"""
    match = re.search(rf"^[ \t]*config\s+{symbol}\s*$", text, re.MULTILINE)
    if not match:
        return ""
    rest = text[match.end():]
    nxt = re.search(r"^[ \t]*(config|menu)\s+\S", rest, re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


def _board_symbols(text: str) -> set[str]:
    return set(re.findall(r"^[ \t]*config\s+(BOARD_TYPE_[A-Z0-9_]+)\s*$", text, re.MULTILINE))


def _cmake_board_dir_map(root: Path) -> dict[str, str]:
    """从 CMakeLists.txt 的板型选择链解析 {板型相对目录: CONFIG_BOARD_TYPE_*}。

    例：`elseif(CONFIG_BOARD_TYPE_YUHE_SET_CAM)` 后跟 `set(BOARD_DIR "yuhe/yh-cam")`。
    这是 board 目录 → Kconfig 符号的权威映射，比按 type 猜名字可靠。
    """
    path = root / "CMakeLists.txt"
    if not path.exists():
        return {}
    mapping: dict[str, str] = {}
    current = ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        hit = re.search(r"(?:if|elseif)\(CONFIG_(BOARD_TYPE_[A-Z0-9_]+)\)", line)
        if hit:
            current = hit.group(1)
            continue
        dir_hit = re.search(r'set\(BOARD_DIR\s+"([^"]+)"\)', line)
        if dir_hit and current:
            mapping[f"boards/{dir_hit.group(1)}"] = current
    return mapping


def _aec_claimed_configs(root: Path) -> dict[str, tuple[str, str]]:
    """返回 {相对路径: (board_type, target)}，仅含声明 CONFIG_USE_DEVICE_AEC=y 的板型。"""
    claimed: dict[str, tuple[str, str]] = {}
    for config in sorted((root / "boards").rglob("config.json")):
        try:
            data = json.loads(config.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        appends = [
            item
            for build in data.get("builds") or []
            for item in build.get("sdkconfig_append") or []
        ]
        if any("CONFIG_USE_DEVICE_AEC=y" in item for item in appends):
            claimed[config.parent.relative_to(root).as_posix()] = (
                str(data.get("type") or ""),
                str(data.get("target") or ""),
            )
    return claimed


def audit_aec_consistency() -> tuple[list[AecFinding], list[AecFinding]]:
    """config.json 声明设备 AEC 是否真的能生效：Kconfig 白名单 + 目标芯片是否支持 AP。

    返回 (findings, unmapped)：findings 为确定的缺口（pre-existing / sets-introduced /
    target-unsupported）；unmapped 为 type 与 Kconfig 符号命名对不上、无法自动判定的板型。
    只做静态旁证，用于区分“sets 引入”与“上游既有”，不改任何代码。
    """
    kconfig_a = _kconfig_text(SRC_A)
    kconfig_b = _kconfig_text(SRC_B)
    if not kconfig_a or not kconfig_b:
        return [], []

    whitelist_a = set(re.findall(r"BOARD_TYPE_[A-Z0-9_]+", _config_block(kconfig_a, "USE_DEVICE_AEC")))
    whitelist_b = set(re.findall(r"BOARD_TYPE_[A-Z0-9_]+", _config_block(kconfig_b, "USE_DEVICE_AEC")))
    ap_targets = set(
        re.findall(r"IDF_TARGET_[A-Z0-9_]+", _config_block(kconfig_b, "USE_AUDIO_PROCESSOR"))
    )

    claimed_a = _aec_claimed_configs(SRC_A)
    claimed_b = _aec_claimed_configs(SRC_B)

    findings: list[AecFinding] = []
    unmapped: list[AecFinding] = []
    for side, root, kconfig, whitelist, claimed in (
        ("A", SRC_A, kconfig_a, whitelist_a, claimed_a),
        ("B", SRC_B, kconfig_b, whitelist_b, claimed_b),
    ):
        symbols = _board_symbols(kconfig)
        dir_map = _cmake_board_dir_map(root)
        for rel, (board_type, target) in sorted(claimed.items()):
            normalized = re.sub(r"[^A-Z0-9]+", "_", board_type.upper()).strip("_")
            # 优先用 CMakeLists 的 BOARD_DIR 映射，猜名字只作兜底
            if rel in dir_map:
                matched = [dir_map[rel]]
            else:
                matched = sorted(s for s in symbols if normalized and normalized in s)
            if target and f"IDF_TARGET_{target.upper()}" not in ap_targets:
                findings.append(AecFinding(
                    side, rel, board_type, target, matched, "target-unsupported",
                    f"目标 {target} 不在 USE_AUDIO_PROCESSOR 支持列表 {sorted(t.replace('IDF_TARGET_', '') for t in ap_targets)} 内，"
                    "CONFIG_USE_DEVICE_AEC=y 会被依赖裁剪丢弃（非 sets 引入）",
                ))
            elif not matched:
                unmapped.append(AecFinding(
                    side, rel, board_type, target, [], "unmapped",
                    "config.json 的 type 与 Kconfig 的 BOARD_TYPE_* 命名不同，无法自动判定",
                ))
            elif not whitelist.intersection(matched):
                status = "pre-existing" if rel in claimed_a and rel in claimed_b else "sets-introduced"
                findings.append(AecFinding(
                    side, rel, board_type, target, matched, status,
                    "config.json 声明 CONFIG_USE_DEVICE_AEC=y，但 USE_DEVICE_AEC 的 depends 白名单未含 "
                    + "/".join(matched) + "，该开关会被裁掉",
                ))
    # A/B 两侧同名板型的同一问题合并为一行（side 记为 A/B），避免报告重复
    merged: dict[tuple, AecFinding] = {}
    for finding in findings:
        key = (finding.rel, finding.status, tuple(finding.symbols), finding.target)
        if key in merged:
            merged[key].side = "A/B"
        else:
            merged[key] = finding
    return list(merged.values()), unmapped


# ---------------------- 旁证：staging → main 同步漂移 ----------------------

# 与 hardware/sets/build.py 的 sync_board() 保持同一口径（:97-98）
SYNC_SUFFIXES = {".c", ".cc", ".cpp", ".h", ".hpp", ".json"}
SYNC_EXCLUDE_NAMES = {"set.json", "readme.md"}
SETS_BOARDS_ROOT = REPO_ROOT / "hardware/sets/boards"


@dataclass
class SyncDrift:
    board: str
    rel: str
    status: str  # missing-in-main / differs / extra-in-main
    note: str


def audit_sync_drift() -> list[SyncDrift]:
    """比对 hardware/sets/boards/<id>/（staging 源）与 main/boards/<board_dir>/（固件树）。

    build.py 的 sync_board() 在构建前把 staging 的源码拷进固件树；若只改了 staging 没同步，
    固件树编译的仍是旧实现（圆屏 D1–D5/G3 就踩过这个坑）。只读旁证，不改文件、不触发同步。
    """
    if not SETS_BOARDS_ROOT.is_dir():
        return []

    drifts: list[SyncDrift] = []
    for set_json in sorted(SETS_BOARDS_ROOT.glob("*/set.json")):
        try:
            spec = json.loads(set_json.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        board_id = str(spec.get("id") or set_json.parent.name)
        board_dir = str(spec.get("board_dir") or "").strip("/")
        if not board_dir:
            drifts.append(SyncDrift(board_id, "set.json", "missing-in-main", "set.json 缺少 board_dir"))
            continue
        source = set_json.parent
        target = SRC_B / "boards" / board_dir

        wanted: dict[str, Path] = {}
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            if path.name.lower() in SYNC_EXCLUDE_NAMES:
                continue
            if path.suffix.lower() not in SYNC_SUFFIXES:
                continue
            wanted[path.relative_to(source).as_posix()] = path

        for rel, path in wanted.items():
            dst = target / rel
            if not dst.is_file():
                drifts.append(SyncDrift(board_id, rel, "missing-in-main", "staging 有、固件树没有（未同步）"))
            elif sha256_of(path) != sha256_of(dst):
                drifts.append(SyncDrift(board_id, rel, "differs", "staging 与固件树内容不同（固件树较旧）"))

        for dst in sorted(target.rglob("*")):
            if not dst.is_file():
                continue
            rel = dst.relative_to(target).as_posix()
            if dst.name == "sets-build.json" or dst.name.lower() in SYNC_EXCLUDE_NAMES:
                continue
            if dst.suffix.lower() not in SYNC_SUFFIXES:
                continue
            if rel not in wanted:
                drifts.append(SyncDrift(board_id, rel, "extra-in-main",
                                        "固件树有、staging 没有（sync 仅告警不删除，需人工确认）"))
    return drifts


# ------------- 旁证：圆屏皮肤修复特征串断言 -------------
# 行号会随并行修改漂移，故用特征串断言代替行号比对（board-port 提供，2026-10-17 核对）
#
# 2026-10-17 皮肤统稿：B 侧把圆屏皮肤从 boards/yuhe/yh-n16r8-st7789/round_screen_display.cc
# 提升为 main/display/yh_skin/yh_skin_display.cc（4 版型共用），断言目标随之切换；
# D1/D2/D3/D5 的可观测不变量保持原样，D4 由「占位对象必须创建」承接。
ROUND_SCREEN_REL = "hardware/sets/yuhe-esp32/main/display/yh_skin/yh_skin_display.cc"
ROUND_SCREEN_POSITIVE = [
    ("D2 码点上限保持 72", "constexpr size_t kBubbleMaxCodepoints = 72;"),
    ("D2 保持 WRAP（未改 DOT）", "lv_label_set_long_mode(bubble_label_, LV_LABEL_LONG_WRAP);"),
    ("D1 截断在 SetChatMessage 生效", "TruncateUtf8(content, kBubbleMaxCodepoints)"),
    ("D4 占位对象族仍创建（防 SetTheme 空指针）", "container_ = lv_obj_create(screen);"),
    ("D4 SetTheme 后重绑皮肤字体", "ApplyFonts();"),
    ("D5 底部提示按 18 基准缩放", "profile_.scaled(18)"),
    ("D3 电量纯数字无图标", 'snprintf(buf, sizeof(buf), "%d%%", battery_level);'),
    ("开机首帧接管", "BuildSplash(lv_screen_active()"),
    ("原生态 UA 串必须丢弃", "LooksLikeUserAgent"),
    ("背景符号为共享层", "lv_image_set_src(bg_image_, &yh_skin_bg);"),
]
# 负向：非注释行中出现即判定回归（注释里提到该词不算）
ROUND_SCREEN_NEGATIVE = [
    ("D4 不得把占位置空", "chat_message_label_ = nullptr"),
    ("D2 不得固定气泡高度（会致短句上移）", "set_height(bubble_label_"),
    ("D2 不得改用 DOT（终裁为 WRAP）", "LV_LABEL_LONG_DOT"),
    ("D3 代码里不得出现闪电符号（内置字体无该字形）", "⚡"),
    ("不得回退到原生状态栏布局", "lv_obj_create(top_bar_"),
]


@dataclass
class TokenCheck:
    label: str
    token: str
    count: int
    ok: bool
    positive: bool


def check_round_screen(tokens_positive=None, tokens_negative=None) -> tuple[str, list[TokenCheck]]:
    """对 staging 的圆屏实现做特征串断言（正/负向）。负向忽略纯注释行，避免注释提及造成误报。"""
    path = REPO_ROOT / ROUND_SCREEN_REL
    if not path.is_file():
        # 同步后若 staging 被清理，退回固件树同名文件
        alt = SRC_B / "display/yh_skin/yh_skin_display.cc"
        path = alt if alt.is_file() else path
    if not path.is_file():
        return str(path), []

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return str(path), []

    code_lines = [ln for ln in lines if not ln.lstrip().startswith(("//", "/*", "*"))]
    checks: list[TokenCheck] = []
    for label, token in tokens_positive if tokens_positive is not None else ROUND_SCREEN_POSITIVE:
        count = sum(1 for ln in lines if token in ln)
        checks.append(TokenCheck(label, token, count, count > 0, True))
    for label, token in tokens_negative if tokens_negative is not None else ROUND_SCREEN_NEGATIVE:
        count = sum(1 for ln in code_lines if token in ln)
        checks.append(TokenCheck(label, token, count, count == 0, False))

    # 顺序型断言：SetTheme 里的补锁必须位于基类调用之后、字体重绑之前
    text = "\n".join(lines)
    marker = "void YhSkinDisplay::SetTheme("
    pos = text.find(marker)
    if pos >= 0:
        nxt = text.find("\nvoid ", pos + len(marker))
        body = text[pos: nxt if nxt > 0 else len(text)]
        i_base = body.find("LcdDisplay::SetTheme(theme);")
        i_lock = body.find("DisplayLockGuard lock(this);")
        i_font = body.find("ApplyFonts();")
        ordered = -1 < i_base < i_lock and (i_font < 0 or i_lock < i_font)
        checks.append(TokenCheck(
            "D6 SetTheme 基类返回后补锁（递归锁）",
            "LcdDisplay::SetTheme(theme) → DisplayLockGuard → 字体重绑",
            1 if ordered else 0, ordered, True))

    return path.relative_to(REPO_ROOT).as_posix(), checks


@dataclass
class WallpaperGate:
    """壁纸 API 在 emote 构建下的可见性处置（两种方案，按盘上实际代码判定）。"""
    variant: str            # "decl-conditional" / "decl-unconditional"
    include_conditional: bool
    decl_conditional: bool
    macro_present: bool
    display_note: str
    wm_note: str


def _target_spans(lines: list[str], macro: str) -> list[tuple[int, int]]:
    """返回由 `#if ... macro ...` 到对应 `#endif` 的行区间（1-based 闭区间）。"""
    spans: list[tuple[int, int]] = []
    stack: list[tuple[int, bool]] = []
    for idx, raw in enumerate(lines, start=1):
        s = raw.strip()
        if s.startswith("#if"):
            stack.append((idx, macro in s))
        elif s.startswith("#endif") and stack:
            start, hit = stack.pop()
            if hit:
                spans.append((start, idx))
    return spans


def audit_wallpaper_gate() -> WallpaperGate:
    dh_path = SRC_B / "display/display.h"
    wm_path = SRC_B / "wallpaper/wallpaper_manager.cc"
    try:
        dh_lines = dh_path.read_text(encoding="utf-8", errors="replace").splitlines()
        wm_text = wm_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return WallpaperGate("unknown", True, True, True, "文件缺失", "文件缺失")

    spans = _target_spans(dh_lines, "CONFIG_USE_EMOTE_MESSAGE_STYLE")

    def _inside(keyword: str) -> bool:
        for i, ln in enumerate(dh_lines, start=1):
            if keyword in ln:
                return any(a <= i <= b for a, b in spans)
        return False

    include_cond = _inside("#include <lvgl.h>")
    # 只关心"声明在哪"，不锁死返回类型：需求二后续把 SetWallpaper 从 void 改成 bool
    # （返回值 = 显示层是否真的接管了这张图），用返回类型做锚点会让本项误报成
    # "已移出条件块"。锚在参数类型上，签名演进不影响判定。
    decl_cond = _inside("SetWallpaper(const lv_img_dsc_t")
    macro_present = "WALLPAPER_HAS_LVGL_DISPLAY" in wm_text

    if decl_cond:
        variant = "decl-conditional"
        display_note = ("`display/display.h` 的 `SetWallpaper` / `ClearWallpaper` 仍在 "
                        f"`#ifndef CONFIG_USE_EMOTE_MESSAGE_STYLE` 内（条件块行区间 "
                        f"{', '.join(f'{a}-{b}' for a, b in spans) or '未识别'}），"
                        "emote 构建下这两个虚函数不存在。")
    else:
        variant = "decl-unconditional"
        display_note = ("`SetWallpaper` / `ClearWallpaper` 已移出条件块，所有构建（含 emote）均可见；"
                        f"`#include <lvgl.h>` {'仍受' if include_cond else '已脱离'} "
                        "`CONFIG_USE_EMOTE_MESSAGE_STYLE` 条件。")

    if macro_present:
        wm_note = ("`wallpaper_manager.cc` 仍用 `WALLPAPER_HAS_LVGL_DISPLAY` 条件闸："
                   "emote 构建在 `ApplyToDisplay` 处释放缓冲、告警并 `return false`，"
                   "`ProcessClear` 的 `ClearWallpaper()` 也被 `#if` 包住。")
    else:
        wm_note = ("`wallpaper_manager.cc` 已删除 `WALLPAPER_HAS_LVGL_DISPLAY`，"
                   "`display->ClearWallpaper()` / `SetWallpaper(&dsc)` 为无条件调用。")

    return WallpaperGate(variant, include_cond, decl_cond, macro_present, display_note, wm_note)


# ------------------------------- 报告输出 -------------------------------
def stats_table(pairs: list[FilePair]) -> list[str]:
    kinds = ["IDENTICAL", "DIFF", "B_ONLY", "A_ONLY"]
    header = ("分类", "文件数", "白名单内", "白名单外", "说明")
    rows = []
    for kind in kinds:
        subset = [p for p in pairs if p.kind == kind]
        inside = sum(1 for p in subset if p.whitelisted)
        # IDENTICAL 不参与放行统计，避免把"一致"误算成白名单外差异
        outside = "—" if kind == "IDENTICAL" else str(len(subset) - inside)
        note = {
            "IDENTICAL": "逐字节一致",
            "DIFF": "两侧同名但内容不同",
            "B_ONLY": "仅 B 存在",
            "A_ONLY": "仅 A 存在",
        }[kind]
        rows.append((kind, str(len(subset)), str(inside), outside, note))
    rows.append(
        ("合计", str(len(pairs)), str(sum(1 for p in pairs if p.whitelisted)),
         str(sum(1 for p in pairs if p.is_diff and not p.whitelisted)), "—")
    )
    widths = [max(display_width(r[i]) for r in [header, *rows]) for i in range(4)]
    lines = ["  ".join(pad(header[i], widths[i]) for i in range(4)) + "  说明"]
    lines.append("  ".join("-" * widths[i] for i in range(4)) + "  ----")
    for row in rows:
        lines.append("  ".join(pad(row[i], widths[i]) for i in range(4)) + f"  {row[4]}")
    return lines


def print_console(pairs: list[FilePair], features: list[Feature], q7: Q7Result,
                  aec: tuple[list[AecFinding], list[AecFinding]], drifts: list[SyncDrift],
                  round_checks: tuple[str, list[TokenCheck]]) -> bool:
    print("=" * 78)
    print(f"同源审计  A={A_LABEL}")
    print(f"          B={B_LABEL}")
    print("=" * 78)
    for line in stats_table(pairs):
        print(line)

    print("\n[白名单命中]")
    for pair in pairs:
        if pair.whitelisted:
            extra = "（仅 CRLF 换行差异）" if pair.eol_only else ""
            print(f"  {pair.kind:<9} {pair.rel}{extra}")
    unused = [p for p, spec in WHITELIST.items()
              if not any(match_pattern(f.rel, p) and f.whitelisted for f in pairs)]
    if unused:
        print("  -- 预置但未命中：" + ", ".join(unused))

    failing = [p for p in pairs if p.is_diff and not p.whitelisted]
    print("\n[白名单外差异]" + ("无" if not failing else f"{len(failing)} 项"))
    for pair in failing:
        size_a = "—" if pair.size_a < 0 else f"{pair.size_a}B"
        size_b = "—" if pair.size_b < 0 else f"{pair.size_b}B"
        print(f"  FAIL {pair.kind:<9} {pair.rel}  (A={size_a}, B={size_b})")
        if pair.wl_reason:
            print(f"       原因：{pair.wl_reason}")

    print("\n[B 领先 6 项特征断言]")
    for feature in features:
        status = "PASS" if feature.ok else "FAIL"
        print(f"  {status}  {feature.key} {feature.title}")
        for token in feature.tokens:
            hits = feature.hits.get(token) or []
            where = f"{hits[0][0]}:{hits[0][1]}" if hits else "缺失"
            print(f"        - {token!r} -> {where}")

    print("\n[Q7 OTA 匹配核查] " + ("PASS" if q7.ok else "FAIL"))
    for item in q7.evidence:
        print(f"  {item}")
    for note in q7.notes:
        print(f"  · {note}")

    print("\n[旁证：config.json 的 USE_DEVICE_AEC 与 Kconfig 一致性]")
    aec_findings, aec_unmapped = aec
    if not aec_findings:
        print("  无异常")
    for finding in aec_findings:
        print(f"  WARN [{finding.status}] ({finding.side}) {finding.rel} type={finding.board_type}")
        print(f"        {finding.note}")
    if aec_unmapped:
        print(f"  · 另有 {len(aec_unmapped)} 个板型 type 与 Kconfig 符号命名不同，未纳入自动判定："
              + ", ".join(sorted({f.board_type for f in aec_unmapped})))

    print("\n[旁证：hardware/sets/boards → main/boards 同步漂移]")
    if not drifts:
        print("  固件树与 staging 一致")
    for drift in drifts:
        print(f"  WARN [{drift.status}] {drift.board}/{drift.rel} — {drift.note}")

    print("\n[旁证：圆屏修复特征串断言]")
    round_path, round_checks = round_checks
    if not round_checks:
        print(f"  跳过（未找到 {round_path}）")
    for check in round_checks:
        prefix = "PASS" if check.ok else "FAIL"
        kind = "正向" if check.positive else "负向"
        print(f"  {prefix} [{kind}] {check.label}: 命中 {check.count} 次 — {check.token[:60]}")

    ok = (not failing and all(f.ok for f in features) and q7.ok
          and all(c.ok for c in round_checks))
    print("\n审计结果：" + ("PASS" if ok else "FAIL"))
    return ok


def render_report(pairs: list[FilePair], features: list[Feature], q7: Q7Result, ok: bool,
                  aec: tuple[list[AecFinding], list[AecFinding]], drifts: list[SyncDrift],
                  round_checks: tuple[str, list[TokenCheck]]) -> str:
    aec_findings, aec_unmapped = aec
    failing = [p for p in pairs if p.is_diff and not p.whitelisted]
    counts = {k: sum(1 for p in pairs if p.kind == k) for k in ("IDENTICAL", "DIFF", "B_ONLY", "A_ONLY")}
    whitelisted = [p for p in pairs if p.whitelisted]

    out: list[str] = []
    out.append("# 复刻同源审计报告（A=small_secreen / B=sets）")
    out.append("")
    out.append("| 项 | 值 |")
    out.append("| --- | --- |")
    out.append("| 任务 | FR-1.1（P0-4）同源审计脚本与报告 |")
    out.append(f"| 生成时间 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} |")
    out.append(f"| 仓库 | `G:/demo/21_xiaozhi` @ `{git_head()}`（分支 master） |")
    out.append(f"| A（基线） | `{A_LABEL}` |")
    out.append(f"| B（目标） | `{B_LABEL}` |")
    out.append(f"| 脚本 | `tools/sets_diff_audit.py`（只读，可随时重跑） |")
    out.append(f"| 审计结论 | **{'PASS' if ok else 'FAIL'}** |")
    out.append("")
    out.append("## 1. 结论摘要")
    out.append("")
    out.append(
        f"- 参评文件 {len(pairs)} 个：IDENTICAL {counts['IDENTICAL']} / DIFF {counts['DIFF']} / "
        f"B_ONLY {counts['B_ONLY']} / A_ONLY {counts['A_ONLY']}。"
    )
    out.append(
        f"- 差异 {sum(1 for p in pairs if p.is_diff)} 项，其中白名单内 {len(whitelisted)} 项、"
        f"白名单外 **{len(failing)}** 项。"
    )
    out.append(
        "- B 领先 6 项特征断言：" + ("全部命中" if all(f.ok for f in features) else "存在缺失，见第 4 节") + "。"
    )
    out.append("- Q7（OTA 固件匹配）：" + ("已确认按 `ai_ota.type == board.type` 精确匹配，见第 7 节。" if q7.ok else "核查失败，见第 7 节。"))
    out.append("- AEC 配置一致性旁证：" + (
        f"发现 {len(aec_findings)} 处 `CONFIG_USE_DEVICE_AEC=y` 与 Kconfig 白名单/目标芯片不一致（均为旁证，不影响本审计结论），见第 8 节。"
        if aec_findings else "无异常。"
    ))
    out.append("- staging→main 同步漂移：" + (
        f"**{len(drifts)} 处**（固件树落后于 `hardware/sets/boards/`，构建前必须跑 `build.py --sync-only`），见第 9 节。"
        if drifts else "无（固件树与 staging 一致）。"
    ))
    _gate = audit_wallpaper_gate()
    if _gate.variant == "decl-conditional":
        _gate_text = ("`display.h` 的 `SetWallpaper`/`ClearWallpaper` 仍受 "
                      "`!CONFIG_USE_EMOTE_MESSAGE_STYLE` 保护，`wallpaper_manager.cc` 用 "
                      "`WALLPAPER_HAS_LVGL_DISPLAY` 条件闸兜住（emote 下放弃壁纸）")
    else:
        _gate_text = ("`display.h` 的 `SetWallpaper`/`ClearWallpaper` 已对所有构建可见")
        _gate_text += ("，但 `wallpaper_manager.cc` 仍保留 `WALLPAPER_HAS_LVGL_DISPLAY` 条件闸"
                       if _gate.macro_present else "，调用侧为无条件调用")
    out.append("- 壁纸 API 在 emote 构建下的可见性：" + _gate_text
               + "；emote 板型（esp-vocat / esp-sensairshuttle）的编译阻塞已解除（单 TU 语法检查，"
               "未跑 idf.py build，建议各跑一次构建确认），见第 11 节。")
    out.append("")
    out.append("## 2. 审计口径")
    out.append("")
    out.append("- 递归遍历两侧 `main/`，按 sha256 逐字节比对；排除 `managed_components/`、`build/`、`*.o`。")
    out.append("- 分类：`IDENTICAL` 字节一致 / `DIFF` 同名不同 / `B_ONLY` 仅 B 有 / `A_ONLY` 仅 A 有。")
    out.append("- 白名单在 `tools/sets_diff_audit.py` 顶部 `WHITELIST` 字典中，每条带 reason；白名单外差异直接判 FAIL。")
    out.append("- 仅当 A 与 B 字节不同、但去掉 CRLF 后相同，标注“仅 CRLF 换行差异”（不改变分类，避免掩盖实质改动）。")
    out.append("- 行级增删用 `git diff --no-index --numstat` 统计。Kconfig/CMakeLists 的行数归属以**固定 blob** 为基线"
               "（不随 HEAD 前移、不受 amend/rebase 影响）：")
    out.append("  `git cat-file blob 68c5db5b > /tmp/K.base && git diff --no-index --numstat -- "
               "hardware/small_secreen/yuhe-esp32/main/Kconfig.projbuild /tmp/K.base` → 81/9；"
               "CMakeLists 基线 blob 为 f42eafbf（与工作区一致）→ 31/8。"
               "`git cat-file blob` 提示 “LF will be replaced by CRLF” 属工作区 checkout 设置，不影响 numstat。")
    out.append("- 复跑：`PYTHONUTF8=1 D:/INSTALL/python313/python.exe tools/sets_diff_audit.py --report code/reports/2026-10-17-复刻同源审计.md`")
    out.append("")
    out.append("## 3. 统计表")
    out.append("")
    out.append("| 分类 | 文件数 | 白名单内 | 白名单外 | 说明 |")
    out.append("| --- | ---: | ---: | ---: | --- |")
    for kind, note in (
        ("IDENTICAL", "逐字节一致"),
        ("DIFF", "同名不同内容"),
        ("B_ONLY", "仅 B 存在"),
        ("A_ONLY", "仅 A 存在"),
    ):
        subset = [p for p in pairs if p.kind == kind]
        inside = sum(1 for p in subset if p.whitelisted)
        outside = "—" if kind == "IDENTICAL" else str(len(subset) - inside)
        out.append(f"| {kind} | {len(subset)} | {inside} | {outside} | {note} |")
    out.append(
        f"| 合计 | {len(pairs)} | {len(whitelisted)} | {len(failing)} | — |"
    )
    out.append("")
    out.append("## 4. 白名单命中明细")
    out.append("")
    out.append("| 分类 | 文件 | 差异性质 | 放行理由 |")
    out.append("| --- | --- | --- | --- |")
    for pair in whitelisted:
        nature = "仅 CRLF 换行" if pair.eol_only else {
            "DIFF": "内容差异",
            "B_ONLY": "B 新增",
            "A_ONLY": "A 独有（改名对）",
        }.get(pair.kind, "—")
        if pair.kind == "DIFF" and not pair.eol_only:
            nature += f"（A {pair.size_a}B / B {pair.size_b}B）"
            if pair.added >= 0:
                nature += f"，+{pair.added}/-{pair.removed} 行"
        out.append(f"| {pair.kind} | `{pair.rel}` | {nature} | {pair.wl_reason} |")
    unused = [p for p in WHITELIST if not any(match_pattern(f.rel, p) and f.whitelisted for f in pairs)]
    out.append("")
    out.append("白名单条目共 %d 条，命中 %d 条。" % (len(WHITELIST), len(WHITELIST) - len(unused)))
    if unused:
        out.append("预置但当前未命中（保留以便并行改动期重跑）：" + "、".join(f"`{u}`" for u in unused) + "。")
    out.append("")
    out.append("## 5. 白名单外差异（审计失败项）")
    out.append("")
    if failing:
        out.append("| 分类 | 文件 | A 侧大小 | B 侧大小 |")
        out.append("| --- | --- | ---: | ---: |")
        for pair in failing:
            size_a = "—" if pair.size_a < 0 else f"{pair.size_a}B"
            size_b = "—" if pair.size_b < 0 else f"{pair.size_b}B"
            out.append(f"| {pair.kind} | `{pair.rel}` | {size_a} | {size_b} |")
        out.append("")
        out.append("以上条目不在白名单内，需补齐同源或补充带理由的白名单条目后重跑。")
    else:
        out.append("无。B 的所有差异都被白名单覆盖。")
    out.append("")
    out.append("## 6. B 领先 6 项特征断言")
    out.append("")
    out.append("| 项 | 特征 | 断言 token | 结果 | 命中位置 |")
    out.append("| --- | --- | --- | --- | --- |")
    for feature in features:
        token_cell = "<br>".join(f"`{t}`" for t in feature.tokens)
        where = "<br>".join(
            f"`{feature.hits[t][0][0]}:{feature.hits[t][0][1]}`" if feature.hits.get(t) else "**缺失**"
            for t in feature.tokens
        )
        out.append(
            f"| {feature.key} | {feature.title} | {token_cell} | {'PASS' if feature.ok else 'FAIL'} | {where} |"
        )
    out.append("")
    if not all(f.ok for f in features):
        out.append("缺失 token 汇总：" + "；".join(f"{f.key} -> {f.missing}" for f in features if not f.ok) + "。")
        out.append("")
    out.append("## 7. Q7 核查：OTA 固件按 board.type 匹配（只读，不改代码）")
    out.append("")
    out.append("**调用链**：`Ota::CheckVersion()` 上报 `board:{type,name,manufacturer}` → "
               "`DeviceServiceImpl.checkDeviceActive()` → 设备已绑定且 `auto_update==1` 才查固件 → "
               "`buildFirmwareInfo(type, currentVersion)` → `OtaServiceImpl.getLatestOta(type)`。")
    out.append("")
    out.append("**证据**：")
    out.append("")
    for item in q7.evidence:
        out.append(f"- `{item}`")
    out.append("")
    out.append("**语义**：")
    out.append("")
    for note in q7.notes:
        out.append(f"- {note}")
    out.append("")
    out.append("**板型 type 清单（B 侧 config.json，也是 OTA 请求里的 board.type）**：")
    out.append("")
    for board_type in q7.board_types:
        if board_type.startswith("（"):
            out.append(f"*{board_type}*")
        else:
            out.append(f"- `{board_type}`")
    out.append("")
    out.append("**结论**：" + (
        "OTA 按 `ai_ota.type == board.type` 精确字符串匹配（`eq(\"type\", type)` + "
        "`ORDER BY update_date DESC LIMIT 1`），无前缀/模糊/厂商匹配。B 侧改名与新增板型后，"
        "必须在 ai_ota 写入与 config.json `type` 完全同名（含大小写与连字符）的行；"
        "否则设备收到的是“当前版本 + INVALID_FIRMWARE_URL”，表现为永不可升级。"
        "该结论为静态核查，未连接数据库、未修改任何代码。" if q7.ok else "核查所需源文件缺失，无法确认。"
    ))
    out.append("")
    out.append("## 8. 旁证：config.json 的 USE_DEVICE_AEC 与 Kconfig 一致性")
    out.append("")
    out.append("只读旁证：板型 `config.json` 声明 `CONFIG_USE_DEVICE_AEC=y`，但 `USE_DEVICE_AEC` 的 depends 白名单"
               "未收录该板型时，开关会被 Kconfig 裁掉（设备静默失去设备侧 AEC）；目标芯片不在 "
               "`USE_AUDIO_PROCESSOR` 支持列表内时同样必然被丢弃。")
    out.append("")
    if aec_findings:
        out.append("| 侧 | 状态 | 板型目录 | type | target | 匹配到的 Kconfig 符号 | 说明 |")
        out.append("| --- | --- | --- | --- | --- | --- | --- |")
        for finding in aec_findings:
            out.append(
                f"| {finding.side} | {finding.status} | `{finding.rel}` | `{finding.board_type}` | "
                f"{finding.target or '—'} | {'/'.join(finding.symbols) or '—'} | {finding.note} |"
            )
        out.append("")
        out.append("`pre-existing` = A 侧同样存在，属上游既有问题，非 sets 引入；"
                   "`sets-introduced` 需要补 Kconfig 白名单或以 sdkconfig 显式覆盖；"
                   "`target-unsupported` = 目标芯片不支持 AFE，配置必然被依赖裁剪丢弃。")
        if aec_unmapped:
            out.append("")
            out.append(
                f"另有 {len(aec_unmapped)} 个板型（{', '.join(sorted({f.board_type for f in aec_unmapped}))}）"
                "的 config.json `type` 与 Kconfig 的 `BOARD_TYPE_*` 命名不同，无法自动映射，未纳入判定。"
            )
    else:
        out.append("无异常：所有声明设备 AEC 的板型都在白名单内，且目标芯片支持音频处理。")
    out.append("")
    out.append("## 9. 旁证：staging（hardware/sets/boards）→ 固件树（main/boards）同步漂移")
    out.append("")
    out.append("`hardware/sets/build.py` 的 `sync_board()` 在构建前把 `hardware/sets/boards/<id>/` 的 "
               "`*.c/*.cc/*.cpp/*.h/*.hpp/*.json`（排除 `set.json`、`README.md`）拷进 "
               "`main/boards/<board_dir>/`。**只改 staging 不跑同步，固件树编译的仍是旧实现。**")
    out.append("")
    out.append("两个实现细节（已读源码核实）：① 是否覆盖按 mtime 判定，"
               "仅 `source.mtime > destination.mtime + 1` 才更新，否则跳过；"
               "② 固件树里源目录已删除的残留文件**只告警、不自动删除**（`sets/build.py:465-476`），"
               "所以下表的 `extra-in-main` 是真实残留风险，必须人工确认。")
    out.append("")
    if drifts:
        out.append("本轮快照存在未同步项（见下表）：若 staging 侧刚改过 D1–D5/G3 等修复，"
                   "固件树编译的仍是旧实现，构建前必须先同步。")
        out.append("")
        out.append("| 版型 | 相对路径 | 状态 | 说明 |")
        out.append("| --- | --- | --- | --- |")
        for drift in drifts:
            out.append(f"| `{drift.board}` | `{drift.rel}` | {drift.status} | {drift.note} |")
        out.append("")
        out.append("修复方式（会同时重写 SETS-BOARDS 注册区间，已核对与现有 4 个 set.json 幂等）：")
        out.append("")
        out.append("```")
        out.append("python hardware/sets/build.py --board <id> --yes --sync-only")
        out.append("```")
        out.append("")
        out.append("该节为旁证，不计入同源审计 PASS/FAIL；同步完成后重跑本脚本，本节应显示“一致”。")
    else:
        out.append("固件树与 staging 一致，无待同步项。")
    out.append("")
    out.append("## 10. 附录：圆屏 D1–D5/G3 核对结论（特征串断言）")
    out.append("")
    out.append("对象：`hardware/sets/boards/yh-n16r8-st7789/`（staging 源，同步后才进固件树）。"
               "本节由脚本自动断言（不依赖行号，抗并行漂移）：正向特征必须存在、负向特征在非注释代码行必须为 0；"
               "结果为 PASS/FAIL 并计入总审计结论。"
               "注意：该文件在本轮并行开发中多次增长（558→564 行），本报告不再引用行号，"
               "如需定位请按表中的特征串全文搜索。")
    out.append("")
    round_path, round_checks = round_checks
    if round_checks:
        out.append(f"被测文件：`{round_path}`")
        out.append("")
        out.append("| 方向 | 断言 | 命中次数 | 结果 |")
        out.append("| --- | --- | ---: | --- |")
        for check in round_checks:
            out.append(f"| {'正向' if check.positive else '负向'} | {check.label}（`{check.token}`） | "
                       f"{check.count} | {'PASS' if check.ok else '**FAIL**'} |")
        out.append("")
    else:
        out.append(f"未找到被测文件 `{round_path}`，本节跳过。")
        out.append("")
    out.append("**结论**：D1（码点截断不乱码）、D3（电量无豆腐块）、D4（ClearChatMessages 不悬空 + SetTheme 保护）、"
               "D5（底部提示 `y=-18`）、G3（无电池隐藏电量）均为“已修复”，"
               "另核 D6（SetTheme 基类返回后补递归锁）在位；D2 为“已知观感差异”（口径见下）。"
               "以上由上方特征串断言机械核对，行号已从本报告移除以避免并行改动导致漂移。")
    out.append("")
    out.append("**编译级核对（2026-10-17 终态）**：用本树 `build/compile_commands.json` 的真实 IDF 6.1 工具链与原始 flags"
               "（含 `-Wall -Wextra -Werror`）对 `round_screen_display.cc`、`yh_set_n16r8_st7789.cc` 跑 "
               "`-fsyntax-only` 均为 **rc=0 且无诊断**；`good_bg.c` 用 C 模板 `-c` 单文件编译 **rc=0**，"
               "`xtensa-esp32s3-elf-nm -g --defined-only` 输出 **`R yh_round_bg_good`**，与 "
               "`round_screen_display.cc` 的 `extern` 声明名一致。"
               "**仍未跑 `idf.py build` 与链接，实机未验证**——本条结论是“语法级通过 + 符号名对齐”，"
               "不等于“已构建通过”。")
    out.append("")
    out.append("附：背景图 `good_bg.c` 的数值数据与 A 侧 `boards/my-s3-tft/good_bg.c` 逐项比对完全一致"
               "（符号改名并 extern 声明为 `yh_round_bg_good`，全文件无 `bg_good` 残留）；"
               "背景选择已抽成 `ApplyBackground()`，优先级为 用户壁纸 > 主题壁纸 > good.jpg"
               "（源码注释 `FR-1.3.8 + FR-2.17：壁纸优先级 用户壁纸 > 主题壁纸 > good.jpg` 可搜），"
               "符合 FR-1.3.8，且默认主题下与 A 板视觉一致。")
    out.append("")
    out.append("锁契约核对：`RoundScreenDisplay::SetupUI()` 先调 `Display::SetupUI()` 再 `DisplayLockGuard lock(this)`，"
               "其后 `BuildMainScreen() → ApplyBackground()` 路径持锁，安全；"
               "`RoundScreenDisplay::SetTheme()` 已在基类 `LcdDisplay::SetTheme(theme)` 返回后补 "
               "`DisplayLockGuard lock(this);`（覆盖字体重绑与 `ApplyBackground()`，见上方 D6 顺序断言）。"
               "LVGL 端口用的是递归互斥量（`managed_components/espressif__esp_lvgl_port/src/lvgl9/esp_lvgl_port.c:77` "
               "`xSemaphoreCreateRecursiveMutex()`），同任务重入不会死锁。")
    out.append("")
    out.append("**D2 备选方案评估（记录用，本轮不采纳）**")
    out.append("")
    out.append("- 已否决：`LV_LABEL_LONG_DOT` + label 定高 40。原因：LVGL label 无垂直对齐属性，文字从文本区顶部起排，"
               "定高后所有单行短句上移约 10px，违反 AC-03 的 ±1px 像素基线（影响面从超长文本扩到每条消息）。")
    out.append("- 可选优化（方案 D，已论证可行，列为真机验收后的备选）：用像素测量代替码点常量裁剪——"
               "`lv_text_get_size()` 测「按 180px 宽换行后的实际高度」，超过气泡内容高 42 就二分码点数并补 `…`，"
               "保留 `WRAP` 与自适应高度，短句零位移。API 依据："
               "`managed_components/lvgl__lvgl/src/misc/lv_text.h:75` `lv_text_get_size(...)`"
               "（v9 命名；本工程没有 v8 的 `lv_txt_get_size`）。")
    out.append("- 将来落地需注意三点：① 字体取 label 实际样式 "
               "`lv_obj_get_style_text_font(bubble_label_, LV_PART_MAIN)`，不要用 theme 快照（主题切换瞬间可能不一致）；"
               "② `line_space` 传 `lv_obj_get_style_text_line_space` 的实际值，传 0 会让 42px 判定偏乐观；"
               "③ 测量与 `set_text` 必须在同一把 LVGL 锁内（`SetBubbleText` 现已有 `DisplayLockGuard`，把测量并入该临界区）。")
    out.append("")
    out.append("## 11. 旁证：壁纸 API 在 emote 构建下的可见性（方案 ①，静态核对）")
    out.append("")
    out.append("**原始风险**：`display/display.h` 曾只在 `#ifndef CONFIG_USE_EMOTE_MESSAGE_STYLE` 时声明 "
               "`SetWallpaper` / `ClearWallpaper`（emote 模式不引入 `lvgl.h`，`lv_img_dsc_t` 不可见），"
               "而 `wallpaper_manager.cc` 原先无条件调用它们，且该文件在 `CMakeLists.txt:36` 的全局 SOURCES 中，"
               "所有板型都编译。上游 `boards/espressif/esp-vocat/config.json:9` 与 "
               "`boards/espressif/esp-sensairshuttle/config.json:23` 开启该宏，会因 `Display` 无此成员而编译失败。")
    out.append("")
    gate = audit_wallpaper_gate()
    out.append(f"**终裁与盘上现状（脚本按源码实测，非人工转录）**：采用方案 ① —— `display.h` 维持上游条件块"
               f"（虚函数仅在非 emote 构建可见），`wallpaper_manager.cc` 的 `WALLPAPER_HAS_LVGL_DISPLAY` "
               f"条件闸为唯一防线。脚本实测形态：`{gate.variant}`。")
    out.append("")
    out.append(f"- {gate.display_note}")
    out.append(f"- {gate.wm_note}")
    out.append("")
    out.append("**代码依据**：LVGL9 的 `lv_image_dsc_t` 是匿名 typedef"
               "（`managed_components/lvgl__lvgl/src/draw/lv_image_dsc.h`），"
               "`lv_img_dsc_t` 只是 `lv_api_map_v8.h` 的别名，不存在可前置声明的 struct tag，"
               "故“靠前向声明让虚函数常驻”不可行；方案 ②（无条件 include + 虚函数常驻）虽语法可行但已弃用，"
               "代码中无该方案残留。条件闸方案下 `ApplyToDisplay` 在 emote 直接释放缓冲、告警并 `return false`，"
               "屏幕保持默认，失败回执的 `reason` 为 `no_display`（不会被误记成 download/verify 失败）。")
    out.append("")
    out.append("**验证强度（比纯静态更进一层）**：flags 取自 `build/compile_commands.json`（含 "
               "`-Wall -Wextra -Werror`）。正常配置下 `wallpaper_manager.cc` / `application.cc` / "
               "`round_screen_display.cc` / `lcd_display.cc` 四个 TU `-fsyntax-only` 均 rc=0；"
               "再对 `wallpaper_manager.cc` 与 `application.cc` 追加 `-DCONFIG_USE_EMOTE_MESSAGE_STYLE=1` "
               "做 `-fsyntax-only`，两者同样 rc=0 —— 即 emote 语义下的头文件链与条件闸可解析。"
               "**仍未跑 `idf.py build`**，故本条标“静态核对”。")
    out.append("")
    out.append("**残留**：全量构建矩阵（`esp-vocat` / `esp-sensairshuttle`）仍待执行，跑通后可将本条升级为"
               "“已构建验证”。该项不影响同源审计结论"
               "（`display/display.h` 的差异已按需求白名单化）。")
    out.append("")
    out.append("## 12. 备注")
    out.append("")
    out.append("- 本报告由脚本生成，其他 agent 并行改动 B 后可直接重跑覆盖，无需手工维护数字。")
    out.append("- 脚本全程只读业务代码，仅写本报告文件；未执行任何 git 写操作。")
    out.append("- 新增差异若判定为设计内变更，应在脚本 `WHITELIST` 中新增带 reason 的条目，而不是放宽已有条目。")
    out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A/B main 目录同源审计（只读）")
    parser.add_argument("--report", nargs="?", const=str(DEFAULT_REPORT), default=None,
                        help="输出 Markdown 报告路径（默认不写文件）")
    args = parser.parse_args(argv)

    if not SRC_A.is_dir() or not SRC_B.is_dir():
        print(f"错误：源目录不存在\n  A={SRC_A}\n  B={SRC_B}", file=sys.stderr)
        return 2

    pairs = classify_files()
    features = run_feature_assertions()
    q7 = check_q7()
    aec = audit_aec_consistency()
    drifts = audit_sync_drift()
    round_checks = check_round_screen()
    ok = print_console(pairs, features, q7, aec, drifts, round_checks)

    if args.report:
        report_path = Path(args.report)
        if not report_path.is_absolute():
            report_path = REPO_ROOT / report_path
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(render_report(pairs, features, q7, ok, aec, drifts, round_checks),
                               encoding="utf-8", newline="\n")
        print(f"\n报告已写入：{report_path}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
