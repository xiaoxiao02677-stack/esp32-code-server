# LVGL 事件栈探针 + 淡出来源标记（**诊断构建，不是修复**）

> ⚠️ 本目录只有补丁文本与说明，**未修改任何源码**。
> 应用补丁会临时改动 `managed_components/lvgl__lvgl/…`（第三方组件目录，不受 git 跟踪）
> 与 `main/display/yh_skin/…`。**定位完成后必须回退**，禁止随发布固件烧出。
>
> **⚠️ 开探针后不再崩 ≠ 修好了。** 探针里的 `return`（`CONTAINED`）与 `break`（`BAD PREV`）
> 改变了失败路径，等于顺手把崩溃"拦"住了 —— 那是取证手段，不是修复证据。
> 且 `CONTAINED` 的 `return` 会跳过 `e->deleted = 1` 标记，在飞事件不会被置为 INVALID，
> 可能在下游继续使用已删对象 —— **仅诊断构建，禁止合入主线**。

## 0. 先做这一步：objdump 复核崩点（零改动、5 分钟）

`EXCVADDR = 0x14` 有**两种**合理解释，不能仅凭它断定崩在哪一行：

| 解释 | 计算 | 对应代码 |
|---|---|---|
| `lv_event_t` 伪节点 | `e = 0x10`，读 `e->original_target`(+0x04) | `lv_event.c:323`（本探针假定的崩点） |
| `lv_anim_t` 字段 | `a = 0x00`，读 `a->deleted_cb`(+0x14) | `lv_anim.c:701` |

> 佐证：本工程 `CONFIG_LV_USE_EXT_DATA` 与 `CONFIG_LV_USE_OBJ_ID` 均关闭（sdkconfig:5182 / 5176），
> `lv_anim_t` 布局为 `var 0x00 / exec_cb 0x04 / custom_exec_cb 0x08 / start_cb 0x0C / completed_cb 0x10 / deleted_cb 0x14`。
> 但 `a==0` 时 `:700` 先读 `a->completed_cb`(0x10) 就会崩在 0x10，所以 0x14 更指向 `e==0x10`；
> **仍需反汇编确认**：

```bash
# PC 取 panic 日志里 "PC : 0x420xxxxx" 那一行
xtensa-esp32s3-elf-addr2line -e build/<proj>.elf -f -i -a <PC>
xtensa-esp32s3-elf-objdump -d build/<proj>.elf --start-address=<PC-0x20> --stop-address=<PC+0x20>
```

判读：

| 指令形态 | 结论 |
|---|---|
| `l32i aX, aY, 4` 且 aY=0x10 | 崩在 `lv_event_mark_deleted`，伪节点实锤 → **本探针有效** |
| `l32i aX, aY, 20` 且 aY=0x00 | 与 `while(e)` 矛盾 → 符号化错位，报告里"崩点已确定"要降级 |
| `l32i aX, aY, 20` 且 aY=某 anim 指针 | 崩在 `lv_anim.c:701` → 方向整体转向 anim 生命周期，本探针不适用 |

## 1. 它解决什么问题

崩点（若 0 步确认）：`anim_completed_handler(lv_anim.c:700) → completed_cb → lv_obj_delete → obj_delete_core → lv_obj_destructor(lv_obj.c:606) → lv_event_mark_deleted(lv_event.c:323)`。

已确认事实：

- `event_head` 即 `LV_GLOBAL_DEFAULT()->event_header`，在 **.bss**（`lv_event.c:19` 的宏）。
- `anim_timer` 不在任何事件派发栈内 → 进 destructor 时 `event_head` 本应为 NULL。
- 886ms 窗口内所有显示调用都在 `lvgl_port_lock` 内（LVGL 任务 `lv_timer_handler` 全程持锁，`esp_lvgl_port.c:241-243`）→ **无跨任务并发 push/pop**。
- 栈溢出 / 堆越界写的是任务栈下方或堆内邻居 → **物理上到不了 .bss 的 `event_head`**。

→ 唯一剩余通道：**更早某次 push/pop 不平衡，留下指向已返回栈帧的悬垂 head**（一次成型、永久保留）。
本探针负责把"何时、由谁、以什么方式"把链弄歪打印出来。

## 2. 两个补丁

| 文件 | 作用 | 影响面 |
|---|---|---|
| `lvgl-event-probe.patch` | 事件栈探针 | `managed_components/lvgl__lvgl/src/misc/lv_event.c` |
| `yh-skin-fade-src.patch` | 淡出来源标记 + 收尾日志（可选，但强烈建议配合使用） | `main/display/yh_skin/{yh_skin_boot.h,yh_skin_boot.cc,yh_skin_cards.cc}` |

`yh-skin-fade-src.patch` 内容：

