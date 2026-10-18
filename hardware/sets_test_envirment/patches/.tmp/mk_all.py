# -*- coding: utf-8 -*-
import io

TMP = "G:/demo/21_xiaozhi/hardware/sets/patches/.tmp/"

# =====================================================================
# 1) LVGL 探针：lv_event.c
# =====================================================================
s = io.open(TMP + "lv_event.c.orig", encoding="utf-8").read()

old_inc = '''#include "lv_event_private.h"
#include "../core/lv_global.h"
#include "../stdlib/lv_mem.h"
#include "lv_assert.h"
#include "lv_types.h"
'''
new_inc = old_inc + '''
/* ===== EVDBG event-stack probe (diagnostic build only) =====
 * 默认关；诊断构建时把下面这行改成 #define YH_LVGL_EVDBG 1 后手动应用本补丁。
 * 说明与判读见 patches/README-lv-event-probe.md。本补丁不修任何问题。 */
#define YH_LVGL_EVDBG 0

/* 坏指针拦截开关：
 *   1 = 拦住（small 命中后 return），可继续观察"后续还崩不崩 / BAD PREV 出不出"；
 *   0 = 放行，让它在原处崩，保留一份新的 panic dump。
 * 需要重新取证时改成 0；默认 1。 */
#define EVDBG_CONTAIN 1

#if defined(YH_LVGL_EVDBG) && YH_LVGL_EVDBG && defined(ESP_PLATFORM)
    #define EVDBG_ENABLED 1
#else
    #define EVDBG_ENABLED 0
#endif

#if EVDBG_ENABLED
    #include <esp_log.h>
    #include <freertos/FreeRTOS.h>
    #include <freertos/task.h>

    #define EVDBG_LOG(...) ESP_DRAM_LOGE("EVDBG", __VA_ARGS__)

    /* 淡出来源标记由 main/display/yh_skin 以 extern "C" 定义（符号未 mangle）。
     * weak：符号不存在时解析为 NULL，非 yh 板型不影响链接。 */
    __attribute__((weak)) extern volatile int g_yh_fade_src;
    #define EVDBG_SRC() ((&g_yh_fade_src) ? (int)g_yh_fade_src : -1)

    /* LVGL 任务栈大小（字节）。来源：esp_lvgl_port.h:68 .task_stack = 7168。
     * ★ 单位是字节，不要乘 sizeof(StackType_t)；若 lcd_display.cc 里改大，这里必须同步改。 */
    #define EVDBG_LVGL_STACK_BYTES 7168

    /* 各通道打印上限；超限后只打一行 SUPPRESSED 再静音，避免刷屏拖慢现场。 */
    #define EVDBG_MAX_NONEMPTY 32
    #define EVDBG_MAX_POP      8
    #define EVDBG_MAX_DRIFT    8
    #define EVDBG_MAX_CONTAIN  8
    #define EVDBG_MAX_BADPREV  8

    static int32_t evdbg_depth = 0;
    static lv_event_t * evdbg_last_push = NULL;  /* 当前栈顶 */
    static int evdbg_lifo_broken = 0;            /* sticky：一旦 POP MISMATCH 就再不复位 */
    static uint32_t evdbg_n_nonempty = 0;
    static uint32_t evdbg_n_pop = 0;
    static uint32_t evdbg_n_drift = 0;
    static uint32_t evdbg_n_contain = 0;
    static uint32_t evdbg_n_badprev = 0;

@@EMIT_MACRO@@

    /* push/pop 埋点的顺序必须**成对**，否则抢占窗口会制造假信号：
     *   push: depth++ 先于写 e->prev / event_head  -> 窗口内 head 是旧值，被 mark_deleted 的 if(e) 滤掉；
     *   pop : head 回退先于 depth--                -> 窗口内 head 已回退、depth 偏大，同样被滤掉。
     * 效果是**只可能少报、不会误报**。反过来（先 depth-- 再写 head）会出现 head!=NULL && depth==0 的假信号。 */
    #define EVDBG_PUSH_HOOK(ev) do { evdbg_depth++; evdbg_last_push = (ev); } while(0)
#else
    #define EVDBG_LOG(...)
    #define EVDBG_SRC() (-1)
    #define EVDBG_EMIT(counter, limit, kind, ...) do { } while(0)
    #define EVDBG_PUSH_HOOK(ev) do { (void)(ev); } while(0)
#endif
'''
assert s.count(old_inc) == 1, "include anchor"

