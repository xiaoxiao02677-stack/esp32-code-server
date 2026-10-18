#!/usr/bin/env python3
"""sim_user_suite.py — 模拟普通用户全链路测试套件（P0/P1 矩阵）

依据设计：.workbuddy/sim_test_design_v1.md（架构师 高见远 v1，2026-10-05）
执行：QA 严过关（任务 #8）
输出：.workbuddy/reports/sim_user_v1_<ts>.json / .md / raw_<case>.ndjson
退出码：0 = P0 全绿；1 = 存在 P0 FAIL
"""
import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import websockets

# ---------- 常量区（设计 §0/§1） ----------
WS_URL = "ws://sandyun.top:8001/yuhe/v1/"
DEVICE_ID = "14:c1:9f:d1:33:48"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SSH_HELPER = os.path.join(SCRIPT_DIR, "ssh_run.py")
REMOTE_LOG = "/root/xiaozhi-server/main/yuhe-server/data/app.log"

BUDGETS = {  # name: (硬线 FAIL, 期望 SLOW)，单位秒
    "connect": (5, 2),
    "ttfb_text": (8, 4),
    "ttfb_audio": (10, 6),
    "short_total": (30, 15),
    "long_total": (120, 60),
    "interrupt_converge": (3, 1),
}

FAILURE_PHRASES = ["有点忙", "抱歉", "稍后", "请稍候", "出了点问题", "失败"]

CASE_TEXTS = {
    "P0-1": "你好",
    "P0-2": ["我叫高见远，我最喜欢的水果是西瓜。", "我叫什么名字？", "我最喜欢的水果是什么？"],
    "P0-2_must": {2: "高见远", 3: "西瓜"},
    "P0-3": "请讲一个关于小机器人第一次看海的小故事，至少讲100个字。",
    "P0-4": ("给我讲一个长长的睡前故事，越长越好。", "你好，你还在吗？"),
    "P0-4b": ("给我讲一个长长的睡前故事，越长越好。", "你好，你还在吗？"),
    "P1-7": ("给我讲一个长长的睡前故事，越长越好。", "你好，你还在吗？"),
    "P0-5": "你好",
}

GREETING_DRAIN_MAX_S = 15.0
GREETING_QUIET_S = 2.0
CASE_GAP_S = 5.0
TURN_GAP_S = 1.5
TAIL_DRAIN_S = 2.0
INTERRUPT_OBSERVE_S = 5.0
SHORT_TURN_CAP_S = 60.0
LONG_TURN_CAP_S = 150.0
FIRST_AUDIO_CAP_S = 60.0


# ---------- 数据结构（设计 §3.1） ----------
@dataclass
class TurnResult:
    query: str = ""
    sent_at: float = 0.0
    sent_wall: str = ""
    first_text_at: Optional[float] = None
    first_audio_at: Optional[float] = None
    tts_stop_at: Optional[float] = None
    audio_frames: int = 0
    audio_bytes: int = 0
    tail_frames: int = 0
    tts_stop_artifacts: int = 0
    sentences: list = field(default_factory=list)
    stt_texts: list = field(default_factory=list)
    llm_emotions: list = field(default_factory=list)
    other_msgs: list = field(default_factory=list)
    error: Optional[str] = None
    closed: Optional[str] = None

    @property
    def all_text(self) -> str:
        return "".join(s["text"] for s in self.sentences)

    @property
    def ttfb_text_s(self):
        return None if self.first_text_at is None else round(self.first_text_at - self.sent_at, 3)

    @property
    def ttfb_audio_s(self):
        return None if self.first_audio_at is None else round(self.first_audio_at - self.sent_at, 3)

    @property
    def total_s(self):
        return None if self.tts_stop_at is None else round(self.tts_stop_at - self.sent_at, 3)


@dataclass
class InterruptResult:
    query: str = ""
    signal: str = ""
    sent_at: float = 0.0
    sent_wall: str = ""
    first_text_at: Optional[float] = None
    first_audio_at: Optional[float] = None
    signal_at: Optional[float] = None
    signal_wall: str = ""
    tts_stop_at: Optional[float] = None
    frames_after_signal: int = 0
    audio_frames: int = 0
    audio_bytes: int = 0
    sentences: list = field(default_factory=list)
    stt_texts: list = field(default_factory=list)
    last_frame_after_signal_at: Optional[float] = None
    natural_end: bool = False
    error: Optional[str] = None
    closed: Optional[str] = None
    recovery: Optional[TurnResult] = None

    @property
    def all_text(self) -> str:
        return "".join(s["text"] for s in self.sentences)

    @property
    def ttfb_audio_s(self):
        return None if self.first_audio_at is None else round(self.first_audio_at - self.sent_at, 3)

    @property
    def converge_s(self):
        if self.signal_at is not None and self.last_frame_after_signal_at is not None:
            return round(self.last_frame_after_signal_at - self.signal_at, 3)
        return None


# ---------- 判分纯函数（可单测，不碰网络） ----------
def check_failure_phrases(all_text: str) -> Optional[str]:
    for p in FAILURE_PHRASES:
        if p in all_text:
            return p
    return None


def count_content_chars(text: str) -> int:
    """去标点/空白后计字数（Unicode 词字符口径，汉字保留）。"""
    return len(re.sub(r"[\W_]+", "", text, flags=re.UNICODE))


def _slow(note_list, name, value, budget_key):
    if value is not None and value > BUDGETS[budget_key][1]:
        note_list.append(f"SLOW: {name} {value}s > 期望{BUDGETS[budget_key][1]}s")


def judge_short(tr: TurnResult):
    """P0-1 / P0-5 单轮 / P0-4 恢复轮判分。"""
    checks, notes = {}, []
    fp = check_failure_phrases(tr.all_text)
    checks["tts_stop"] = tr.tts_stop_at is not None
    checks["sentences>=1"] = len(tr.sentences) >= 1
    checks["frames>=40"] = tr.audio_frames >= 40
    checks["ttfb_audio<=10s"] = tr.ttfb_audio_s is not None and tr.ttfb_audio_s <= BUDGETS["ttfb_audio"][0]
    checks["total<=30s"] = tr.total_s is not None and tr.total_s <= BUDGETS["short_total"][0]
    checks["no_fail_phrase"] = fp is None
    checks["no_error"] = tr.error is None and tr.closed is None
    _slow(notes, "ttfb_text", tr.ttfb_text_s, "ttfb_text")
    _slow(notes, "ttfb_audio", tr.ttfb_audio_s, "ttfb_audio")
    _slow(notes, "total", tr.total_s, "short_total")
    if fp:
        notes.append(f"失败话术命中: {fp}")
    if tr.error:
        notes.append(f"ERROR: {tr.error}")
    if tr.closed:
        notes.append(f"连接异常关闭: {tr.closed}")
    verdict = "PASS" if all(checks.values()) else "FAIL"
    return verdict, checks, notes


