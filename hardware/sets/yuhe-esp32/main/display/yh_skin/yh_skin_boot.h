#pragma once

// 开机画面（首帧接管）
//
// 目标：上电后屏幕亮起的第一帧就是品牌画面，绝不出现原生 yuhe 状态栏 /
// 机器人 AI logo / UserAgent 版本串。
//
// 时间线：
//   SetupUI()        → BuildSplash()：背景图 + 品牌名 + 副标题 + 呼吸点 + 版本
//   WiFi 连接中      → SetSplashStatus("正在连接网络…")
//   配网 / 激活      → yh_skin_cards 的卡片盖在 splash 之上（不销毁 splash）
//   首次进入待机     → DismissSplash()（300ms 淡出），交还主界面
//
// 约束：DisplayLockGuard 为递归锁，本模块函数**可重入**（允许在已持锁的
// 上下文里调用）。但若从 esp_timer / 协议任务等非 LVGL 上下文进来，
// 调用方仍须自行加锁 —— 内层刻意不再重复加锁，避免掩盖无锁窗口。

#include <lvgl.h>

#include "yh_skin_types.h"

namespace yh_skin {

struct SplashInfo {
    const char* brand = "琳琳";
    const char* subtitle = "";
    const char* version = "";  // 右下角小字
    // 开机底图：优先用户壁纸（WallpaperManager 已生效的那张）。
    // nullptr = 无壁纸，回落编译期品牌底纹 yh_skin_bg。缓冲归 WallpaperManager
    // 所有，这里只读；固件重启后壁纸是从服务器重拉的（NVS 只存 url/md5 元数据），
    // 所以"开机即用户壁纸"只在本次运行已应用过壁纸后成立（含重建 splash 场景）。
    const void* background = nullptr;
};

void BuildSplash(lv_obj_t* parent, const YhSkinProfile& profile, const YhSkinFonts& fonts,
                 const SplashInfo& info);

// 开机画面是 assets 生效前建的，用的是编译进固件的 basic 字体（890 字）。
// assets 的 common（5258 字）加载完之后必须调一次本函数重绑，否则品牌名/
// 副标题里不在 basic 的字（例如「柚」）会一直是方框。
// 调用方必须已持有 LVGL 锁；splash 不存在时安全空转。
void SetSplashFont(const lv_font_t* text_font);

// 进度文案（「正在连接网络…」）；nullptr 或空串 = 清除
void SetSplashStatus(const char* text);

// 进度条 0..100；<0 隐藏
void SetSplashProgress(int percent);

void DismissSplash();
bool SplashVisible();

// splash 可见期间换底图（壁纸到达/清除时同步开机画面）。
// 与 BuildSplash 底图段同一套规则；调用方必须已持 LVGL 锁；
// splash 不存在时静默空转。nullptr = 回落品牌底纹。
void UpdateSplashBackground(const void* background);

// 显示层据此判断：splash 可见时是否吞掉普通状态文案，避免「待机中」盖住品牌画面
bool SplashAbsorbsStatus(const char* status);

}  // namespace yh_skin
