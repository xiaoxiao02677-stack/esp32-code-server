# -*- coding: utf-8 -*-
"""SD 卡版高画质背景生成（bigscreen-s3 专用）

输出: sd_card/bg.gif  ->  直接拷贝到 FAT32 SD 卡根目录
预算: <= 3.8MB (固件 4MB 上限内留余量)

参数（2026-10 标定,对齐 Flash 版工具 mp4_to_gif_bg.py 的管线,画质拉满）:
  64 级线性灰阶 + 轻模糊(0.2) + 无相似帧合并(全 201 帧 @ 10fps)
  => ~3.2MB, 对比 Flash 版(12 级/171 帧/blur 1.0/835KB) 画质大幅提升
"""
import os
import sys
import cv2
import numpy as np
from PIL import Image

SRC = r"G:\demo\21_xiaozhi\code\big_secreen\big_screen.mp4"
OUT_DIR = r"G:\demo\21_xiaozhi\code\big_secreen\sd_card"
OUT_GIF = os.path.join(OUT_DIR, "bg.gif")

SAMPLE_FPS = 10
BLUR = 0.2
GRAY_LEVELS = 64
STRETCH_LO, STRETCH_HI = 40, 215
MAX_BYTES = int(3.8 * 1024 * 1024)


def quant_idx(g, levels):
    q = (g.astype(np.float32) * levels / 256.0).astype(np.int16)
    return np.clip(q, 0, levels - 1).astype(np.uint8)


def to_p(idx, levels):
    img = Image.fromarray(idx, mode="P")
    vals = [round(255 * k / (levels - 1)) for k in range(levels)]
    img.putpalette([v for c in vals for v in (c, c, c)])
    return img


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
            g = np.clip((g.astype(np.float32) - STRETCH_LO) * 255.0 /
                        (STRETCH_HI - STRETCH_LO), 0, 255).astype(np.uint8)
            grays.append(g)
        i += 1
    cap.release()
    print(f"sampled {len(grays)} frames @ {SAMPLE_FPS}fps")

    kept = []
    for g in grays:
        if BLUR > 0:
            g = cv2.GaussianBlur(g, (0, 0), BLUR)
        kept.append(quant_idx(g, GRAY_LEVELS))

    duration = int(1000 / SAMPLE_FPS)
    p_frames = [to_p(k, GRAY_LEVELS) for k in kept]
    os.makedirs(OUT_DIR, exist_ok=True)
    p_frames[0].save(OUT_GIF, save_all=True, append_images=p_frames[1:],
                     duration=duration, loop=0, disposal=1, optimize=True)
    size = os.path.getsize(OUT_GIF)
    print(f"{len(kept)} frames, {duration}ms/frame, {size} bytes ({size/1024:.0f} KB)")
    if size > MAX_BYTES:
        print(f"ERROR: exceeds {MAX_BYTES} budget")
        sys.exit(1)
    print("written:", OUT_GIF)
    print("copy bg.gif to the FAT32 SD card root, insert, power on.")


if __name__ == "__main__":
    main()