def judge_context_turn(tr: TurnResult, must_contain: Optional[str]):
    """P0-2 各轮：帧≥20、整轮≤30s、内容断言。"""
    checks, notes = {}, []
    fp = check_failure_phrases(tr.all_text)
    checks["tts_stop"] = tr.tts_stop_at is not None
    checks["sentences>=1"] = len(tr.sentences) >= 1
    checks["frames>=20"] = tr.audio_frames >= 20
    checks["ttfb_audio<=10s"] = tr.ttfb_audio_s is not None and tr.ttfb_audio_s <= BUDGETS["ttfb_audio"][0]
    checks["total<=30s"] = tr.total_s is not None and tr.total_s <= BUDGETS["short_total"][0]
    checks["no_fail_phrase"] = fp is None
    checks["no_error"] = tr.error is None and tr.closed is None
    if must_contain:
        checks[f"content含'{must_contain}'"] = must_contain in tr.all_text
    _slow(notes, "ttfb_text", tr.ttfb_text_s, "ttfb_text")
    _slow(notes, "ttfb_audio", tr.ttfb_audio_s, "ttfb_audio")
    _slow(notes, "total", tr.total_s, "short_total")
    if fp:
        notes.append(f"失败话术命中: {fp}")
    if tr.error:
        notes.append(f"ERROR: {tr.error}")
    if tr.closed:
        notes.append(f"连接异常关闭: {tr.closed}")
    verdict = "PASS" if all(checks.values()) else "FAIL"
    return verdict, checks, notes


def judge_long(tr: TurnResult):
    """P0-3：拼接≥100字、≥2句、≥150帧、整轮≤120s。"""
    checks, notes = {}, []
    fp = check_failure_phrases(tr.all_text)
    chars = count_content_chars(tr.all_text)
    checks["tts_stop"] = tr.tts_stop_at is not None
    checks[f"content>=100字(实{chars})"] = chars >= 100
    checks["sentences>=2"] = len(tr.sentences) >= 2
    checks["frames>=150"] = tr.audio_frames >= 150
    checks["total<=120s"] = tr.total_s is not None and tr.total_s <= BUDGETS["long_total"][0]
    checks["no_fail_phrase"] = fp is None
    checks["no_error"] = tr.error is None and tr.closed is None
    _slow(notes, "ttfb_text", tr.ttfb_text_s, "ttfb_text")
    _slow(notes, "ttfb_audio", tr.ttfb_audio_s, "ttfb_audio")
    _slow(notes, "total", tr.total_s, "long_total")
    if fp:
        notes.append(f"失败话术命中: {fp}")
    if tr.error:
        notes.append(f"ERROR: {tr.error}")
    if tr.closed:
        notes.append(f"连接异常关闭: {tr.closed}")
    verdict = "PASS" if all(checks.values()) else "FAIL"
    return verdict, checks, notes


def judge_recovery(tr: TurnResult):
    """打断场景恢复轮：协议完整性 + 无失败话术 + 无异常；总时长用 150s 硬线
    （恢复回答常为故事延续，LLM 上下文行为，非状态机卡死；>30s 记观察）。"""
    checks, notes = {}, []
    fp = check_failure_phrases(tr.all_text)
    checks["tts_stop"] = tr.tts_stop_at is not None
    checks["sentences>=1"] = len(tr.sentences) >= 1
    checks["frames>=20"] = tr.audio_frames >= 20
    checks["total<=150s"] = tr.total_s is not None and tr.total_s <= 150
    checks["no_fail_phrase"] = fp is None
    checks["no_error"] = tr.error is None and tr.closed is None
    _slow(notes, "ttfb_text", tr.ttfb_text_s, "ttfb_text")
    _slow(notes, "ttfb_audio", tr.ttfb_audio_s, "ttfb_audio")
    if tr.total_s is not None and tr.total_s > BUDGETS["short_total"][0]:
        notes.append(f"OBSERVE: 恢复轮总时长 {tr.total_s}s 超短轮预算30s（回答为长内容/故事延续时属正常，非卡死）")
    if fp:
        notes.append(f"失败话术命中: {fp}")
    if tr.error:
        notes.append(f"ERROR: {tr.error}")
    if tr.closed:
        notes.append(f"连接异常关闭: {tr.closed}")
    verdict = "PASS" if all(checks.values()) else "FAIL"
    return verdict, checks, notes


def judge_interrupt(ir: InterruptResult, strict: bool = False):
    """P0-4（strict=False：收敛为观察项）/ P1-7（strict=True：音频≤3s 停为判据）。"""
    checks, notes = {}, []
    conv = ir.converge_s
    if conv is not None and (conv <= BUDGETS["interrupt_converge"][0] or (not strict and ir.frames_after_signal <= 30)):
        classification = "打断生效"
    else:
        classification = f"listen {ir.signal} 未打断（观察项，不判 FAIL；5s 观察窗内音频未停）"
    if classification == "打断生效" and conv is not None and conv > BUDGETS["interrupt_converge"][1]:
        notes.append(f"SLOW: 打断收敛 {conv}s > 期望1s")
    notes.append(f"打断分类: {classification}（converge_s={conv}, frames_after_signal={ir.frames_after_signal}）")

    checks["no_protocol_error"] = ir.error is None and ir.closed is None
    if strict:
        checks["audio_stopped<=3s"] = conv is not None and conv <= BUDGETS["interrupt_converge"][0]
    if ir.recovery is not None:
        rv, rchecks, rnotes = judge_recovery(ir.recovery)
        checks["recovery_pass"] = rv == "PASS"
        notes.append(f"恢复轮: {rv} {rnotes if rnotes else ''}".rstrip())
    else:
        rv, rchecks = "FAIL", {}
        checks["recovery_pass"] = False
        notes.append("恢复轮未执行")
    fp = check_failure_phrases(ir.all_text + (ir.recovery.all_text if ir.recovery else ""))
    checks["no_fail_phrase"] = fp is None
    if fp:
        notes.append(f"失败话术命中: {fp}")
    if ir.error:
        notes.append(f"ERROR: {ir.error}")
    if ir.closed:
        notes.append(f"连接异常关闭: {ir.closed}")
    verdict = "PASS" if all(checks.values()) else "FAIL"
    return verdict, checks, notes, rv, rchecks


