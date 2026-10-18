#ifndef WALLPAPER_MANAGER_H
#define WALLPAPER_MANAGER_H

#include <cstddef>
#include <functional>
#include <string>

// 壁纸槽位：
//   idle = 待机壁纸（主界面背景，原有行为）
//   boot = 开机壁纸（splash 画面底图，新增）。两种壁纸独立下发/独立 NVS/
//          独立 PSRAM 缓冲，互不干扰；同一张图可以同时下发到两个槽。
enum class WallpaperKind {
    Idle,
    Boot,
};

// 用户壁纸下发请求。
//
// 两个来源共用本结构（详见需求 FR-2.11 / FR-2.16）：
//   1. WS/MQTT 文本帧 {"type":"wallpaper","action":"set",...}（from_config=false，需要回执）
//   2. device_config.payload.wallpaper / boot_wallpaper（from_config=true，不回执）
struct WallpaperRequest {
    std::string version;   // 服务端版本号（字符串，幂等键）
    std::string url;       // HTTP 下载地址（.bin，240x240 RGB565 裸数据）
    std::string md5;       // 32 位十六进制 MD5
    int size = 0;          // 期望字节数；0 表示未携带（按 240*240*2 校验实际长度）
    int width = 0;         // 0 表示未携带（按 240 处理）
    int height = 0;
    std::string format;    // "rgb565"（空字符串按 rgb565 处理）
    bool from_config = false;
    WallpaperKind kind = WallpaperKind::Idle;  // 默认待机壁纸（向后兼容）
};

// 结果回调：ok=true 表示已应用（含幂等命中）；false 时 reason 见 kReason* 常量。
using WallpaperResultCallback = std::function<void(bool ok, const std::string& reason)>;

// 壁纸管理器（单例）。
//
// 职责（FR-2.11~2.23 / NFR-2~6/9）：
//   - 校验（format / 尺寸 / 长度）→ 后台任务下载 → MD5 校验 → PSRAM 载入 → 应用 → 回执；
//   - 图与 lv_img_dsc_t 的生命周期由本类持有，Display 只持裸指针（FR-2.22）；
//   - NVS 持久化（idle 槽 namespace "wallpaper"，boot 槽 "wallpaper_boot"，
//     各存 version/url/md5），重启后重拉（FR-2.16）；
//   - 下载全程在独立任务中执行，不占用音频/协议任务（NFR-2）。
class WallpaperManager {
public:
    static WallpaperManager& GetInstance();

    // 下发/更新壁纸。校验失败会立即（调用者任务上下文）回调；下载与校验在后台任务完成。
    // 幂等：version 与已应用版本相同直接回调 ok，不重复下载、不重复写 NVS（NFR-5）。
    void HandleSet(const WallpaperRequest& request, WallpaperResultCallback on_result);

    // 清除用户壁纸，恢复 theme.background_image / bg_good 背景（FR-2.15）。
    void HandleClear(WallpaperResultCallback on_result);

    // 清除指定槽位的壁纸（boot 槽独立清除用）。
    void HandleClear(WallpaperKind kind, WallpaperResultCallback on_result);

    // 网络就绪后调用：NVS 里有 url/version 且当前未应用同版本时后台重拉。
    // 失败静默（屏幕保持当前背景，不影响启动）；重复调用幂等。
    void RestoreFromNvsAsync();

    // 当前已应用版本（空 = 无用户壁纸），调试/日志用。默认 idle 槽。
    std::string applied_version(WallpaperKind kind = WallpaperKind::Idle);

private:
    WallpaperManager();
    ~WallpaperManager();
    WallpaperManager(const WallpaperManager&) = delete;
    WallpaperManager& operator=(const WallpaperManager&) = delete;

    struct Impl;
    Impl* impl_ = nullptr;
};

#endif  // WALLPAPER_MANAGER_H
