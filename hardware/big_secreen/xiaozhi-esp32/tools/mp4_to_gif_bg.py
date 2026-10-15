# -*- coding: utf-8 -*-
"""mp4 -> LVGL 嵌入式 GIF 背景转换脚本（bigscreen-s3 专用）

输入: big_screen.mp4 (320x240, 60fps, 20s, 黑白手绘漫画风)
输出: main/boards/bigscreen-s3/bigscreen_bg.c  (uint8_t bigscreen_bg_gif[])

适配硬件: ESP32-S3 16MB Flash / 8MB Octal PSRAM / ILI9341 320x240 SPI 屏
预算: GIF <= 900KB（ota 分区 3.84MB，当前 app ~2.7MB，余量 ~1.1MB）

实测参数（2026-10 标定，画质/体积平衡点）:
  10fps 采样 -> 对比度拉伸 -> Gaussian blur(1.0) -> 12 级线性灰阶量化
  -> 相似帧合并(diff<1.2) -> GIF 差分编码(disposal=1)
  => 171 帧, ~117ms/帧, 828KB
重新生成: python tools/mp4_to_gif_bg.py
"""
import os
import sys
import cv2
import numpy as np
from PIL import Image

SRC = r"G:\demo\21_xiaozhi\code\big_secreen\big_screen.mp4"
OUT_C = r"G:\demo\21_xiaozhi\code\big_secreen\xiaozhi-esp32\main\boards\bigscreen-s3\bigscreen_bg.c"
TMP_GIF = r"G:\demo\21_xiaozhi\code\big_secreen\_bg_probe\bigscreen_bg.gif"

SAMPLE_FPS = 10        # 采样帧率
BLUR = 1.0             # 高斯模糊 sigma（压纸纹噪点，让差分编码生效）
GRAY_LEVELS = 12       # 线性灰阶级数
DIFF_THRESH = 1.2      # 相似帧合并阈值（平均灰度差）
STRETCH_LO, STRETCH_HI = 40, 215   # 对比度拉伸输入区间（黑更黑白更白）
MAX_BYTES = 900 * 1024


def quant_idx(g, levels):
    q = (g.astype(np.float32) * levels / 256.0).astype(np.int16)
    return np.clip(q, 0, levels - 1).astype(np.uint8)


def to_p(idx, levels):
    img = Image.fromarray(idx, mode="P")
    vals = [round(255 * k / (levels - 1)) for k in range(levels)]
    img.putpalette([v for c in vals for v in (c, c, c)])
    return img


def diff_idx(a, b, levels):
    return np.abs(a.astype(np.int16) - b.astype(np.int16)).mean() * (256.0 / levels)


def main():
    cap = cv2.VideoCapture(SRC)
    if not cap.isOpened():
        print("ERROR: cannot open", SRC)
        sys.exit(1)
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 60
    step = max(1, round(src_fps / SAMPLE_FPS))
    grays, i = [], 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % step == 0:
            g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # 对比度拉伸：黑白漫画质感（黑更黑、白更白）
            g = np.clip((g.astype(np.float32) - STRETCH_LO) * 255.0 /
                        (STRETCH_HI - STRETCH_LO), 0, 255).astype(np.uint8)
            grays.append(g)
        i += 1
    cap.release()
    if not grays:
        print("ERROR: no frames")
        sys.exit(1)
    print(f"sampled {len(grays)} frames @ {SAMPLE_FPS}fps")

    def prep(g):
        if BLUR > 0:
            g = cv2.GaussianBlur(g, (0, 0), BLUR)
        return quant_idx(g, GRAY_LEVELS)

    kept = [prep(grays[0])]
    gaps = [1]
    for g in grays[1:]:
        q = prep(g)
        if diff_idx(kept[-1], q, GRAY_LEVELS) < DIFF_THRESH:
            gaps[-1] += 1
        else:
            kept.append(q)
            gaps.append(1)

    total_ms = sum(gaps) * (1000 / SAMPLE_FPS)
    duration = max(20, int(total_ms / len(kept)))
    p_frames = [to_p(k, GRAY_LEVELS) for k in kept]
    p_frames[0].save(TMP_GIF, save_all=True, append_images=p_frames[1:],
                     duration=duration, loop=0, disposal=1, optimize=True)
    size = os.path.getsize(TMP_GIF)
    print(f"kept {len(kept)} frames, {duration}ms/frame, {size} bytes ({size/1024:.0f} KB)")
    if size > MAX_BYTES:
        print(f"ERROR: exceeds {MAX_BYTES} budget — lower GRAY_LEVELS or raise DIFF_THRESH")
        sys.exit(1)

    gif = open(TMP_GIF, "rb").read()
    name = "bigscreen_bg_gif"
    lines = []
    lines.append("/* Auto-generated from big_screen.mp4 (320x240) by tools/mp4_to_gif_bg.py")
    lines.append(f" * {len(kept)} frames, {duration}ms/frame, {len(gif)} bytes ({len(gif)//1024} KB), loop forever.")
    lines.append(" * Pipeline: 10fps sample -> contrast stretch(40..215) -> Gaussian blur(1.0)")
    lines.append(" *           -> 12-level linear gray quantize -> similar-frame merge(<1.2)")
    lines.append(" *           -> GIF differential encode (disposal=1).")
    lines.append(" * Runtime: gifdec decodes into ARGB8888 canvas in LVGL pool (PSRAM),")
    lines.append(" *          played by LvglGif as the bottom UI layer.")
    lines.append(" * Regenerate: python tools/mp4_to_gif_bg.py  (see header for knobs) */")
    lines.append("#include \"lvgl.h\"")
    lines.append("")
    lines.append("#ifndef LV_ATTRIBUTE_IMG_DATA")
    lines.append("#define LV_ATTRIBUTE_IMG_DATA const")
    lines.append("#endif")
    lines.append("")
    lines.append("LV_ATTRIBUTE_IMG_DATA uint8_t %s[] = {" % name)
    for off in range(0, len(gif), 16):
        chunk = gif[off:off + 16]
        lines.append("    " + ", ".join("0x%02X" % b for b in chunk) + ",")
    lines.append("};")
    lines.append("")
    lines.append(f"const size_t {name}_len = sizeof({name});")
    lines.append("")
    with open(OUT_C, "w", newline="\n") as f:
        f.write("\n".join(lines))
    print("written:", OUT_C)


if __name__ == "__main__":
    main()