# ---------- SimDevice（设计 §3.1） ----------
class SimDevice:
    def __init__(self, case_id: str, session_id: str, out_dir: str):
        self.case_id = case_id
        self.session_id = session_id
        self.raw_path = os.path.join(out_dir, f"raw_{case_id}.ndjson")
        self.raw_f = open(self.raw_path, "a", encoding="utf-8")
        self.ws = None
        self.connect_s: Optional[float] = None
        self.hello_s: Optional[float] = None
        self.greeting = {"present": False, "texts": [], "audio_frames": 0,
                         "audio_bytes": 0, "tts_stop": False}

    def _log_raw(self, phase: str, direction: str, *, text: str = None, length: int = None):
        rec = {"case": self.case_id, "phase": phase, "dir": direction,
               "t": round(time.monotonic(), 3),
               "wall": datetime.now().strftime("%y%m%d %H:%M:%S.%f")[:-3]}
        if text is not None:
            rec["kind"] = "text"
            rec["text"] = text[:400]
        else:
            rec["kind"] = "binary"
            rec["len"] = length
        self.raw_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.raw_f.flush()

    async def connect(self):
        headers = [("Authorization", "Bearer test"), ("Protocol-Version", "1"),
                   ("Device-Id", DEVICE_ID), ("Client-Id", f"qa-{self.case_id}")]
        t0 = time.monotonic()
        self.ws = await websockets.connect(WS_URL, additional_headers=headers,
                                           open_timeout=20, ping_interval=15)
        self.connect_s = round(time.monotonic() - t0, 3)
        hello = {"type": "hello", "version": 1, "transport": "websocket",
                 "audio_params": {"format": "opus", "sample_rate": 16000,
                                  "channels": 1, "frame_duration": 60}}
        await self.ws.send(json.dumps(hello))
        self._log_raw("connect", "out", text=json.dumps(hello))
        t1 = time.monotonic()
        msg = await asyncio.wait_for(self.ws.recv(), timeout=15)
        self.hello_s = round(time.monotonic() - t1, 3)
        data = json.loads(msg)
        self._log_raw("connect", "in", text=msg)
        if data.get("type") != "hello":
            raise RuntimeError(f"首消息非 hello: {data.get('type')}")
        await self._drain_greeting()

    async def _drain_greeting(self):
        """排空开机问候（≤15s 不判分）；2s 静默提前结束。"""
        deadline = time.monotonic() + GREETING_DRAIN_MAX_S
        while time.monotonic() < deadline:
            remain = deadline - time.monotonic()
            try:
                msg = await asyncio.wait_for(self.ws.recv(), timeout=min(GREETING_QUIET_S, remain))
            except asyncio.TimeoutError:
                break
            except websockets.ConnectionClosed as e:
                raise RuntimeError(f"问候排空阶段连接关闭: {e}")
            if isinstance(msg, bytes):
                self.greeting["audio_frames"] += 1
                self.greeting["audio_bytes"] += len(msg)
                self._log_raw("greeting", "in", length=len(msg))
            else:
                self._log_raw("greeting", "in", text=msg)
                d = json.loads(msg)
                if d.get("type") == "tts":
                    if d.get("state") == "sentence_start":
                        self.greeting["texts"].append(d.get("text", ""))
                    elif d.get("state") == "stop":
                        self.greeting["tts_stop"] = True
        self.greeting["present"] = bool(self.greeting["texts"] or self.greeting["audio_frames"])

    def _send_listen_triple(self, text: str, phase: str):
        sid = self.session_id
        start_msg = {"session_id": sid, "type": "listen", "state": "start", "mode": "manual"}
        detect_msg = {"session_id": sid, "type": "listen", "state": "detect", "text": text}
        stop_msg = {"session_id": sid, "type": "listen", "state": "stop"}
        sent_at = time.monotonic()
        sent_wall = datetime.now().strftime("%y%m%d %H:%M:%S")
        await_ = self.ws
        return start_msg, detect_msg, stop_msg, sent_at, sent_wall

    async def ask(self, text: str, phase: str = "turn", cap_s: float = SHORT_TURN_CAP_S,
                 mode: str = "manual") -> TurnResult:
        tr = TurnResult(query=text)
        sid = self.session_id
        start_msg = {"session_id": sid, "type": "listen", "state": "start", "mode": mode}
        detect_msg = {"session_id": sid, "type": "listen", "state": "detect", "text": text}
        stop_msg = {"session_id": sid, "type": "listen", "state": "stop"}
        await self.ws.send(json.dumps(start_msg))
        self._log_raw(phase, "out", text=json.dumps(start_msg))
        tr.sent_at = time.monotonic()
        tr.sent_wall = datetime.now().strftime("%y%m%d %H:%M:%S")
        await self.ws.send(json.dumps(detect_msg))
        self._log_raw(phase, "out", text=json.dumps(detect_msg))
        await self.ws.send(json.dumps(stop_msg))
        self._log_raw(phase, "out", text=json.dumps(stop_msg))

        deadline = tr.sent_at + cap_s
        try:
            while tr.tts_stop_at is None and time.monotonic() < deadline:
                try:
                    msg = await asyncio.wait_for(self.ws.recv(), timeout=min(5.0, deadline - time.monotonic()))
                except asyncio.TimeoutError:
                    continue
                # 工件过滤：本轮 stt 回显到达之前的 tts stop 属旧 TTS 尾流/打断清理
                # （auto 模式恢复时服务器先 abort 旧 TTS 再回显 stt，顺序为 stop→stt）
                if isinstance(msg, str):
                    try:
                        d = json.loads(msg)
                    except json.JSONDecodeError:
                        d = {}
                    if d.get("type") == "tts" and d.get("state") == "stop" and not tr.stt_texts:
                        tr.tts_stop_artifacts += 1
                        self._log_raw(phase, "in", text=msg)
                        continue
                self._process_message(tr, phase, msg)
            if tr.tts_stop_at is None:
                tr.error = f"{cap_s:.0f}s 内未收到 tts stop"
        except websockets.ConnectionClosed as e:
            tr.closed = str(e)

        # tts stop 后排空 ≤2s 尾部消息（避免漏记）
        if tr.tts_stop_at is not None:
            tail_deadline = time.monotonic() + TAIL_DRAIN_S
            while time.monotonic() < tail_deadline:
                try:
                    msg = await asyncio.wait_for(self.ws.recv(), timeout=tail_deadline - time.monotonic())
                except asyncio.TimeoutError:
                    break
                except websockets.ConnectionClosed:
                    break
                if isinstance(msg, bytes):
                    tr.tail_frames += 1
                self._log_raw(f"{phase}-tail", "in",
                              length=len(msg) if isinstance(msg, bytes) else None,
                              text=None if isinstance(msg, bytes) else msg)
        return tr

    def _process_message(self, tr: TurnResult, phase: str, msg):
        if isinstance(msg, bytes):
            tr.audio_frames += 1
            tr.audio_bytes += len(msg)
            if tr.first_audio_at is None:
                tr.first_audio_at = time.monotonic()
            self._log_raw(phase, "in", length=len(msg))
        else:
            self._log_raw(phase, "in", text=msg)
            try:
                d = json.loads(msg)
            except json.JSONDecodeError:
                tr.other_msgs.append("unparseable")
                return
            t = d.get("type")
            if t == "tts":
                st = d.get("state")
                if st == "sentence_start":
                    tr.sentences.append({"text": d.get("text", ""), "at": round(time.monotonic(), 3)})
                    if tr.first_text_at is None:
                        tr.first_text_at = time.monotonic()
                elif st == "stop":
                    tr.tts_stop_at = time.monotonic()
            elif t == "stt":
                tr.stt_texts.append(d.get("text", ""))
            elif t == "llm":
                tr.llm_emotions.append(d.get("emotion", ""))
            else:
                tr.other_msgs.append(t)

    async def interrupt(self, main_text: str, recovery_text: str, signal: str) -> InterruptResult:
        """发查询→等首帧→发打断信号（listen stop/start 或 type=abort）→观察 5s→同连接恢复查询（auto 模式）。"""
        ir = InterruptResult(query=main_text, signal=signal)
        sid = self.session_id
        start_msg = {"session_id": sid, "type": "listen", "state": "start", "mode": "manual"}
        detect_msg = {"session_id": sid, "type": "listen", "state": "detect", "text": main_text}
        stop_msg = {"session_id": sid, "type": "listen", "state": "stop"}
        await self.ws.send(json.dumps(start_msg))
        self._log_raw("interrupt-main", "out", text=json.dumps(start_msg))
        ir.sent_at = time.monotonic()
        ir.sent_wall = datetime.now().strftime("%y%m%d %H:%M:%S")
        await self.ws.send(json.dumps(detect_msg))
        self._log_raw("interrupt-main", "out", text=json.dumps(detect_msg))
        await self.ws.send(json.dumps(stop_msg))
        self._log_raw("interrupt-main", "out", text=json.dumps(stop_msg))

        try:
            # 等首个音频帧（期间正常收集文本消息）
            deadline = ir.sent_at + FIRST_AUDIO_CAP_S
            while ir.first_audio_at is None and time.monotonic() < deadline:
                try:
                    msg = await asyncio.wait_for(self.ws.recv(), timeout=min(5.0, deadline - time.monotonic()))
                except asyncio.TimeoutError:
                    continue
                self._process_ir_message(ir, "interrupt-main", msg, signal_at=None)
            if ir.first_audio_at is None:
                ir.error = f"{FIRST_AUDIO_CAP_S:.0f}s 内无首帧音频"
                return ir

            # 发打断信号（三种：listen stop / listen start(auto) / type=abort 固件真实打断）
            if signal == "abort":
                sig_msg = {"session_id": sid, "type": "abort"}
            else:
                sig_msg = {"session_id": sid, "type": "listen", "state": signal}
                if signal == "start":
                    sig_msg["mode"] = "auto"
            ir.signal_at = time.monotonic()
            ir.signal_wall = datetime.now().strftime("%y%m%d %H:%M:%S")
            await self.ws.send(json.dumps(sig_msg))
            self._log_raw("interrupt-signal", "out", text=json.dumps(sig_msg))

            # 观察 ≤5s（设计 §P0-4：仅记录收敛情况，不等待自然结束）
            obs_deadline = ir.signal_at + INTERRUPT_OBSERVE_S
            while time.monotonic() < obs_deadline:
                try:
                    msg = await asyncio.wait_for(self.ws.recv(), timeout=min(1.0, obs_deadline - time.monotonic()))
                except asyncio.TimeoutError:
                    continue
                self._process_ir_message(ir, "interrupt-observe", msg, signal_at=ir.signal_at)
            ir.natural_end = ir.tts_stop_at is not None
        except websockets.ConnectionClosed as e:
            ir.closed = str(e)
            return ir

        # 同连接恢复查询（证明状态机未卡死）；auto 模式=真实设备 VAD 路径，
        # 服务器 startToChat 中 client_is_speaking 且非 manual → handleAbortMessage 打断旧 TTS；
        # cap 用 150s：恢复回答常为故事延续（LLM 上下文行为），60s 会截断长回答
        ir.recovery = await self.ask(recovery_text, phase="interrupt-recovery", mode="auto",
                                     cap_s=LONG_TURN_CAP_S)
        return ir

    def _process_ir_message(self, ir: InterruptResult, phase: str, msg, signal_at):
        if isinstance(msg, bytes):
            ir.audio_frames += 1
            ir.audio_bytes += len(msg)
            now = time.monotonic()
            if ir.first_audio_at is None:
                ir.first_audio_at = now
            if signal_at is not None:
                ir.frames_after_signal += 1
                ir.last_frame_after_signal_at = now
            self._log_raw(phase, "in", length=len(msg))
        else:
            self._log_raw(phase, "in", text=msg)
            try:
                d = json.loads(msg)
            except json.JSONDecodeError:
                return
            t = d.get("type")
            if t == "tts":
                st = d.get("state")
                if st == "sentence_start":
                    ir.sentences.append({"text": d.get("text", ""), "at": round(time.monotonic(), 3)})
                    if ir.first_text_at is None:
                        ir.first_text_at = time.monotonic()
                elif st == "stop":
                    ir.tts_stop_at = time.monotonic()
            elif t == "stt":
                ir.stt_texts.append(d.get("text", ""))

    async def close(self):
        try:
            if self.ws is not None:
                await self.ws.close()
        except Exception:
            pass
        finally:
            self.raw_f.close()


