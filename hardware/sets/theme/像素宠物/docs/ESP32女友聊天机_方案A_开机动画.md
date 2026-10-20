# 方案 A · 开机动画（Boot Sequence）

> ESP32 女友聊天机 · **240×240 方形 IPS**（ST7789 / ILI9341）· 软萌像素宠物
> 可交互预览：**`esp32_boot_preview_square.html`**（浏览器打开即可播放，含时间轴拖拽、慢放、四条分支）
> 静态分镜：`esp32_gui_scheme_A_boot.png`（圆屏时期的版本，仅供动效顺序参考）
>
> **本版按方屏布局**：顶栏 / 主舞台 / 气泡区 / 底栏四区纵向排布，四角加取景框角标。

---

## 1. 为什么要做开机动画

这块板子不是工具，是礼物。**一次开机 = 一次重逢。**

如果上电直接跳到待机界面，她看到的是"设备启动了"；如果上电是一只小兽从黑暗里慢慢睁开眼、开口说"你回来啦"，她看到的是"它在等我"。差别只在那 3.8 秒，但礼物的属性全在这 3.8 秒里。

所以这一版开机动画的设计原则只有一条：

> **不是播一段过场动画，是让"它醒过来"。**
> 所有元素依次点亮，顺序严格遵循"生命苏醒"的逻辑——先有微光，再有轮廓，再有血色（填充），再是耳朵、腮红，最后是睁眼。**睁眼必须放在最后**，因为睁眼 = 意识上线。顺序错了就只是动画，对了才是醒来。

**核心创意：屏幕「开灯」。**
前半程是暗底，宠物以**发光轮廓**的形式出现（像黑暗中有个东西亮起来）；到第 1.5 秒，填充色注入的同一瞬间，整块屏幕由暖黑提亮到奶油米——就像有人按下了房间的灯。这是全片的情绪高点，也是最容易被记住的一帧。

---

## 2. 时间轴总表（3.8s）

| 幕 | 时间 | 时长 | 画面 | 曲线 | 情绪 |
|---|---|---|---|---|---|
| — | 0.00–0.20 | 0.20 | 黑屏（硬件初始化，背光延迟开启） | — | 屏息 |
| ① | 0.20–0.60 | 0.40 | 中心一粒暖光种子，轻微呼吸 | `ease_out` 淡入 | 有什么要醒了 |
| ② | 0.60–1.00 | 0.40 | 种子扩散成三层柔光涟漪，种子随之淡出 | `ease_out` 扩散 | 扩散 |
| ③ | 1.00–1.50 | 0.50 | **轮廓沿椭圆生长**：从 12 点双向展开，最后在底部合拢 | `ease_in_out` | 成形 |
| ④ | 1.50–1.90 | 0.40 | **开灯**：填充色由中心扩散注入，屏幕同步提亮 | `ease_out` | **高潮** |
| ⑤ | 1.90–2.20 | 0.30 | 耳朵弹出（带过冲回弹） | `back_out` | 支棱起来 |
| ⑥ | 2.20–2.45 | 0.25 | 腮红点亮，左右各 0.05s 错开 | linear | 有了血色 |
| ⑦ | 2.45–2.85 | 0.40 | **睁眼**：细线撑开成矩形，高光淡入，嘴微张 | `back_out` | 意识上线 |
| ⑧ | 2.85–3.40 | 0.55 | 气泡「你回来啦」淡入 + 轻微上弹，耳朵晃一下 | `back_out` | 开口 |
| ⑨ | 3.40–3.80 | 0.40 | 气泡淡出、音量弧淡入、落位待机 | `ease_out` | 归于日常 |

**节奏设计**：前 1.5 秒慢（暗、静、悬念），1.5–2.9 秒连续快动作（开灯 + 五官四连击，信息密度最高），最后 0.9 秒收。**慢—快—收**，而不是匀速播完——匀速的开机动画会显得廉价。

---

## 3. 逐幕分镜说明

