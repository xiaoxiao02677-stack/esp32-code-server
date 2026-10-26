#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
猫咪主题素材转换 v2：表情/嘴部视频 → yuhe assets 帧序列（平铺命名）

v2（2026-10-26，对照原项目 integrated.ino 逻辑重审后的修正）：
  · 每段表情：60 帧全视频均匀采样（原项目 80 帧 × 50ms = 4s/段；
    60 帧 × 66ms = 15fps × 4s，段长与原项目一致。v1 只截中段 2s，
    动画换得太频繁——用户实测反馈"一直变化视频，不是很好看"）
  · 帧尺寸 320×240（4:3 = 源视频 1112×834 / 原项目 284×240 的原生比例；
    v1 的 240×240 把猫脸横向压扁变形。显示层按板 contain-fit，
    320×240 板全出血、240×240 / 240×320 板上下留黑居中）
  · 嘴形：从 v1 的 80×50 小块叠加（错位浮在下巴上）改为 320×240
    全帧——按 muzzle（口鼻部）对齐裁剪自嘴部视频。嘴部视频是
    完整猫脸（1440×1080），说话时整帧轮换 4 形状。

产物命名（与固件 display/cat_skin/cat_anim.h 一一对应）：
  frames/cat_a{1-8}_f{00-59}.jpg   表情动画：8 段 × 60 帧（15fps × 4s）
  frames/cat_m{1-4}.jpg            嘴形：small/big/wide/oshape（320×240 全帧）

容量预算：assets 分区 8MB，现有字体/emoji/语音约 4.05MB，
猫咪帧预算 3.7MB；60帧×8段×q60 ≈ 3.3MB。

使用方法：
  pip install opencv-python numpy
  python video_to_frames.py                       # 用默认源路径
  python video_to_frames.py --expr-src <dir> ...  # 自定义源

转换完成后：
  cd G:\\demo\\21_xiaozhi\\hardware\\sets
  python build.py --theme cat    # 帧会自动经 extra_files 进 assets 分区
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

# ==================== 默认配置 ====================

SCRIPT_DIR = Path(__file__).parent.resolve()
THEME_DIR = SCRIPT_DIR.parent  # hardware/sets/theme/cat
DEFAULT_OUT = THEME_DIR / "frames"

# 源视频（原 cat 项目）
DEFAULT_EXPR_SRC = Path(r"G:\demo\22 cat\upload_facial_expression\表情")
DEFAULT_MOUTH_SRC = Path(r"G:\demo\22 cat\upload_facial_expression\mouth_flash_files\anime")

# 表情动画：320×240（4:3），15fps × 4s = 60 帧/段
# （原项目 80 帧 × 50ms = 4s/段，全视频采样；此处等时长）
EXPR_TARGET_SIZE = (320, 240)
EXPR_FRAME_COUNT = 60
EXPR_JPEG_QUALITY = 60

# 嘴形：320×240 全帧（muzzle 对齐裁剪），q65
MOUTH_TARGET_SIZE = (320, 240)
MOUTH_JPEG_QUALITY = 65

# 表情视频 → 动画编号（cat_anim.h 的 cat_anim_id_t + 1）
EXPR_MAP = {
    "1.mp4": 1,  # idle1 待机1
    "2.mp4": 2,  # idle2 待机2
    "3.mp4": 3,  # idle3 待机3
    "4.mp4": 4,  # cry 哭
    "5.mp4": 5,  # angry 生气
    "6.mp4": 6,  # happy 开心
    "7.mp4": 7,  # sad 难过
    "8.mp4": 8,  # shy 害羞
}

# 嘴部视频 → 形状编号（cat_m{1-4}.jpg：1=small 2=big 3=wide 4=oshape）
MOUTH_MAP = {
    "small.mp4": 1,
    "big.mp4": 2,
    "wide.mp4": 3,
    "oshape.mp4": 4,
}

BUDGET_BYTES = 3_700_000  # assets 分区 8MB − 现有 4.05MB − 余量


# ==================== 测量工具 ====================


def muzzle_bbox_norm(frame_bgr: np.ndarray):
    """口鼻部（鼻梁-嘴的深色区）归一化 bbox。

    在中央竖带（x 0.28-0.72、y 0.50-0.92）找最大深色连通块——
    避开眼睛（更上方）和画面边缘的杂散笔触。返回 (x0,y0,x1,y1)
    归一化坐标，失败返回 None。
    """
    g = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    bx0, bx1 = int(w * 0.28), int(w * 0.72)
    by0, by1 = int(h * 0.50), int(h * 0.92)
    roi = g[by0:by1, bx0:bx1]
    dark = (roi < 140).astype(np.uint8)
    n, _, st, _ = cv2.connectedComponentsWithStats(dark)
    best, best_area = None, 0
    for i in range(1, n):
        x, y, ww, hh, a = st[i]
        if a > best_area:
            best_area, best = a, (x, y, x + ww, y + hh)
    if best is None or best_area < roi.size * 0.005:
        return None
    x0, y0, x1, y1 = best
    return ((x0 + bx0) / w, (y0 + by0) / h, (x1 + bx0) / w, (y1 + by0) / h)


