# 猫咪主题（cat）

> 移植自 `G:\demo\22 cat` 项目（upload_facial_expression/integrated）——
> 8 段 JPEG 表情动画 + 说话嘴形拟态的猫脸，融入 yuhe 六主题体系
> （`--theme cat`）。

## 设计要点

| 项 | 值 | 说明 |
|---|---|---|
| 视觉模型 | JPEG 帧序列 + canvas 直写 | 原项目 1:1 移植，非矢量自绘 |
| 表情动画 | 8 段 × 60 帧 | idle1-3 / cry / angry / happy / sad / shy，15fps × 4s（与原项目同段长）|
| 嘴形拟态 | 4 形状全帧轮换 | small→big→wide→oshape，90ms；320×240 全帧按口鼻对齐（素材端裁剪）|
| 待机循环 | 60/30/10 随机 | 60% idle / 30% happy+shy / 10% cry+angry+sad（原项目分布）|
| 循环切换 | **硬切无缝** | 原项目 animLoop 注释："无缝衔接，不渐变"；淡入只给情绪指令 |
| 状态角标 | 右上角彩色圆点 | 动画之外的第二信号通道（face 主题辉光同哲学）|
| 交叉淡入 | 300ms | RGB565 逐像素 lerp（原项目 500ms 的紧凑版），仅情绪指令路径 |
| 帧缓存 | 无（逐帧按需解码） | 总 PSRAM ~615KB；整段缓存会挤爆语音模型加载（v1 实机崩溃教训）|
| 帧尺寸 | 320×240（4:3） | 源视频 1112×834 / 原项目 284×240 均为 4:3；显示 contain-fit 四板 |

## 状态信号对照表（用户硬需求：按 BOOT 后必须知道自己处于哪个状态）

| 设备态 | 动画 | 角标 | BOOT 按下时 |
|---|---|---|---|
| 待机 idle | 随机猫动画循环 | 淡蓝 #B4DCFF | — |
| 聆听 listening | **idle1 定格注视帧**（动画骤停） | 青绿 #7BE8A0 | 单击进入 |
| 说话 speaking | 嘴形全帧轮换（口鼻对齐，脸不跳） | 暖橙 #F7B96A | 单击打断 |
| 连接/配网/升级/激活 | 沿用当前动画 | 琥珀 #F7D96A 慢闪 1.6s | — |
| 致命错误 | angry 锁定 | 珊瑚红 #F76E5E | — |
| 静音（长按切换） | 沿用 | 灰 #9E9E9E 短显 2s | 长按触发 |

角标色表与 face 主题状态辉光完全一致——跨主题视觉语言统一，用户
换主题不用重新学习状态色。

## BOOT 键（板级行为 + 皮肤视觉）

| 事件 | 板级行为（已有） | 皮肤视觉（本主题） |
|---|---|---|
| 单击 | ToggleChatState（进聆听/打断） | idle1 定格 + 青绿角标**即时**亮（不等 250ms 轮询） |
| 双击 | HandleKeyEvent(1) | 彩蛋动画（cry/angry/sad 随机，播完回循环） |
| 长按 1s | 静音切换（音量 0⇄70） | 灰角标短显 2s |
| 长按（聆听/说话中） | 取消对话回待机 | 角标回淡蓝 |

## 开机流程（WiFi/配网）

复用 yuhe 基类骨架，零新增代码：
1. 基类 SetupUI 建品牌 splash（屿禾工坊）→ 猫脸在其下，恒不遮挡
2. 无 WiFi → 基类系统卡片弹出配网指引（ShowNotification 白嫖）
3. Connecting/Activating 态 → 轮询亮琥珀角标慢闪
4. 联网完成 → 角标回落淡蓝，随机循环开始

## 素材管线（用户本地执行）

```bash
# 1. 生成帧（源：G:\demo\22 cat\upload_facial_expression）
pip install opencv-python numpy
python theme/cat/tools/video_to_frames.py
# 产物：theme/cat/frames/cat_a{1-8}_f{00-59}.jpg + cat_m{1-4}.jpg
#       表情 60 帧/段 全视频均匀采样 q60；嘴形 320×240 全帧口鼻对齐裁剪

# 2. 编译（帧自动经 DEFAULT_ASSETS_EXTRA_FILES 进 assets 分区）
python build.py --board yh-n16r8-st7789 --theme cat
```

容量预算：assets 分区 8MB − 现有字体/emoji/语音 4.05MB ≈ 3.7MB 可用；
60帧×8段×q60 ≈ 3.3MB，余量 0.4MB。缺帧时 CMake 直接 FATAL_ERROR
并提示生成命令（构建期拦截，不烧空主题）。

## 源布局

```
theme/cat/                          # 归档（设计文档 + 素材工具）
├── README.md                       # 本文件
├── tools/video_to_frames.py        # 视频 → 帧序列（OpenCV，v2 口鼻对齐）
└── frames/                         # 生成产物（平铺命名，进 assets 分区）

yuhe-esp32/main/display/cat_skin/   # 固件源
├── cat_anim.h/.cc                  # 渲染核心：JPEG 解码 + 缩放 blit + 播放状态机
└── cat_skin_display.h/.cc          # 显示层：YhSkinDisplay 子类（状态对账 + 按键视觉）
```

## 与原项目的差异

| 项 | 原项目 | yuhe cat 主题 |
|---|---|---|
| 存储 | LittleFS 目录（/cat/animN/） | mmap assets 分区平铺文件 |
| 段长 | 80 帧 × 50ms = 4s | 60 帧 × 66ms = 4s（等时长）|
| 帧尺寸 | 284×240 | 320×240（同为 4:3）|
| 嘴形驱动 | 舵机（音量实时驱动） | 嘴形全帧 90ms 定时轮换（拿不到解码音量）|
| 状态区分 | 无（主循环纯随机） | 角标 + 聆听定格 + 彩蛋/静音反馈 |
| 网络交互 | WiFi 固定 + WS 调试 | yuhe 协议全链路（配网/OTA/激活）|
| 交叉淡入 | 500ms（EXPR 路径） | 300ms（同仅情绪路径；循环硬切与原项目一致）|

## 屏幕适配（四板 contain-fit）

素材 320×240（4:3），`cat_geom_make` 按屏宽高比 contain-fit 缩放居中：

| 板 | 屏 | 猫脸绘制区 | 留黑 |
|---|---|---|---|
| n16r8-st7789 / 154tft | 240×240 圆屏 | 240×180 @(0,30) | 上下各 30px |
| big-ili9341 / cam 横屏 | 320×240 | **320×240 满屏** | 无 |
| cam 竖屏 | 240×320 | 240×180 @(0,70) | 上下各 70px |

缩放用整数比最近邻（320→240 即 3:4 整数比，无锯齿）；角标落在猫脸
右上空白区 (0.85W, 0.10H)，圆屏验证距圆心 111 < 内切圆 120。
