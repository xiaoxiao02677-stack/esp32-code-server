// ════════════════════════════════════════════════════════════════════════
// 猫咪 cat 主题 · 动画渲染核心实现（cat_anim.cc）
// ════════════════════════════════════════════════════════════════════════
// LVGL v9。移植自 G:\demo\22 cat 项目的 integrated.ino 动画引擎
// （upload_facial_expression/integrated/integrated.ino）：
//   JPEG 帧序列 → esp_new_jpeg 解码（RGB565_LE）→ canvas 像素直写
//   交叉淡入 300ms（原项目 CROSSFADE_DURATION_MS=500 的紧凑版，逐像素
//   RGB565 lerp，仅情绪指令路径用）
//   随机循环硬切（原项目 animLoop 路径注释："循环模式：动画自然播完，
//   直接切到下一个（无缝衔接，不渐变）"）
//   嘴形全帧轮换（v2：嘴部视频是完整猫脸，素材端按口鼻对齐裁剪成
//   320×240 全帧；说话时整帧轮换 4 形状，代替 v1 的 80×50 小块叠加）
//   待机随机分布 60/30/10（原项目 pickRandomAnim 随机分布搬运）
//
// 存储迁移：原项目 LittleFS 文件（/cat/animN/xxxx.jpg）→ yuhe mmap
// assets 分区平铺文件（cat_a{N}_f{NN}.jpg / cat_m{N}.jpg），
// Assets::GetAssetData 按名取，帧按需解码（不做整段缓存，见下）。
//
// 状态角标（cat_badge_t）：与 face 主题状态辉光同哲学的第二信号通道，
// 零文字 UI 下按 BOOT 后一眼可辨状态；色表与 face 辉光完全一致。
//
// 内存预算（PSRAM，四板均 8MB）：
//   canvas 缓冲（屏幕尺寸）≤ 320×240×2 ≈ 154KB
//   face/prev 工作缓冲 2×154KB + 嘴形单缓冲 154KB ≈ 462KB
//   合计 ~615KB。
//
//   ★ 不做整段帧缓存（v1 教训，2026-10-26 实机崩溃）：60 帧 × 154KB
//   ≈ 9.2MB 的 PSRAM 预分配会直接挤爆开机期 AfeAudioEngine/multinet
//   的模型加载（hufzip 32KB psram alloc failed → NULL 解引用
//   StoreProhibited 崩溃循环）。语音模型 + LVGL + 协议栈已占大半
//   PSRAM，显示层必须克制。改为逐帧按需解码：JPEG 源 mmap 在 flash
//   零 RAM 成本，解码单帧 ~10ms（esp_new_jpeg 软解 320×240），15fps
//   帧间隔 66ms 内绰绰有余。淡入期间 prev_buf 承担旧画面快照，
//   不需要旧动画的帧缓存。
//
// 线程纪律：只在 LVGL 任务上下文（lv_timer 回调）或已持 DisplayLockGuard
// 时调用；本文件不加锁（调用方持有）。

#include "cat_anim.h"

#include "assets.h"
#include "display/lvgl_display/jpg/jpeg_to_image.h"

#include <esp_heap_caps.h>
#include <esp_log.h>
#include <esp_random.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define TAG "CatAnim"

// ---- 素材几何常量（4:3 全帧素材；定义在 cat_anim.h：CAT_ASSET_W/H）----
#define CAT_FACE_PX (CAT_ASSET_W * CAT_ASSET_H)       // 76800
#define CAT_FACE_BYTES (CAT_FACE_PX * 2)              // 153600

// 帧节奏常量在 cat_anim.h（CAT_FRAME_MS 显示层 timer 共用）

// 交叉淡入 300ms ≈ 4.5 帧 → 每帧推进 0.22
#define CAT_FADE_STEP 0.22f
// 嘴形轮换 90ms（原项目说话口型节奏）
#define CAT_MOUTH_MS 90
// 连接态角标慢闪 1.6s（半周期 800ms）
#define CAT_BLINK_MS 800
// 静音角标短显 2s 后回落
#define CAT_MUTED_MS 2000