def mid_frame(video: Path) -> np.ndarray | None:
    """视频中间帧（顺序读到中点，避免 seek 在短视频上不可靠）。"""
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        return None
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame = None
    for _ in range(total // 2 + 1):
        ret, fr = cap.read()
        if not ret:
            break
        frame = fr
    cap.release()
    return frame


# ==================== 核心函数 ====================


def extract_expr_video(video: Path, anim_no: int, out_dir: Path) -> int:
    """表情视频 → 60 帧序列（全视频均匀采样，与原项目同段长 4s）。"""
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        print(f"  [错误] 无法打开: {video}")
        return 0

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"  源视频: {w}x{h} @ {src_fps:.1f}fps, {total} 帧")

    if total <= 0:
        cap.release()
        return 0

    # 全视频均匀采样 60 帧（原项目 video_to_jpeg_frames.py 同款均匀采样）
    indices = [
        max(0, min(total - 1, int(round(i * (total - 1) / (EXPR_FRAME_COUNT - 1)))))
        for i in range(EXPR_FRAME_COUNT)
    ]

    saved = 0
    try:
        for i, idx in enumerate(indices):
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue
            resized = cv2.resize(frame, EXPR_TARGET_SIZE, interpolation=cv2.INTER_AREA)
            out_file = out_dir / f"cat_a{anim_no}_f{i:02d}.jpg"
            cv2.imwrite(str(out_file), resized,
                        [int(cv2.IMWRITE_JPEG_QUALITY), EXPR_JPEG_QUALITY])
            saved += 1
    finally:
        cap.release()
    return saved


def extract_mouth_video(video: Path, shape_no: int, out_dir: Path,
                        ref_muzzle_norm) -> bool:
    """嘴部视频 → 320×240 全帧（muzzle 对齐裁剪）。

    嘴部视频是完整猫脸（1440×1080）。以表情参考帧的口鼻部
    归一化 bbox 为目标：把嘴部视频的口鼻部缩放/平移到与
    表情帧一致的位置与大小，裁剪后 resize 到 320×240——
    说话整帧轮换时脸不会跳。
    """
    frame = mid_frame(video)
    if frame is None:
        print(f"  [错误] 无法读取: {video}")
        return False

    m = muzzle_bbox_norm(frame)
    if m is None:
        print(f"  [错误] 口鼻部检测失败: {video.name}")
        return False

    mh, mw = frame.shape[:2]
    tw, th = MOUTH_TARGET_SIZE
    # 参考口鼻部在输出（320×240）里的像素矩形
    rx0, ry0 = ref_muzzle_norm[0] * tw, ref_muzzle_norm[1] * th
    rx1, ry1 = ref_muzzle_norm[2] * tw, ref_muzzle_norm[3] * th
    # 嘴部视频口鼻部像素矩形
    mx0, my0 = m[0] * mw, m[1] * mh
    mx1, my1 = m[2] * mw, m[3] * mh

    sx = (rx1 - rx0) / (mx1 - mx0)
    sy = (ry1 - ry0) / (my1 - my0)
    if sx <= 0 or sy <= 0:
        print(f"  [错误] 口鼻部比例异常: {video.name}")
        return False
    aniso = abs(sx - sy) / max(sx, sy)
    if aniso > 0.15:
        print(f"  [警告] 口鼻部各向异性 {aniso:.0%}（>15%，脸会有轻微变形）")

    s = (sx + sy) / 2  # 各向同性平均，避免拉伸变形
    crop_w, crop_h = tw / s, th / s
    mcx, mcy = (mx0 + mx1) / 2, (my0 + my1) / 2
    rcx, rcy = (rx0 + rx1) / 2, (ry0 + ry1) / 2
    cx0 = mcx - rcx / s
    cy0 = mcy - rcy / s

    # 裁剪窗钳回视频边界（保大小平移，必要时缩窗）
    if cx0 < 0:
        cx0 = 0
    if cy0 < 0:
        cy0 = 0
    if cx0 + crop_w > mw:
        cx0 = max(0, mw - crop_w)
    if cy0 + crop_h > mh:
        cy0 = max(0, mh - crop_h)
    crop_w = min(crop_w, mw - cx0)
    crop_h = min(crop_h, mh - cy0)

    crop = frame[int(cy0):int(cy0 + crop_h), int(cx0):int(cx0 + crop_w)]
    out = cv2.resize(crop, MOUTH_TARGET_SIZE, interpolation=cv2.INTER_AREA)
    out_file = out_dir / f"cat_m{shape_no}.jpg"
    cv2.imwrite(str(out_file), out,
                [int(cv2.IMWRITE_JPEG_QUALITY), MOUTH_JPEG_QUALITY])
    print(f"  口鼻对齐: muzzle {m[0]:.2f},{m[1]:.2f}-{m[2]:.2f},{m[3]:.2f} "
          f"-> scale {s:.2f}, crop {crop_w:.0f}x{crop_h:.0f} at "
          f"({cx0:.0f},{cy0:.0f}) of {mw}x{mh}")
    return True


