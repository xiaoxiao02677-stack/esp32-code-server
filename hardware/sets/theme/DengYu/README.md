# 灯语 DengYu · AI 女友陪聊主题（光萤情绪灯 + 剧场字幕流）

> 屏幕是一盏会说话的灯。
> 光萤（orb）承载情绪——呼吸、涟漪、轮换配色；剧场字幕流承载语言——
> 角色分色、逐字浮现。无气泡框、无 emoji、无多余 chrome，夜幕底色上
> 只剩「她」和「你们的话」。

先打开 `docs/dengyu_ui_preview.html` 看设计提案（240×320 设备仿真器，
六态可切换：待机/聆听/思考/说话/晨间/断连，色板 token 表与 LVGL 落地
路径都在里面）。

本主题已集成进 sets 构建链，不再作为独立工程维护：

```bash
cd hardware/sets
python build.py --board yh-cam --theme dengyu          # 单板单主题
python build.py --all                                   # 全矩阵（含 dengyu）
```

四板全适配：`yh-cam`（320×240 横/240×320 竖，NVS `lcd_mode` 切换）、
`yh-big-ili9341`（320×240 横）、`yh-154tft-wifi` / `yh-n16r8-st7789`
（240 圆屏）。

---

## 1. 设计要点

| 要点 | 说明 |
|---|---|
| **光萤即情绪** | 4 层硬边同心圆（芯 20/64 → 外 64/64），呼吸 zoom 256↔284、双道错相涟漪。**绝不用渐变**——RGB565 连续渐变必带色带，分层圆是风格不是妥协 |
| **配色轮换** | 双击 BOOT：炭火(暖橙)→月光(青蓝)→紫暮(薰衣草)→珊瑚(蜜桃)，NVS `dengyu/palette` 记忆 |
| **状态光语** | 待机=呼吸+涟漪+短句轮播 / 聆听=青苔绿提速 / 思考=三点跳动 / 说话=迷你光萤+EQ / 断连=珊瑚红放缓呼吸 |
| **剧场字幕流** | 无框字幕，你=右对齐暖橙、灯灯=左对齐纸白，who 标签 14px 雾蓝；行入场 y+8+淡入 340ms |
| **逐字打字机** | AI 回复 90~140ms/字随机抖动（`lv_timer_set_period` 每 tick 重设），UTF-8 按码点追加绝不切半 |
| **晨间卡片** | 每天 07:00 纸白底大时钟 30 秒 + 陪伴天数问候（NVS `dengyu/days` 跨日 +1）；天气胶囊占位预留 |
| **圆屏变体** | 光萤上区 + 单行字幕居中（不做 6 行历史） |
| **状态机真源** | `Application::GetDeviceState()` 250ms 轮询对账（PetSkin 先例），协议事件只做即时预置，TTS 结束自然回待机 |

## 2. 字体策略（重要）

| 内容 | 字体 | 理由 |
|---|---|---|
| 动态聊天文本 | 主题 text 字体（basic 890 字 → assets 运行时 common 5258 字） | 继承基类退休池/全树重绑，零悬垂风险 |
| 固定文案（状态短语/短句/问候/标签） | `font_dengyu_16_4` 专属字档（158 码位，~24KB flash） | 组件 16_4 是**限词表**（连「灯/萤」都没有），固定文案必须走专属字档 |
| 晨间时钟 | 主题 text（20_4） | 冒号+数字 basic 全有 |

`font_dengyu_16_4.c` 由 `yuhe-esp32/main/display/DengYu_skin/gen_dengyu_font.py`
生成（`npx lv_font_conv`，TTF 取 lvgl 测试目录 NotoSansSC，与
`yh_skin/font_splash_20_4.c` 同一模式）。**改固定文案后必须重跑脚本**，
新字符不重打包就会显示豆腐块。

## 3. 源码位置

```
yuhe-esp32/main/display/DengYu_skin/
├── dengyu_skin_types.h    # 状态/调色板/几何/动效类型
├── dengyu_orb.h/.c        # 光萤渲染模块（wrapper 容器 + CENTER 对齐，
│                          #   size 动画自动居中不漂移）
├── dengyu_skin_display.h/.cc  # 主类（继承 YhSkinDisplay 骨架）
├── font_dengyu_16_4.c     # 固定文案专属字档（生成物）
└── gen_dengyu_font.py     # 字档生成脚本
```

接线点（与 pixel-pet/emopet 完全同构）：
- `main/Kconfig.projbuild`：`choice YH_UI_THEME` 的 `YH_UI_THEME_DENGYU`
- `main/CMakeLists.txt`：条件编入 + `BOARD_TYPE` 追加 `-dengyu` 后缀
  （OTA 轨道隔离，`out/<id>-dengyu/` 产物目录一致）
- 四板 `yh_set_*.cc` / `yh_set_lcd_display.h`：`#elif CONFIG_YH_UI_THEME_DENGYU`
  分支（构造签名与 YhSkinDisplay 完全一致，只换类名）
- `build.py`：`THEMES["dengyu"]` + `theme_keys` 剔除集

## 4. 交互

| 操作 | 反馈 |
|---|---|
| 短按 BOOT | 进入聆听（青苔绿光语 +「在听，慢慢说」） |
| 双击 BOOT | 轮换光萤配色（4 盘循环，NVS 记忆，短语报盘名） |
| 长按 BOOT | 静音状态提示（「已静音」/「声音开着」） |

## 5. 色板（RGB565 量化，与提案 token 表对账）

| token | RGB888 | RGB565 | 用途 |
|---|---|---|---|
| night | `#080C19` | 0x0863 | 全局底色 |
| ember400 | `#F7A65A` | 0xF52B | 用户字幕 |
| ember300 | `#FFCA8C` | 0xFE51 | 思考态短语 / EQ 柱 |
| cream | `#F7EFE6` | 0xF77C | AI 字幕 / 待机短句（对底 17.1:1） |
| haze500 | `#8C96BD` | 0x8CB7 | who 标签 |
| sage | `#ADDBB5` | 0xAED6 | 聆听态（全案唯一冷色） |
| coral | `#EF715A` | 0xEB8B | 断连/异常 |
| paper | `#F7EFE6` | 0xF77C | 晨间卡片底 |
| d-text | `#312819` | 0x3143 | 晨间卡片正文 |

## 6. 已知取舍

- **早晚问候 emoji 不可见**：基类 07:00/23:30 的问候走 `LcdDisplay::SetEmotion`
  emoji 路径，光语主题 avatar 已隐藏——晨间卡片（07:00 大钟）已覆盖早晨
  场景，晚安问候缺失属可接受损耗（提案 TIER B 项）。
- **天气胶囊预留未实现**：服务器 weather 指令通道未接，字段占位。
- **打字机为本地模拟**：全文到达后 90-140ms/字播放，非流式 TTS 对齐
  （用户选定方案，见三轮问答记录）。