- `yh_skin_boot.h`：**全局作用域**（`namespace yh_skin` 之外）`enum YhFadeSrc { kYhFadeNone, kYhFadeSplash, kYhFadeCards }` + `extern "C" volatile int g_yh_fade_src;`；`namespace yh_skin` 内声明 `const char* FadeSrcName(int)`
- `yh_skin_boot.cc`：全局作用域定义 `extern "C" volatile int g_yh_fade_src = kYhFadeNone;` 与 `FadeSrcName()`；`DismissSplash()` 置 `kYhFadeSplash` 并打印 `start fade-out (src=…, root=…)`；`OnFadeOutCompleted()` 打印 `fade-out completed: target=%p src=%s valid=%d` 后置回 `kYhFadeNone`
- `yh_skin_cards.cc`：`HideCards()` 置 `kYhFadeCards`，卡片 completed_cb 置回 `kYhFadeNone`

> 用 `enum` 而非字符串指针：字符串指针被别处覆盖会让日志撒谎，int 至少不会变成野指针。
> 用 `extern "C"` + 全局作用域而非 namespace 内变量：否则符号被 mangle 成 `_ZN7yh_skin…`，
> C 侧 weak 引用解析为 0，`src=` 永远打印 -1（看着有来源、其实没有）。

## 3. 探针做了什么（只加日志，不改行为）

**默认关闭**：`lv_event.c` 顶部是 `#define YH_LVGL_EVDBG 0`，整段新增代码（静态变量、push/pop 埋点、`mark_deleted` 块）都被 `#if EVDBG_ENABLED` 包住，不开启时编译产物与原来完全一致。
**启用方式**：应用补丁后，把那一行改成 `#define YH_LVGL_EVDBG 1` 再编译（不引入 Kconfig，避免污染 `sets_diff_audit.py` 的 whitelist）。
**两个开关**：`YH_LVGL_EVDBG`（总闸，默认 0）与 `EVDBG_CONTAIN`（坏指针拦截，默认 **1**，改 0 可放行以重取 panic dump）。

`lv_event.c` 三处：

| 位置 | 内容 |
|---|---|
| `lv_event_push()` | **先** `evdbg_depth++` 并记 `last_push = e`（= 当前栈顶），**再**写 `e->prev`/`event_head`。顺序必须与 pop 侧配对：先写 head 会出现 `head` 非空而 `depth==0` 的窗口，正好穿过 `mark_deleted` 的 `if(e)` 闸门，打出一条假的"计数与链不一致" |
| `lv_event_pop()` | `event_head != e` 或 `depth <= 0` → `POP MISMATCH`，并置 sticky `lifo_broken=1`；随后**先** `event_head = e->prev;`、**再** `depth--`。窗口内 head 已回退、depth 偏大 → 被闸门滤掉，**只可能少报、不会误报** |
| `lv_event_mark_deleted()` 入口 | 当 `event_head != NULL` 打印 `NONEMPTY #n head/target/depth/drift/small/in_lvgl_stack/lifo_broken/stack/hwm/task/src`；`drift` 时追加 `HEAD DRIFT expected/actual`。`drift = (head != last_push)` **不带 `depth>0` 条件**：静默时刻两者必须相等，本案正是 `depth==0 && head!=NULL`，加条件会把主判据关掉 |
| `lv_event_mark_deleted()` 拦现场 | `small=1` → 打 `CONTAINED small=1 head=… target=…`。是否 `return` 由文件顶部 `#define EVDBG_CONTAIN` 决定：**默认 `1`**（拦住，可继续观察"后续还崩不崩 / BAD PREV 出不出"）；改 `0` 则放行，让它在原处崩以保留一份新的 panic dump。不拦的话必然进 `while(e)` 解引用 `e=0x10`，同一个 crash 原样复发 |
| `lv_event_mark_deleted()` 循环内 | 复用本来就要读的 `e->prev` 做一次数值校验：`prev != NULL && prev < 0x10000` → 打 `BAD PREV prev=%p owner=%p depth=…` 后 `break`。`owner` 是持有坏 prev 的**那个节点地址**，pop 侧拿不到 |

**限流**：`NONEMPTY` 32 条；`POP MISMATCH`、`HEAD DRIFT`、`CONTAINED`、`BAD PREV` 各 8 条（永久损坏场景下后两者每次删除都会命中，不限流会把 886ms 窗口挤掉）。超限后只打一行 `SUPPRESSED kind=… first_suppressed=…` 然后静音。注意 `first_suppressed` 是"从第 N 次起静音"，**不是**总次数。

设计红线（评审一致，改补丁时别破坏）：

