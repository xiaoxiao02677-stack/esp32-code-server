#pragma once

// 系统态卡片（全屏浮层，盖在主界面/开机画面之上）
//
// 为什么需要：原生 yuhe 把这些信息塞进状态栏/聊天区（14px 字），240 圆屏上
// 配网 SSID、6 位激活码、升级百分比都读不清。卡片用大字 + 居中 + 品牌配色重做。
//
// 触发点（由 YhSkinDisplay 路由，不新增 Application 逻辑）：
//   ShowWifiCard        ← 配网模式（swifi_board 的 ShowNotification 文案）
//   ShowActivationCard  ← SetStatus(ACTIVATION) + SetChatMessage("system", code)
//   ShowProgressCard    ← 升级中（状态文案 + 百分比）
//   ShowErrorCard       ← Alert(错误) 类
//
// 约束：所有函数必须在 LVGL 线程 / 已持有显示锁的上下文调用；
//       重复调用只更新内容（幂等），不会堆积 LVGL 对象。

#include <lvgl.h>

#include <string>

#include "yh_skin_types.h"

namespace yh_skin {

struct WifiCardInfo {
    std::string ssid;
    std::string password;
    std::string hint;
};

void ShowWifiCard(lv_obj_t* parent, const YhSkinProfile& profile, const YhSkinFonts& fonts,
                  const WifiCardInfo& info);

void ShowActivationCard(lv_obj_t* parent, const YhSkinProfile& profile, const YhSkinFonts& fonts,
                        const std::string& code, const std::string& message);

void ShowProgressCard(lv_obj_t* parent, const YhSkinProfile& profile, const YhSkinFonts& fonts,
                      const char* title, const char* detail, int percent);

void ShowErrorCard(lv_obj_t* parent, const YhSkinProfile& profile, const YhSkinFonts& fonts,
                   const char* title, const char* detail);

void HideCards();
// 立即同步销毁（不走淡出）。给「切主题时必须马上消失」这类场景用。
// ★ 只能在持锁、且不在事件回调 / 动画回调栈内的上下文调用：
//   同步 lv_obj_del 会在当前栈里递归析构整棵树，若已经身处
//   lv_anim 的 completed_cb 或 lv 事件回调里，就会重演本次开机崩溃。
//   那种上下文请改用 HideCards()（走 lv_obj_delete_async）。
void DropCardsImmediately();
bool CardVisible();

}  // namespace yh_skin
