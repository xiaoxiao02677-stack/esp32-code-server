# -*- coding: utf-8 -*-
"""生成 DengYu 主题固定文案字档 font_dengyu_16_4.c。

与 yh_skin/font_splash_20_4.c 同一模式：编译进固件的专属小字档，
只打包主题固定文案字符（状态短语/待机短句/晨间问候/调色板名/who 标签），
动态聊天文本不靠它（跟随主题字体 → assets 运行时接管）。

用法：python gen_dengyu_font.py   （在 DengYu_skin/ 目录下执行）
依赖：npx lv_font_conv（联网首跑会装包）、NotoSansSC-Regular.ttf
     （取 managed_components/lvgl__lvgl 测试字体，与 splash 字档同源）。
"""
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
TTF = HERE.parents[2] / "managed_components" / "lvgl__lvgl" / "tests" / "src" / \
    "test_files" / "fonts" / "noto" / "NotoSansSC-Regular.ttf"

# ---- 全部固定文案（与 dengyu_skin_display.cc 逐字对齐）----
TEXTS = [
    # 待机短句
    "想着你", "今晚风好安静", "等你说晚安", "我在呢",
    # 思考轮词
    "想想哦", "让我翻翻记忆", "快好了", "在想啦",
    # 状态短语
    "在听，慢慢说", "信号走丢了", "已静音", "声音开着",
    # 调色板名 + 提示模板
    "炭火", "月光", "紫暮", "珊瑚", "光萤换成了",
    # who 标签
    "灯灯", "你",
    # 晨间问候
    "早安，今天是我们在一起的第 99999 天。",
    "去把今天过好，我在家等你。",
    "早安。", "新的一天，我也在。",
    # 断连恢复提示
    "回来啦",
]

FONT_NAME = "font_dengyu_16_4"
OUT = HERE / f"{FONT_NAME}.c"


def collect_ranges() -> str:
    cps = set()
    # ASCII 可打印区一把梭（数字/冒号/百分号/字母，95 码位）
    cps.update(range(0x20, 0x7F))
    cps.add(0x2026)  # …
    for t in TEXTS:
        cps.update(ord(c) for c in t)
    cps = sorted(c for c in cps if c > 0x1F)
    # 收敛成 range 表达式
    parts = []
    start = prev = cps[0]
    for c in cps[1:] + [None]:
        if c is not None and c == prev + 1:
            prev = c
            continue
        parts.append(f"0x{start:x}" if start == prev else f"0x{start:x}-0x{prev:x}")
        if c is not None:
            start = prev = c
    return ",".join(parts)


def main() -> int:
    if not TTF.exists():
        print(f"TTF not found: {TTF}", file=sys.stderr)
        return 1
    ranges = collect_ranges()
    n_cp = sum(1 for _ in
               (c for c in range(0x20, 0x10000)
                if any(a <= c <= b for a, b in
                       ((int(p.split('-')[0], 16),
                         int(p.split('-')[1], 16) if '-' in p else int(p.split('-')[0], 16))
                        for p in ranges.split(',')))))
    print(f"charset: {n_cp} codepoints")
    npx = shutil.which("npx.cmd") or shutil.which("npx") or shutil.which("npx.exe")
    if npx is None:
        print("npx not found in PATH", file=sys.stderr)
        return 1
    cmd = [
        npx, "--yes", "lv_font_conv",
        "--no-compress", "--no-prefilter", "--force-fast-kern-format",
        "--font", str(TTF),
        "--format", "lvgl", "--bpp", "4", "--size", "16",
        "-r", ranges,
        "--lv-include", "lvgl.h",
        "--lv-font-name", FONT_NAME,
        "-o", str(OUT),
    ]
    print(" ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode == 0:
        size = OUT.stat().st_size
        print(f"OK -> {OUT} ({size} bytes source, ~{size // 4} bytes flash)")
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