### ① 种子微光（0.20–0.60s）
屏幕中心 r=4 的暖光点，`opa 0→255`，同时以 6Hz 轻微呼吸（半径 4→7）。暗底上用高斯辉光叠加 4 层——**这是全片唯一允许用模糊的地方**（只有一帧、只有一个小圆，开销可忽略）。

### ② 涟漪扩散（0.60–1.00s）
三层同心圆由 r=8 扩到 r=70，透明度随扩散衰减。**种子点必须在这一幕淡出**——它不退场，后面轮廓出现时中心会一直有个亮斑，整个"成形"的过程就废了（这是我在分镜里修掉的第一个 bug）。

### ③ 轮廓生长（1.00–1.50s）
从 **12 点方向双向对称展开**，各画 180°，最后在 6 点位置合拢。

> 为什么不是单向画一圈：单向画圆会有明显的"起点"和"终点"，看起来像进度条；双向对称展开最后**合拢**，读起来是"一个完整的东西成形了"。同样 0.5 秒，感受完全不同。

暗底阶段轮廓用 `LINE_D = #FFC3A8`（亮）并叠加辉光；开灯后过渡到 `LINE_L = #BE7664`（常规描边色）。

### ④ 开灯（1.50–1.90s）—— 全片高潮
两件事**必须严格同步**：
1. 填充色 `FACE` 以中心扩散圆为遮罩注入（半径 0→62）
2. 背景色 `BG_DARK #1A1412` → `BG_LIT #FFF3E4`

同步的瞬间就是"灯亮了"。如果填充先于背景，会看到一块粉色浮在黑底上；如果背景先亮，会看到空白屏一闪。**这两条曲线的时间对齐是这段代码里最该小心的地方。**

配套：**如果接了喇叭，就在这一刻播一声轻响**（0.4s 上行音阶，或你自己录的一声）。声音落点和视觉高点重合，记忆点翻倍。

### ⑤⑥⑦ 五官三连击（1.90–2.85s）
耳朵 → 腮红 → 眼睛，间隔 0.3 / 0.25 / 0.40s，**连贯不停顿**。

- 耳朵用 `back_out`（过冲回弹），弹出来的瞬间有"支棱"的俏皮感
- 腮红左右错开 0.05s，避免机械的对称感
- **睁眼**：高度 6→24、宽度 18→16，用 `back_out` 让它微微撑过头再收回；高光在睁眼进度过 70% 后才淡入（先有眼睛，再有眼神）

### ⑧⑨ 问候与落位（2.85–3.80s）
气泡「你回来啦」淡入并轻微上弹（`back_out` + 6px 位移）。停留约 0.5s 后随音量弧淡入一起淡出，落位到常规待机态。

> 问候文案建议做成**动态的**：平日「你回来啦」、早上「早呀」、深夜「还没睡呀」。读 RTC 小时切换，一行代码，但每天开机都不重样。

---

## 4. 三条分支路径

| 分支 | 触发条件 | 处理 |
|---|---|---|
| **未配网 · 首开机** | NVS 无 Wi-Fi 凭据 | 动画照常播完，但结尾不落位待机，改为**显示配网二维码** + 宠物耳朵耷拉；扫码配网成功后才进待机。**且此分支不响应 BOOT 跳过**（她得看到二维码） |
| **深度唤醒** | `esp_sleep_get_wakeup_cause() != ESP_SLEEP_WAKEUP_UNDEFINED` | 只播 **0.6s 短版**：直接睁眼 + 音量弧淡入。每次开机都等 3.8s 会烦 |
| **生日 / 纪念日** | RTC 日期 == NVS 中存的日子 | 结尾改撒花彩蛋 + 气泡「生日快乐！」，或者「在一起第 520 天」 |

**BOOT 跳过**：动画期间单击 BOOT → 所有进度直接置 1 并进入待机。首次开机（未配网）分支除外。

---

## 5. 实现要点（这些比动画本身更容易翻车）

### 5.0 方屏布局常量（与预览 HTML 一致）