# 统一续行反斜杠列，避免改字段名后对齐被打散
_emit = [
    '    #define EVDBG_EMIT(counter, limit, kind, ...)',
    '        do {',
    '            (counter)++;',
    '            if((counter) <= (uint32_t)(limit)) { EVDBG_LOG(__VA_ARGS__); }',
    '            else if((counter) == (uint32_t)(limit) + 1u) {',
    '                EVDBG_LOG("SUPPRESSED kind=%s first_suppressed=%lu", (kind),',
    '                          (unsigned long)(counter));',
    '            }',
    '        } while(0)',
]
_col = max(len(x) for x in _emit) + 2
_emit_macro = "\n".join(
    x if i == len(_emit) - 1 else x + " " * (_col - len(x)) + "\\"
    for i, x in enumerate(_emit))
new_inc = new_inc.replace("@@EMIT_MACRO@@", _emit_macro)
s = s.replace(old_inc, new_inc)

# push：计数必须在写 head 之前，避免 "head 非空 / depth==0" 的假窗口
old_push = '''    e->prev = event_head;
    event_head = e;

}
'''
new_push = '''    EVDBG_PUSH_HOOK(e);         /* 先计数再改 head，避免出现 head 非空而 depth==0 的假窗口 */
    e->prev = event_head;
    event_head = e;
}
'''
assert s.count(old_push) == 1, "push anchor"
s = s.replace(old_push, new_push)

old_pop = '''void lv_event_pop(lv_event_t * e)
{
    event_head = e->prev;
}
'''
new_pop = '''void lv_event_pop(lv_event_t * e)
{
#if EVDBG_ENABLED
    /* LIFO + 计数不变式：
     *   head != e  -> 乱序 pop / pop 了别人的节点；
     *   depth <= 0 -> pop 多于 push。
     * 一旦触发，event_head 已经歪了，后续删除就可能崩在 lv_event_mark_deleted。
     * ★ 这里**不能**再加 if(event_head != NULL) 闸门：最常见的现场恰恰是
     *   head == NULL && e != NULL（漏 push / 多 pop），加闸门会把最该抓的一类静默掉。
     * ★ 顺序：先写 head、后 depth--（与 push 侧配对，窗口内只会少报）。
     *   sticky 置位后，后面 NONEMPTY 行的 lifo_broken=1 表示"LIFO 早已坏"，别再当成独立的外部写。 */
    if(event_head != e || evdbg_depth <= 0) {
        evdbg_lifo_broken = 1;
        EVDBG_EMIT(evdbg_n_pop, EVDBG_MAX_POP, "POP",
                   "POP MISMATCH head=%p e=%p depth=%ld task=%s src=%d",
                   (void *)event_head, (void *)e, (long)evdbg_depth,
                   pcTaskGetName(NULL), EVDBG_SRC());
    }
#endif
    event_head = e->prev;
#if EVDBG_ENABLED
    if(evdbg_depth > 0) evdbg_depth--;
    evdbg_last_push = event_head;   /* pop 后新的栈顶 */
#endif
}
'''
assert s.count(old_pop) == 1, "pop anchor"
s = s.replace(old_pop, new_pop)

