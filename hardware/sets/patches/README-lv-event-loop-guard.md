# `lv-event-loop-guard.patch` —— 把 `event_head` 的无限自旋降级为“这次少标几个标记”

**性质：加固，不是修根因。可选。** 根因是“非 LVGL 任务并发调用 LVGL”（见主报告），  
本补丁只保证**万一链再次被写坏，设备不会假死**。

## 它*改了什么*

*只改 `managed_components/lvgl__lvgl/src/misc/lv_event.c` 的 `lv_event`*`_mark_deleted()`：  
给 `while(e)` 加一个 256 次的计数上限，命中即 `break`。

```c
uint32_t yh_guard = 0;
while(e) {
    if(e->original_target == target || e->current_target == target) e->deleted = 1;
    e = e->prev;
    if(++yh_guard > 256) break;   /* 链成环：放弃本次标记，绝不在这里自旋 */
}
```

## 为什么需要它

`event_head` 是 `lv_global` 里的**单个全局链表**，节点却是各调用者**栈上**的  
`lv_event_t` 局部变量；本工程 `sdkconfig` 里没有 `CONFIG_LV_USE_OS`，即  
`LV_OS_NONE`，LVGL 内部**零加锁**。两个任务同时 push/pop 时，`pop` 会把 `head`  
还原成“另一个任务早已返回的栈槽”，该槽被同深度复用后  
`lv_event_push` 写出 `e->prev = &e` 的**自环**，于是本函数永久空转。

实测后果（2026-10-17 17:00 现场）：

```
taskLVGL 卡在 lv_event_mark_deleted:323 的 while(e) 30 秒+
→ CPU1 的 IDLE1 饿死，task_wdt 每 10 秒打印完全相同的栈
→ LVGL 锁再也不归还，其他任务 30 秒后开始刷 "Failed to lock display"
→ 设备假死（不重启、不响应），只能断电
```

加上限后，同样的损坏只会导致**这一次删除少给几个对象打 `deleted` 标记**，  
下游可能漏一次 invalidate / 少一次事件去重，但不会假死。

## 应用 / 回退

```bash
cd hardware/sets/xiaozhi-esp32
patch -p1 --dry-run --forward < ../patches/lv-event-loop-guard.patch   # 先干跑，应 rc=0
patch -p1 --forward < ../patches/lv-event-loop-guard.patch

# 回退
patch -p1 --reverse < ../patches/lv-event-loop-guard.patch
# 或者最彻底：
rm -rf managed_components/lvgl__lvgl && idf.py reconfigure
```

**注意**：`managed_c`<u>`omponents/` 是依赖目录，`idf.py update-dependencies`  
或删除 `dependenci`</u>`es.lock` 后重新拉取会**覆盖本补丁**。它是本地加固，不是上游修复；  
升级 LVGL 后需要重新评估（若上游已给 `event_head` 加锁/加界，则本补丁可弃）。

## 判读

打完这个补丁后，如果设备**不再假死**，但出现偶发的：

- 局部刷新残留 / 某次删除后控件没消失
- 事件去重偶尔失效

那是本补丁生效的预期副作用（说明链确实损坏过），**不代表问题已修好**。  
真正的验证标准是：`event_head` 不再被写坏——即日志里不再出现  
`Failed to lock display`，且长跑无 WDT。