```c
#define CY_BASE   126    // 待机 / 聆听时宠物中心 y
#define CY_SPEAK  156    // 回应时下移 30px，给气泡让位
#define FACE_RX    70    // 脸宽半径（方屏可放大；圆屏受 r<60 限制只能 62）
#define FACE_RY    62
#define TOPBAR_Y   22    // 顶栏：左时间 / 右 Wi-Fi + 电量
#define VOL_Y     218    // 底部音量条（直线，宽 160 高 6）
#define BUBBLE_W  200    // 气泡宽（方屏可拉满，一行 10 字）
```

宠物中心在回应时下移、落位时回归，由气泡进度驱动：

```c
int cy = CY_BASE + (CY_SPEAK - CY_BASE) * ease_out(p.bubble) * (1 - p.settle);
```

**四角角标**（方屏专属，圆屏做不了）：

```c
static void draw_corner_marks(lv_draw_ctx_t *ctx, uint8_t opa) {
    lv_draw_line_dsc_t d; lv_draw_line_dsc_init(&d);
    d.width = 2; d.color = SUB_COLOR; d.opa = opa;      // SUB #C49E8A @55%
    const int m = 9, L = 14;
    lv_point_t pts[4][2][2] = {
        {{{m,m},{m+L,m}}, {{m,m},{m,m+L}}},                     // 左上
        {{{240-m-L,m},{240-m,m}}, {{240-m,m},{240-m,m+L}}},     // 右上
        {{{m,240-m},{m+L,240-m}}, {{m,240-m},{m,240-m-L}}},     // 左下
        {{{240-m-L,240-m},{240-m,240-m}}, {{240-m,240-m},{240-m,240-m-L}}}
    };
    for (int i = 0; i < 4; i++) for (int k = 0; k < 2; k++)
        lv_draw_line(ctx, &d, &pts[i][k][0], &pts[i][k][1]);
}
```

### 5.1 上电花屏：先清屏，再开背光

ST7789 / ILI9341 上电瞬间会闪一下白屏或花屏。必须把背光（BLK 引脚）用 GPIO 单独控制：

```
上电 → 背光拉低 → SPI/ST7789 初始化 → 整屏刷成暖黑 #1A1412
     → 延时 120ms → 背光拉高 → 开始播动画
```

不这么做，她每次开机第一眼看到的都是一帧花屏，仪式感直接归零。

### 5.2 动画期间别干重活

Wi-Fi 连接、音频编解码器初始化、NTP 校时**都不要在动画播放时跑**，会把 30fps 卡成 10fps，而且卡顿出现在最该丝滑的地方。

- ESP32-S3 双核：LVGL 任务钉在 core1，网络/音频任务放 core0
- 单核 ESP32：**先播完动画再连网**（反面：配网二维码分支必须先连……这时改为动画期间只做扫码所需的初始化，其他延后）

### 5.3 帧率

动画期间提到 **30fps**，播完降回待机的 15fps 省电。

---

## 6. 关键代码

### 6.1 进度结构体 + 单一推进定时器

**不要用 10 个 `lv_anim` 串联**——管理成本高、结束判定麻烦。用一个全局进度结构 + 一个 20ms 定时器推进，绘制侧只读不写，最省也最好控。

