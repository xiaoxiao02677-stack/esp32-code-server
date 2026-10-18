#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对 sets 固件树做单文件语法校验（不编译、不链接、不烧录）。

原理：直接复用 ESP-IDF 已有的 build/compile_commands.json 里的编译参数
（包含全部 -D/-I/-std/-march），把输入文件换成目标文件、把 `-o xxx -c` 换成
`-fsyntax-only`，用同一个 xtensa 工具链跑一遍。这样能抓住 90% 的「写错 API /
漏 inlude / 类型不匹配」问题，而不需要跑完整 CMake。

限制（必须知道，否则会误判）：
  * 只做语法与类型检查，不做链接检查 —— 未定义的符号（例如图片资源还没生成）
    不会在这里报错，要靠完整编译才能发现；
  * 用的是 build/ 里最后一次 configure 的板型参数（BOARD_NAME 等），换板型后
    需要重新 configure 才能得到该板型的 -D，否则板型条件编译分支可能走错；
  * 不做代码生成（如 lv_font 转换），因此只适用于 .cc/.c 源文件。

用法：
  python tools/yh_syntax_check.py main/display/yh_skin/yh_skin_display.cc
  python tools/yh_syntax_check.py --all-skin
  python tools/yh_syntax_check.py --board yuhe/yh-cam main/boards/yuhe/yh-cam/*.cc
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FW = REPO / "hardware" / "sets" / "xiaozhi-esp32"
CC_JSON = FW / "build" / "compile_commands.json"

# 皮肤模块默认清单
SKIN_FILES = [
    "main/display/yh_skin/yh_skin_display.cc",
    "main/display/yh_skin/yh_skin_boot.cc",
    "main/display/yh_skin/yh_skin_cards.cc",
    "main/display/yh_skin/yh_skin_assets.c",
]


def load_entries() -> list[dict]:
    if not CC_JSON.exists():
        sys.exit(f"[FAIL] 找不到 {CC_JSON}，先在 IDF 环境里 configure 一次")
    with CC_JSON.open(encoding="utf-8") as fp:
        return json.load(fp)


def pick_template(entries: list[dict], board_hint: str | None, want_c: bool = False) -> dict:
    """挑一个 main/ 下的编译单元作为参数模板。

    want_c=True 时优先挑 C 编译单元（.c 文件必须用 gcc，用 g++ 编会撞 newlib 头）。
    """
    want = "-elf-gcc" if want_c else "-elf-g++"
    candidates = [e for e in entries
                  if e["file"].replace("\\", "/").endswith("main/application.cc")
                  and want in e.get("command", e.get("arguments", [""])[0])]
    if not candidates:
        candidates = [e for e in entries
                      if "/main/" in e["file"].replace("\\", "/")
                      and want in e.get("command", "")].copy()
    if not candidates:
        sys.exit(f"[FAIL] compile_commands.json 里没有 main/ 的 {'C' if want_c else 'C++'} 编译单元")
    if board_hint:
        for e in candidates:
            cmd = e.get("command", "")
            if f'BOARD_NAME=\\"{board_hint}\\"' in cmd or f'BOARD_NAME="{board_hint}"' in cmd:
                return e
        print(f"[WARN] 没有板型 {board_hint} 的编译单元，退回默认模板（板型 -D 可能不匹配）")
    return candidates[0]


def build_argv(template: dict, target: Path) -> list[str]:
    """把模板命令改造成 -fsyntax-only。"""
    cmd = template.get("command")
    if cmd is None:  # 少数生成器用 arguments 数组
        argv = list(template["arguments"])
    else:
        # 注意：这里不能 shlex.split —— 原命令里的 -DXXX=\"val\" 是靠 shell 去掉
        # 反斜杠的，直接 subprocess 传参会把反斜杠当字面量，宏值变成 \"val\" 并
        # 报 "missing terminating \" character"。所以手工按空格切再反转义。
        argv = [tok.replace('\\"', '"') for tok in cmd.split()]
        # CMake 把大头编译参数塞在响应文件里（形如 @".../build/toolchain/cxxflags"）。
        # 直接传参会把引号当路径的一部分，gcc 找不到文件 → 所有 -D/-I 丢失，
        # 于是报出一堆「FILE 未声明 / gpio.h 语法错」的假故障。这里去掉引号。
        argv = [('@' + tok[1:].strip('"')) if tok.startswith('@') else tok for tok in argv]
    out: list[str] = []
    skip_next = False
    for i, tok in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        if tok == "-o":          # 去掉 -o <file>
            skip_next = True
            continue
        if tok == "-c":          # 去掉 -c
            continue
        if tok.endswith((".cc", ".c", ".cpp")) and i > 0 and not tok.startswith("-"):
            # 原输入文件位置：换成目标文件
            out.append(str(target))
            continue
        if tok == "-MD" or tok == "-MT" or tok == "-MF":
            skip_next = True
            continue
        out.append(tok)
    if str(target) not in out:
        out.append(str(target))
    out.insert(1, "-fsyntax-only")
    return out


def run_one(template: dict, target: Path) -> tuple[int, str]:
    if not target.exists():
        return 2, f"文件不存在: {target}"
    argv = build_argv(template, target)
    env = dict(os.environ)
    env.pop("MSYSTEM", None)  # Git Bash 下 MSYSTEM 会让 IDF 工具链行为异常
    env["PYTHONUTF8"] = "1"
    proc = subprocess.run(argv, cwd=str(FW), capture_output=True, text=True,
                          errors="replace", env=env)
    out = (proc.stdout or "") + (proc.stderr or "")
    # 只留 error / warning 行，避免刷屏
    lines = [ln for ln in out.splitlines()
             if re.search(r"\b(error|warning|fatal error)\b", ln, re.IGNORECASE)]
    return proc.returncode, "\n".join(lines[:40]) if lines else out[-800:]


def main() -> int:
    ap = argparse.ArgumentParser(description="sets 固件单文件语法校验（不编译烧录）")
    ap.add_argument("files", nargs="*", help="相对 hardware/sets/xiaozhi-esp32 的源文件路径")
    ap.add_argument("--all-skin", action="store_true", help="校验皮肤模块 4 个文件")
    ap.add_argument("--board", default=None, help="板型名（用于挑 BOARD_NAME 匹配的模板）")
    args = ap.parse_args()

    targets = list(args.files)
    if args.all_skin:
        targets += SKIN_FILES
    if not targets:
        ap.print_help()
        return 1

    entries = load_entries()
    print("-" * 72)

    failed = 0
    c_template = None
    cpp_template = pick_template(entries, args.board, want_c=False)
    print(f"C++ 模板: {Path(cpp_template['file']).name}")

    for rel in targets:
        p = Path(rel)
        if not p.is_absolute():
            p = FW / rel
        if p.suffix == ".c":
            if c_template is None:
                c_template = pick_template(entries, args.board, want_c=True)
                print(f"C   模板: {Path(c_template['file']).name}")
            template = c_template
        else:
            template = cpp_template
        rc, detail = run_one(template, p)
        status = "OK  " if rc == 0 else "FAIL"
        print(f"[{status}] {rel}" + (f"  (rc={rc})" if rc else ""))
        if rc != 0:
            failed += 1
            for ln in detail.splitlines():
                print("       " + ln)
    print("-" * 72)
    print(f"合计 {len(targets)} 个文件，失败 {failed} 个")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
