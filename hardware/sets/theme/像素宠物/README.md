# 女友聊天机 · 方案 A（软萌像素宠物） · ESP-IDF v6.1 工程

240×240 **方形** IPS（ST7789）+ 三键（BOOT / VOL+ / VOL-）+ I2S 麦克风。
包含完整的 **3.8s 开机动画**：暗底发光登场 → 屏幕「开灯」→ 五官依次点亮 → 睁眼问候 → 落位待机。

---

## 1. 环境

| 项目 | 要求 |
|---|---|
| ESP-IDF | **v6.1**（v6.0 亦可；v5.x 需改回 legacy I2S 与 `bits_per_pixel`） |
| 安装方式 | 推荐 EIM：`eim install -i v6.1` |
| Python | ≥ 3.10（v6.x 的硬性要求） |
| 芯片 | ESP32-S3（**强烈建议带 PSRAM**，双缓冲 + canvas 共约 350KB） |
| 工具链 | GCC 15.x（v6.1 自带） |

## 2. 编译

```bash
idf.py set-target esp32s3
idf.py menuconfig          # → 女友聊天机 · 硬件配置（改引脚）
idf.py build
idf.py -p /dev/ttyUSB0 flash monitor
```

首次 `build` 会自动从组件注册表拉取 `lvgl/lvgl ^9` 与 `espressif/esp_lvgl_port ^2`，需要联网。

若启动后屏幕方向/偏移不对，调 `menuconfig → LCD_GAP_X / LCD_GAP_Y / 镜像`。
（1.3" 240×240 ST7789 模块常见需要 `LCD_GAP_Y = 0`，1.54" 常见需要 `20`。）

## 3. 接线（默认，可在 menuconfig 改）

### LCD — ST7789 SPI 240×240
| 屏 | ESP32-S3 GPIO | menuconfig 项 |
|---|---|---|
| SCLK | 12 | `LCD_PIN_SCLK` |
| MOSI | 11 | `LCD_PIN_MOSI` |
| CS | 10 | `LCD_PIN_CS` |
| DC | 13 | `LCD_PIN_DC` |
| RST | 14 | `LCD_PIN_RST` |
| BLK | 15 | `LCD_PIN_BLK` |

### 按键（按下接地，内部上拉）
| 键 | GPIO | 说明 |
|---|---|---|
| BOOT | 0 | 单击说话 / 长按菜单 / 双击发预录语音 |
| VOL+ | 4 | 音量 +，菜单内上移 |
| VOL- | 5 | 音量 −，长按换表情 |

### 麦克风 — INMP441（I2S）
| 引脚 | GPIO |
|---|---|
| BCLK | 41 |
| WS | 42 |
| DIN | 2 |

没有麦克风也能玩：把 `MIC_ENABLE` 关掉，或开 `PET_FAKE_AUDIO`，用模拟能量驱动嘴形动画。

## 4. 目录结构

```
esp32_pet_chat/
├── CMakeLists.txt
├── sdkconfig.defaults        # PSRAM / LVGL9 / CJK 字体 / 1ms tick
├── partitions.csv
├── main/
│   ├── CMakeLists.txt
│   ├── idf_component.yml     # lvgl ^9 + esp_lvgl_port ^2
│   ├── Kconfig.projbuild      # 引脚与行为全部可配置
│   ├── include/
│   │   ├── app_config.h      # 布局常量 / 状态枚举 / 开机进度结构
│   │   └── pet_ui.h          # 模块接口
│   └── src/
│       ├── main.c            # 初始化 + 状态机 + 渲染循环
│       ├── display.c         # SPI + ST7789 + LVGL port（含防花屏）
│       ├── pet_canvas.c      # ★ 像素宠物自绘（核心）
│       ├── boot_anim.c       # ★ 3.8s 开机动画进度推进
│       ├── ui_screens.c      # 顶栏 / 气泡 / 音量条 / 2×2 菜单
│       ├── keys.c            # 三键状态机（单击/双击/长按/双键同按）
│       └── audio.c           # I2S std 采集 + RMS 能量
```

## 5. 开机动画（11 幕，3.8s）

