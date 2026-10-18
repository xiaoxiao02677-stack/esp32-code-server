#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""push_chain_simulator.py — 小智推送音频·硬件通信链路模拟器

忠实复刻固件通知播放链路的语义，对任意 URL/文件判定「设备能否完整播放」：

固件链路（small_secreen/yuhe-esp32）：
  yh_protocol.cc SEND_NOTIFY → Application::NotifyAudio → NotifyPlayer
  (main/notify/notify_player.cc)
    HTTP GET，请求头：Accept: audio/ogg, application/ogg
                      Accept-Encoding: identity
    2xx 才播；1024 字节块流式读取喂给 OggDemuxer；EOF 时 Finish() 判定
  OggDemuxer (main/audio/demuxer/ogg_demuxer.cc) 硬约束：
    - 仅 Ogg Opus；首包必须 "OpusHead"（声道数必须 1；8~18 字节的截断头=错误）
    - 次包必须 "OpusTags"；非 Opus 的 Ogg 流（Vorbis 等）包被丢弃
    - 帧时长仅支持 SILK 10/20/40/60ms、CELT 2.5/5/10/20ms、混合 10/20ms 档
    - Finish 条件：无错误 && head_seen && tags_seen && mono && packet_count>0
                  && 干净收尾（不处于页/包中间）——不要求 EOS 标志位
    采样率 8000/12000/16000/24000/48000 之外的 OpusHead 归一为 48000（合法）

用法：
  python push_chain_simulator.py check <url>          # 模拟设备拉流判定
  python push_chain_simulator.py check-file <path>    # 本地文件判定
  python push_chain_simulator.py scan <dir>           # 批量扫描，退出码=不可播数>0?1:0
  附加 --json 输出机器可读结果