old_md = '''void lv_event_mark_deleted(void * target)
{
    lv_event_t * e = event_head;

    while(e) {
'''
new_md = '''void lv_event_mark_deleted(void * target)
{
    lv_event_t * e = event_head;

#if EVDBG_ENABLED
    /* 入口探针，四条硬约束：
     *   1) 只读 event_head 的值，**绝不沿 e->prev 遍历**：链已损坏时每走一步都是
     *      野指针解引用，会把崩点从本函数漂到日志里、丢掉原始 backtrace。
     *   2) 不做 configASSERT(event_head == NULL)：在事件回调里删对象是 LVGL 合法范式。
     *   3) 只做数值比较（指针关系比较在 C 标准下是 UB），全程不解引用。
     *   4) small（小整数 head）命中后是否 return 由 EVDBG_CONTAIN 决定（默认 1）：
     *      不拦就会进 while(e)，第一句 e->original_target 立刻解引用 e=0x10，同一个 crash 原样复发。
     * 判读见 README 第 5 节；in_lvgl_stack=1 只有在 depth==0 时才等于"悬垂栈帧"。 */
    if(e != NULL) {
        unsigned long lo = (unsigned long)pxTaskGetStackStart(NULL);
        unsigned long hi = lo + (unsigned long)EVDBG_LVGL_STACK_BYTES;
        unsigned long h = (unsigned long)e;
        int small = (h < 0x10000ul) ? 1 : 0;
        int in_lvgl_stack = (h >= lo && h < hi) ? 1 : 0;
        /* drift 不依赖 depth：pop 末尾已把 last_push 同步成 head，静默时刻两者必须相等。
         * 本案正是 depth==0 && head!=NULL —— 加 depth>0 条件会把最关键的一格关掉。 */
        int drift = (e != evdbg_last_push) ? 1 : 0;

        EVDBG_EMIT(evdbg_n_nonempty, EVDBG_MAX_NONEMPTY, "NONEMPTY",
                   "NONEMPTY #%lu head=%p target=%p depth=%ld drift=%d small=%d "
                   "in_lvgl_stack=%d lifo_broken=%d stack=[%08lx,%08lx) hwm=%uB task=%s src=%d",
                   (unsigned long)evdbg_n_nonempty, (void *)e, target,
                   (long)evdbg_depth, drift, small, in_lvgl_stack, evdbg_lifo_broken, lo, hi,
                   (unsigned)uxTaskGetStackHighWaterMark(NULL),
                   pcTaskGetName(NULL), EVDBG_SRC());
        if(drift) {
            EVDBG_EMIT(evdbg_n_drift, EVDBG_MAX_DRIFT, "DRIFT",
                       "HEAD DRIFT expected=%p actual=%p depth=%ld lifo_broken=%d",
                       (void *)evdbg_last_push, (void *)e, (long)evdbg_depth, evdbg_lifo_broken);
        }
        if(small) {
            /* 坏链拦截（开关在文件顶部 EVDBG_CONTAIN）：
             *   1 -> 打一行即 return，让系统继续跑，后续行为还能观察；
             *   0 -> 放行，在原处崩，保留一份新的 panic dump。 */
            EVDBG_EMIT(evdbg_n_contain, EVDBG_MAX_CONTAIN, "CONTAIN",
                       "CONTAINED small=%d head=%p target=%p depth=%ld task=%s src=%d",
                       small, (void *)e, target, (long)evdbg_depth,
                       pcTaskGetName(NULL), EVDBG_SRC());
#if EVDBG_CONTAIN
            return;
#endif
        }
    }
#endif

    while(e) {
'''
assert s.count(old_md) == 1, "mark_deleted anchor"
s = s.replace(old_md, new_md)

# 循环内 prev 校验：这次 e->prev 本来就要读，不新增解引用
old_eq = '''        if(e->original_target == target || e->current_target == target) e->deleted = 1;
        e = e->prev;
    }
'''
new_eq = '''        if(e->original_target == target || e->current_target == target) e->deleted = 1;
#if EVDBG_ENABLED
        {
            /* 这次 e->prev 本来就要读，只拿读出的值做数值比较：不新增解引用、不额外汇遍历。
             * owner = 持有坏 prev 的那个节点地址 —— pop 侧永远拿不到这个信息，能直接钉死谁被写坏。 */
            lv_event_t * prev = e->prev;
            if(prev != NULL && (unsigned long)prev < 0x10000ul) {
                EVDBG_EMIT(evdbg_n_badprev, EVDBG_MAX_BADPREV, "BADPREV",
                           "BAD PREV prev=%p owner=%p depth=%ld task=%s src=%d",
                           (void *)prev, (void *)e, (long)evdbg_depth,
                           pcTaskGetName(NULL), EVDBG_SRC());
                break;
            }
            if(prev == NULL) break;
            e = prev;
        }
#else
        e = e->prev;
#endif
    }
'''
assert s.count(old_eq) == 1, "mark_deleted loop anchor"
s = s.replace(old_eq, new_eq)

io.open(TMP + "lv_event.c.new", "w", encoding="utf-8", newline="\n").write(s)