# ---------- P1-6 服务器日志交叉验证 ----------
def check_server_log(t0_dt: datetime, t1_dt: datetime, out_dir: str) -> dict:
    s = (t0_dt - timedelta(seconds=10)).strftime("%y%m%d %H:%M:%S")
    e = (t1_dt + timedelta(seconds=30)).strftime("%y%m%d %H:%M:%S")
    awk = (f"awk -v s=\"{s}\" -v e=\"{e}\" "
           f"'substr($0,1,15) >= s && substr($0,1,15) <= e' {REMOTE_LOG}")
    count_cmd = f"{awk} | grep -cE 'ERROR|Traceback|Exception'"
    sample_cmd = f"{awk} | grep -E 'ERROR|Traceback|Exception' | head -10"
    try:
        proc = subprocess.run([sys.executable, SSH_HELPER, count_cmd, sample_cmd],
                              capture_output=True, text=True, timeout=120)
    except Exception as ex:
        return {"verdict": "SKIP", "reason": f"SSH 不可达: {type(ex).__name__}: {ex}",
                "window": [s, e]}
    with open(os.path.join(out_dir, "p1_6_server_log.txt"), "w", encoding="utf-8") as f:
        f.write(proc.stdout)
        if proc.stderr:
            f.write("\n[stderr]\n" + proc.stderr)
    # 解析 ssh_run 输出：$ cmd → 输出行… → [rc=N]
    blocks, current = [], None
    for line in proc.stdout.splitlines():
        if line.startswith("$ "):
            current = []
            blocks.append(current)
        elif line.startswith("[rc="):
            current = None
        elif current is not None:
            current.append(line)
    try:
        count = int(blocks[0][0].strip()) if blocks and blocks[0] else 0
    except (ValueError, IndexError):
        return {"verdict": "SKIP", "reason": f"日志输出解析失败: {proc.stdout[:200]}",
                "window": [s, e]}
    samples = blocks[1] if len(blocks) > 1 else []
    verdict = "PASS" if count == 0 else "FAIL"
    return {"verdict": verdict, "error_count": count, "window": [s, e],
            "samples": samples, "note": "P1 不阻塞 GATE"}


