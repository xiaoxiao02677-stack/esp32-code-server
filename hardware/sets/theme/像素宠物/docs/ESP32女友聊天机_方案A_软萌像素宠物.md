# 方案 A · 软萌像素宠物（Pixel Pet）

> ESP32 女友聊天机 · **240×240 方形 IPS**（ST7789 / ILI9341）· VOL+ / VOL− / BOOT 三键
> 可交互预览：`esp32_boot_preview_square.html`（浏览器打开，实时播放开机动画）
>
> **硬件已确认为方屏**，本文档按方屏布局编写。方屏相对圆屏的红利：四角可用、气泡可拉宽、宠物可放大、菜单可用列表。

---

## 1. 设计定位

屏幕正中养一只像素小兽。**它不是图标，是一个会呼吸的角色**——会眨眼、打哈欠、听你说话时竖起耳朵、回应你时嘴巴一张一合。

这套方案的核心赌注是：**情感反馈靠"生命感"，不靠信息量**。三个键、240×240 的屏，塞不下复杂 UI；但一只会动的小兽，足够让人每天想摸一下。所以全部设计资源都押在"让它看起来是活的"这件事上：

- 眨眼**随机**（不是定时）——规律眨眼一眼假，随机才像活的
- 耳朵**跟着你的声音竖起**——声音越大竖得越直，给它一个"被你唤醒"的反应
- 嘴形**跟着 TTS 开合**——它说话时嘴巴真的在动，而不是播个动画

**气质关键词**：治愈、暖、不闹。配色是奶油米 + 蜜桃粉，长时间摆桌上不刺眼。

---

## 2. 方屏布局：四区纵向排布

方屏 240×240 没有内切圆约束，**四角全部可用**，布局按纵向四区切分：

| 区域 | y 范围 | 内容 | 说明 |
|---|---|---|---|
| 顶栏 | 0–34 | 左：时间 `20:14`；右：Wi-Fi 弧 + 电量 | 圆屏只能挤在顶部弧内，方屏可占满整行 |
| 主舞台 | 40–200 | 像素小兽的脸（`rx 70 / ry 62`，中心 y≈126） | 方屏可放大；圆屏受 r<60 限制只能 62 |
| 气泡区 | 26–92 | 聊天气泡（宽 200，一行 10 字） | 方屏横向空间足，气泡可拉满 |
| 底栏 | 210–240 | 音量条（直线，宽 160）+ 提示文字 | **弧线在方屏会切掉四角，改用直条** |

**四角角标**：屏幕四角画 L 形取景框（长 14px、宽 2px、`sub` 色 @55%）。这是方屏独有的装饰——圆屏物理上做不到。它让界面读起来像"一台设备的取景框"，精致感提升明显，成本只有 8 条线。

**宠物是绝对主角**：脸占 140×124，几乎顶满主舞台。其余元素全部压扁、压小、压到边上——这是"养宠物"和"用工具"的区别。

---

## 3. 四个状态的界面定义

| 状态 | 界面 |
|---|---|
| **① 待机 Idle** | 眼睛眯成线（3–5s 随机眨一次，偶尔打哈欠）；底栏直条显示当前音量；底部「Zzz · 按 BOOT 说话」 |
| **② 聆听中 Listening** | 耳朵瞬间竖起、瞳孔放大；屏幕下方一排像素声波条随你的声音跳动；文案「在听你说…」 |
| **③ 回应中 Speaking** | 气泡从上方淡入并轻微上弹，小兽**下移 18px** 给气泡让位、耳朵耷拉（放松态）；嘴随 TTS 能量开合 |
| **④ 菜单 Menu** | **2×2 网格**：音量 / 表情 / 亮度 / 夜间，选中项放大 8% 并填充主色；四角保留取景框角标 |

**两个容易忽略但很加分的细节**：

1. **回应时小兽要下移**。气泡占了上方空间，如果宠物不动，两张脸会挤在一起；让它往下挪一点、耳朵顺势耷拉下来，读起来就是"它抬头看着气泡在念"——一个位移换来一个叙事。
2. **音量条只在待机时高亮**。调音量时条亮起，2 秒后自动淡回低对比度。常亮的装饰元素会夺走宠物焦点。

