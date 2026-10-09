#!/usr/bin/env python3
"""将 good.jpg 转成 LVGL 9.5 RGB565 C 数组（圆屏背景）。

用法: python jpg_to_lvgl565.py <input.jpg> <output.c> <symbol>
240x240 直接 1:1 像素，无缩放。
"""
import sys

from PIL import Image


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    src, dst, symbol = sys.argv[1], sys.argv[2], sys.argv[3]

    img = Image.open(src).convert("RGB")
    w, h = img.size
    if (w, h) != (240, 240):
        print(f"[WARN] size {w}x{h} != 240x240，将中心裁剪/缩放到 240x240")
        side = min(w, h)
        left, top = (w - side) // 2, (h - side) // 2
        img = img.crop((left, top, left + side, top + side)).resize((240, 240))

    w, h = 240, 240
    px = img.load()
    stride = w * 2  # RGB565 每像素 2 字节

    lines = []
    lines.append("/* Auto-generated from good.jpg (240x240 RGB565) by jpg_to_lvgl565.py */")
    lines.append("#include \"lvgl.h\"")
    lines.append("")
    lines.append("#ifndef LV_ATTRIBUTE_IMG_DATA")
    lines.append("#define LV_ATTRIBUTE_IMG_DATA const")
    lines.append("#endif")
    lines.append("")
    lines.append(f"static LV_ATTRIBUTE_IMG_DATA uint8_t {symbol}_map[] = {{")

    chunk = []
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            # LVGL9 RGB565 图像数据按小端存储（低字节在前），与官方测试资产一致
            chunk.append(f"0x{rgb565 & 0xFF:02X},0x{(rgb565 >> 8) & 0xFF:02X},")
        if len(chunk) >= 24:  # 每行写 12 像素
            lines.append("    " + "".join(chunk[:24]))
            chunk = chunk[24:]
    if chunk:
        lines.append("    " + "".join(chunk))
    lines.append("};")
    lines.append("")
    lines.append(f"const lv_image_dsc_t {symbol} = {{")
    lines.append(f"    .header = {{.magic = LV_IMAGE_HEADER_MAGIC,")
    lines.append(f"                .cf = LV_COLOR_FORMAT_RGB565,")
    lines.append(f"                .flags = 0,")
    lines.append(f"                .w = {w}, .h = {h},")
    lines.append(f"                .stride = {stride},")
    lines.append(f"                .reserved_2 = 0}},")
    lines.append(f"    .data_size = {w * h * 2},")
    lines.append(f"    .data = {symbol}_map,")
    lines.append("};")
    lines.append("")

    with open(dst, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[OK] {dst}: {w}x{h} RGB565, {w*h*2} bytes")


if __name__ == "__main__":
    main()
