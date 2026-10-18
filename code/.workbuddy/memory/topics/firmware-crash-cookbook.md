# 固件崩溃排查手册（累计现场）

> 从 `MEMORY.md` 拆出。这里放"下次再崩怎么定位"的判据与血泪，索引仍在 `MEMORY.md`。

## 通用定位手法

- 串口回溯常被 `[COMxx]` 交错截断，**别硬读文本**；拿 `build/xiaozhi.elf` 跑
  `xtensa-esp32s3-elf-addr2line -pfiaC -e build/xiaozhi.elf <addr>`。
  工具链：`/d/INSTALL/esp/tools/xtensa-esp-elf/esp-15.2.0_20251204/xtensa-esp-elf/bin/`。
- **先校验 elf 与设备镜像同源**：日志里 `ELF file SHA256: e0de67621` 与
  `sha256sum build/xiaozhi.elf` 前 9 位一致才可信。不一致时 addr2line 会解出跨模块的
  荒谬符号（实测解出 `DCT2D_V_270`（jpeg 汇编）、`lv_point_array_transform`）——
  **一条栈里出现风马牛不相及的符号 = 地址不属于这个 elf**，不是真的调用了它。
- `objdump` 对 `.flash.text` 不解码时的绕法：
  `objcopy -O binary --only-section=.flash.text` → `dd` 切片 →
  `objdump -D -b binary -m xtensa --adjust-vma=<ADDR>`。
- 栈里 `A0`/`A8` 高位常打印成 `0x82xxxxxx`，真地址把首字节改成 `0x42`。
- **不要用 `git show HEAD:` / `git diff` 判断未跟踪目录的历史状态**：
  `main/display/yh_skin/` 至今未入库，`git cat-file -e` 报
  `exists on disk, but not in 'HEAD'`，`grep -c` 会得到假的 0（曾据此误判"HEAD 里一把锁都没有"）。

## 现场 ①：`LoadProhibited` / `EXCVADDR=0x14`（`event_head` 悬垂）

- 判据：`EXCVADDR=0x14` + 栈里 `lv_event_mark_deleted(lv_event.c:323)` +
  `lv_obj_destructor:606`。`0x14` = 基址 0x10 读 `original_target(+0x04)`。
- 成因链：`event_head` 是**单个全局链表**（`#define event_head LV_GLOBAL_DEFAULT()->event_header`，
  实体在 `lv_global_t` 的 `.bss`，实测 `0x3fca616c` = lv_global + 0x70）；`lv_event_t` 是**栈上局部变量**；
  `LV_OS_NONE` ⇒ LVGL 内部零加锁。并发 push/pop **区间交叉**（push_A<push_B<pop_A<pop_B）时
  pop 不是弹栈顶而是恢复入栈时记住的 prev ⇒ 残留悬垂 ⇒ 之后同一调用点复用同一栈槽 ⇒
  `e->prev = &e` 单节点自环。嵌套调用是干净的，只有交叉才出事。
- `lv_event_t` 28 字节布局：`current_target 0x00 / original_target 0x04 / code 0x08 /
  user_data 0x0C / param 0x10 / prev 0x14 / flags 0x18`。
- 只有 create/size/pos/align/delete 一族会 push：`lv_obj_create`(lv_obj_class.c:128)、
  `lv_obj_set_size`(lv_obj_pos.c:278)、`lv_obj_set_pos/align/center`(lv_obj_pos.c:942)、
  `lv_obj_delete`(DELETE)。**`lv_obj_add_flag/remove_flag/has_flag` 不 push**；
  `lv_obj_set_style_*` 仅 `LAYOUT_UPDATE` 类属性（`BORDER_WIDTH`、`TEXT_FONT`）才发 `STYLE_CHANGED`。
- 本案种子：`YhSetLcdDisplay::SetupUI()` 里的 `SetupHighTempWarningPopup()`——
  唯一"非 LVGL 任务 + 无锁 + 会 push"的活跃路径。`EnsureCard` 的调用者都在锁内，安全。
- 处置：① `DisplayLockGuard` 由 30s 一次性长等改 **4×500ms 分片重试**（总 2s）+ `locked()`；
  ② `yh_skin_display.cc` 27 处加 `if (!lock) { return; }` **fail-closed**；
  ③ `lv_event_mark_deleted` 的 `while(e)` 加 256 次上限兜底（`patches/lv-event-loop-guard.patch`）。