# =====================================================================
# 2) yh_skin 来源标记（全局作用域 + extern "C"）
# =====================================================================
h = io.open(TMP + "m/boot.h.orig", encoding="utf-8").read()
old = '''namespace yh_skin {

struct SplashInfo {'''
new = '''// ---- 诊断探针：淡出来源标记（仅诊断构建；见 patches/README-lv-event-probe.md）----
// ★ 必须放在**全局作用域**且用 extern "C"：LVGL 侧（C 文件）以
//   `__attribute__((weak)) extern volatile int g_yh_fade_src;` 引用，
//   若放进 namespace 会被 mangle 成 _ZN7yh_skin…，C 侧解析为 0 → 日志永远是 -1。
enum YhFadeSrc {
    kYhFadeNone = 0,
    kYhFadeSplash = 1,  // DismissSplash() 启动的 300ms 淡出
    kYhFadeCards = 2,   // HideCards() 启动的 200ms 淡出
};
extern "C" volatile int g_yh_fade_src;   // 定义在 yh_skin_boot.cc 的全局作用域

namespace yh_skin {

const char* FadeSrcName(int src);

struct SplashInfo {'''
assert h.count(old) == 1, "boot.h anchor"
h = h.replace(old, new)
io.open(TMP + "m/boot.h.new", "w", encoding="utf-8", newline="\n").write(h)

c = io.open(TMP + "m/boot.cc.orig", encoding="utf-8").read()
old = '''#define TAG "YhSkinBoot"

namespace yh_skin {
namespace {
'''
new = '''#define TAG "YhSkinBoot"

// ---- 诊断探针：淡出来源（全局作用域 + C 链接，供 LVGL 探针读取）----
extern "C" volatile int g_yh_fade_src = kYhFadeNone;

namespace yh_skin {

const char* FadeSrcName(int src) {
    switch (src) {
        case kYhFadeSplash: return "splash_fade";
        case kYhFadeCards: return "cards_fade";
        default: return "-";
    }
}

namespace {
'''
assert c.count(old) == 1, "boot.cc anchor"
c = c.replace(old, new)

old = '''    g_dismissing = true;
    ESP_LOGI(TAG, "DismissSplash: start fade-out");
'''
new = '''    g_dismissing = true;
    ::g_yh_fade_src = kYhFadeSplash;   // EVDBG: 标记 300ms 淡出来源
    ESP_LOGI(TAG, "DismissSplash: start fade-out (src=%s, root=%p)",
             FadeSrcName(::g_yh_fade_src), static_cast<void*>(g_root));
'''
assert c.count(old) == 1, "DismissSplash anchor"
c = c.replace(old, new)

old = '''    if (lv_obj_is_valid(target)) {
        lv_obj_add_flag(target, LV_OBJ_FLAG_HIDDEN);
    }
}
'''
new = '''    // EVDBG: 直接打印"这一刻是谁在收尾、要动哪个对象"，与 LVGL 侧 NONEMPTY 日志按 target 对齐
    ESP_LOGI(TAG, "fade-out completed: target=%p src=%s valid=%d",
             static_cast<void*>(target), FadeSrcName(::g_yh_fade_src),
             lv_obj_is_valid(target) ? 1 : 0);
    if (lv_obj_is_valid(target)) {
        lv_obj_add_flag(target, LV_OBJ_FLAG_HIDDEN);
    }
    ::g_yh_fade_src = kYhFadeNone;   // EVDBG: 收尾后清标记
}
'''
assert c.count(old) == 1, "OnFadeOutCompleted anchor"
c = c.replace(old, new)
io.open(TMP + "m/boot.cc.new", "w", encoding="utf-8", newline="\n").write(c)

k = io.open(TMP + "m/cards.cc.orig", encoding="utf-8").read()
old = '''#include "yh_skin_cards.h"
'''
new = '''#include "yh_skin_cards.h"

#include "yh_skin_boot.h"   // EVDBG: 共享淡出来源标记（全局 extern "C" 变量）
'''
assert k.count(old) == 1, "cards include anchor"
k = k.replace(old, new)

old = '''    g_hiding = true;

    // 先置空指针再删对象'''
new = '''    g_hiding = true;
    ::g_yh_fade_src = kYhFadeCards;   // EVDBG: 标记 200ms 淡出来源

    // 先置空指针再删对象'''
assert k.count(old) == 1, "HideCards anchor"
k = k.replace(old, new)

old = '''        if (obj != nullptr && lv_obj_is_valid(obj)) {
            lv_obj_delete_async(obj);
        }
    });
'''
new = '''        if (obj != nullptr && lv_obj_is_valid(obj)) {
            lv_obj_delete_async(obj);
        }
        ::g_yh_fade_src = kYhFadeNone;   // EVDBG: 收尾后清标记
    });
'''
assert k.count(old) == 1, "cards completed_cb anchor"
k = k.replace(old, new)
io.open(TMP + "m/cards.cc.new", "w", encoding="utf-8", newline="\n").write(k)

print("ok")