---

## 4. 三种表情皮肤（长按 VOL− 切换）

同一套骨架，只换耳朵形状参数 + 配色，**零额外内存**。

| 皮肤 | 耳朵画法 | 配色 |
|---|---|---|
| ① 猫 · 尖耳 | 三角形（默认） | 脸 `#FFCAB8`，描边 `#BE7664` |
| ② 小熊 · 圆耳 | 两个圆 | 脸 `#E8C39A`，描边 `#A87B55` |
| ③ 云兽 · 云朵耳 | 三圆叠成云 | 脸 `#DCEBF7`，描边 `#8FB4D0` |

> 换皮肤不是换图——是改一个 `pet_skin_t` 结构体里的 6 个颜色 + 1 个耳朵枚举。这是这套方案最省的地方。

---

## 5. 配色表

| 用途 | 色值 | 说明 |
|---|---|---|
| 背景 | `#FFF3E4` | 奶油米，久看不累 |
| 宠物脸 | `#FFCAB8` | 蜜桃粉 |
| 描边 | `#BE7664` | 比脸深两档的暖褐，**保证像素轮廓清晰** |
| 眼 / 主文字 | `#4A3B37` | 暖黑，比纯黑柔和 |
| 次级文字 | `#C49E8A` | 状态行、提示语 |
| 腮红 | `#FF9E9E` @170 | 三格像素块，位置在眼下 |
| 强调 / 声波 | `#FF9682` | 音量弧、声波条、菜单选中 |
| 气泡底 | `#FFFFFF` | 白底 + 暖褐描边 |

**描边色是这套配色的命门**：像素画全靠轮廓线立住，描边太浅会让整只兽糊成一团；`#BE7664` 比脸深约两档，正好。

---

## 6. 动效参数表

| 动画 | 时长 | 曲线 | 说明 |
|---|---|---|---|
| 眨眼 | 120 ms | linear | 随机延迟 2–6s，回调里再启一次形成不规则节奏 |
| 耳朵竖起 | 200 ms | `ease_out` | 由音频能量驱动，非定时动画 |
| 嘴形开合 | 50 ms 更新 | 指数平滑 0.85 | 直接映射 RMS |
| 气泡淡入 | 160 ms | `back_out` | 带轻微上弹 |
| 呼吸浮动 | 2400 ms | `ease_in_out` | 整体 y ±3px，只有待机时开 |
| 菜单选中放大 | 150 ms | `ease_out` | 半径 19 → 24 |
| 音量弧提示 | 2000 ms 后淡出 | — | 调完自动回到低对比度 |

**帧率**：待机 15fps（省电），聆听 / 回应 25–30fps。别追 60，宠物动画 20Hz 更新足够。

---

## 7. 三键交互

| 操作 | 待机 | 聆听中 | 回应/播放中 | 菜单内 |
|---|---|---|---|---|
| **BOOT 单击** | 唤醒 + 开始录音 | 结束录音并发送 | 打断，停止播放 | 确认 / 进入 |
| **BOOT 长按 2s** | 打开环形菜单 | 取消 → 待机 | 取消 → 待机 | 返回上一级 |
| **BOOT 双击** | 发送预录语音「想你了」 | — | — | — |
| **VOL+ 单击** | 音量 +1（弧闪） | 音量 +1 | 音量 +1 | 上一项 |
| **VOL− 单击** | 音量 −1 | 音量 −1 | 音量 −1 | 下一项 |
| **VOL+ 长按 1s** | 亮度 +10% | — | — | 连续滚动 |
| **VOL− 长按 1s** | **换表情**（猫→熊→云兽） | — | — | 连续滚动 |
| **VOL+ 与 VOL− 同按** | 夜间模式 + 静音 | 同左 | 同左 | 退出菜单 |
| **三键齐按 3s** | 重新配网 / 恢复出厂 | — | — | — |

**省电**：30s 无操作 → 亮度 30%；60s → 熄屏，只留一个 r=3 的极暗呼吸点；BOOT 唤醒。

---

## 8. 实现要点

### 8.1 不要逐帧 PNG——整只兽用图元画