def show_summary(out_dir: Path) -> int:
    print("\n" + "=" * 60)
    print("  处理完成汇总")
    print("=" * 60)
    total_size = 0
    total_files = 0
    for f in sorted(out_dir.glob("*.jpg")):
        total_size += f.stat().st_size
        total_files += 1
    anim_frames = len(list(out_dir.glob("cat_a*_f*.jpg")))
    mouth_frames = len(list(out_dir.glob("cat_m*.jpg")))
    print(f"  表情帧: {anim_frames} / {len(EXPR_MAP) * EXPR_FRAME_COUNT}")
    print(f"  嘴形帧: {mouth_frames} / {len(MOUTH_MAP)}")
    print(f"  总计: {total_files} 文件, {total_size / 1024 / 1024:.2f} MB")
    if total_size > BUDGET_BYTES:
        print(f"\n  [警告] 超出预算 {BUDGET_BYTES / 1024 / 1024:.1f}MB！"
              f"请降低 EXPR_JPEG_QUALITY 后重跑")
        return 1
    print(f"\n  预算检查: {total_size / 1024 / 1024:.2f}MB / "
          f"{BUDGET_BYTES / 1024 / 1024:.1f}MB ✓")
    print(f"\n下一步:")
    print(f"  cd G:\\demo\\21_xiaozhi\\hardware\\sets")
    print(f"  python build.py --theme cat   # 帧自动经 extra_files 打进 assets 分区")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="猫咪主题素材转换 v2（视频 → assets 帧序列）")
    parser.add_argument("--expr-src", type=Path, default=DEFAULT_EXPR_SRC,
                        help=f"表情视频目录 (默认: {DEFAULT_EXPR_SRC})")
    parser.add_argument("--mouth-src", type=Path, default=DEFAULT_MOUTH_SRC,
                        help=f"嘴部视频目录 (默认: {DEFAULT_MOUTH_SRC})")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help=f"输出目录 (默认: {DEFAULT_OUT})")
    args = parser.parse_args()

    print("=" * 60)
    print("  猫咪主题素材转换 v2（yuhe cat theme）")
    print(f"  表情: {EXPR_FRAME_COUNT} 帧/段 全视频均匀采样, "
          f"q{EXPR_JPEG_QUALITY}, {EXPR_TARGET_SIZE[0]}x{EXPR_TARGET_SIZE[1]} (4:3)")
    print(f"  嘴形: 320x240 全帧 muzzle 对齐裁剪, q{MOUTH_JPEG_QUALITY}")
    print("=" * 60)

    if not args.expr_src.exists():
        print(f"\n[错误] 表情视频目录不存在: {args.expr_src}")
        print("  请用 --expr-src 指定，或确认源项目路径")
        return 1

    # 参考口鼻部：1.mp4（idle1，最中性的表情）中间帧
    ref_frame = mid_frame(args.expr_src / "1.mp4")
    if ref_frame is None:
        print("\n[错误] 无法读取参考视频 1.mp4")
        return 1
    ref_muzzle = muzzle_bbox_norm(ref_frame)
    if ref_muzzle is None:
        print("\n[错误] 参考帧口鼻部检测失败（1.mp4 中间帧）")
        return 1
    print(f"\n参考口鼻部 (1.mp4 中间帧): "
          f"{ref_muzzle[0]:.3f},{ref_muzzle[1]:.3f}-{ref_muzzle[2]:.3f},{ref_muzzle[3]:.3f}")

    args.out.mkdir(parents=True, exist_ok=True)
    # v2 命名空间（f00-f59 + m1-m4）完整覆盖 v1（f00-f29 + m1-m4），
    # 无需清理——所有旧文件名都会被新帧覆写，不会混入旧规格。

    print("\n[表情动画]")
    for video_name, anim_no in EXPR_MAP.items():
        video = args.expr_src / video_name
        print(f"[{video_name} -> cat_a{anim_no}_f*.jpg]")
        if not video.exists():
            print(f"  [跳过] 不存在: {video}")
            continue
        saved = extract_expr_video(video, anim_no, args.out)
        print(f"  {'✓' if saved else '✗'} 已保存 {saved}/{EXPR_FRAME_COUNT} 帧")

    print("\n[嘴形全帧]")
    if not args.mouth_src.exists():
        print(f"[警告] 嘴部视频目录不存在: {args.mouth_src}（说话将无嘴形轮换）")
    else:
        for video_name, shape_no in MOUTH_MAP.items():
            video = args.mouth_src / video_name
            print(f"[{video_name} -> cat_m{shape_no}.jpg]")
            if not video.exists():
                print(f"  [跳过] 不存在: {video}")
                continue
            ok = extract_mouth_video(video, shape_no, args.out, ref_muzzle)
            print(f"  {'✓ 已保存' if ok else '✗ 失败'}")

    return show_summary(args.out)


if __name__ == "__main__":
    sys.exit(main())