1. **绝不额外沿 `e->prev` 遍历打印链**——链已损坏时每走一步都是一次野指针解引用，崩点会从 LVGL 漂到日志函数，原始 backtrace 直接丢失。唯一例外是 `while(e)` 里**本来就要读**的那次 `e->prev`，只拿它做数值比较。
2. **不用 `configASSERT(event_head == NULL)`**——"在事件回调里删对象"是 LVGL 合法范式（卡片隐藏、屏幕切换都会），断言会在正常路径误报并毁现场。
3. `push`/`pop` 只在这两个**汇聚函数**埋点（`lv_obj_send_event` 与 `lv_event_push_and_send` 都经过）。
4. 地址判定**只做数值比较**（指针关系比较在 C 标准下是 UB，统一转 `unsigned long`），全程不解引用：`small = (head < 0x10000)`、`in_lvgl_stack = head ∈ [stack_start, stack_start + 7168)`。
5. **NONEMPTY / HEAD DRIFT / BAD PREV 必须在 `if(head)` 内**；**`POP MISMATCH` 不能加这个闸门**——它的核心条件是 `head != e`，最常见现场就是 `head == NULL && e != NULL`（漏 push / 多 pop），塞进闸门会把最该抓的一类静默掉。
6. 任何"只打 `depth`、不连同 head 一行"的打点都不要加：depth 只有和 head 同行才可解释。
7. `drift` 是**主判据**（快判"head 被改指"）；若要再分"曾 push 过但已成悬垂槽位"与"从未 push（.bss 野写）"，才需要环形缓冲 rec 做**补充分类**。两者是主从关系，不是并列判据。


## 4. 应用 / 回退

工作目录：`hardware/sets/yuhe-esp32`

```bash
# 干跑 → 应用（顺序无关）
patch -p1 --dry-run --forward < ../patches/lvgl-event-probe.patch
patch -p1 --forward          < ../patches/lvgl-event-probe.patch
patch -p1 --dry-run --forward < ../patches/yh-skin-fade-src.patch
patch -p1 --forward          < ../patches/yh-skin-fade-src.patch

# 回退
patch -p1 --reverse < ../patches/yh-skin-fade-src.patch
patch -p1 --reverse < ../patches/lvgl-event-probe.patch
# 或彻底还原 LVGL 组件
rm -rf managed_components/lvgl__lvgl && idf.py reconfigure
```

自检：`grep -rn "EVDBG" managed_components/lvgl__lvgl/src/misc/lv_event.c main/display/yh_skin/` 应无输出。
PowerShell 下若 `patch` 不可用，用 Git Bash 执行。

**`src=` 字段自检（重要）**：`g_yh_fade_src` 必须落在**全局作用域 + `extern "C"`**，否则 C 侧 weak 引用解析为 0、日志永远是 `src=-1`（看着有来源、其实没有）。应用第二个补丁后验证符号名未 mangle：

```bash
nm -C build/yuhe.elf | grep g_yh_fade_src
# 期望：恰好一行、形如 00000000 B g_yh_fade_src
# 若看到 _ZN7yh_skin... 说明声明/定义被放进了 namespace，必须改回全局作用域
```


## 5. 日志判读表

先按时间取 **886ms ± 200ms** 的日志窗口。

| 观测（按优先级） | 判定 | 下一步 |
|---|---|---|
| `NONEMPTY` 且 `src != 0`（淡出窗口内） | **链脏已实锤**。`depth` 只用于定位：head 从未被 push 过 → `.bss` 野写；head 是记录过的节点但 `prev` 变了 → 该节点栈槽被覆盖 | 按 `drift` / `in_lvgl_stack` / `BAD PREV owner` 三分支往下查 |
| `NONEMPTY` 且 `src == 0`（普通交互回调里删对象） | **正常，忽略** | 不改结论 |
| `POP MISMATCH` | push/pop 不平衡（漏 push / 乱序 pop / 多 pop）——独立缺陷线索，**不是本崩因的充分证据** | 按该行时间点回溯那一处调用路径 |
| `CONTAINED head=… target=…` | 坏值已被拦截，本次**未崩**；**「没崩」不能当修复证据** | 结合同一时刻 `NONEMPTY` 行的 `small=1` 定位写者 |
| `BAD PREV prev=… owner=…` | 直接钉死"谁被写坏"：去 `owner` 指向的那个节点查它的 `prev` 栈槽（栈槽被覆盖 / 野写） | 在 `owner` 上设 watchpoint |
| `HEAD DRIFT expected=… actual=…` | `head` 不等于当前栈顶（push 记录过的节点），被中途改指 | 若紧跟 crash，抓 watchpoint；先看 `lifo_broken` 是否为 1 |
| `NONEMPTY … in_lvgl_stack=1` | head 落在 LVGL 任务栈区间。**仅当 `depth==0` 时**才解释为"悬垂栈帧"；`depth>0` 时它=1 是正常的（本次删除就在派发栈里） | 结合同行 `depth=` 与 `POP MISMATCH` 判断 |
| `NONEMPTY … lifo_broken=1` | 之前已发生过 `POP MISMATCH`，`last_push` 基线已被重绑到歪掉的 head，**此后所有 drift / small 结论一律降级**为"同一次损坏的下游证据"，不能再当独立怀疑点 | 回到最早那条 `POP MISMATCH` |
| 全程无 `EVDBG` 输出仍崩原处 | 探针未覆盖（外部野写直接把 head 写成合法地址等） | 上硬件 watchpoint；并回第 0 步确认 PC |
| `hwm=` < 1024B | LVGL 任务栈偏紧（默认 7168B） | 独立隐患，**不能**用作本崩因解释（写不到 .bss） |