```c
typedef struct {
    float seed, ripple, outline, fill, bg, ear, blush, eye, bubble, settle;
} boot_prog_t;
static boot_prog_t bp;
static uint32_t    t0;
static bool        boot_done;

static float seg(uint32_t now, float a, float b) {          // 归一化段进度
    return fmaxf(0.f, fminf(1.f, (now - a) / (b - a)));
}
static float ease_out(float p)   { return 1 - powf(1 - p, 3); }
static float ease_inout(float p) { return p < .5f ? 4*p*p*p : 1 - powf(-2*p+2, 3)/2; }
static float back_out(float p)   { float c = 1.70158f; return 1 + (c+1)*powf(p-1,3) + c*powf(p-1,2); }

static void boot_tick(lv_timer_t *t) {
    float s = (lv_tick_get() - t0) / 1000.f;                 // 秒
    bp.seed    = ease_out(seg(s, 0.20f, 0.60f));
    bp.ripple  = ease_out(seg(s, 0.60f, 1.00f));
    bp.outline = ease_inout(seg(s, 1.00f, 1.50f));
    bp.fill    = ease_out(seg(s, 1.50f, 1.90f));
    bp.bg      = ease_inout(seg(s, 1.55f, 1.90f));           // 与 fill 严格同步
    bp.ear     = back_out(seg(s, 1.90f, 2.20f));
    bp.blush   = seg(s, 2.20f, 2.45f);
    bp.eye     = back_out(seg(s, 2.45f, 2.85f));
    bp.bubble  = back_out(seg(s, 2.85f, 3.40f));
    bp.settle  = ease_out(seg(s, 3.40f, 3.80f));
    lv_obj_invalidate(pet_obj);

    if (!beep_played && s >= 1.5f) { beep_played = true; play_boot_chime(); }  // 开灯那一刻的配音

    if (s >= 3.80f) {
        boot_done = true;
        lv_timer_del(t);
        lv_timer_set_period(ui_timer, 67);                   // 15fps，省电
        if (!wifi_configured()) show_qr_screen();            // 未配网分支
    }
}
```

### 6.2 绘制：同一个 draw 事件，读进度

宠物绘制函数同时被开机动画和主界面复用——主界面把 `bp.*` 全部置 1 即可，不用写两套绘制代码。

```c
static void pet_draw(lv_event_t *e) {
    lv_draw_ctx_t *ctx = lv_event_get_draw_ctx(e);
    bool dark = bp.bg < 0.55f;
    lv_color_t line = lv_color_mix(LINE_DARK, LINE_LIT, (uint8_t)(bp.bg * 255));
    int cy = 124;

    // ① 种子微光（仅暗底阶段）
    if (bp.bg < 0.9f && bp.seed * (1 - bp.ripple) > 0.02f) {
        float op = bp.seed * (1 - bp.ripple);
        float r  = 4 + 3 * fabsf(sinf(s_now * 6));
        // 用 3 层递减透明度的实心圆模拟辉光，别用模糊
        for (int k = 3; k >= 1; k--) {
            lv_draw_rect_dsc_t rd; lv_draw_rect_dsc_init(&rd);
            rd.radius = LV_RADIUS_CIRCLE; rd.bg_color = SEED_COL;
            rd.bg_opa = (lv_opa_t)(60 * op / k);
            lv_area_t a = {120 - r*k, cy - r*k, 120 + r*k, cy + r*k};
            lv_draw_rect(ctx, &rd, &a);
        }
    }

    // ② 涟漪
    if (bp.bg < 0.9f) {
        for (int k = 0; k < 3; k++) {
            float pk = fmaxf(0, bp.ripple * 3 - k * 0.35f);
            if (pk <= 0) continue;
            float rr = 8 + 62 * ease_out(pk);
            lv_draw_arc_dsc_t ad; lv_draw_arc_dsc_init(&ad);
            ad.color = SEED_COL; ad.width = 3;
            ad.opa = (lv_opa_t)(150 * (1 - pk) * (1 - bp.bg));
            lv_draw_arc(ctx, &ad, 120, cy, rr, 0, 360);
        }
    }

    // ③ 轮廓：从 12 点双向展开
    if (bp.outline > 0.01f) {
        float e = bp.outline * 180.f;
        lv_draw_arc_dsc_t ad; lv_draw_arc_dsc_init(&ad);
        ad.color = line; ad.width = 8;
        ad.opa = dark ? LV_OPA_COVER : LV_OPA_COVER;
        lv_draw_arc(ctx, &ad, 120, cy, 62, -90, -90 + e);      // 右半
        lv_draw_arc(ctx, &ad, 120, cy, 62, -90 - e, -90);      // 左半
        if (dark) {  /* 辉光：同一条弧再画两次，宽度 16/12、opa 40/70 */ }
    }

    // ④ 填充：以中心扩散圆为遮罩（LVGL 用 radius 圆 + 尺寸动画，天然就是扩散圆）
    if (bp.fill > 0.01f) {
        int R = (int)(62 * bp.fill);
        lv_draw_rect_dsc_t fd; lv_draw_rect_dsc_init(&fd);
        fd.bg_color = FACE; fd.bg_opa = LV_OPA_COVER; fd.radius = LV_RADIUS_CIRCLE;
        lv_area_t f = {120 - R, cy - R * 0.87f, 120 + R, cy + R * 0.87f};
        lv_draw_rect(ctx, &fd, &f);
    }

    // ⑤ 耳朵：三角形顶点按 back_out 缩放
    if (bp.ear > 0.01f) { /* 外层 line 三角 + 内层 FACE 三角，顶点绕根部缩放 */ }

    // ⑥ 腮红：opa 0→170，左右错开 0.05s
    // ⑦ 眼睛：h = 6+18p, w = 18-2p, 中心 y 上移；p>0.7 后画高光
    // ⑧ 气泡：opa + 6px 位移
}
```

