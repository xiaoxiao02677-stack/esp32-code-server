#!/usr/bin/env python3
"""批量转码矩阵：41 个损坏 topic MP3 -> Ogg Opus mono 24k，统计成功率/时长一致性/耗时。"""
import glob
import json
import os
import subprocess
import time

SRC = "/root/xiaozhi-server/main/xiaozhi-server/tmp"
DST = "/tmp/matrix"
os.makedirs(DST, exist_ok=True)

rows = []
for f in sorted(glob.glob(os.path.join(SRC, "topic-*.mp3"))):
    name = os.path.basename(f)
    ogg = os.path.join(DST, name.replace(".mp3", ".ogg"))
    t0 = time.time()
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", f, "-ac", "1", "-ar", "24000",
         "-c:a", "libopus", "-b:a", "32k", ogg],
        capture_output=True, text=True, timeout=60)
    el = time.time() - t0
    src_dur = ogg_dur = None
    channels = None
    if r.returncode == 0:
        for path, key in ((f, "src"), (ogg, "ogg")):
            rp = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "json", path], capture_output=True, text=True, timeout=15)
            try:
                d = float(json.loads(rp.stdout)["format"]["duration"])
            except Exception:
                d = None
            if key == "src":
                src_dur = d
            else:
                ogg_dur = d
        rc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=channels",
             "-of", "json", ogg], capture_output=True, text=True, timeout=15)
        try:
            channels = json.loads(rc.stdout)["streams"][0]["channels"]
        except Exception:
            channels = None
    rows.append((name, r.returncode, len(r.stderr.strip().splitlines()),
                 src_dur, ogg_dur, channels, el, os.path.getsize(ogg) if os.path.exists(ogg) else 0))

ok = [r for r in rows if r[1] == 0]
bad = [r for r in rows if r[1] != 0]
dur_dev = [abs(r[3] - r[4]) for r in ok if r[3] and r[4]]
mono = [r for r in ok if r[5] == 1]
print(f"total={len(rows)} ok={len(ok)} fail={len(bad)} mono={len(mono)}/{len(ok)}")
print(f"duration dev: max={max(dur_dev):.3f}s avg={sum(dur_dev)/len(dur_dev):.3f}s")
print(f"time: avg={sum(r[6] for r in rows)/len(rows):.2f}s max={max(r[6] for r in rows):.2f}s")
if bad:
    print("FAILED:")
    for r in bad:
        print(f"  {r[0]} rc={r[1]} errs={r[2]}")
big = [r for r in ok if r[3] and r[4] and abs(r[3] - r[4]) > 0.5]
if big:
    print("DURATION MISMATCH >0.5s:")
    for r in big:
        print(f"  {r[0]} src={r[3]:.2f} ogg={r[4]:.2f}")

# 极端输入测试
print("\n== edge cases ==")
# a) 截断 ogg
src = os.path.join(DST, os.path.basename(sorted(glob.glob(os.path.join(SRC, 'topic-*.mp3')))[0]).replace('.mp3', '.ogg'))
if os.path.exists(src):
    data = open(src, "rb").read()
    for cut in (100, 500, 2000):
        p = f"/tmp/matrix/trunc-{cut}.ogg"
        open(p, "wb").write(data[:-cut] if cut < len(data) else b"")
        rp = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                             "-of", "json", p], capture_output=True, text=True, timeout=15)
        try:
            d = float(json.loads(rp.stdout)["format"]["duration"])
        except Exception:
            d = None
        print(f"trunc-{cut}: ffprobe_duration={d}")
# b) 纯垃圾
open("/tmp/matrix/garbage.mp3", "wb").write(b"\xaa" * 512)
r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", "/tmp/matrix/garbage.mp3",
                    "-ac", "1", "-ar", "24000", "-c:a", "libopus", "-b:a", "32k",
                    "/tmp/matrix/garbage.ogg"], capture_output=True, text=True, timeout=30)
print(f"garbage-512B: rc={r.returncode} stderr={r.stderr.strip()[:100]}")
# c) 空文件
open("/tmp/matrix/empty.mp3", "wb").close()
r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", "/tmp/matrix/empty.mp3",
                    "-ac", "1", "-ar", "24000", "-c:a", "libopus", "-b:a", "32k",
                    "/tmp/matrix/empty.ogg"], capture_output=True, text=True, timeout=30)
print(f"empty: rc={r.returncode} stderr={r.stderr.strip()[:100]}")
