#pragma once

// ════════════════════════════════════════════════════════════════════════
// 猫咪 cat 主题 · 动画渲染核心（cat_anim.h）
// ════════════════════════════════════════════════════════════════════════
//
// 移植自 G:\demo\22 cat\upload_facial_expression\integrated\integrated.ino
// 的动画引擎（JPEG 帧序列 + LCD 直刷），素材源不变（8 段表情动画 +
// 4 嘴形全帧），存储从 LittleFS 迁到 yuhe 的 mmap assets 分区
//（Assets::GetAssetData 按平铺文件名取）。
//
// 渲染模型（对应原项目 JPEG 帧序列 + LCD 直刷）：
//   全屏 lv_canvas（RGB565，PSRAM）← JPEG 按需解码直写 + 说话嘴形
//   全帧轮换 + 情绪切换交叉淡入 —— 全部在 canvas 像素级完成，
//   LVGL 只管把 canvas flush 出去。
//
// v2 修正（2026-10-26，用户实测反馈"一直变化视频不好看"后对照
// 原项目 integrated.ino 重审）：
//   · 段长 2s→4s：60 帧 × 66ms（原项目 80 帧 × 50ms = 4s/段）
//   · 随机循环切换：淡入→硬切（原项目 animLoop 路径注释明说
//     "无缝衔接，不渐变"；淡入只保留给情绪指令 EXPR 路径——
//     v1 每段都淡入造成幻灯片感）
//   · 帧尺寸 240×240→320×240：4:3 原生比例（源 1112×834、
//     原项目 284×240 都是 4:3；v1 的 240×240 把猫脸横向压扁）
//   · 嘴形：80×50 小块叠加→320×240 全帧轮换（嘴部视频本身是
//     完整猫脸，素材端已按口鼻对齐裁剪；说话时整帧轮换 4 形状）
//   · 四板适配：320×240 素材 contain-fit——320×240 板全出血、
//     240×240 / 240×320 板按高缩放居中、上下/左右留黑
//
// 内存纪律（v1 实机教训）：**不做整段帧缓存**。帧 × 150KB 的
// PSRAM 预分配会挤爆开机期语音模型加载（multinet hufzip 32KB
// psram alloc failed → NULL 解引用崩溃循环）。逐帧按需解码，
// 总占用 ~600KB（canvas 154KB + 工作缓冲 2×150KB + 嘴形 4×150KB）。
//
// 帧驱动：cat_anim_tick() 由显示层 66ms lv_timer 调（15fps）。
//
// 线程纪律：只在 LVGL 任务上下文（lv_timer 回调）或已持 DisplayLockGuard
// 时调用；渲染函数自身不加锁（调用方持有）。

#include <lvgl.h>
#include <stdbool.h>
#include <stdint.h>

// 注：本核心实现（cat_anim.cc）是 C++ 编译——要调 Assets::GetInstance()
// 的 C++ API 取帧，因此头文件不做 extern "C" 包装（两个消费者均为 .cc）。
// 这与 face_core（纯 C 实现）不同。

// ── 动画编号（与素材文件 cat_a{N}_f*.jpg 对应；1 基）────────────────
typedef enum {
    CAT_ANIM_IDLE1 = 1,   // 待机1（平静）
    CAT_ANIM_IDLE2 = 2,   // 待机2（张望）
    CAT_ANIM_IDLE3 = 3,   // 待机3（打盹）
    CAT_ANIM_CRY = 4,     // 哭
    CAT_ANIM_ANGRY = 5,   // 生气
    CAT_ANIM_HAPPY = 6,   // 开心
    CAT_ANIM_SAD = 7,     // 难过
    CAT_ANIM_SHY = 8,     // 害羞
} cat_anim_id_t;

#define CAT_ANIM_COUNT 8     // 动画段数
#define CAT_ANIM_FRAMES 60   // 每段帧数（15fps × 4s，v2：与原项目同段长）
#define CAT_FPS 15           // 播放帧率
#define CAT_FRAME_MS (1000 / CAT_FPS)  // 帧间隔 66ms（显示层 timer 周期）
#define CAT_MOUTH_FRAMES 4   // 嘴形帧数（small/big/wide/oshape 全帧）

// ── 素材几何（4:3 全帧素材；显示 contain-fit 到各板）────────────────
#define CAT_ASSET_W 320
#define CAT_ASSET_H 240