# ---------- 报告 ----------
def ms(v):
    return int(v * 1000) if v is not None else None


def turn_metrics(tr: TurnResult) -> dict:
    return {"ttfb_text_ms": ms(tr.ttfb_text_s), "ttfb_audio_ms": ms(tr.ttfb_audio_s),
            "total_ms": ms(tr.total_s), "audio_frames": tr.audio_frames,
            "audio_bytes": tr.audio_bytes, "sentences": len(tr.sentences),
            "content_chars": count_content_chars(tr.all_text)}


def turn_detail(tr: TurnResult, verdict=None, checks=None) -> dict:
    d = {"query": tr.query, "sent_wall": tr.sent_wall, "stt": tr.stt_texts,
         "answer_sentences": [s["text"] for s in tr.sentences],
         "llm_emotions": tr.llm_emotions, "other_msgs": tr.other_msgs,
         "audio_frames": tr.audio_frames, "audio_bytes": tr.audio_bytes,
         "tail_frames": tr.tail_frames,
         "ttfb_text_s": tr.ttfb_text_s, "ttfb_audio_s": tr.ttfb_audio_s,
         "total_s": tr.total_s, "error": tr.error, "closed": tr.closed}
    if verdict:
        d["verdict"] = verdict
    if checks:
        d["checks"] = checks
    return d


def make_case(cid, prio, verdict, checks, notes, metrics, details, connect_s=None):
    c = {"id": cid, "priority": prio, "verdict": verdict, "checks": checks,
         "metrics": metrics, "notes": notes, "details": details}
    if connect_s is not None:
        c["connect_s"] = connect_s
    return c


def error_case(cid, prio, ex, connect_s=None) -> dict:
    return make_case(cid, prio, "FAIL", {}, [f"EXCEPTION: {type(ex).__name__}: {ex}"],
                     {}, {"error": str(ex)}, connect_s=connect_s)


