# bigscreen-s3 UI 规格书（提示词适配版）

> 本文档是"小柚桌宠 UI 提示词"针对本项目硬件的适配版本。
> 原提示词面向 240x240 圆屏 + LVGL v8；本项目硬件与之不同，按实际板卡重写。

## 0. 本项目硬件（不可改动的事实）

| 项目 | 本项目实际值 |
|---|---|
| 主控 | ESP32-S3（16MB Flash / 8MB Octal PSRAM） |
| 屏幕 | ILI9341 2.8" SPI **320x240 横屏**，无触屏 |
| 音频 | ES8311 codec（I2C 探测失败自动降级纯 I2S） |
| 按键 | 仅 BOOT 键（GPIO0，低电平按下） |
| 电池 | 无（板载无电池，不显示电量） |
| TTS | 云端（WS 服务端 ASR→LLM→TTS 全链路） |
| LVGL | **v9**（lv_screen_active / lv_obj_remove_flag 等 v9 API） |
| 框架 | yuhe-esp32 固件，Application 状态机 + Display 抽象 |

## 1. 屏幕定位

**big_screen.mp4 动画背景 + 一句话气泡 + 表情徽章 + 状态提示**，交互全靠 BOOT 键 + 语音。

背景动画（`big_screen.mp4` → `bigscreen_bg.c`，171 帧 GIF 循环）：
黑白手绘漫画风少女（双辫、发夹、严肃/嘟嘴表情变化）+ 两侧简笔小猫 + 粉色爱心。
转换管线：10fps 采样 → 对比度拉伸(40..215) → 高斯模糊(σ=1.0) → 12 级线性灰阶 →
相似帧合并(diff<1.2) → GIF 差分编码，最终 835KB，运行时 gifdec 解码到
ARGB8888 画布（LVGL PSRAM 池），`LvglGif` 驱动循环播放。

```text
 10:24                                    (◔ ‿ ◔)
 ┌──────────────────────────────────────────────┐
 │                                              │
 │         （big_screen.mp4 动画背景）            │
 │         少女面部居中，勿遮挡                    │
 │                                              │
 └──────────────────────────────────────────────┘
        ┌────────────────────────┐
        │ 我在呢                  │  <- 气泡 280x64
        └────────────────────────┘
      短按说话  双击彩蛋  长按静音
```

精确坐标（320x240 横屏）：

| 对象 | 位置 | 尺寸 | 说明 |
|---|---|---|---|
| GIF 背景 | 全屏 | 320x240 | 动画主体居中 |
| 时间 | 左上 (8,6) | 自适应 | 半透明深底胶囊 |
| 状态胶囊 | 左上 (8,30) | 自适应 | 配网/连接等状态（隐藏式） |
| 表情徽章 | 右上 (-8,6) | 60x60 | 圆形，noto emoji 大字号 |
| 气泡 | 中下 (0,-36) | 280x64 | 圆角 16，260 宽自动换行 |
| 底部提示 | 底部 (0,-8) | 自适应 | 12 号字 |

颜色（叠加层，深色系保证在动画上可读）：

```c
气泡底：0x1A1020 (LV_OPA_80)
徽章底：0x2A1633 (LV_OPA_70)
主粉：0xFF7AA2（气泡边框/徽章描边）
主文字：0xFFF7FB
次文字：0xC9B8D9
提示文字：0x8B7A99
```

## 2. 单 BOOT 键交互（三事件）

| 状态 | 短按 | 双击 | 长按 1 秒 |
|---|---|---|---|
| Starting | 进配网 | — | 前 30s 进配网，之后忽略 |
| 待机 | 开始说话 | 切换表情彩蛋 | 静音切换 |
| 聆听 | 结束录音 | 取消 | 取消，返回待机 |
| 说话中 | 打断 TTS | 切表情 | 打断，返回待机 |

- 长按 3 秒留给恢复出厂/重启（system_reset，原有机制不变）。
- 静音切换反馈：sad + "已静音" / cool + "声音开启啦"。

## 3. 实现架构（源码映射）

提示词里的 `ui.c` 独立状态机**不采用**——本项目已有 Application 设备状态机
（idle/listening/speaking/...）和 Display 渲染抽象，皮肤只覆写渲染层：

| 提示词概念 | 本项目实现 |
|---|---|
| `ui_init()` 建屏 | `BigscreenDisplay::SetupUI()`（`bigscreen_display.cc`） |
| `ui_set_state()` | `Application::SetDeviceState()`（原有，不动） |
| `ui_set_emotion()` | `Display::SetEmotion()`（基类管线：emoji_collection 图片 / noto emoji 字符） |
| `ui_set_bubble()` | `BigscreenDisplay::SetChatMessage()` 覆写 → 气泡 |
| `ui_set_time()` | `LvglDisplay::UpdateStatusBar()` 节拍 → 覆写 `SetStatus("HH:MM")` → 左上时间 |
| `ui_handle_key()` | 板级 `Button` 三回调 → `BigscreenDisplay::HandleKeyEvent()` 皮肤反馈 |
| `key_scan()` 轮询 | 不需要，iot_button 中断驱动（Click/DoubleClick/LongPress） |
| `[emotion:xx]` 标签解析 | 服务端协议已内置（`SetEmotion(协议名)`），无需本地解析 |
| 嘴巴动画 | 背景动画本身持续播放，不额外做说话嘴型 |

