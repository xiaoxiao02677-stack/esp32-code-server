# ════════════════════════════════════════════════════════════════════════
# pet_ui 移植契约（port from hardware/sets/theme/像素宠物 → main/display/pet_skin/）
# ════════════════════════════════════════════════════════════════════════

源工程（独立 ESP-IDF 项目，只读，勿改）：`hardware/sets/theme/像素宠物/`
- `main/src/pet_canvas.c`   352 行 —— 像素宠物自绘（核心，直接移植）
- `main/src/boot_anim.c`    152 行 —— 开机动画进度推进（直接移植）
- `main/src/ui_screens.c`   229 行 —— 顶栏/气泡/音量条/2x2 菜单（部分移植）
- `main/include/app_config.h 74 行 —— 布局常量/枚举（并入 pet_skin_types.h）
- `main/include/pet_ui.h`   81 行 —— 模块接口（分解并入各头）

## 移植规则（三方共同遵守）
1. **不移植** keys.c / display.c / audio.c / main.c —— 主固件已有按键状态机
   （board.cc 的 BOOT 三事件）、LCD 初始化（各板 yh_set_*.cc）、音频链路
   （Application 层）。宠物 UI 侧只消费事件，不自己采集。
2. 源码引用方式：`#include "display/pet_skin/pet_skin_types.h"`，C 文件放
   `main/display/pet_skin/`，CMake 挂 `#if CONFIG_YH_UI_THEME_PIXELPET` 条件
   （见 CMakeLists 契约段）。
3. C/C++ 混编：pet_skin 内 C 文件用 CMake `target_compile_options` 或文件名
   命名区分（保持现有工程风格——现有工程 yh_skin_assets.c 也是 C 文件直接
   进主组件源列表，无特殊处理）。
4. 音频能量（驱动嘴形/耳朵）：`Application::instance()` → `audio_energy`
   或按 pet 原工程的“模拟能量”简化——首版用 `esp_timer` 正弦/随机模拟
   即可，真实能量接 Application 输出级监听后续迭代。
5. LVGL 版本：主固件锁 LVGL 9（idf_component.yml `lvgl ^9`），pet 源码按
   LVGL9 API 编写（canvas 用 LV_COLOR_FORMAT_RGB565），无需版本宏。
6. 中文字体：pet 原工程依赖 CONFIG_LV_FONT_SIMSUN_16_CJK；主固件字体走
   assets OTA（basic/common 档位），pet 模块字体一律从 YhSkinFonts
   （基类 CurrentFonts()）取，取不到就继承父对象——**严禁自行 lv_font
   新建/释放**（2026-10-08 悬垂崩溃根因）。
7. 几何适配：不写死 240。所有布局常量经 YhSkinProfile::scaled() 换算；
   圆屏（round=true）内容按内切圆收边，宠物中心可适当上移避开圆角。

## 性能架构（2026-10-19 直写 buffer 重写，真机实测后定稿）

首版经 LVGL 绘制任务管线（lv_draw_rect/line 逐格挂任务 → 软件光栅化 →
PSRAM canvas → 全屏 blit → 全屏 SPI flush）在真机上"卡成 PPT"：
- pixel_ellipse 逐 8px 格挂 lv_draw_rect，一帧 ~2700 个绘制任务；
- 每帧无条件全屏 fill_bg + lv_obj_invalidate（全屏失效）；
- 说话态 30fps 持续重绘。

现 pet_canvas.c 为**直写 buffer 版**（视觉零变化）：
1. **零绘制任务**：px_span / fill_disc / fill_capsule / tri 直接写
   RGB565 buffer（stride 经 lv_draw_buf_width_to_stride 官方换算，
   位序 lv_color_to_u16，与 LVGL 内部编码一致）。
2. **像素椭圆行跨度解析**：凸形每行算出连续 [xs,xe] 一次写入，
   替代逐格判定（同判据，结果完全一致，快 10 倍+）。
3. **粗弧线 = 圆盘笔触**：采样点画实心圆盘（半径 = width/2，
   步长 = r/2，重叠 ≥50% 无缝），视觉 = 原版圆头粗线。
4. **完成态局部失效**：只清 + 只失效宠物包围盒 pet_bbox()（耳朵顶
   到脸底 + grid 余量），blit/flush 量降 ~75%；动画期仍全屏
   （涟漪/bg 渐变是全屏元素）。动画→完成态过渡帧强制全屏一次
   （擦包围盒外残迹）。
5. **说话态 15fps 隔帧**（pet_skin_display.cc frame_div_）：3Hz 嘴部
   动画足够平滑，给音频任务让出一半渲染预算。

后续若仍需提速：宠物层可改 ARGB8888 小画布浮于壁纸上（全屏层只画
背景色），或说话态动画降 10fps。改前先量：lv_timer 回调里
esp_timer_get_time 差值打点。