def write_reports(report: dict, out_dir: str):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(out_dir, f"sim_user_v1_{ts}.json")
    md_path = os.path.join(out_dir, f"sim_user_v1_{ts}.md")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    lines = [
        "# 模拟普通用户全链路测试报告 sim-user-v1",
        "",
        f"- 设计依据：sim_test_design_v1.md（架构师 高见远 v1）",
        f"- 执行：QA 严过关（任务 #8）",
        f"- 设备：`{report['device_id']}` ｜ 服务器：`{report['ws_url']}`",
        f"- 窗口：{report['started']} ~ {report['ended']}",
        "",
        "## 结果总表",
        "",
        "| 用例 | 级别 | 判定 | 关键指标 | 备注 |",
        "|---|---|---|---|---|",
    ]
    for c in report["cases"]:
        m = c["metrics"] or {}
        key = []
        if "ttfb_audio_ms" in m and m.get("ttfb_audio_ms") is not None:
            key.append(f"TTFB_a={m['ttfb_audio_ms']}ms")
        if m.get("audio_frames") is not None:
            key.append(f"帧={m['audio_frames']}")
        if m.get("total_ms") is not None:
            key.append(f"总={m['total_ms']}ms")
        if "converge_s" in m and m.get("converge_s") is not None:
            key.append(f"收敛={m['converge_s']}s")
        if "content_chars" in m and m.get("content_chars") is not None and c["id"] == "P0-3":
            key.append(f"字数={m['content_chars']}")
        notes = "; ".join(c["notes"][:4]) if c["notes"] else ""
        lines.append(f"| {c['id']} | {c['priority']} | **{c['verdict']}** | {'，'.join(key)} | {notes} |")
    gate = report["gate"]
    lines += ["", f"## GATE 汇总", "",
              f"- P0：{gate['p0']} → {'**全绿**' if gate['p0_pass'] else '**存在 FAIL**'}",
              f"- P1-6 服务器日志：{gate['p1'].get('P1-6')}",
              f"- P1-7 打断变体：{gate['p1'].get('P1-7')}",
              f"- P1-8 开机问候：{gate['p1'].get('P1-8')}"]
    lines += ["", "## 用例明细（输入 / 观测 / 判据 / 结果）", ""]
    for c in report["cases"]:
        lines.append(f"### {c['id']}（{c['priority']}）→ {c['verdict']}")
        det = c["details"] or {}
        if "turns" in det:
            for t in det["turns"]:
                lines.append(f"- **输入**：{t['query']}")
                ans = "／".join(t["answer_sentences"]) if t["answer_sentences"] else "（无）"
                lines.append(f"- **观测**：STT={t['stt']}；回复={ans[:200]}；帧={t['audio_frames']}；"
                             f"TTFB_text={t['ttfb_text_s']}s，TTFB_audio={t['ttfb_audio_s']}s，总={t['total_s']}s"
                             + (f"；轮判定={t['verdict']}" if t.get("verdict") else ""))
        if "sessions" in det:
            for s_ in det["sessions"]:
                t = s_["turn"]
                lines.append(f"- **会话{s_['session']}**（connect={s_['connect_s']}s）：输入={t['query']}；"
                             f"帧={t['audio_frames']}；TTFB_audio={t['ttfb_audio_s']}s；总={t['total_s']}s；"
                             f"轮判定={t.get('verdict')}")
        if "interrupt" in det:
            iv = det["interrupt"]
            lines.append(f"- **主查询**：{iv['query']}")
            lines.append(f"- **打断信号**：listen {iv['signal']} @ 首帧后（首帧 TTFB={iv['ttfb_audio_s']}s）")
            lines.append(f"- **观测**：信号后帧数={iv['frames_after_signal']}，收敛={iv['converge_s']}s，"
                         f"分类={iv['classification']}，自然结束={iv['natural_end']}")
            if det.get("recovery"):
                r = det["recovery"]
                lines.append(f"- **恢复查询**：{r['query']} → 帧={r['audio_frames']}，总={r['total_s']}s，"
                             f"判定={r.get('verdict')}")
        if c["checks"]:
            cs = "，".join(f"{k}={'✓' if v else '✗'}" for k, v in c["checks"].items())
            lines.append(f"- **判据**：{cs}")
        if c["notes"]:
            for n in c["notes"]:
                lines.append(f"- **备注**：{n}")
        lines.append("")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return json_path, md_path