## 4. 自动行为（1s 节拍，`Tick1s()`）

- 23:30 → sleepy + "该睡啦，别熬夜"
- 07:00 → happy + "早呀宝宝，今天也要加油"
- 彩蛋展示 10 秒后自动恢复协议驱动表情
- 息屏/省电模式：停 GIF 省 SPI 带宽，唤醒后从头循环

彩蛋语音命令（服务端 LLM 侧配置，客户端走标准 SetEmotion/SetChatMessage）：

- "小智，摸摸头" → 害羞 + "摸头会变矮的"
- "小智，亲我一下" → 爱心眼 + "么么"
- "小智，晚安" → 睡觉表情 + "晚安宝宝"
- "小智，我好累" → 难过 + "先靠一会儿，我陪你"

## 5. 资源清单

| 资源 | 来源 | 位置 |
|---|---|---|
| GIF 背景 | big_screen.mp4 → `tools/mp4_to_gif_bg.py` | `main/boards/bigscreen-s3/bigscreen_bg.c`（835KB） |
| 表情 | noto emoji 字体（内置）+ 服务端 emoji_collection 资产 | 运行时下发 |
| 字体 | font_noto_sans_basic_20_4（内置） | CMake BOARD_TYPE_BIGSCREEN_S3 段 |
| GIF 解码器 | gifdec（仓库内置） | `main/display/lvgl_display/gif/` |

## 6. 测试清单

1. 上电：GIF 背景循环播放，时间/表情徽章/气泡/提示全部叠加显示。
2. 短按 BOOT：待机 → 聆听（laughing + "我在听..."）。
3. 双击 BOOT：待机 → 表情彩蛋轮播，10 秒后恢复。
4. 长按 BOOT：待机 → 静音切换（sad/cool + 气泡反馈）。
5. 长按 BOOT：聆听/说话中 → 取消/打断返回待机。
6. AI 回复带情绪：表情徽章切换 + 气泡显示最新回复（>96 字符截断）。
7. 23:30 / 07:00 整点自动行为触发。
8. 配网模式：状态文字进气泡/状态胶囊。
9. 内存：GIF 画布 ~300KB 在 PSRAM（LVGL 池），不挤占音频缓冲。
10. ES8311 缺失时降级纯 I2S，UI 不受影响。

## 7. SD 卡大背景（可选升级，v3 新增）

板背面有 microSD 卡槽（SDMMC 4-bit：CLK=38 CMD=40 D0=39 D1=41 D2=48 D3=47，
与显示/音频/BOOT 零冲突，引脚来自 Freenove 官方例程）。

**用法**：
1. SD 卡格式化为 **FAT32**（>32GB 的卡默认 exFAT，必须重新格成 FAT32）。
2. 放入 `bg.gif`（320x240 循环 GIF，**≤4MB**；用 `tools/mp4_to_gif_bg.py`
   调大 `GRAY_LEVELS`/降 `DIFF_THRESH` 可生成更高画质版本，如 16 灰阶+全帧率）。
3. 插卡上电。串口看到 `SD card mounted` + `SD background playing` 即生效。

**降级链**（任何一步失败自动回退，设备永不错过启动）：
```
SD 挂载失败(无卡/exFAT/接触不良) → Flash 内置 835KB 背景
bg.gif 不存在/超 4MB/非 GIF 魔数 → Flash 内置背景
GIF 解码失败 → Flash 内置背景
```

**内存账本**：4MB GIF 数据（PSRAM 直读）+ 320x240 解码画布 ~384KB（LVGL
PSRAM 池）+ 音频/WebSocket 缓冲 —— 8MB Octal PSRAM 内安全。

**性能提示**：SDMMC HighSpeed 40MHz 4-bit 实测读 ~2-4MB/s，开机一次性
读入 4MB 约 1-2 秒（后台任务，不阻塞 UI/配网）。

## 8. 已知取舍

- 12 级灰阶 + σ1.0 模糊是 835KB 预算内的画质平衡点；黑白漫画风格损失可接受。
- 相似帧合并后实际帧率 ~8.5fps（171 帧/20 秒），手绘动画观感够用。
- 表情徽章在右上角而非中心：背景动画主体（少女面部）不可遮挡。
- 无电池，省略电量显示（提示词中的电量行不适用）。