| 幕 | 时间 | 画面 |
|---|---|---|
| — | 0.00–0.20 | 黑屏（背光延迟开启，避免上电花屏） |
| ① | 0.20–0.60 | 中心一粒暖光种子，轻微呼吸 |
| ② | 0.60–1.00 | 三层柔光涟漪扩散，种子随之淡出 |
| ③ | 1.00–1.50 | 轮廓沿椭圆**从 12 点双向展开**，底部合拢 |
| ④ | 1.50–1.90 | **开灯**：填充注入 + 背景提亮（严格同步，全片高潮） |
| ⑤ | 1.90–2.20 | 耳朵弹出（back_out 过冲回弹） |
| ⑥ | 2.20–2.45 | 腮红点亮（左右错开 0.05s） |
| ⑦ | 2.45–2.85 | **睁眼**（必须最后：睁眼 = 意识上线） |
| ⑧ | 2.85–3.40 | 气泡「你回来啦」淡入上弹 |
| ⑨ | 3.40–3.80 | 气泡淡出、顶栏/音量条/四角角标淡入、落位待机 |

三条分支：
- **未配网首开机** → 结尾显示二维码占位，且**不响应跳过**
- **深度唤醒** → 0.6s 短版，只播睁眼（`esp_sleep_get_wakeup_cause()` 判定）
- **纪念日 / 生日** → 结尾撒花彩蛋

## 6. 已实现 / 待接入

**已实现**：开机动画、宠物绘制、三种表情、随机眨眼、音频 RMS 驱动嘴形与耳朵、三键状态机、2×2 菜单、气泡、顶栏、音量条、四角取景框。

**待接入**（工程里已留好位置）：
- 语音上传与 LLM 回复 —— 见 `main.c` 的 `KEY_EVT_BOOT_SINGLE` 分支与「演示回路」注释
- BOOT 双击的预录语音「想你了」—— **建议用你自己的声音**，8kHz 存 flash
- 开机 1.50s 的配音 —— `boot_anim.c` 中 `play_boot_chime()` 的注释处
- 真实二维码 —— 用 `espressif/qrcode` 替换 `ui_show_qr_placeholder()`
- RTC 校时 —— 现在问候语用 `esp_random()` 演示，接 RTC 后按小时选

## 7. 首次编译若报错，优先看这 3 处

本工程按 v6.1 API 编写，以下三处受版本差异影响最大（已在代码里注释标出）：

1. **`esp_lcd_panel_dev_config_t` 的色格式字段**（`display.c`）
   v6.1 用 `.color_format = LCD_COLOR_FORMAT_RGB565` 取代 `.bits_per_pixel = 16`。
   若报字段名不存在，打开 `$IDF_PATH/components/esp_lcd/include/esp_lcd_panel_dev.h` 确认实际字段名。

2. **LVGL canvas 的 buffer 参数**（`pet_canvas.c`）
   LVGL 9 用 `LV_COLOR_FORMAT_RGB565`；若你锁到 LVGL 8，改回 `LV_IMG_CF_TRUE_COLOR`（代码里已有版本宏）。

3. **中文字体宏**（`ui_screens.c`）
   依赖 `CONFIG_LV_FONT_SIMSUN_16_CJK`。若 menuconfig 里没有这一项，选任意一个 CJK 字体并把 `UI_FONT_CN` 指向它。

另外 v6.x **默认开启"警告即错误"**，本项目已在 `main/CMakeLists.txt` 里加 `-Wno-unused-parameter` 兜底；若你的代码新增后出现新警告，先修警告再构建。

## 8. docs/ 目录

- `esp32_boot_preview_square.html` —— 开机动画可交互预览（浏览器打开，含时间轴拖拽、0.25× 慢放、四条分支），**改代码前先在这里确认观感**
- `ESP32女友聊天机_方案A_开机动画.md` —— 11 幕分镜与实现要点
- `ESP32女友聊天机_方案A_软萌像素宠物.md` —— 方屏布局、配色、动效参数

## 9. 验证状态

本工程的全部 `.c` 已通过 **语法与符号级静态检查**（桩环境 + `gcc -Wall -Wextra`），
但**未在本环境做真实交叉编译**（沙盒无 ESP-IDF 工具链与 xtensa 编译器）。
因此裸机实跑前请按第 7 节核对三处版本相关字段。