一套眨眼 + 张嘴的逐帧动画，10 帧 240×240 RGB565 就要 1.1 MB，PSRAM 也扛不住。而整只兽**全是椭圆和矩形**：

- 脸 = 两个椭圆（描边层 + 填充层）
- 耳朵 = 两个三角 / 两个圆
- 眼睛 = 两个矩形（+ 高光小矩形）
- 腮红 = 六个小矩形
- 嘴 = **一个椭圆的高度参数**

所以：一个自定义 obj + `LV_EVENT_DRAW_MAIN`，几十行代码、零位图、内存几乎为零。嘴形动画只是改一个数字，比换图快一个数量级。

### 8.2 嘴形与耳朵：一个 RMS 驱动两个参数

```c
// 音频采集任务：20ms 周期，只算 RMS（方案 A 不需要 FFT）
#define MIC_BUF 256
static int16_t mic[MIC_BUF];
static float   smooth_rms = 0.f;

void audio_rms_task(void *arg) {
    size_t bytes;
    while (1) {
        i2s_read(I2S_NUM_0, mic, sizeof(mic), &bytes, portMAX_DELAY);
        float sum = 0.f;
        for (int i = 0; i < MIC_BUF; i++) { float s = mic[i] / 32768.f; sum += s * s; }
        float rms = sqrtf(sum / MIC_BUF);
        smooth_rms = smooth_rms * 0.85f + rms * 0.15f;          // 指数平滑，防抖
        ui_push_energy(fminf(1.0f, smooth_rms * 8.f));           // 归一化 0..1
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}

// UI 侧定时器：20Hz 更新嘴形与耳朵，避免跨线程直接操作 LVGL 对象
static void pet_anim_timer(lv_timer_t *t) {
    float e = ui_get_energy();
    pet.mouth_h = 4 + (int)(26 * e);                 // 嘴高 4..30
    pet.ear_lift = e;                                 // 耳朵竖起量 0..1
    pet.head_y   = (ui_state() == ST_SPEAK) ? 142 : 124;
    lv_obj_invalidate(pet_obj);                       // 触发重绘
}
lv_timer_create(pet_anim_timer, 50, NULL);
```

### 8.3 随机眨眼：不规律才像活的

```c
static void blink_anim(void *obj, int32_t v) { pet.eye_open = v; lv_obj_invalidate(obj); }

static void blink_start(lv_anim_t *a) {
    lv_anim_t n; lv_anim_init(&n);
    lv_anim_set_var(&n, pet_obj);
    lv_anim_set_exec_cb(&n, blink_anim);
    lv_anim_set_values(&n, 255, 0);                  // 睁 → 闭
    lv_anim_set_time(&n, 120);
    lv_anim_set_delay(&n, esp_random() % 4000 + 2000); // 随机 2–6s
    lv_anim_set_ready_cb(&n, blink_ready);            // 播完再起一次，间隔重新随机
    lv_anim_start(&n);
}
// 打哈欠：每 5 次眨眼里随机插一次 800ms 的张大嘴版本，小概率事件最出戏
```

### 8.4 宠物绘制（完整骨架）