- **`DisplayLockGuard` 曾经是 fail-open**：`Lock(30000)` 失败只 `ESP_LOGE` 然后无锁裸调
  `lv_*`，把"等不到锁"升级成"无锁并发送把 LVGL 链写坏"。改后日志必含
  `after %d ms; caller must skip LVGL work` —— **这条文案是判断固件新旧的指纹**（旧版只有裸 `Failed to lock display`）。
- 已被源码证否、别再当结论：①「栈溢出/堆越界写坏 event_head」——`lv_global` 在 `.bss`，无写入通道；
  ②「completed_cb 里删对象本身非法」——LVGL 官方 `lv_obj_delete_anim_completed_cb` 就是 `lv_obj_delete(a->var)`；
  ③「async 删除可免疫」——`lv_obj_delete_async` 最终仍走 `obj_delete_core → lv_obj_destructor:606`。
- `anim_timer` 四个入口已穷举，**都不在事件派发栈内** ⇒ 进 destructor 时 `event_head` 本应为 NULL；
  非 NULL 即脏链。
- 插桩红线：**别用 `configASSERT(event_head==NULL)`**（对象在自身事件回调里被删时链合法非空）；
  坏指针必须 `return`/`break` **拦住**，只打日志会立刻在原处崩；**开探针后不崩 ≠ 修好了**。
  探针判据两个静默假阴性：① `drift` 若写成 `depth>0 && e!=last_push`，因为 pop 末尾把 `last_push`
  重绑到 head，`depth==0` 时它必等于 NULL ⇒ 主判据被整格关掉；② `POP MISMATCH` **不能加 `if(head)` 闸门**，
  最常见现场恰是 `head==NULL && e!=NULL`。

## 现场 ②：`InstrFetchProhibited` / `EXCVADDR=0x0`（字体悬垂，换 assets 字体后循环重启）

- 判据：`PC=0x0`、`EXCVADDR=0x0`、`Core 1 panic'ed (InstrFetchProhibited)`，发生在
  `Assets: Refreshing display theme...` 之后，栈为
  `lvgl_port_task → lv_display_refr_timer(lv_refr.c:402) → lv_obj_update_layout(lv_obj_pos.c:395) →
  layout_update_core(1537/1542) → lv_font_get_glyph_width(lv_font.c:163) → lv_font_get_glyph_dsc(lv_font.c:112)`。
- **铁证**：`A12=0x5c0f`（'小'）、`A7=0x67da`（'柚'）⇒ 正在对「小柚」取字形；
  第一个字就崩 ⇒ font 从开头就是死的。
- 机制：`get_glyph_dsc` 正好在 `lv_font_t` **偏移 0**；堆块 `free()` 后首字被写成空闲链表
  `next`（链尾=0）⇒ `get_glyph_dsc == NULL` ⇒ `callx0 0`。
- 谁释放的：`LvglBuiltInFont` 把 `lv_font_t` **按值**存在自己身上（`lvgl_font.h:15/20`，`font() { return &font_; }`），
  而 LVGL 样式只存裸 `const lv_font_t*`。`LvglDisplay::SetTextFont()`（`assets.cc:294` 调）
  把主题 `shared_ptr` 换成新字体后，函数末尾对旧 `shared_ptr` `reset()` ⇒ 旧对象析构。
  基类**只在 `SetTheme()` 期间**用局部 `previous_*_font` 保活，`SetTheme` 返回后立刻 `reset()`，
  之后再没人重绑的控件就悬垂。
- 谁没被重绑（必然存在，不只一处）：本板 `SetupHighTempWarningPopup()` 的 `high_temp_label_`
  ——它在 SetupUI（assets 之前）用 basic 字体创建、`HIDDEN` 但 **`layout_update_core` 照样递归进隐藏子树**。
- 处置（`yh_skin_display.cc`）：
  ① **字体退休池** `RetiredFontOwners()/RetiredFontPtrs()`，`SetTextFont` 覆写在调基类**之前**
  把 light/dark 的旧字体收进池、永不释放（一个 `lv_font_t` 才几十字节，大数组在 flash/PSRAM 不归它管）；
  ② **全树改绑** `RebindStaleFontsEverywhere()`：`lv_obj_tree_walk` 走
  `lv_screen_active + lv_layer_top/sys/bottom`，凡"当前实际渲染字体"落在退休池里的对象，
  一律改绑新字体。**不依赖任何句柄**，开机画面/高温弹窗/基类占位族/将来新控件全覆盖。