> **`src` 的边界**：`splash` 路径在 `OnFadeOutCompleted` 内同步收尾，`src` 全程非 0，按上表第一行判读即可。
> `cards` 路径用的是 `lv_obj_delete_async`，真正删除发生在**下一次** `lv_timer_handler`，此时 `src` 已清回 0 ——
> 该路径请用 `fade-out completed: target=%p` 日志与 `NONEMPTY … target=` 对齐，**不要**单看 `src`。
>
> 另：`anim_timer` 的 4 个入口已穷举排除事件派发（`lv_timer.c:337-373` 无 push；`lv_anim_refr_now` 仅本工程 `sleep_timer.cc:94` 的 main 任务、≥60s；`anim_vsync_event` 需显式开启、本库无调用；`obj_delete_core:676` 的 DELETE 事件 push→dispatch→pop 恒定配对）。
> 因此**旧版"`NONEMPTY depth>0` 可能是合法事件栈内删除"这一行是错的，已删除** —— timer 栈内 `event_head` 必为 NULL，出现非空就是异常。

两条已知边界（写在这里，避免把预期现象当新证据）：

1. **`CONTAINED` 之后的二次崩溃不计入判读**。`EVDBG_CONTAIN=1` 时 `return` 会跳过 `e->deleted = 1` 标记，而在飞事件随后仍会随对象正常删除 —— 可能在**下游换一处崩**。那是预期副作用，不是新证据，也不能据此反推"原崩点不是这里"。要重取干净 dump 就把 `EVDBG_CONTAIN` 改 0。
2. **`drift` 有一个理论噪声窗口**：`lv_event_push()` 里 `EVDBG_PUSH_HOOK` 已 `depth++`、而 `event_head = e` 尚未执行的那两条语句之间，若有别的任务观测 `event_head`，会假报 `drift=1`。当前 `lvgl_mux` 串行化保证不会发生；若将来有人摘掉该锁，这一格判据需重评（注意方向仍是"head 是旧值"，被 `if(e)` 滤掉的是日志本身，不是误报链脏）。

## 6. 单位坑（初稿写错过两次，别再踩）

- `.task_stack = 7168` 单位是**字节**（`esp_lvgl_port.h:68`）；栈区间 = `(uint8_t*)pxTaskGetStackStart(NULL) + 7168`，**不是** `7168 * 4`。
- `pxTaskGetStackStart()` 返回 `StackType_t*`（或 `uint32_t*`），算字节必须转 `uint8_t*`；补丁里用 `EVDBG_LVGL_STACK_BYTES` 宏并注明单位。
- `uxTaskGetStackHighWaterMark()` 在 ESP-IDF 返回**字节**（不是字），日志里以 `%uB` 标注。
- **编译依赖**：`uxTaskGetStackHighWaterMark` 受 `CONFIG_FREERTOS_USE_TRACE_FACILITY` / `INCLUDE_uxTaskGetStackHighWaterMark` 控制，被裁掉会**编译失败**。若报未声明，二选一：打开该配置，或在补丁里把这一项换成常量 `0`（其余字段不受影响）。
- 若日后把 `port_cfg.task_stack` 改大，必须同步改 `EVDBG_LVGL_STACK_BYTES`，否则 `in_lvgl_stack` 判定失真。


## 7. 与"修复"的关系

- 两个补丁**都不修任何东西**，只提供定性证据。
- 当前工作区的 splash 已改为「淡出后 **隐藏**（`lv_obj_add_flag(HIDDEN)`）而非销毁」，即崩溃路径已被绕开；`g_yh_fade_src` 日志仍可在该形态下确认"谁在收尾"。
- 独立隐患（与本次崩溃无因果关系，需单独排期）：
  1. LVGL 任务栈 7168B 偏小；
  2. `boards/common/sleep_timer.cc:94` 在 main 任务裸调 `lv_refr_now(nullptr)`（无 `DisplayLockGuard`）；
  3. `boards/yuhe/yh-154tft-wifi/yh_set_lcd_display.h:73-84` 温度告警在 esp_timer 任务裸调 `lv_obj_*`（无锁）；
  4. `protocols/websocket_protocol.cc:41/51` payload 变长 `memcpy`，需核对分配长度。