```c
typedef struct {
    lv_color_t bg, face, line, ink, sub, blush, accent;
    uint8_t    ear_shape;        // 0=尖耳 1=圆耳 2=云朵耳
} pet_skin_t;

static void pet_draw(lv_event_t *e) {
    lv_obj_t *obj = lv_event_get_target(e);
    lv_draw_ctx_t *ctx = lv_event_get_draw_ctx(e);
    const pet_skin_t *s = &g_skin;
    int cx = 120, cy = pet.head_y;
    int lift = (int)(16 * pet.ear_lift);              // 耳朵竖起量

    // 耳朵（三种形状）
    for (int k = 0; k < 2; k++) {
        int sgn = k ? 1 : -1, bx = cx + sgn * 34, tip = cy - 62 - lift;
        if (s->ear_shape == 0) {
            lv_point_t tri[] = {{bx - 5, cy - 44}, {bx + 5, cy - 44}, {bx + sgn * 27, tip}};
            lv_draw_polygon_dsc_t pd; lv_draw_polygon_dsc_init(&pd);
            pd.bg_color = s->line; pd.bg_opa = LV_OPA_COVER;
            lv_draw_polygon(ctx, &pd, tri, 3);
        } else if (s->ear_shape == 1) {
            lv_draw_rect_dsc_t rd; lv_draw_rect_dsc_init(&rd);
            rd.bg_color = s->line; rd.radius = LV_RADIUS_CIRCLE;
            lv_area_t a = {bx + sgn * 17 - 15, tip + 12 - 15, bx + sgn * 17 + 15, tip + 12 + 15};
            lv_draw_rect(ctx, &rd, &a);
        } else { /* 云朵耳：三个小圆 */ }
    }

    // 脸：描边椭圆 + 填充椭圆（像素感靠"边缘对齐到 8px 网格"实现）
    lv_draw_rect_dsc_t fd; lv_draw_rect_dsc_init(&fd);
    fd.radius = LV_RADIUS_CIRCLE; fd.bg_opa = LV_OPA_COVER;
    fd.bg_color = s->line;
    lv_area_t o = {cx - 66, cy - 58, cx + 66, cy + 58};  lv_draw_rect(ctx, &fd, &o);
    fd.bg_color = s->face;
    lv_area_t f = {cx - 62, cy - 54, cx + 62, cy + 54};  lv_draw_rect(ctx, &fd, &f);

    // 腮红（各 3 格）
    fd.bg_color = s->blush; fd.bg_opa = LV_OPA_70;
    for (int k = 0; k < 2; k++)
        for (int i = 0; i < 3; i++) {
            int bx = (k ? cx + 42 : cx - 42) - 8 + i * 8;
            lv_area_t b = {bx, cy + 16, bx + 6, cy + 22}; lv_draw_rect(ctx, &fd, &b);
        }

    // 眼睛：睁开=矩形+高光，眯眼=细横条
    fd.bg_opa = LV_OPA_COVER; fd.radius = 0; fd.bg_color = s->ink;
    for (int k = 0; k < 2; k++) {
        int ex = cx + (k ? 22 : -22);
        lv_area_t a = pet.eye_open > 128 ? (lv_area_t){ex - 8, cy - 20, ex + 8, cy + 4}
                                         : (lv_area_t){ex - 9, cy - 10, ex + 9, cy - 4};
        lv_draw_rect(ctx, &fd, &a);
        if (pet.eye_open > 128) {
            fd.bg_color = lv_color_white();
            lv_area_t h = {ex - 4, cy - 16, ex - 1, cy - 12}; lv_draw_rect(ctx, &fd, &h);
            fd.bg_color = s->ink;
        }
    }

    // 嘴：一个椭圆，高度由 RMS 驱动
    int mh = pet.mouth_h;
    lv_area_t m = {cx - 13, cy + 26 - mh / 2, cx + 13, cy + 26 + mh / 2};
    lv_draw_rect(ctx, &fd, &m);
}
```

> 想要真正的"像素颗粒感"，把上述所有坐标对齐到 8px 网格（`x & ~7`），或在 `lv_draw_rect_dsc_t` 里关掉抗锯齿。LVGL 默认圆角矩形有抗锯齿，会显得不够"像素"——这是像素风最容易翻车的一点。

### 8.5 底部音量条（方屏用直条，不用弧）

圆屏可以沿屏幕边缘画弧，方屏画弧会切掉四角、视觉上很别扭。改用底部直线进度条，宽 160、高 6、圆角 3。

```c
lv_obj_t *bar = lv_bar_create(lv_scr_act());
lv_obj_set_size(bar, 160, 6);
lv_obj_align(bar, LV_ALIGN_BOTTOM_MID, 0, -18);      // 距底 18px
lv_obj_set_style_radius(bar, 3, LV_PART_MAIN);
lv_obj_set_style_bg_color(bar, lv_color_hex(0xEED8C6), LV_PART_MAIN);          // 轨道
lv_obj_set_style_bg_color(bar, lv_color_hex(0xFF9682), LV_PART_INDICATOR);     // 已用
lv_obj_remove_style(bar, NULL, LV_PART_KNOB);
lv_bar_set_range(bar, 0, 100);

void ui_set_volume(uint8_t v) {                      // v: 0..10
    lv_bar_set_value(bar, v * 10, LV_ANIM_ON);       // 200ms 平滑
}
```