// ---- 状态角标色表（与 face_core 状态辉光同表，跨主题视觉统一）----
static const uint32_t kBadgeColors[CAT_BADGE_MAX] = {
    [CAT_BADGE_OFF] = 0x000000,       // 不显示（占位）
    [CAT_BADGE_IDLE] = 0xB4DCFF,      // 淡蓝（默认）
    [CAT_BADGE_LISTENING] = 0x7BE8A0, // 青绿：在听
    [CAT_BADGE_SPEAKING] = 0xF7B96A,  // 暖橙：说话中
    [CAT_BADGE_CONNECTING] = 0xF7D96A,// 琥珀：联网/升级（慢闪）
    [CAT_BADGE_ERROR] = 0xF76E5E,     // 珊瑚红：致命错误
    [CAT_BADGE_MUTED] = 0x9E9E9E,     // 灰：静音（短显）
};

struct cat_anim_s {
    lv_obj_t* parent = nullptr;
    lv_obj_t* canvas = nullptr;
    lv_obj_t* badge_obj = nullptr;
    cat_geom_t geom;

    // canvas（屏幕尺寸，PSRAM）
    uint8_t* canvas_buf = nullptr;
    uint16_t canvas_stride = 0;

    // 320×240 工作缓冲：当前表情帧 + 淡入源帧快照
    uint16_t* face_buf = nullptr;
    uint16_t* prev_buf = nullptr;
    bool fade_active = false;
    float fade_pos = 0.0f;

    // 播放状态
    cat_anim_id_t cur_anim = CAT_ANIM_IDLE1;
    int frame_idx = 0;
    uint32_t last_frame_ms = 0;
    bool easter_active = false;
    bool frozen = false;

    // 嘴形（320×240 全帧，单缓冲：当前形状按需解码，90ms 轮换一次
    // 解码 ~10ms 完全来得及；4 形状全缓存要 4×154KB，砍掉）
    uint16_t* mouth_buf = nullptr;
    bool mouth_loaded = false;   // 当前形状已解码成功
    bool mouth_active = false;
    int mouth_shape = 0;
    uint32_t last_mouth_ms = 0;

    // 角标
    cat_badge_t badge = CAT_BADGE_OFF;
    uint32_t badge_muted_at = 0;
    uint32_t last_blink_ms = 0;
    bool badge_blink_visible = true;
};

// ---- 几何（320×240 素材 contain-fit → 实际屏型）----

cat_geom_t cat_geom_make(int width, int height) {
    cat_geom_t g;
    g.screen_w = (int16_t)width;
    g.screen_h = (int16_t)height;
    // contain-fit：比较屏宽高比与素材宽高比（交叉相乘避免浮点）
    //   320×240 板 → 全出血 1:1；240×240 / 240×320 板 → 按宽 0.75x 缩放
    //   （240×180），垂直/水平居中留黑
    const int screen_aspect_num = width * CAT_ASSET_H;   // W 与 320×240 比较
    const int screen_aspect_den = height * CAT_ASSET_W;
    int16_t fw, fh;
    if (screen_aspect_num <= screen_aspect_den) {
        fw = (int16_t)width;
        fh = (int16_t)(width * CAT_ASSET_H / CAT_ASSET_W);
    } else {
        fh = (int16_t)height;
        fw = (int16_t)(height * CAT_ASSET_W / CAT_ASSET_H);
    }
    g.face_w = fw;
    g.face_h = fh;
    g.face_x = (int16_t)((width - fw) / 2);
    g.face_y = (int16_t)((height - fh) / 2);
    // 角标：素材 (0.85W, 0.10H) 处（猫脸右上空白区，不压五官）→ 屏坐标。
    // 240 圆屏验证过落点在内切圆内（(204,48)，距圆心 110 < 120）。
    g.badge_x = (int16_t)(g.face_x + fw * 85 / 100);
    g.badge_y = (int16_t)(g.face_y + fh * 10 / 100);
    g.badge_r = (int16_t)(fh / 40);
    if (g.badge_r < 4) {
        g.badge_r = 4;
    }
    return g;
}

// ---- assets 可用性 ----

bool cat_anim_assets_available(void) {
    void* ptr = nullptr;
    size_t size = 0;
    return Assets::GetInstance().GetAssetData("cat_a1_f00.jpg", ptr, size) && size > 0;
}

// ---- JPEG 解码（esp_new_jpeg，硬件优先自动回退）----

