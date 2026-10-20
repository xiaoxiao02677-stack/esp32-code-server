# EMOpet 主题移植说明（PORTING.md）

> 源工程：`hardware/sets/theme/EMOpet/`（240x240 独立 ESP-IDF 工程，1711 行）
> 移植目标：主固件第三主题 `--theme emopet`，四版型（240 圆屏 / 320x240 / 240x320）自适应。

## 移植了什么

| 源文件 | 目标 | 处置 |
|---|---|---|
| `main/src/emopet_face.c`（615 行） | `emo_face.c`（直写 buffer 重写） | 表情表/插值/眨眼/转场逻辑 1:1，绘制层全换 |
| `main/include/app_config.h` | `emo_skin_types.h` | 常量改 240 基准经 layout 换算 |
| `main/include/emopet_ui.h` | `emo_face.h` | API 收窄为 canvas/表情/配色/tick |
| `main/src/overlay.c` / `keys.c` / `audio.c` / `display.c` / `main.c` | — | **不移植**（数据源/按键/音频由主固件骨架提供） |

不移植的功能与理由：
- **顶部点阵状态栏**（时间/WiFi/电量）：基类 chrome 已有（时间/电量条），重复实现无收益。
- **配网二维码（EM_QR）**：主固件走 yh_skin_cards 系统卡片 + 配网页。
- **真实频段声波**（overlay RMS 链路）：主题层不接音频链路，说话能量用 ~3Hz 正弦拟态（与像素宠物同策略），视觉语义一致。

## 渲染架构（为什么重写绘制层）

源工程全部用 `lv_canvas_draw_rect/line/polygon/arc` —— **LVGL 9.5 已删除这些旧 API**，且
绘制任务管线在 ESP32-S3 上每帧数百任务曾把像素宠物主题刷成幻灯片（2026-10-19 教训）。
本移植全部直写 RGB565 buffer（零绘制任务、零 layer 往返）：

- `px_span / px_span_blend / blend565`：像素原语（自动裁剪出界）
- `fill_blob`：胶囊/椭圆眼体（= 源 draw_blob 的 LVGL 大圆角矩形）
- `stroke_seg`：圆头粗线（贝塞尔弯月/螺旋/X 叉的笔触）
- `fill_poly`：even-odd 扫描线多边形（爱心/五角星）
- RGB565 位序经 `lv_color_to_u16()` 官方换算；stride 经 `lv_draw_buf_width_to_stride()`

### 性能三件套

1. **脏区跟踪**：`s_dirty`（上帧失效区 ∪ 本帧绘制区）局部清+局部失效，
   20MHz SPI 大屏（yh-big-ili9341）flush 量降 ~60%。
   反射光晕用 `fill_disc_y`（带 y 裁剪的圆盘）只重画脏区内部分。
2. **隔帧分频**：静止态 15fps；眨眼（0.14s）/转场（0.30s）/说话跳动自动 30fps 全速。
3. **背景跳过**：完成态背景色恒定，只有局部清屏（清屏区=脏区）。

换色（双击彩蛋）/关声波等残迹场景置 `s_full_redraw` 整屏重画一次。

## 集成方式（与 pixel-pet 完全同构）

```
Kconfig.projbuild:  choice YH_UI_THEME 新增 YH_UI_THEME_EMOPET
CMakeLists.txt:     if(CONFIG_YH_UI_THEME_EMOPET) → emo_face.c + emo_skin_display.cc
build.py:           THEMES["emopet"] = CONFIG_YH_UI_THEME_EMOPET=y
板级 yh_set_*.cc:   #elif CONFIG_YH_UI_THEME_EMOPET → new EmoSkinDisplay(...)
```

`EmoSkinDisplay` 继承 `YhSkinDisplay` 白嫖全部骨架：壁纸双槽 / 字体退休池 /
锁纪律（DisplayLockGuard fail-closed）/ 基类占位族 / chrome 控件 / 系统卡片。
只覆写视觉层（SetupUI 隐藏 avatar + 建 canvas + 帧timer / SetEmotion 映射 /
SetChatMessage 落笑意 / HandleKeyEvent / NextEasterEgg / Tick1s）。

### 状态驱动语义

- **说话/聆听态**：`OnFrameTimer` 直接读 `Application::GetDeviceState()`，
  不依赖协议消息回灌——TTS 结束自然回待机（与像素宠物同策略）。
  说话态：EMO_SPEAK 表情 + 能量拟态驱动眼睛跳动 + 底部 22 条声波条。
- **协议 emotion**：映射 15 态（happy→EMO_HAPPY / sad→EMO_SAD / winking→EMO_WINK…），
  说话/聆听期间不覆盖。
- **双击彩蛋**：眼睛配色轮换（冰蓝→玫粉→薄荷绿→暖橙），10s 窗口后恢复协议驱动。
- **低电量**：有电池的板（154tft）Tick 循环里 5s 查一次，`emo_set_battery_low`
  驱动辉光呼吸闪烁（EMO_LOWBATT 的 pulse 同款效果）。
- **开机首帧**：canvas 创建时当前态 = 压扁零光、目标态 = IDLE，插值（k=0.16）
  自然完成 ~0.5s 睁眼渐亮——**无需独立出生动画模块**。

## 眼睛绘制五层（可爱圆眼，源码设计原样保留）

1. 外光晕（1.22× 尺寸、95×g 透明）—— EMOPET 质感来源
2. 主体（主色满不透明）
3. 亮芯（主色混白 150，位置偏上）
4. **主高光**（上方偏右小白椭圆）——「灯」与「眼睛」的分界线
5. 次高光（下方偏左，更小更淡）—— 球面湿润感

其余形状（弯月/爱心/星/螺旋/X）走三层辉光：尺寸倍率 {1.00, 0.90, 0.78} ×
透明度 {70g, 150g, 255}，第 3 层用芯色（近白）。

## 顺手修复（本次发现的存量 bug）

`boards/yh-154tft-wifi/yh_set_lcd_display.h` 的 `SetupUI()` 硬编码
`YhSkinDisplay::SetupUI()` —— pixel-pet 主题下会**整层跳过 PetSkinDisplay::SetupUI**
（宠物 canvas 永不创建，屏幕只显示基类背景）。已改为继承别名
`SkinBase::SetupUI()`，三主题分支统一（继承式板级的正确写法）。

## 编译

```bash
# 用户手动执行（流程红线：编译烧录不经 agent）
python hardware/sets/build.py --board yh-n16r8-st7789 --theme emopet
# 四板同理：yh-154tft-wifi / yh-big-ili9341 / yh-cam
```

- 产物归档后缀 `-emopet`（`out/<board>-emopet/`）
- flash 占用增量 ≈ emo_face.c + emo_skin_display.cc ≈ 12KB（无位图资源）
