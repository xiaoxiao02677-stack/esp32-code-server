#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把已生成的 LVGL RGB565 C 数组改名为皮肤共享符号。

为什么需要：`good.jpg` 的 240x240 RGB565 数据早在 yh-n16r8-st7789 版型里生成过
（`good_bg.c`，符号 `yh_round_bg_good`）。皮肤抽成跨版型共享层后，同一份像素
数据只需要一份、符号固定为 `yh_skin_bg`，四个版型都引用它 —— 既省一份 flash，
也避免「同一个背景图在 4 个板目录各存 578KB 源码」的重复。

本脚本只做**符号与注释重写**，不重新采样像素：源数据已经是正确的 RGB565，
重跑 jpg_to_lvgl565.py 反而会因为 JPEG 解码器差异引入色差。

用法：
  python tools/gen_yh_skin_assets.py \
      --src hardware/sets/boards/yh-n16r8-st7789/good_bg.c \
      --out hardware/sets/yuhe-esp32/main/display/yh_skin/yh_skin_assets.c \
      --symbol yh_skin_bg
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(description="重命名 LVGL 图片 C 数组的符号")
    ap.add_argument("--src", default="hardware/sets/boards/yh-n16r8-st7789/good_bg.c")
    ap.add_argument("--out",
                    default="hardware/sets/yuhe-esp32/main/display/yh_skin/yh_skin_assets.c")
    ap.add_argument("--symbol", default="yh_skin_bg", help="目标 lv_image_dsc_t 符号名")
    ap.add_argument("--map-suffix", default="_map", help="像素数组后缀")
    args = ap.parse_args()

    src = Path(args.src)
    if not src.is_absolute():
        src = REPO / src
    out = Path(args.out)
    if not out.is_absolute():
        out = REPO / out
    if not src.exists():
        print(f"[FAIL] 源文件不存在: {src}", file=sys.stderr)
        return 2

    text = src.read_text(encoding="utf-8")

    # 找出源里的两个符号：静态像素数组 + lv_image_dsc_t 定义
    dsc = re.search(r"const\s+lv_image_dsc_t\s+(\w+)\s*=", text)
    if not dsc:
        print("[FAIL] 源文件里找不到 `const lv_image_dsc_t <name> = {`", file=sys.stderr)
        return 3
    old_dsc = dsc.group(1)
    arr = re.search(r"uint8_t\s+(\w+)\[\]\s*=", text)
    if not arr:
        print("[FAIL] 源文件里找不到像素数组 `uint8_t <name>[] =`", file=sys.stderr)
        return 4
    old_arr = arr.group(1)

    new_dsc = args.symbol
    new_arr = args.symbol + args.map_suffix

    # 先替换长的（数组名通常包含 dsc 名做前缀，先换 dsc 会误伤）
    text = re.sub(rf"\b{re.escape(old_arr)}\b", new_arr, text)
    text = re.sub(rf"\b{re.escape(old_dsc)}\b", new_dsc, text)

    banner = (
        "/* Auto-generated from good.jpg (240x240 RGB565) by tools/gen_yh_skin_assets.py\n"
        f" * 源: {src.relative_to(REPO).as_posix() if src.is_relative_to(REPO) else src}\n"
        f" * 符号: {new_dsc} / {new_arr}\n"
        " * 屿禾「小柚」皮肤共享背景图；4 个 yh-* 版型共用这一份，勿在板目录再放副本。 */\n"
    )
    text = re.sub(r"^/\*.*?\*/\n", banner, text, count=1, flags=re.S)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")

    size = out.stat().st_size
    print(f"[OK] {out}")
    print(f"     源 {src.name} -> 符号 {old_dsc}/{old_arr} => {new_dsc}/{new_arr}")
    print(f"     输出大小 {size} 字节")
    return 0


if __name__ == "__main__":
    sys.exit(main())