static bool decode_frame(const uint8_t* src, size_t len, uint16_t* dst, size_t dst_w,
                         size_t dst_h) {
    uint8_t* out = nullptr;
    size_t out_len = 0, w = 0, h = 0, stride = 0;
    if (jpeg_to_image(src, len, &out, &out_len, &w, &h, &stride) != ESP_OK || out == nullptr) {
        return false;
    }
    if (w != dst_w || h != dst_h) {
        ESP_LOGW(TAG, "frame size %dx%d != %dx%d", (int)w, (int)h, (int)dst_w, (int)dst_h);
        heap_caps_free(out);
        return false;
    }
    for (size_t y = 0; y < dst_h; y++) {
        memcpy((uint8_t*)dst + y * dst_w * 2, out + y * stride, dst_w * 2);
    }
    heap_caps_free(out);
    return true;
}

// ---- 帧供给（按名从 assets 取 → 解码进 face_buf，逐帧无缓存）----
// JPEG 源 mmap 在 flash；esp_new_jpeg 软解 320×240 单帧 ~10ms，
// 66ms 帧间隔内绰绰有余。
static bool ensure_frame(cat_anim_t* p, int idx) {
    if (idx < 0 || idx >= CAT_ANIM_FRAMES) {
        return false;
    }
    char name[24];
    snprintf(name, sizeof(name), "cat_a%d_f%02d.jpg", (int)p->cur_anim, idx);
    void* ptr = nullptr;
    size_t size = 0;
    if (!Assets::GetInstance().GetAssetData(name, ptr, size) || size == 0) {
        return false;
    }
    return decode_frame((const uint8_t*)ptr, size, p->face_buf, CAT_ASSET_W, CAT_ASSET_H);
}

// ---- 嘴形全帧（当前形状按需解码进 mouth_buf）----

static bool ensure_mouth_shape(cat_anim_t* p, int shape) {
    char name[16];
    snprintf(name, sizeof(name), "cat_m%d.jpg", shape + 1);
    void* ptr = nullptr;
    size_t size = 0;
    if (!Assets::GetInstance().GetAssetData(name, ptr, size) || size == 0) {
        return false;
    }
    return decode_frame((const uint8_t*)ptr, size, p->mouth_buf, CAT_ASSET_W, CAT_ASSET_H);
}

// ---- 交叉淡入（逐像素 RGB565 lerp，原项目同款）----

static inline uint16_t blend565(uint16_t a, uint16_t b, uint8_t t) {
    const int ra = (a >> 11) & 0x1F, ga = (a >> 5) & 0x3F, ba = a & 0x1F;
    const int rb = (b >> 11) & 0x1F, gb = (b >> 5) & 0x3F, bb = b & 0x1F;
    const int r = (ra * (255 - t) + rb * t) >> 8;
    const int g = (ga * (255 - t) + gb * t) >> 8;
    const int bl = (ba * (255 - t) + bb * t) >> 8;
    return (uint16_t)((r << 11) | (g << 5) | bl);
}

static void blend_fade(cat_anim_t* p) {
    const uint8_t t = (uint8_t)(p->fade_pos * 255.0f);
    for (int i = 0; i < CAT_FACE_PX; i++) {
        p->face_buf[i] = blend565(p->prev_buf[i], p->face_buf[i], t);
    }
}

// ---- canvas 直写（整数比最近邻缩放；素材 320×240 → 屏 1:1 / 3:4）----

static void blit_scaled(cat_anim_t* p, const uint16_t* src) {
    uint8_t* dst = p->canvas_buf;
    const int dw = p->geom.face_w;
    const int dh = p->geom.face_h;
    const int dx = p->geom.face_x;
    const int dy = p->geom.face_y;
    for (int y = 0; y < dh; y++) {
        const uint16_t* srow = src + (y * CAT_ASSET_H / dh) * CAT_ASSET_W;
        uint16_t* drow = (uint16_t*)(dst + (dy + y) * p->canvas_stride) + dx;
        if (dw == CAT_ASSET_W) {
            memcpy(drow, srow, dw * 2);
        } else {
            for (int x = 0; x < dw; x++) {
                drow[x] = srow[x * CAT_ASSET_W / dw];
            }
        }
    }
}

// 当前实际显示的内容（说话嘴形激活时是嘴形全帧，否则是表情帧）
static const uint16_t* cur_displayed(const cat_anim_t* p) {
    return (p->mouth_active && p->mouth_loaded) ? p->mouth_buf : p->face_buf;
}