- 最后一道保险：`patches/lv-font-null-glyph-guard.patch` 给 `lv_font_get_glyph_dsc` 加
  `if(f->get_glyph_dsc == NULL) break;` + `line_height` 夹 `1..512`。失效字体退化成空心方框，**不重启**。
  `managed_components/` 在 `.gitignore` 里 ⇒ 改动不出现在 `git status`，`fullclean` 也不还原。

## 中文乱码（"有些字乱有些正常"）的双因

1. **拿图标字体渲染中文**：`fonts.large` 是 Material Symbols（U+E000–F8FF 私用区），
   品牌名用它会每个汉字落 `.notdef`，配 `CONFIG_LV_USE_FONT_PLACEHOLDER=y` **必现方框**。品牌名/副标题一律 `fonts.text`。
2. **字体档位 + 时序**：`SetupUI()` 在 `application.cc:169`，assets 的 common 字体到
   `CheckAssetsVersion()`（`application.cc:534` 附近）才加载；splash 用编译进固件的
   `font_noto_sans_basic_20_4`（890 码点 / 285 汉字，只覆盖 ASCII+Latin-1+`language.json` 静态串）建的。
   `柚 U+67DA` 在 basic **没有**、common 有 ⇒ 「小柚」出方框而气泡正常。
   处置：`ApplyFonts()` 末尾 `yh_skin::SetSplashFont(fonts.text)` 补一次，再由全树改绑兜底。
3. 已核对：common 档下我们的固定文案**零缺字**（含「小柚」「AI 陪伴助手」「我在呢」「警告：温度过高」、`…` U+2026）。
4. `IsTextFontInRam()` **不存在**（曾沿用错误前提），`assets.cc:287-329` 是无条件加载。

## 烧写没生效（"改了代码烧了固件现象没变"）

- 判据优先级：**看开机版本戳** `I (xxx) YhSkin: yh_skin build <date> <time>`（`YhSkinDisplay::SetupUI()` 首行）。
  看不到就是没烧进去，别再往下猜。
- 交叉验证：`grep -c "Failed to lock display after" build/xiaozhi.bin` 证明编译产物含新代码；
  再 addr2line 解旧镜像地址会得到跨模块荒谬符号 ⇒ 地址不属于该 elf ⇒ 镜像确实是旧的。
- 两条成因：① `build/flash_args` **书写顺序 assets 在 app 之前**（`0x800000` 在前），
  一行 `idf.py flash` 若 assets(4MB) 断链则 app 一字节没写；② `otadata` 没写而设备曾 OTA ⇒ 从 `ota_1` 起旧镜像。
- 一律用 `python flash.py --clean`，禁用 `idf.py flash` / `.bat`。

## 现场 ③：`ESP_ERR_NVS_INVALID_HANDLE(0x1107)` abort（触发唤醒词/device_config 即重启）

- **症状**：一触发唤醒词/语音/LLM 就 `ESP_ERROR_CHECK failed: esp_err_t 0x1107` 重启；
  日志先出「云端唤醒词已生效」（wakeword 命名空间 8 字符合法先写完），死在 interrupt 段
- **根因双因**：① 命名空间超限——`NVS_NS_NAME_MAX_SIZE=16` **含 null 终止符**，有效字符上限 **15**；
  `"interrupt_config"`/`"wake_word_config"` 均 16 字符 → `nvs_open` 失败；② 防御不对称——
  `Settings::Get*` 有 `nvs_handle_==0` 判 0，`Set*` 无 → `ESP_ERROR_CHECK(nvs_set_i32(0,…))` 直接 abort
- **定位**：ELF SHA 前缀比对（日志 `61980b2d1` == `sha256sum build/xiaozhi.elf | cut -c1-9`）
  → `addr2line -pf -e build/xiaozhi.elf 0x42029a9c` → `Settings::SetInt(settings.cc:63) ← Board::ApplyDeviceConfig`
- **修法**：命名空间全改 ≤15 字符（interrupt_cfg/wake_word_cfg）+ Settings 全写方法判 0；
  新增 NVS 命名空间时**先数字符**（上限 15，不是 16）
- **判据**：崩溃日志带 `0x1107` 且 backtrace 落在 settings.cc 的 Set* 家族 → 先量命名空间长度