// ── 状态角标（设备态 → 右上角圆点颜色，独立于动画通道）──────────────
// 与 face 主题的 glow 同哲学：零文字 UI 的第二信号通道，按 BOOT 后
// 一眼可辨当前状态。色值复用 face 的状态辉光表，视觉语言跨主题统一。
typedef enum {
    CAT_BADGE_OFF = 0,      // 不显示（splash / 系统卡片全屏期间）
    CAT_BADGE_IDLE,         // 淡蓝  #B4DCFF（默认）
    CAT_BADGE_LISTENING,    // 青绿  #7BE8A0（聆听）
    CAT_BADGE_SPEAKING,     // 暖橙  #F7B96A（说话）
    CAT_BADGE_CONNECTING,   // 琥珀  #F7D96A 慢闪 1.6s（联网/升级/激活）
    CAT_BADGE_ERROR,        // 珊瑚红 #F76E5E（致命错误）
    CAT_BADGE_MUTED,        // 灰    #9E9E9E（静音；仅长按切换时短显 2s）
    CAT_BADGE_MAX
} cat_badge_t;

// ── 几何（320×240 素材 contain-fit → 实际屏型）──────────────────────
typedef struct {
    int16_t screen_w, screen_h;
    int16_t face_w, face_h;      // 素材绘制尺寸（contain-fit 后）
    int16_t face_x, face_y;      // 素材在屏上的左上角（居中）
    int16_t badge_x, badge_y;    // 状态角标圆心（右上角，屏坐标系）
    int16_t badge_r;             // 角标半径（最小 4）
} cat_geom_t;

cat_geom_t cat_geom_make(int width, int height);

// ── 生命周期 ──────────────────────────────────────────────────────────
typedef struct cat_anim_s cat_anim_t;

// 创建：parent 挂载点（屏幕），geom 几何。失败返回 NULL（assets 未挂载等）
cat_anim_t* cat_anim_create(lv_obj_t* parent, const cat_geom_t* geom);

// 销毁（删对象树，释放工作缓冲）
void cat_anim_destroy(cat_anim_t* player);

// assets 分区是否含猫咪素材（cat_a1_f00.jpg 可取到）。false 时显示层
// 应回落基类皮肤（拷机/无素材固件防呆）
bool cat_anim_assets_available(void);

// ── 播放控制 ──────────────────────────────────────────────────────────
// 切动画。fade=true 走交叉淡入（情绪指令路径，原项目 EXPR→startCrossfade）；
// fade=false 硬切（随机循环路径，原项目 animLoop 注释"无缝衔接不渐变"）。
// anim 无效值忽略。
void cat_anim_play(cat_anim_t* player, cat_anim_id_t anim, bool fade);

cat_anim_id_t cat_anim_current(const cat_anim_t* player);

// 待机随机挑下一段：60% idle1-3 / 30% happy+shy / 10% cry+angry+sad
// （原项目 pickRandomAnim 随机分布搬运）。播完当前段时由 tick 自动调用。
void cat_anim_pick_idle_next(cat_anim_t* player);

// 说话嘴形拟态：激活后每 90ms 在 small/big/wide/oshape 全帧间轮换
// （v2：整帧轮换，素材端已按口鼻对齐）；deactivate 后回正常表情帧。
void cat_anim_mouth_active(cat_anim_t* player, bool active);

// 当前是否处于说话拟态（显示层 PollDeviceState 换动画前查）
bool cat_anim_mouth_is_active(const cat_anim_t* player);

// 冻结帧推进（聆听态：定格注视帧 = 与待机动画的可辨差异；角标照常）。
// 冻结期间 cat_anim_play 仍可切动画（切完停在新帧）。
void cat_anim_set_frozen(cat_anim_t* player, bool frozen);
bool cat_anim_is_frozen(const cat_anim_t* player);

// 跳到当前动画指定帧（0 基；不改变播放/冻结状态）。聆听定格用：
// play(idle1) + seek(30) + freeze —— 取中段稳定帧作注视画面。
void cat_anim_seek(cat_anim_t* player, int frame_idx);

// 双击彩蛋：随机播 cry/angry/sad 之一，播完自动回待机随机循环。
// 窗口内 SetEmotion/轮询让路（face_core_in_interact 同款语义）。
void cat_anim_easter_egg(cat_anim_t* player);

// 彩蛋窗口内（彩蛋动画展示期）
bool cat_anim_in_easter(const cat_anim_t* player);

// ── 状态角标 ──────────────────────────────────────────────────────────
void cat_anim_set_badge(cat_anim_t* player, cat_badge_t badge);

// ── 渲染推进（显示层每 66ms 调）───────────────────────────────────────
// render_this_frame=false 时只推进状态不刷 canvas（重负载让路用）。
void cat_anim_tick(cat_anim_t* player, bool render_this_frame);