// ---- 角标 ----

static void apply_badge(cat_anim_t* p) {
    if (p->badge_obj == nullptr) {
        return;
    }
    if (p->badge == CAT_BADGE_OFF) {
        lv_obj_add_flag(p->badge_obj, LV_OBJ_FLAG_HIDDEN);
        return;
    }
    lv_obj_remove_flag(p->badge_obj, LV_OBJ_FLAG_HIDDEN);
    lv_obj_set_style_bg_color(p->badge_obj, lv_color_hex(kBadgeColors[p->badge]), 0);
    lv_obj_set_style_bg_opa(p->badge_obj, LV_OPA_COVER, 0);
    p->badge_blink_visible = true;
    p->last_blink_ms = lv_tick_get();
}

// ---- 生命周期 ----

cat_anim_t* cat_anim_create(lv_obj_t* parent, const cat_geom_t* geom) {
    if (parent == nullptr || geom == nullptr) {
        return nullptr;
    }
    if (!cat_anim_assets_available()) {
        ESP_LOGE(TAG, "cat frames not found in assets partition");
        return nullptr;
    }

    cat_anim_t* p = (cat_anim_t*)calloc(1, sizeof(cat_anim_t));
    if (p == nullptr) {
        return nullptr;
    }
    p->parent = parent;
    p->geom = *geom;

    // canvas 缓冲（PSRAM，失败退内部 RAM）
    p->canvas_stride =
        (uint16_t)lv_draw_buf_width_to_stride((uint32_t)geom->screen_w, LV_COLOR_FORMAT_RGB565);
    const size_t canvas_bytes = (size_t)p->canvas_stride * geom->screen_h;
    p->canvas_buf = (uint8_t*)heap_caps_malloc(canvas_bytes, MALLOC_CAP_SPIRAM);
    if (p->canvas_buf == nullptr) {
        p->canvas_buf = (uint8_t*)heap_caps_malloc(canvas_bytes, MALLOC_CAP_8BIT);
    }
    if (p->canvas_buf == nullptr) {
        ESP_LOGE(TAG, "canvas buffer alloc failed (%u bytes)", (unsigned)canvas_bytes);
        cat_anim_destroy(p);
        return nullptr;
    }
    memset(p->canvas_buf, 0, canvas_bytes);  // 黑底（猫脸四周留黑）

    // 工作缓冲（PSRAM；不分配帧缓存——见文件头内存预算说明）
    p->face_buf = (uint16_t*)heap_caps_malloc(CAT_FACE_BYTES, MALLOC_CAP_SPIRAM);
    p->prev_buf = (uint16_t*)heap_caps_malloc(CAT_FACE_BYTES, MALLOC_CAP_SPIRAM);
    p->mouth_buf = (uint16_t*)heap_caps_malloc(CAT_FACE_BYTES, MALLOC_CAP_SPIRAM);
    if (p->face_buf == nullptr || p->prev_buf == nullptr || p->mouth_buf == nullptr) {
        ESP_LOGE(TAG, "work buffer alloc failed");
        cat_anim_destroy(p);
        return nullptr;
    }

    // canvas 对象
    p->canvas = lv_canvas_create(parent);
    lv_obj_set_size(p->canvas, geom->screen_w, geom->screen_h);
    lv_obj_set_pos(p->canvas, 0, 0);
    lv_canvas_set_buffer(p->canvas, p->canvas_buf, (int32_t)geom->screen_w,
                         (int32_t)geom->screen_h, LV_COLOR_FORMAT_RGB565);

    // 状态角标（圆点，建在 canvas 之后 → z 序在 canvas 之上）
    p->badge_obj = lv_obj_create(parent);
    lv_obj_remove_flag(p->badge_obj, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_size(p->badge_obj, geom->badge_r * 2, geom->badge_r * 2);
    lv_obj_set_pos(p->badge_obj, geom->badge_x - geom->badge_r, geom->badge_y - geom->badge_r);
    lv_obj_set_style_radius(p->badge_obj, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_border_width(p->badge_obj, 0, 0);
    lv_obj_set_style_bg_color(p->badge_obj, lv_color_hex(kBadgeColors[CAT_BADGE_IDLE]), 0);
    lv_obj_add_flag(p->badge_obj, LV_OBJ_FLAG_HIDDEN);  // 开机 splash 期间 OFF

    // 首帧
    p->cur_anim = CAT_ANIM_IDLE1;
    p->badge = CAT_BADGE_OFF;
    p->last_frame_ms = lv_tick_get();
    if (!ensure_frame(p, 0)) {
        ESP_LOGE(TAG, "first frame decode failed");
        cat_anim_destroy(p);
        return nullptr;
    }
    blit_scaled(p, p->face_buf);

    ESP_LOGI(TAG, "cat anim ready (%dx%d, face %dx%d at %d,%d)", geom->screen_w, geom->screen_h,
             geom->face_w, geom->face_h, geom->face_x, geom->face_y);
    return p;
}

void cat_anim_destroy(cat_anim_t* p) {
    if (p == nullptr) {
        return;
    }
    if (p->canvas != nullptr) {
        lv_obj_delete(p->canvas);
    }
    if (p->badge_obj != nullptr) {
        lv_obj_delete(p->badge_obj);
    }
    if (p->canvas_buf != nullptr) {
        heap_caps_free(p->canvas_buf);
    }
    if (p->face_buf != nullptr) {
        heap_caps_free(p->face_buf);
    }
    if (p->prev_buf != nullptr) {
        heap_caps_free(p->prev_buf);
    }
    if (p->mouth_buf != nullptr) {
        heap_caps_free(p->mouth_buf);
    }
    free(p);
}

// ---- 播放控制 ----

void cat_anim_play(cat_anim_t* p, cat_anim_id_t anim, bool fade) {
    if (p == nullptr || anim < CAT_ANIM_IDLE1 || anim > CAT_ANIM_SHY) {
        return;
    }
    if (anim == p->cur_anim && !p->easter_active && !fade) {
        // 同动画硬切重播：只回卷（帧逐个按需解码，无需缓存清理）
        p->frame_idx = 0;
        p->last_frame_ms = lv_tick_get();
        return;
    }
    if (fade) {
        // 情绪指令路径：快照当前显示帧做淡出源（说话嘴形期间是嘴形帧，
        // 正好平滑过渡回表情帧）
        memcpy(p->prev_buf, cur_displayed(p), CAT_FACE_BYTES);
        p->fade_active = true;
        p->fade_pos = 0.0f;
    } else {
        // 随机循环/彩蛋路径：硬切无缝衔接（原项目 animLoop 同款）
        p->fade_active = false;
    }
    p->cur_anim = anim;
    p->frame_idx = 0;
    p->last_frame_ms = lv_tick_get();
}

cat_anim_id_t cat_anim_current(const cat_anim_t* p) {
    return (p != nullptr) ? p->cur_anim : CAT_ANIM_IDLE1;
}

void cat_anim_pick_idle_next(cat_anim_t* p) {
    if (p == nullptr) {
        return;
    }
    // 原项目待机随机分布：60% idle1-3 / 30% happy+shy / 10% cry+angry+sad
    const uint32_t r = esp_random() % 100;
    cat_anim_id_t anim;
    if (r < 60) {
        anim = (cat_anim_id_t)(CAT_ANIM_IDLE1 + (esp_random() % 3));
    } else if (r < 90) {
        anim = (esp_random() & 1) ? CAT_ANIM_HAPPY : CAT_ANIM_SHY;
    } else {
        static const cat_anim_id_t mood[] = {CAT_ANIM_CRY, CAT_ANIM_ANGRY, CAT_ANIM_SAD};
        anim = mood[esp_random() % 3];
    }
    cat_anim_play(p, anim, false);  // 随机循环：硬切
}

void cat_anim_mouth_active(cat_anim_t* p, bool active) {
    if (p == nullptr) {
        return;
    }
    if (active && !p->mouth_active) {
        p->mouth_shape = 0;
        p->mouth_loaded = ensure_mouth_shape(p, 0);  // 首次激活解码形状 0
        p->last_mouth_ms = lv_tick_get();
    }
    p->mouth_active = active;
}

bool cat_anim_mouth_is_active(const cat_anim_t* p) {
    return (p != nullptr) && p->mouth_active;
}

void cat_anim_set_frozen(cat_anim_t* p, bool frozen) {
    if (p != nullptr) {
        p->frozen = frozen;
    }
}

bool cat_anim_is_frozen(const cat_anim_t* p) {
    return (p != nullptr) && p->frozen;
}

void cat_anim_seek(cat_anim_t* p, int frame_idx) {
    if (p == nullptr || frame_idx < 0 || frame_idx >= CAT_ANIM_FRAMES) {
        return;
    }
    p->frame_idx = frame_idx;
    p->fade_active = false;  // seek = 硬切（聆听定格要的就是骤停感，
                             // 不做淡入；否则解冻时会拿陈旧快照鬼影过渡）
    ensure_frame(p, frame_idx);
}

void cat_anim_easter_egg(cat_anim_t* p) {
    if (p == nullptr || p->easter_active) {
        return;
    }
    static const cat_anim_id_t eggs[] = {CAT_ANIM_CRY, CAT_ANIM_ANGRY, CAT_ANIM_SAD};
    p->easter_active = true;
    cat_anim_play(p, eggs[esp_random() % 3], false);  // 彩蛋：硬切（惊喜感）
}

bool cat_anim_in_easter(const cat_anim_t* p) {
    return (p != nullptr) && p->easter_active;
}

void cat_anim_set_badge(cat_anim_t* p, cat_badge_t badge) {
    if (p == nullptr || badge < 0 || badge >= CAT_BADGE_MAX || badge == p->badge) {
        return;
    }
    p->badge = badge;
    if (badge == CAT_BADGE_MUTED) {
        p->badge_muted_at = lv_tick_get();
    }
    apply_badge(p);
}

// ---- 渲染推进 ----

void cat_anim_tick(cat_anim_t* p, bool render_this_frame) {
    if (p == nullptr) {
        return;
    }
    const uint32_t now = lv_tick_get();

    // 帧推进（15fps；聆听冻结或说话嘴形顶替期间定格表情帧推进——
    // 嘴形期间表情帧不可见，解码纯属浪费 CPU，说话时音频链路正忙）
    if (!p->frozen && !p->mouth_active && now - p->last_frame_ms >= CAT_FRAME_MS) {
        p->last_frame_ms = now;
        p->frame_idx++;
        if (p->frame_idx >= CAT_ANIM_FRAMES) {
            p->frame_idx = 0;
            // 段播完：彩蛋结束回待机随机；非彩蛋同样回待机随机
            //（原项目行为：随机表达式循环永续）
            p->easter_active = false;
            cat_anim_pick_idle_next(p);
        }
        if (ensure_frame(p, p->frame_idx) && p->fade_active) {
            p->fade_pos += CAT_FADE_STEP;
            if (p->fade_pos >= 1.0f) {
                p->fade_pos = 1.0f;
                p->fade_active = false;
            }
            blend_fade(p);
        }
    }

    // 嘴形轮换（说话拟态：small→big→wide→oshape 全帧循环）
    if (p->mouth_active && now - p->last_mouth_ms >= CAT_MOUTH_MS) {
        p->last_mouth_ms = now;
        p->mouth_shape = (p->mouth_shape + 1) % CAT_MOUTH_FRAMES;
        if (!ensure_mouth_shape(p, p->mouth_shape)) {
            ESP_LOGW(TAG, "mouth shape %d decode failed", p->mouth_shape + 1);
            p->mouth_loaded = false;  // 解码失败：回落表情帧（cur_displayed 判定）
        } else {
            p->mouth_loaded = true;
        }
    }

    // 静音角标 2s 后回落 idle
    if (p->badge == CAT_BADGE_MUTED && now - p->badge_muted_at >= CAT_MUTED_MS) {
        p->badge = CAT_BADGE_IDLE;
        apply_badge(p);
    }

    // 连接态角标慢闪
    if (p->badge == CAT_BADGE_CONNECTING && now - p->last_blink_ms >= CAT_BLINK_MS) {
        p->last_blink_ms = now;
        p->badge_blink_visible = !p->badge_blink_visible;
        lv_obj_set_style_bg_opa(p->badge_obj, p->badge_blink_visible ? LV_OPA_COVER : LV_OPA_30,
                                0);
    }

    if (!render_this_frame) {
        return;
    }

    blit_scaled(p, cur_displayed(p));
    lv_obj_invalidate(p->canvas);
}
