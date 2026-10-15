#!/usr/bin/env python3
"""tmp/ 音频全量损坏扫描：垃圾尾部特征 + ffmpeg 解码健康度。生产只读。"""
import glob
import json
import os
import re
import subprocess
import sys

TMP = "/root/xiaozhi-server/main/xiaozhi-server/tmp"


def tail_garbage(d: bytes):
    """从尾部往前找 AA/55 垃圾区（允许 AA/55 交错与少量间隔），返回 (起始偏移, 垃圾长度, 形态)。"""
    n = len(d)
    if n == 0 or d[-1:] not in (b"\xaa", b"\x55"):
        return None
    i = n - 1
    while i > 0 and d[i - 1] in (0xAA, 0x55):
        i -= 1
    # 再往前扩：允许隔 <=16 字节非垃圾的 AA/55 簇
    j = i
    while j > 16:
        k = j
        gap = 0
        while k > 0 and d[k - 1] not in (0xAA, 0x55) and gap < 16:
            k -= 1
            gap += 1
        if gap >= 16 or k == 0:
            break
        # 找到 16 字节内的 AA/55 簇，继续往前吃
        while k > 0 and d[k - 1] in (0xAA, 0x55):
            k -= 1
        if k == j:
            break
        j = k
    start = j
    seg = d[start:]
    aa = seg.count(b"\xaa")
    s5 = seg.count(b"\x55")
    form = "AA" if aa > s5 else "55"
    return (start, n - start, form)


def main():
    files = sorted(
        glob.glob(os.path.join(TMP, "*.mp3"))
        + glob.glob(os.path.join(TMP, "*.wav"))
        + glob.glob(os.path.join(TMP, "*.ogg"))
        + glob.glob(os.path.join(TMP, "*.txt"))
    )
    rows = []
    for f in files:
        name = os.path.basename(f)
        d = open(f, "rb").read()
        n = len(d)
        g = tail_garbage(d)
        gstart, glen, gform = (g if g else (0, 0, "-"))
        # ffmpeg 探测（txt 跳过）
        errs, dur = 0, -1.0
        if not name.endswith(".txt"):
            try:
                r = subprocess.run(
                    ["ffmpeg", "-v", "error", "-i", f, "-f", "null", "-"],
                    capture_output=True, text=True, timeout=30,
                )
                errs = len([l for l in r.stderr.strip().splitlines() if l.strip()])
                rp = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "json", f],
                    capture_output=True, text=True, timeout=15,
                )
                dur = float(json.loads(rp.stdout)["format"]["duration"])
            except Exception as e:
                errs, dur = -1, -1.0
        rows.append((name, n, gstart, glen, gform, errs, dur))

    print(f"{'file':46} {'size':>7} {'gstart':>7} {'glen':>6} {'form':>4} {'errs':>4} {'dur':>6}")
    for r in rows:
        print(f"{r[0]:46} {r[1]:>7} {r[2]:>7} {r[3]:>6} {r[4]:>4} {r[5]:>4} {r[6]:>6.1f}")

    mp3s = [r for r in rows if r[0].endswith(".mp3")]
    topic = [r for r in mp3s if r[0].startswith("topic-")]
    print(f"\nmp3 total={len(mp3s)}  topic-={len(topic)}")
    print(f"topic 尾部垃圾: {sum(1 for r in topic if r[3] > 0)}/{len(topic)}")
    print(f"topic ffmpeg报错: {sum(1 for r in topic if r[5] not in (0,))}/{len(topic)}")

    def day(r):
        m = re.search(r"topic-(\d{10})", r[0])
        return "1014" if m and m.group(1)[:5] in ("17919", "17918") else "1015"

    for dd in ("1014", "1015"):
        sub = [r for r in topic if day(r) == dd]
        if sub:
            print(f"day {dd}: n={len(sub)} garbage={sum(1 for r in sub if r[3] > 0)} "
                  f"errs={sum(1 for r in sub if r[5] != 0)}")

    # 非 topic 音频（其他功能 TTS 产物）
    others = [r for r in mp3s if not r[0].startswith("topic-")]
    print(f"非topic音频: {len(others)} 个，垃圾尾部: "
          f"{sum(1 for r in others if r[3] > 0)}，ffmpeg错: "
          f"{sum(1 for r in others if r[5] != 0)}")

    # 垃圾区与有效数据交界 hex（对第一个垃圾样本）
    for r in rows:
        if r[3] > 0 and r[0].endswith(".mp3"):
            d = open(os.path.join(TMP, r[0]), "rb").read()
            b = max(0, r[2] - 48)
            print(f"\n交界 hexdump [{r[0]}] 垃圾起始={r[2]}:")
            seg = d[b:r[2] + 48]
            for k in range(0, len(seg), 16):
                off = b + k
                chunk = seg[k:k + 16]
                hexs = " ".join(f"{c:02x}" for c in chunk)
                print(f"  {off:08x}: {hexs}")
            break


if __name__ == "__main__":
    main()