仅依赖 Python 标准库（3.8+）。
"""
import argparse
import json
import os
import sys
import time
import urllib.request

# 固件常量（notify_player.cc）
FIRMWARE_ACCEPT = "audio/ogg, application/ogg"
FIRMWARE_READ_CHUNK = 1024  # kHttpReadBufferSize
FIRMWARE_HTTP_TIMEOUT = 5.0  # kHttpTimeoutMs

# 失败原因枚举（对齐固件日志语义）
NO_OGG_PAGE = "NO_OGG_PAGE"            # 全程找不到 OggS 页（如 MP3/二进制垃圾）
NO_OPUSHEAD = "NO_OPUSHEAD"            # 有 Ogg 页但无 OpusHead（如 Vorbis/截断在头部前）
NO_OPUSTAGS = "NO_OPUSTAGS"            # 有 OpusHead 但无 OpusTags
NOT_MONO = "NOT_MONO"                  # OpusHead 声道数 != 1
BAD_PACKET_DURATION = "BAD_PACKET_DURATION"  # Opus 帧时长不在支持档位
DEMUXER_ERROR = "DEMUXER_ERROR"        # 页结构非法（版本/段数/截断在页中间等）
ZERO_PACKETS = "ZERO_PACKETS"          # 头标签齐全但零音频包
TRUNCATED = "TRUNCATED"                # 流在页/包中间截断（Finish 干净收尾不满足）
HTTP_ERROR = "HTTP_ERROR"              # HTTP 层失败（非 2xx/网络错误/空响应）
EMPTY_FILE = "EMPTY_FILE"


def opus_packet_duration_ms(data: bytes):
    """复刻 OggDemuxer::GetOpusPacketDurationMs，返回毫秒，非法返回 -1。"""
    if not data:
        return -1
    toc = data[0]
    config = toc >> 3
    if config < 12:  # SILK
        silk_us = (10000, 20000, 40000, 60000)
        frame_duration_us = silk_us[config & 0x03]
    elif config < 16:  # hybrid
        frame_duration_us = 20000 if (config & 0x01) else 10000
    else:  # CELT
        celt_us = (2500, 5000, 10000, 20000)
        frame_duration_us = celt_us[config & 0x03]
    code = toc & 0x03
    if code == 0:
        frame_count = 1
    elif code in (1, 2):
        frame_count = 2
    else:
        if len(data) < 2:
            return -1
        frame_count = data[1] & 0x3F
    total_us = frame_duration_us * frame_count
    if frame_count == 0 or total_us > 120000 or total_us % 1000 != 0:
        return -1
    return total_us // 1000


VALID_OPUS_RATES = {8000, 12000, 16000, 24000, 48000}


class OggDemuxerSim:
    """增量式 Ogg Opus 解复用器（语义对齐 ogg_demuxer.cc）。

    feed(chunk) 按 1024 字节块喂入；finish() 对应固件 EOF 时的 Finish() 判定。
    """

    def __init__(self):
        self.state = "FIND_PAGE"
        self._carry = b""          # 跨块未消费字节
        self._partial = b""        # FIND_PAGE 跨块部分匹配窗口（≤3 字节）
        self._page = None          # 当前页缓冲（已含 OggS 起 27 字节头）
        self._need = 0             # 还需读入的字节数
        self._seg_table = []       # 段表
        self._seg_idx = 0
        self._seg_remaining = 0
        self._packet = bytearray()
        # Opus 流状态
        self.head_seen = False
        self.tags_seen = False
        self.mono = False
        self.sample_rate = 48000
        self.packet_count = 0
        self.page_count = 0
        self.total_duration_ms = 0
        self.has_error = False
        self.error_reason = None
        self.error_detail = ""

    def _fail(self, reason, detail=""):
        self.has_error = True
        self.error_reason = reason
        self.error_detail = detail

    def feed(self, chunk: bytes):
        """喂入一块数据；返回后可用 has_error 提前中止（复刻 packet_error 语义）。"""
        buf = self._partial + chunk
        self._partial = b""
        pos = 0
        n = len(buf)
        while pos < n and not self.has_error:
            if self.state == "FIND_PAGE":
                # 跨块部分匹配：先尝试用 carry 前缀拼出 OggS
                idx = buf.find(b"OggS", pos)
                if idx < 0:
                    # 保留最长可能是 OggS 前缀的尾部（≤3 字节）
                    keep = 0
                    for k in range(min(3, n - pos), 0, -1):
                        if b"OggS".startswith(buf[n - k:n]):
                            keep = k
                            break
                    self._partial = buf[n - keep:n] if keep else b""
                    return
                self.page_count += 1
                pos = idx + 4
                avail = min(23, n - pos)
                # _page 始终是完整 27 字节页头（含 OggS 4 字节），对齐固件 ctx_.header
                self._page = bytearray(b"OggS") + bytearray(buf[pos:pos + avail])
                pos += avail
                if avail == 23:
                    if not self._parse_header_done():
                        return
                else:
                    self._need = 27 - len(self._page)
                    self.state = "PARSE_HEADER"
                    return
            elif self.state == "PARSE_HEADER":
                take = min(n - pos, self._need)
                self._page.extend(buf[pos:pos + take])
                pos += take
                self._need -= take
                if self._need > 0:
                    return
                # _page 现为完整 27 字节页头
                if not self._parse_header_done():
                    return
            elif self.state == "PARSE_SEGMENTS":
                take = min(n - pos, self._need)
                got = len(self._seg_table)
                self._seg_table.extend(buf[pos:pos + take])
                pos += take
                self._need -= take
                if self._need > 0:
                    return
                self.state = "PARSE_DATA"
                self._seg_idx = 0
                self._seg_remaining = 0
            elif self.state == "PARSE_DATA":
                if not self._parse_data(buf, pos):
                    return
                pos = self._data_consumed
                if self.state == "PARSE_DATA" and self._seg_idx >= len(self._seg_table):
                    # 整页数据读完（body 可能有剩余但段表已尽——对齐固件：
                    # 段表消费完即回 FIND_PAGE）
                    self.state = "FIND_PAGE"
        # while 结束

    # ---- 内部：页头完成校验 ----
    def _parse_header_done(self):
        h = self._page
        version = h[4]
        if version != 0:
            self._fail(DEMUXER_ERROR, f"Invalid Ogg version: {version}")
            return False
        seg_count = h[26]
        if seg_count == 0:
            self.state = "FIND_PAGE"
            return True
        if seg_count > 255:
            self._fail(DEMUXER_ERROR, f"Invalid Ogg segment count: {seg_count}")
            return False
        self._seg_table = []
        self._need = seg_count
        self.state = "PARSE_SEGMENTS"
        return True

    # ---- 内部：段数据处理；返回 False 表示需要更多数据/出错 ----
    def _parse_data(self, buf, pos):
        n = len(buf)
        while self._seg_idx < len(self._seg_table):
            seg_len = self._seg_table[self._seg_idx]
            if self._seg_remaining > 0:
                seg_len = self._seg_remaining
            else:
                self._seg_remaining = seg_len
            if seg_len > 0 and pos >= n:
                self._data_consumed = pos
                return False  # 等下一块
            take = min(n - pos, seg_len)
            self._packet.extend(buf[pos:pos + take])
            pos += take
            self._seg_remaining -= take
            if self._seg_remaining > 0:
                self._data_consumed = pos
                return False
            # 段完整
            seg_continued = (self._seg_table[self._seg_idx] == 255)
            if not seg_continued:
                self._on_packet(bytes(self._packet))
                self._packet = bytearray()
            self._seg_idx += 1
            self._seg_remaining = 0
        self._data_consumed = pos
        return True

    # ---- 内部：完整包回调（对齐 PARSE_DATA 中组包完成后的处理）----
    def _on_packet(self, pkt: bytes):
        if not self.head_seen:
            if len(pkt) >= 8 and pkt[:8] == b"OpusHead":
                self.head_seen = True
                if len(pkt) >= 19:
                    ch = pkt[9]
                    if ch == 1:
                        self.mono = True
                    else:
                        self._fail(NOT_MONO, f"channels={ch}（固件仅支持单声道）")
                        return
                    rate = int.from_bytes(pkt[12:16], "little")
                    self.sample_rate = rate if rate in VALID_OPUS_RATES else 48000
                else:
                    self._fail(DEMUXER_ERROR, f"OpusHead 截断（{len(pkt)} 字节 <19）")
                    return
            # 非 OpusHead 的前置包：固件丢弃并告警，不报错
            return
        if not self.tags_seen:
            if len(pkt) >= 8 and pkt[:8] == b"OpusTags":
                self.tags_seen = True
            return
        # 音频包
        dur = opus_packet_duration_ms(pkt)
        if dur <= 0:
            self._fail(BAD_PACKET_DURATION,
                       f"packet#{self.packet_count + 1} TOC=0x{pkt[0]:02x}")
            return
        self.packet_count += 1
        self.total_duration_ms += dur

    # ---- 对应固件 Finish() ----
    def finish(self):
        """EOF 判定：返回 (playable, reason, detail)。"""
        if self.has_error:
            return False, self.error_reason, self.error_detail
        # 干净收尾：不处于页/段/包中间（对齐 state==FIND_PAGE && bytes_needed==4 && packet_len==0）
        mid_page = self.state != "FIND_PAGE"
        mid_packet = len(self._packet) > 0 or self._seg_remaining > 0 or (
            self.state == "PARSE_DATA" and self._seg_idx < len(self._seg_table))
        if mid_page or mid_packet:
            return False, TRUNCATED, f"state={self.state} 未收尾"
        if not self.head_seen:
            if self.page_count == 0:
                return False, NO_OGG_PAGE, "未发现任何 OggS 页（非 Ogg 容器）"
            return False, NO_OPUSHEAD, f"发现 {self.page_count} 页但无 OpusHead"
        if not self.tags_seen:
            return False, NO_OPUSTAGS, "有 OpusHead 但无 OpusTags"
        if not self.mono:
            return False, NOT_MONO, "OpusHead 声道数非 1"
        if self.packet_count == 0:
            return False, ZERO_PACKETS, "零音频包"
        return True, "OK", ""


def http_get_like_device(url: str):
    """复刻 NotifyPlayer 的 HTTP 拉流：同款请求头 + 1KB 块读。

    返回 (meta, chunks) 或抛 RuntimeError（HTTP_ERROR）。
    """
    req = urllib.request.Request(url, headers={
        "Accept": FIRMWARE_ACCEPT,
        "Accept-Encoding": "identity",
        "User-Agent": "yuhe-push-chain-simulator/1.0",
    })
    t0 = time.time()
    try:
        resp = urllib.request.urlopen(req, timeout=FIRMWARE_HTTP_TIMEOUT + 25)
    except Exception as e:
        raise RuntimeError(f"{HTTP_ERROR}: 打开失败 {e}")
    status = getattr(resp, "status", None) or resp.getcode()
    if not (200 <= status < 300):
        resp.close()
        raise RuntimeError(f"{HTTP_ERROR}: HTTP {status}")
    chunks = []
    total = 0
    while True:
        block = resp.read(FIRMWARE_READ_CHUNK)
        if not block:
            break
        chunks.append(block)
        total += len(block)
    meta = {
        "status": status,
        "content_type": resp.headers.get("Content-Type"),
        "content_length_header": resp.headers.get("Content-Length"),
        "bytes_received": total,
        "elapsed_s": round(time.time() - t0, 3),
        "server": resp.headers.get("Server"),
    }
    resp.close()
    return meta, chunks


def judge_chunks(chunks):
    """按固件语义判定字节流；返回结果 dict。"""
    dem = OggDemuxerSim()
    for c in chunks:
        dem.feed(c)
        if dem.has_error:
            break  # 对应固件 packet_error 提前中止下载
    playable, reason, detail = dem.finish()
    return {
        "playable": playable,
        "reason": reason,
        "detail": detail,
        "pages": dem.page_count,
        "packets": dem.packet_count,
        "duration_ms": dem.total_duration_ms,
        "sample_rate": dem.sample_rate,
        "bytes_fed": sum(len(c) for c in chunks),
    }


def check_url(url: str):
    try:
        meta, chunks = http_get_like_device(url)
    except RuntimeError as e:
        return {"url": url, "playable": False, "reason": str(e).split(":")[0],
                "detail": str(e), "http": None}
    res = judge_chunks(chunks)
    res["url"] = url
    res["http"] = meta
    hdr_len = meta["content_length_header"]
    if hdr_len is not None and int(hdr_len) != meta["bytes_received"]:
        res.setdefault("detail", "")
        res["detail"] += f" [Content-Length={hdr_len} 与实收 {meta['bytes_received']} 不符]"
    return res


def check_file(path: str):
    data = open(path, "rb").read()
    if not data:
        return {"file": path, "playable": False, "reason": EMPTY_FILE, "detail": ""}
    chunks = [data[i:i + FIRMWARE_READ_CHUNK] for i in range(0, len(data), FIRMWARE_READ_CHUNK)]
    res = judge_chunks(chunks)
    res["file"] = path
    return res


def human_line(res):
    where = res.get("url") or res.get("file")
    verdict = "PLAYABLE ✅" if res["playable"] else f"NOT PLAYABLE ❌ [{res['reason']}]"
    extra = []
    if "http" in res and res["http"]:
        h = res["http"]
        extra.append(f"HTTP {h['status']} {h['content_type']} "
                     f"{h['bytes_received']}B/{h['elapsed_s']}s")
    if res.get("pages") is not None:
        extra.append(f"pages={res['pages']} packets={res['packets']} "
                     f"dur={res['duration_ms']}ms rate={res['sample_rate']}")
    if res.get("detail"):
        extra.append(str(res["detail"]))
    return f"{verdict}  {where}\n    " + "\n    ".join(extra)


def main():
    ap = argparse.ArgumentParser(description="小智推送音频·硬件链路模拟器")
    ap.add_argument("cmd", choices=["check", "check-file", "scan"])
    ap.add_argument("target")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.cmd in ("check", "check-file"):
        res = check_url(args.target) if args.cmd == "check" else check_file(args.target)
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(human_line(res))
        sys.exit(0 if res["playable"] else 1)
    else:  # scan
        d = args.target
        names = sorted(f for f in os.listdir(d)
                       if f.lower().endswith((".ogg", ".opus", ".mp3", ".wav")))
        results = []
        bad = 0
        for name in names:
            res = check_file(os.path.join(d, name))
            results.append(res)
            if not res["playable"]:
                bad += 1
            if not args.json:
                print(human_line(res))
        summary = {"dir": d, "total": len(results), "playable": len(results) - bad,
                   "not_playable": bad,
                   "fail_reasons": {}}
        for r in results:
            if not r["playable"]:
                summary["fail_reasons"][r["reason"]] = \
                    summary["fail_reasons"].get(r["reason"], 0) + 1
        if args.json:
            print(json.dumps({"summary": summary, "results": results},
                             ensure_ascii=False, indent=2))
        else:
            print(f"\n== {d}: {summary['playable']}/{summary['total']} PLAYABLE，"
                  f"{bad} NOT PLAYABLE {summary['fail_reasons']} ==")
        sys.exit(0 if bad == 0 else 1)


if __name__ == "__main__":
    main()