> LVGL 绘制弧的 `lv_draw_arc` 需要 bbox，椭圆弧可通过在 draw 事件里手动采样点连 `lv_draw_line` 实现；或直接用一个 `lv_arc` 控件配合 `lv_arc_set_angles` 做动画（更简单，推荐先用控件跑通）。

### 6.3 分支与跳过

```c
void app_boot_start(void) {
    gpio_set_level(BLK_GPIO, 0);                              // 先灭背光
    gc9a01_init(); gc9a01_fill(BG_DARK);                      // 清成暖黑，避免花屏
    vTaskDelay(pdMS_TO_TICKS(120));
    gpio_set_level(BLK_GPIO, 1);                              // 再开背光

    bool wake  = esp_sleep_get_wakeup_cause() != ESP_SLEEP_WAKEUP_UNDEFINED;
    bool first = !wifi_configured();

    if (wake && !first) { boot_short(); return; }             // 0.6s 短版
    memset(&bp, 0, sizeof(bp));
    t0 = lv_tick_get();
    lv_timer_create(boot_tick, 20, NULL);                     // 50Hz 推进
    skip_allowed = !first;                                    // 首开机不响应跳过
}

static void on_boot_during_anim(void) {                        // 单击跳过
    if (!skip_allowed || boot_done) return;
    bp = (boot_prog_t){1,1,1,1,1,1,1,1,1,1};
    lv_tick_set(t0, lv_tick_get() - 3800);
}
```

### 6.4 纪念日彩蛋

```c
// NVS 里存 anniversary = {month, day}，开机比对 RTC
if (today == anniversary) {
    boot_greeting = "纪念日快乐！";
    confetti_enable = true;      // 尾部 0.6s 撒花：34 个 3px 方块，随机色，重力下落
} else if (today == birthday) {
    boot_greeting = "生日快乐！";
}
```

---

## 7. 可定制清单（让这份礼物变成"你们的"）

| 项目 | 做法 | 成本 |
|---|---|---|
| **开机问候语** | 数组里放 4–6 句，按小时/星期轮换 | 一行代码 |
| **称呼** | 气泡里带她的名字或你们的昵称 | 一行代码 |
| **开机音** | **你自己录的一声**（「早呀」「我醒啦」），8kHz 存 flash | 最高性价比 |
| **纪念日倒计时** | NVS 存起始日，开机显示「在一起第 520 天」 | 少量代码 |
| **生日撒花** | 见 §6.4 | 少量代码 |
| **她的生日当天** | 宠物换一套专属配色（比如她喜欢的颜色） | 一个结构体 |

**最后一条建议**：开机动画里最贵的不是代码，是那段**你自己的声音**。TTS 谁都能做，但屏幕亮起时听到的那声"早呀"是你说的——这一版方案的全部意义就在这里。

---

## 8. 落地顺序

1. **先做静态第 ⑨ 帧**（完整待机态）——确认宠物在方屏上好看，这是地基
2. **加时间轴推进器**（§6.1）——把 10 个进度值打印到串口，确认曲线对
3. **接绘制**（§6.2）——先跑 ③④ 开灯段，这是高潮，值得单独调
4. **加声音落点**——在 1.5s 处对齐
5. **最后做三条分支**——依赖主流程稳定
