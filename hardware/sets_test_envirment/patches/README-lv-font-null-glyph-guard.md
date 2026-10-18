# lv-font-null-glyph-guard.patch

对 vendored LVGL（`managed_components/lvgl__lvgl/src/font/lv_font.c`）的两处最小加固。
不是修 bug 的"主方案"，是**最后一道保险**：主方案在 `yh_skin_display.cc`（字体退休池 + 全树改绑）。

## 为什么需要它

2026-10-17 17:36 那版固件在 `Assets: Refreshing display theme...` 之后
`Core 1 panic'ed (InstrFetchProhibited)`，`EXCVADDR = 0x0`、`PC = 0x0`，`rst:0xc` 无限重启。

用 `ELF file SHA256: e0de67621` 校验过 `build/yuhe.elf` 一致后 addr2line：

```
PC      : 0x00000000          ← 跳到地址 0 执行
A12     : 0x00005c0f          ← '小' U+5C0F（kerning 里的 letter_next / letter）
A7      : 0x000067da          ← '柚' U+67DA
A8      : 0x820d3c63          ← lv_font.c:112  f->get_glyph_dsc(...) 的返回地址
A0      : 0x820d3d50          ← lv_font.c:163  lv_font_get_glyph_width
0x420c0a15  lvgl_port_task            esp_lvgl_port.c:242
0x420cee..  lv_display_refr_timer     lv_refr.c:402
0x420cb2c3  lv_obj_update_layout      lv_obj_pos.c:395
0x420cb273  layout_update_core        lv_obj_pos.c:1537  (递归子节点)
0x420cb242  layout_update_core        lv_obj_pos.c:1542  (lv_obj_refr_size)
```

即：布局一个内容宽度自适应的 label（字符串「小柚」）→ 取字形宽度 →
`f->get_glyph_dsc(...)` 这条 `callx` 跳到 0。

`get_glyph_dsc` 正好是 `lv_font_t` 的**偏移 0**。堆块被 `free()` 之后首字会被写成
空闲链表 `next` 指针，空闲块链尾就是 0 —— 于是"字体对象已释放"干净地表现为
`get_glyph_dsc == NULL`。

## 改了什么

| 位置 | 改动 | 作用 |
| --- | --- | --- |
| `lv_font_get_glyph_dsc()` 的 `while(f)` 循环 | 调回调前 `if(f->get_glyph_dsc == NULL) break;` | 失效字体退化成"查不到字形"，不再 `callx 0` |
| 同函数末尾的占位分支 | `line_height` 读进局部变量并夹到 `1..512` | `font_p` 已失效时 `line_height` 是垃圾值，避免 `box_h = 0` 让布局算出负高度/死循环 |

失败时的可见行为：`CONFIG_LV_USE_FONT_PLACEHOLDER=y` ⇒ 该字画成一个 1px 空心小方框，
**不会重启**。看到方框应该去查"谁没重绑字体"，而不是查硬件。

## 应用 / 回滚

```bash
cd hardware/sets/yuhe-esp32
git apply --check --reverse ../patches/lv-font-null-glyph-guard.patch   # 已应用时应通过
git apply ../patches/lv-font-null-glyph-guard.patch                    # 未应用时应用
git apply -R ../patches/lv-font-null-glyph-guard.patch                 # 回滚
```

注意：`managed_components/` 在 `.gitignore` 里，所以这两处改动**不会出现在 `git status`**，
`idf.py fullclean` 也不会还原它们；只有在组件管理器重新解压 LVGL 时才会丢失，届时重打本补丁即可。

同类加固另见：`lv-event-loop-guard.patch`（`lv_event_mark_deleted` 的有界遍历）。