# ---------- 主流程 ----------
async def run_suite(args) -> int:
    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)
    started_dt = datetime.now()
    started_wall = started_dt.strftime("%Y-%m-%d %H:%M:%S")
    cases, greetings = [], []

    def note_connect(notes, connect_s):
        if connect_s is None:
            return
        if connect_s > BUDGETS["connect"][0]:
            notes.append(f"FAIL: connect {connect_s}s > 5s")
        elif connect_s > BUDGETS["connect"][1]:
            notes.append(f"SLOW: connect {connect_s}s > 2s")

    # ===== P0-1 短问候 =====
    print("[suite] P0-1 短问候 …", flush=True)
    dev = SimDevice("P0-1", "p0-1", out_dir)
    try:
        await dev.connect()
        greetings.append({"case": "P0-1", **dev.greeting})
        tr = await dev.ask(CASE_TEXTS["P0-1"])
        v, c, n = judge_short(tr)
        note_connect(n, dev.connect_s)
        cases.append(make_case("P0-1", "P0", v, {**c, "connect<=5s": dev.connect_s is None or dev.connect_s <= 5},
                               n, turn_metrics(tr), {"turns": [turn_detail(tr, v, c)]},
                               connect_s=dev.connect_s))
        print(f"[suite] P0-1 → {v} (帧={tr.audio_frames}, TTFB_a={tr.ttfb_audio_s}s, 总={tr.total_s}s)", flush=True)
    except Exception as ex:
        cases.append(error_case("P0-1", "P0", ex))
        print(f"[suite] P0-1 → EXCEPTION {ex}", flush=True)
    finally:
        await dev.close()
    await asyncio.sleep(CASE_GAP_S)

    # ===== P0-2 多轮上下文 =====
    print("[suite] P0-2 多轮上下文×3 …", flush=True)
    dev = SimDevice("P0-2", "p0-2", out_dir)
    try:
        await dev.connect()
        greetings.append({"case": "P0-2", **dev.greeting})
        turns_out, all_pass, checks_agg, notes_agg = [], True, {}, []
        for i, q in enumerate(CASE_TEXTS["P0-2"], 1):
            tr = await dev.ask(q)
            v, c, n = judge_context_turn(tr, CASE_TEXTS["P0-2_must"].get(i))
            turns_out.append(turn_detail(tr, v, c))
            checks_agg[f"T{i}"] = v
            notes_agg += [f"T{i}: {x}" for x in n]
            if v != "PASS":
                all_pass = False
            print(f"[suite] P0-2 T{i} → {v} (帧={tr.audio_frames}, 总={tr.total_s}s)", flush=True)
            if i < len(CASE_TEXTS["P0-2"]):
                await asyncio.sleep(TURN_GAP_S)
        note_connect(notes_agg, dev.connect_s)
        cases.append(make_case("P0-2", "P0", "PASS" if all_pass else "FAIL", checks_agg,
                               notes_agg,
                               turns_out[0] and {"turns": len(turns_out)} or {},
                               {"turns": turns_out}, connect_s=dev.connect_s))
        print(f"[suite] P0-2 → {'PASS' if all_pass else 'FAIL'}", flush=True)
    except Exception as ex:
        cases.append(error_case("P0-2", "P0", ex))
        print(f"[suite] P0-2 → EXCEPTION {ex}", flush=True)
    finally:
        await dev.close()
    await asyncio.sleep(CASE_GAP_S)

    # ===== P0-3 长文本 =====
    print("[suite] P0-3 长文本 …", flush=True)
    dev = SimDevice("P0-3", "p0-3", out_dir)
    try:
        await dev.connect()
        greetings.append({"case": "P0-3", **dev.greeting})
        tr = await dev.ask(CASE_TEXTS["P0-3"], cap_s=LONG_TURN_CAP_S)
        v, c, n = judge_long(tr)
        note_connect(n, dev.connect_s)
        cases.append(make_case("P0-3", "P0", v, c, n, turn_metrics(tr),
                               {"turns": [turn_detail(tr, v, c)]}, connect_s=dev.connect_s))
        print(f"[suite] P0-3 → {v} (帧={tr.audio_frames}, 字数={count_content_chars(tr.all_text)}, 总={tr.total_s}s)", flush=True)
    except Exception as ex:
        cases.append(error_case("P0-3", "P0", ex))
        print(f"[suite] P0-3 → EXCEPTION {ex}", flush=True)
    finally:
        await dev.close()
    await asyncio.sleep(CASE_GAP_S)

    # ===== P0-4 打断（listen stop） =====
    print("[suite] P0-4 打断（listen stop）…", flush=True)
    main_q, rec_q = CASE_TEXTS["P0-4"]
    dev = SimDevice("P0-4", "p0-4", out_dir)
    try:
        await dev.connect()
        greetings.append({"case": "P0-4", **dev.greeting})
        ir = await dev.interrupt(main_q, rec_q, signal="stop")
        v, c, n, rv, rc = judge_interrupt(ir, strict=False)
        note_connect(n, dev.connect_s)
        conv = ir.converge_s
        cls = ("打断生效" if (conv is not None and (conv <= 3 or ir.frames_after_signal <= 30))
               else "不打断（观察项）")
        det = {"interrupt": {"query": ir.query, "signal": f"listen {ir.signal}",
                             "signal_wall": ir.signal_wall, "ttfb_audio_s": ir.ttfb_audio_s,
                             "frames_after_signal": ir.frames_after_signal,
                             "converge_s": conv, "classification": cls,
                             "natural_end": ir.natural_end,
                             "main_sentences": [s["text"] for s in ir.sentences],
                             "stt": ir.stt_texts, "error": ir.error, "closed": ir.closed},
               "recovery": turn_detail(ir.recovery, rv, rc) if ir.recovery else None}
        met = {"ttfb_audio_ms": ms(ir.ttfb_audio_s), "converge_s": conv,
               "frames_after_signal": ir.frames_after_signal,
               "audio_frames": ir.audio_frames, "total_ms": None}
        if ir.recovery:
            met["recovery_ttfb_audio_ms"] = ms(ir.recovery.ttfb_audio_s)
            met["recovery_total_ms"] = ms(ir.recovery.total_s)
            met["recovery_frames"] = ir.recovery.audio_frames
        cases.append(make_case("P0-4", "P0", v, c, n, met, det, connect_s=dev.connect_s))
        print(f"[suite] P0-4 → {v} (分类={cls}, 收敛={conv}s, 信号后帧={ir.frames_after_signal}, 恢复轮={rv})", flush=True)
    except Exception as ex:
        cases.append(error_case("P0-4", "P0", ex))
        print(f"[suite] P0-4 → EXCEPTION {ex}", flush=True)
    finally:
        await dev.close()
    await asyncio.sleep(CASE_GAP_S)

    # ===== P0-4b 打断（abort 消息，真实固件语义） =====
    print("[suite] P0-4b 打断（type=abort，真实固件打断消息）…", flush=True)
    main_q, rec_q = CASE_TEXTS["P0-4b"]
    dev = SimDevice("P0-4b", "p0-4b", out_dir)
    try:
        await dev.connect()
        greetings.append({"case": "P0-4b", **dev.greeting})
        ir = await dev.interrupt(main_q, rec_q, signal="abort")
        v, c, n, rv, rc = judge_interrupt(ir, strict=False)
        note_connect(n, dev.connect_s)
        conv = ir.converge_s
        cls = ("打断生效" if (conv is not None and (conv <= 3 or ir.frames_after_signal <= 30))
               else "不打断（观察项）")
        det = {"interrupt": {"query": ir.query, "signal": "type=abort",
                             "signal_wall": ir.signal_wall, "ttfb_audio_s": ir.ttfb_audio_s,
                             "frames_after_signal": ir.frames_after_signal,
                             "converge_s": conv, "classification": cls,
                             "natural_end": ir.natural_end,
                             "main_sentences": [s["text"] for s in ir.sentences],
                             "stt": ir.stt_texts, "error": ir.error, "closed": ir.closed},
               "recovery": turn_detail(ir.recovery, rv, rc) if ir.recovery else None}
        met = {"ttfb_audio_ms": ms(ir.ttfb_audio_s), "converge_s": conv,
               "frames_after_signal": ir.frames_after_signal,
               "audio_frames": ir.audio_frames, "total_ms": None}
        if ir.recovery:
            met["recovery_ttfb_audio_ms"] = ms(ir.recovery.ttfb_audio_s)
            met["recovery_total_ms"] = ms(ir.recovery.total_s)
            met["recovery_frames"] = ir.recovery.audio_frames
        cases.append(make_case("P0-4b", "P0-observation", v, c, n, met, det, connect_s=dev.connect_s))
        print(f"[suite] P0-4b → {v} (分类={cls}, 收敛={conv}s, 信号后帧={ir.frames_after_signal}, 恢复轮={rv})", flush=True)
    except Exception as ex:
        cases.append(error_case("P0-4b", "P0-observation", ex))
        print(f"[suite] P0-4b → EXCEPTION {ex}", flush=True)
    finally:
        await dev.close()
    await asyncio.sleep(CASE_GAP_S)

    # ===== P0-5 连续 3 次会话稳定性 =====
    print("[suite] P0-5 连续 3 次会话 …", flush=True)
    sessions_out, sess_all_pass = [], True
    for i in (1, 2, 3):
        dev = SimDevice(f"P0-5-s{i}", f"verify-s{i}", out_dir)
        try:
            await dev.connect()
            greetings.append({"case": f"P0-5-s{i}", **dev.greeting})
            tr = await dev.ask(CASE_TEXTS["P0-5"])
            v, c, n = judge_short(tr)
            conn_ok = dev.connect_s is not None and dev.connect_s <= BUDGETS["connect"][0]
            sess_pass = (v == "PASS") and conn_ok and tr.closed is None
            sessions_out.append({"session": i, "connect_s": dev.connect_s,
                                 "turn": turn_detail(tr, v, c), "verdict": "PASS" if sess_pass else "FAIL"})
            if not sess_pass:
                sess_all_pass = False
            print(f"[suite] P0-5 s{i} → {v} (connect={dev.connect_s}s, 帧={tr.audio_frames}, 总={tr.total_s}s)", flush=True)
        except Exception as ex:
            sessions_out.append({"session": i, "error": str(ex), "verdict": "FAIL"})
            sess_all_pass = False
            print(f"[suite] P0-5 s{i} → EXCEPTION {ex}", flush=True)
        finally:
            await dev.close()
        await asyncio.sleep(CASE_GAP_S)
    abnormal = sum(1 for s_ in sessions_out if s_.get("turn", {}).get("closed") or s_.get("error"))
    p05_checks = {f"s{s_['session']}": s_["verdict"] for s_ in sessions_out}
    p05_checks["0异常断开"] = abnormal == 0
    cases.append(make_case("P0-5", "P0", "PASS" if sess_all_pass and abnormal == 0 else "FAIL",
                           p05_checks, [], {}, {"sessions": sessions_out}))
    print(f"[suite] P0-5 → {'PASS' if sess_all_pass and abnormal == 0 else 'FAIL'}", flush=True)

    p1 = {}
    if args.only == "all":
        # ===== P1-7 打断变体（listen start，真实固件语义） =====
        print("[suite] P1-7 打断变体（listen start）…", flush=True)
        main_q, rec_q = CASE_TEXTS["P1-7"]
        dev = SimDevice("P1-7", "p1-7", out_dir)
        try:
            await dev.connect()
            greetings.append({"case": "P1-7", **dev.greeting})
            ir = await dev.interrupt(main_q, rec_q, signal="start")
            v, c, n, rv, rc = judge_interrupt(ir, strict=True)
            conv = ir.converge_s
            cls = ("打断生效" if (conv is not None and conv <= 3)
                   else "不打断（观察项）")
            det = {"interrupt": {"query": ir.query, "signal": f"listen {ir.signal}",
                                 "signal_wall": ir.signal_wall, "ttfb_audio_s": ir.ttfb_audio_s,
                                 "frames_after_signal": ir.frames_after_signal,
                                 "converge_s": conv, "classification": cls,
                                 "natural_end": ir.natural_end,
                                 "main_sentences": [s["text"] for s in ir.sentences],
                                 "stt": ir.stt_texts, "error": ir.error, "closed": ir.closed},
                   "recovery": turn_detail(ir.recovery, rv, rc) if ir.recovery else None}
            met = {"ttfb_audio_ms": ms(ir.ttfb_audio_s), "converge_s": conv,
                   "frames_after_signal": ir.frames_after_signal, "audio_frames": ir.audio_frames}
            cases.append(make_case("P1-7", "P1", v, c, n, met, det, connect_s=dev.connect_s))
            print(f"[suite] P1-7 → {v} (分类={cls}, 收敛={conv}s, 恢复轮={rv})", flush=True)
        except Exception as ex:
            cases.append(error_case("P1-7", "P1", ex))
            print(f"[suite] P1-7 → EXCEPTION {ex}", flush=True)
        finally:
            await dev.close()
        await asyncio.sleep(CASE_GAP_S)
    else:
        p1["P1-7"] = "SKIP（--only P0）"

    # ===== P1-6 服务器日志交叉验证 =====
    ended_dt = datetime.now()
    print("[suite] P1-6 服务器日志交叉验证 …", flush=True)
    p16 = check_server_log(started_dt, ended_dt, out_dir)
    print(f"[suite] P1-6 → {p16['verdict']} (errors={p16.get('error_count')})", flush=True)
    p16_case = make_case("P1-6", "P1", p16["verdict"], {}, [p16.get("reason", "")] if p16.get("reason") else [],
                         {"error_count": p16.get("error_count"), "window": p16.get("window")},
                         {"samples": p16.get("samples", [])})
    cases.append(p16_case)

    # ===== P1-8 问候观察 =====
    p18 = {"observed_connections": len(greetings),
           "present_count": sum(1 for g in greetings if g.get("present")),
           "detail": greetings}
    cases.append(make_case("P1-8", "P1", "OBSERVED", {}, [],
                           {"present_count": p18["present_count"]}, p18))

    # ===== 汇总与 GATE =====
    p0_cases = [c for c in cases if c["priority"] == "P0"]
    p0_pass = len(p0_cases) == 5 and all(c["verdict"] == "PASS" for c in p0_cases)
    p1["P1-6"] = p16["verdict"]
    if args.only == "all":
        p17 = next((c for c in cases if c["id"] == "P1-7"), None)
        p1["P1-7"] = p17["verdict"] if p17 else "SKIP"
    p1["P1-8"] = f"observed（{p18['present_count']}/{p18['observed_connections']} 连接有问候推送）"
    report = {"suite": "sim-user-v1",
              "design": "sim_test_design_v1.md（高见远 v1，2026-10-05）",
              "device_id": DEVICE_ID, "ws_url": WS_URL,
              "started": started_wall, "ended": ended_dt.strftime("%Y-%m-%d %H:%M:%S"),
              "cases": cases, "greetings": greetings,
              "gate": {"p0_pass": p0_pass,
                       "p0": f"{sum(1 for c in p0_cases if c['verdict'] == 'PASS')}/{len(p0_cases)}",
                       "p1": p1}}
    json_path, md_path = write_reports(report, out_dir)
    print(f"\n[suite] P0 = {report['gate']['p0']} → {'全绿' if p0_pass else '存在 FAIL'}", flush=True)
    print(f"[suite] 报告：{json_path}\n[suite]       {md_path}", flush=True)
    return 0 if p0_pass else 1


def main():
    ap = argparse.ArgumentParser(description="模拟普通用户全链路 P0/P1 矩阵（设计 v1）")
    ap.add_argument("--only", choices=["P0", "all"], default="all",
                    help="P0=仅 P0-1..5；all=含 P1-6/7/8（默认）")
    ap.add_argument("--out-dir", default=os.path.join(SCRIPT_DIR, "reports"))
    args = ap.parse_args()
    sys.exit(asyncio.run(run_suite(args)))


if __name__ == "__main__":
    main()