> 待机时轨道为浅色 `#EED8C6`；调音量的 2 秒内用主色 `#FF9682` 高亮，之后淡回。

### 8.6 按键状态机

```c
typedef enum { ST_IDLE, ST_LISTEN, ST_THINK, ST_SPEAK, ST_MENU } ui_state_t;
static ui_state_t g_state = ST_IDLE;

static void on_boot_single(void *a) {
    switch (g_state) {
    case ST_IDLE:   ui_enter_listen();  break;
    case ST_LISTEN: ui_send_audio();    break;
    case ST_SPEAK:  ui_stop_playback(); break;
    case ST_MENU:   ui_menu_confirm();  break;
    default: break;
    }
}
static void on_boot_long(void *a) {
    if (g_state == ST_MENU) ui_menu_back(); else ui_enter_menu();
}
static void on_boot_double(void *a) {
    if (g_state == ST_IDLE) ui_send_preset("想你了");   // 建议用你自己录的声音
}
static void on_volm_long(void *a) {                     // VOL− 长按换表情
    if (g_state == ST_IDLE) pet_next_skin();
}

void ui_keys_init(void) {
    button_config_t cfg = {.type = BUTTON_TYPE_GPIO,
                           .long_press_time = 2000, .short_press_time = 180};
    button_handle_t boot = iot_button_create(&cfg, GPIO_NUM_0, 0);
    iot_button_register_cb(boot, BUTTON_SINGLE_CLICK, on_boot_single, NULL);
    iot_button_register_cb(boot, BUTTON_LONG_PRESS_START, on_boot_long, NULL);
    iot_button_register_cb(boot, BUTTON_DOUBLE_CLICK, on_boot_double, NULL);
    // VOL+ / VOL− 同理；另加一个"双键同按"检测（两个 GPIO 同时为低持续 500ms）
}
```

---

## 9. 性能与内存预算

| 项目 | 数值 / 建议 |
|---|---|
| 帧缓冲 | 240×240 RGB565 = 115 KB，双缓冲 230 KB → **建议 ESP32-S3 + PSRAM** |
| 无 PSRAM 降级 | partial buffer 240×20 行（9.6 KB）×2，LVGL 分块渲染，可跑 20–25fps |
| 位图资源 | **零位图**（全图元绘制）——这是本方案最大的省内存点 |
| 字模 | `lv_font_conv` 只打包常用 1500 字 + 固定文案，16px 约 60–90 KB。**别用全量字库** |
| 音频算法 | 只需 RMS，无需 FFT，CPU 占用极低 |
| SPI | ST7789 / ILI9341 跑 60–80 MHz + DMA，否则动画必卡 |

这套方案是四套里**资源占用最低的**——没有模糊、没有频谱、没有位图，老款 ESP32（无 PSRAM）也能跑顺。

---

## 10. 落地顺序

1. **先画静态宠物**——把图元绘制跑通，确认像素轮廓在方屏上好看（这一步最花时间，也最决定成败）。
2. **加眨眼**——随机延迟一加上，"活"的感觉立刻出来一半。
3. **接 I2S RMS → 嘴形 / 耳朵**——先用固定正弦数据调试，再接真实麦克风。
4. **做气泡与音量弧**——文字换行、气泡随文本长度自适应高度。
5. **最后做菜单与表情切换**——依赖前四步稳定后再加。

---

## 11. 几个加分细节（都很便宜）

- **BOOT 双击那句「想你了」，用你自己的声音录**。8kHz mp3 存 flash，比任何 TTS 都戳人。
- **开机动画 2 秒**：两个简笔小人从两侧走到中间。
- **配网做成二维码**显示在屏幕上，她扫码就能改 Wi-Fi，不用你远程救场。
- **长按 VOL− 换表情**是彩蛋——不写在说明书里，让她自己发现。
- **外壳用透明亚克力**，底部刻一行日期——它就有了"礼物"属性，而不只是一块开发板。
