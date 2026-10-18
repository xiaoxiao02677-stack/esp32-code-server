#include "wallpaper_manager.h"

#include "board.h"
#include "display.h"
#include "settings.h"

#include <esp_heap_caps.h>
#include <esp_log.h>
#include <esp_rom_md5.h>

#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <freertos/task.h>

#include <lvgl.h>

#include <cctype>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <string>
#include <utility>

#define TAG "Wallpaper"

// Emote 风格构建（esp-vocat / esp-sensairshuttle）的 Display 不声明
// SetWallpaper/ClearWallpaper（display.h 在无 lvgl.h 的分支里不提供），
// 这里用同一宏做条件闸：不带壁纸渲染能力的板型直接放弃壁纸，屏幕保持默认。
#if defined(CONFIG_USE_EMOTE_MESSAGE_STYLE)
#define WALLPAPER_HAS_LVGL_DISPLAY 0
#else
#define WALLPAPER_HAS_LVGL_DISPLAY 1
#endif

namespace {

// 圆屏固定 240x240 RGB565（FR-2.11 / FR-2.23）
constexpr int kWidth = 240;
constexpr int kHeight = 240;
constexpr size_t kImageBytes = static_cast<size_t>(kWidth) * kHeight * 2;  // 115200

// 下载任务：必须 ≥8KB（HTTP + DNS 解析 + 日志），12KB 留余量
constexpr uint32_t kTaskStackBytes = 12 * 1024;
constexpr UBaseType_t kTaskPriority = 4;
constexpr int kHttpTimeoutMs = 20000;

// 回执失败原因（服务端按原值落库，见 yh/yuhe-server/core/utils/wallpaper_ack.py）
constexpr char kReasonBadFormat[] = "bad_format";
constexpr char kReasonSize[] = "size_mismatch";
constexpr char kReasonMd5[] = "md5_mismatch";
constexpr char kReasonDownload[] = "download_failed";
constexpr char kReasonNoMem[] = "no_mem";
constexpr char kReasonNoDisplay[] = "no_display";
// 显示层拒收（UI 未就绪 / 拿不到 LVGL 锁 / lv_image_set_src 被 LVGL 拒）。
// 以前这种情况被吞成"成功"，现在如实回 fail，服务端才会重试。
constexpr char kReasonRender[] = "render_failed";
// 单槽 pending 被后到的请求顶掉：前一条根本没执行，必须给它的调用方一个明确结论，
// 否则那条 command_id 的结果回执永远不发（服务端只能等超时）。
constexpr char kReasonSuperseded[] = "superseded";

bool EqualsIgnoreCase(const std::string& value, const char* expected) {
    const size_t expected_len = strlen(expected);
    if (value.size() != expected_len) {
        return false;
    }
    for (size_t i = 0; i < expected_len; ++i) {
        if (std::tolower(static_cast<unsigned char>(value[i])) != expected[i]) {
            return false;
        }
    }
    return true;
}

int HexDigit(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

// "9f2c...."（32 hex）→ 16 字节；格式非法返回 false
bool ParseMd5(const std::string& hex, uint8_t out[ESP_ROM_MD5_DIGEST_LEN]) {
    if (hex.size() != ESP_ROM_MD5_DIGEST_LEN * 2) {
        return false;
    }
    for (size_t i = 0; i < ESP_ROM_MD5_DIGEST_LEN; ++i) {
        const int hi = HexDigit(hex[i * 2]);
        const int lo = HexDigit(hex[i * 2 + 1]);
        if (hi < 0 || lo < 0) {
            return false;
        }
        out[i] = static_cast<uint8_t>((hi << 4) | lo);
    }
    return true;
}

void Md5ToHex(const uint8_t digest[ESP_ROM_MD5_DIGEST_LEN], char out[ESP_ROM_MD5_DIGEST_LEN * 2 + 1]) {
    static const char kHex[] = "0123456789abcdef";
    for (size_t i = 0; i < ESP_ROM_MD5_DIGEST_LEN; ++i) {
        out[i * 2] = kHex[digest[i] >> 4];
        out[i * 2 + 1] = kHex[digest[i] & 0x0F];
    }
    out[ESP_ROM_MD5_DIGEST_LEN * 2] = '\0';
}

}  // namespace

// 内部状态与后台工作线程。图片缓冲与 lv_img_dsc_t 的所有权都在这里（FR-2.22）。
//
// 双槽结构：idle（待机壁纸）与 boot（开机壁纸）各自独立持有
// applied_version/buffer/dsc/NVS 恢复记账，互不覆盖。pending 队列同样按槽
// 独立（单槽会让 boot 下发顶掉 idle 的回执，反之亦然）。
struct WallpaperSlot {
    // 本槽种类（idle/boot），由 Impl 构造时写入。分流必须信它而不是 pending_request.kind：
    // clear 排队时 pending_request 是空请求（kind 恒 Idle），boot 槽的 clear 若按
    // request.kind 分流会被错送进 idle 的显示接口与 NVS namespace。
    WallpaperKind kind = WallpaperKind::Idle;

    // 待处理请求（单槽，后到覆盖先到；两个壁纸槽各自一条）
    bool pending = false;
    bool pending_clear = false;
    WallpaperRequest pending_request;
    WallpaperResultCallback pending_callback;

    // 已应用状态
    std::string applied_version;
    std::string applied_url;
    std::string applied_md5;
    uint8_t* buffer = nullptr;     // PSRAM，kImageBytes
    lv_img_dsc_t dsc{};
    // dsc_valid 只表示"buffer/dsc 指向一张可用的图"，**不代表屏上正显示它**：
    // rebind 若被 lv_image_set_src 拒绝，bg_image_ 的 src 会退回兜底图，
    // 而 dsc_valid 仍为 true。看到这个组合不要顺手去清 dsc_valid/applied_version。
    bool dsc_valid = false;

    // 本次开机已尝试过的 NVS 恢复版本（避免每次重连都重拉）
    std::string restore_version;
};

struct WallpaperManager::Impl {
    std::mutex mutex;              // 保护下方全部状态
    SemaphoreHandle_t wake = nullptr;
    bool worker_started = false;

    WallpaperSlot slots[2];        // [Idle] [Boot]，下标见 SlotIndexOf()

    Impl() {
        // 槽位种类在构造期写死：boot 槽的分流依据（见 WallpaperSlot::kind 注释）
        slots[SlotIndexOf(WallpaperKind::Boot)].kind = WallpaperKind::Boot;
    }

    // 显式命令命中幂等时的三种结局（调用方据此决定回执，不能一概回 ok）
    enum class RebindResult {
        kOk,          // 已重新绑上并触发重绘
        kNoState,     // 已经没有图可绑 → 调用方回落成重新下载
        kRenderFail,  // 有图但显示层没接 → 回 fail:render，下次命令再试
    };

    static int SlotIndexOf(WallpaperKind kind) { return kind == WallpaperKind::Boot ? 1 : 0; }
    static const char* KindName(WallpaperKind kind) { return kind == WallpaperKind::Boot ? "boot" : "idle"; }

    static void TaskEntry(void* arg) { static_cast<Impl*>(arg)->Run(); }

    bool EnsureWorker();
    void Run();
    void ProcessSet(WallpaperSlot& slot, const WallpaperRequest& request,
                    const WallpaperResultCallback& callback);
    void ProcessClear(WallpaperSlot& slot, WallpaperKind kind, const WallpaperResultCallback& callback);
    bool ApplyToDisplay(WallpaperSlot& slot, uint8_t* new_buffer, const WallpaperRequest& request);
    // 把当前已缓存的图重新绑到显示层（显式命令遇幂等命中时用，不重新下载）
    RebindResult RebindCurrent(WallpaperSlot& slot, const std::string& expected_version);
};

bool WallpaperManager::Impl::EnsureWorker() {
    {
        std::lock_guard<std::mutex> lock(mutex);
        if (worker_started) {
            return true;
        }
        worker_started = true;
    }
    if (wake == nullptr) {
        wake = xSemaphoreCreateBinary();
        if (wake == nullptr) {
            std::lock_guard<std::mutex> lock(mutex);
            worker_started = false;
            return false;
        }
    }
    if (xTaskCreate(TaskEntry, "wallpaper", kTaskStackBytes, this, kTaskPriority, nullptr) !=
        pdPASS) {
        ESP_LOGE(TAG, "Failed to create wallpaper task");
        std::lock_guard<std::mutex> lock(mutex);
        worker_started = false;
        return false;
    }
    return true;
}

void WallpaperManager::Impl::Run() {
    for (;;) {
        xSemaphoreTake(wake, portMAX_DELAY);
        for (;;) {
            WallpaperSlot* slot = nullptr;
            bool clear = false;
            WallpaperRequest request;
            WallpaperResultCallback callback;
            {
                std::lock_guard<std::mutex> lock(mutex);
                // 轮询两个槽：谁有待处理就处理谁（同一轮两条都挂起时按 idle→boot 顺序）
                for (auto& candidate : slots) {
                    if (candidate.pending) {
                        slot = &candidate;
                        break;
                    }
                }
                if (slot == nullptr) {
                    break;
                }
                clear = slot->pending_clear;
                request = slot->pending_request;
                callback = std::move(slot->pending_callback);
                slot->pending = false;
                slot->pending_clear = false;
                slot->pending_request = WallpaperRequest{};
                slot->pending_callback = nullptr;
            }
            if (clear) {
                // clear 排队时 pending_request 是空请求（kind 恒 Idle），
                // 分流必须信槽位自身的 kind
                ProcessClear(*slot, slot->kind, callback);
            } else {
                ProcessSet(*slot, request, callback);
            }
        }
    }
}

void WallpaperManager::Impl::ProcessSet(WallpaperSlot& slot,
                                        const WallpaperRequest& request,
                                        const WallpaperResultCallback& callback) {
    auto finish = [&callback](bool ok, const char* reason) {
        if (callback) {
            callback(ok, reason);
        }
    };
    const char* kind_name = KindName(request.kind);

    // NFR-5：排队期间前一个请求可能已经应用了同一版本
    bool duplicate = false;
    {
        std::lock_guard<std::mutex> lock(mutex);
        duplicate = slot.dsc_valid && !request.version.empty() &&
                    request.version == slot.applied_version;
    }
    if (duplicate) {
        ESP_LOGI(TAG, "wallpaper: skip kind=%s version=%s (already applied)", kind_name,
                 request.version.c_str());
        finish(true, "");
        return;
    }

    // 校验链（不做任何屏幕改动，FR-2.14）
    if (!request.format.empty() && !EqualsIgnoreCase(request.format, "rgb565")) {
        ESP_LOGW(TAG, "wallpaper: fail kind=%s version=%s reason=%s format=%s", kind_name,
                 request.version.c_str(), kReasonBadFormat, request.format.c_str());
        finish(false, kReasonBadFormat);
        return;
    }
    if ((request.width != 0 && request.width != kWidth) ||
        (request.height != 0 && request.height != kHeight) ||
        (request.size != 0 && request.size != static_cast<int>(kImageBytes))) {
        ESP_LOGW(TAG, "wallpaper: fail kind=%s version=%s reason=%s size=%d %dx%d", kind_name,
                 request.version.c_str(), kReasonSize, request.size, request.width, request.height);
        finish(false, kReasonSize);
        return;
    }
    uint8_t expected_md5[ESP_ROM_MD5_DIGEST_LEN];
    if (!ParseMd5(request.md5, expected_md5)) {
        ESP_LOGW(TAG, "wallpaper: fail kind=%s version=%s reason=%s md5=%s", kind_name,
                 request.version.c_str(), kReasonBadFormat, request.md5.c_str());
        finish(false, kReasonBadFormat);
        return;
    }

#if !WALLPAPER_HAS_LVGL_DISPLAY
    // ★ 止损点放在校验链**之后**、下载之前。
    //   这个构建（emote 风格）没有壁纸渲染能力，原顺序是
    //   「判重 → 校验 → 下载整块 115KB → ApplyToDisplay 才发现 no_display」，
    //   每次下发都白下 115KB。既然注定显示不了，一个字节都不该下。
    //   放在校验链之后是为了让 format/size/md5 错误继续报它们自己的 reason
    //   （放到最前面会用 no_display 盖掉 bad_format，反而更难查）。
    ESP_LOGW(TAG, "wallpaper: display unsupported, skip download version=%s",
             request.version.c_str());
    finish(false, kReasonNoDisplay);
    return;
#endif

    uint8_t* buffer = static_cast<uint8_t*>(
        heap_caps_malloc(kImageBytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    if (buffer == nullptr) {
        ESP_LOGE(TAG, "wallpaper: fail version=%s reason=%s (psram free=%u)",
                 request.version.c_str(), kReasonNoMem,
                 static_cast<unsigned>(heap_caps_get_free_size(MALLOC_CAP_SPIRAM)));
        finish(false, kReasonNoMem);
        return;
    }

    ESP_LOGI(TAG, "wallpaper: download start kind=%s version=%s url=%s bytes=%u", kind_name,
             request.version.c_str(), request.url.c_str(), static_cast<unsigned>(kImageBytes));

    const char* fail_reason = nullptr;
    size_t received = 0;

    auto network = Board::GetInstance().GetNetwork();
    if (network == nullptr) {
        ESP_LOGW(TAG, "wallpaper: network is not ready");
        fail_reason = kReasonDownload;
    } else {
        auto http = network->CreateHttp(0);
        if (http == nullptr) {
            fail_reason = kReasonDownload;
        } else {
            http->SetTimeout(kHttpTimeoutMs);
            http->SetKeepAlive(false);
            auto opened = http->Open("GET", request.url);
            if (!opened) {
                ESP_LOGW(TAG, "wallpaper: open failed: %s", opened.error().ToString().c_str());
                fail_reason = kReasonDownload;
            } else {
                auto status_code = http->GetStatusCode();
                if (!status_code) {
                    fail_reason = kReasonDownload;
                } else if (*status_code != 200) {
                    ESP_LOGW(TAG, "wallpaper: http status %d", *status_code);
                    fail_reason = kReasonDownload;
                } else if (http->GetBodyLength() > kImageBytes) {
                    ESP_LOGW(TAG, "wallpaper: body too large: %u", static_cast<unsigned>(http->GetBodyLength()));
                    fail_reason = kReasonSize;
                } else {
                    // 边下边写 PSRAM：HttpClient 内部只缓存 ~8KB，峰值受控（NFR-3）
                    for (;;) {
                        const size_t room = kImageBytes - received;
                        if (room == 0) {
                            char extra[32];
                            auto extra_read = http->Read(extra, sizeof(extra));
                            if (extra_read && *extra_read > 0) {
                                ESP_LOGW(TAG, "wallpaper: body exceeds %u bytes",
                                         static_cast<unsigned>(kImageBytes));
                                fail_reason = kReasonSize;
                            }
                            break;
                        }
                        auto read = http->Read(reinterpret_cast<char*>(buffer) + received, room);
                        if (!read) {
                            ESP_LOGW(TAG, "wallpaper: read failed: %s",
                                     read.error().ToString().c_str());
                            fail_reason = kReasonDownload;
                            break;
                        }
                        if (*read == 0) {
                            break;
                        }
                        received += static_cast<size_t>(*read);
                    }
                }
            }
            http->Close();
        }
    }

    if (fail_reason != nullptr) {
        heap_caps_free(buffer);
        ESP_LOGW(TAG, "wallpaper: fail version=%s reason=%s", request.version.c_str(), fail_reason);
        finish(false, fail_reason);
        return;
    }
    if (received != kImageBytes) {
        ESP_LOGW(TAG, "wallpaper: fail version=%s reason=%s received=%u", request.version.c_str(),
                 kReasonSize, static_cast<unsigned>(received));
        heap_caps_free(buffer);
        finish(false, kReasonSize);
        return;
    }

    // MD5 校验（NFR-6：不符即放弃，屏幕保持原状）
    uint8_t actual_md5[ESP_ROM_MD5_DIGEST_LEN];
    md5_context_t md5_context;
    esp_rom_md5_init(&md5_context);
    esp_rom_md5_update(&md5_context, buffer, static_cast<uint32_t>(received));
    esp_rom_md5_final(actual_md5, &md5_context);
    char actual_hex[ESP_ROM_MD5_DIGEST_LEN * 2 + 1];
    Md5ToHex(actual_md5, actual_hex);
    ESP_LOGI(TAG, "wallpaper: verify kind=%s version=%s md5=%s expect=%s", kind_name,
             request.version.c_str(), actual_hex, request.md5.c_str());
    if (memcmp(actual_md5, expected_md5, ESP_ROM_MD5_DIGEST_LEN) != 0) {
        heap_caps_free(buffer);
        ESP_LOGW(TAG, "wallpaper: fail kind=%s version=%s reason=%s", kind_name,
                 request.version.c_str(), kReasonMd5);
        finish(false, kReasonMd5);
        return;
    }

    ESP_LOGI(TAG, "wallpaper: apply kind=%s version=%s source=%s", kind_name,
             request.version.c_str(), request.from_config ? "config" : "ws");
    if (!ApplyToDisplay(slot, buffer, request)) {
        ESP_LOGW(TAG, "wallpaper: fail kind=%s version=%s reason=%s", kind_name,
                 request.version.c_str(), kReasonNoDisplay);
        finish(false, kReasonNoDisplay);
        return;
    }

    {
        // boot 槽独立 NVS namespace，与 idle 槽互不覆盖
        Settings settings(request.kind == WallpaperKind::Boot ? "wallpaper_boot" : "wallpaper",
                          true);
        settings.SetString("version", request.version);
        settings.SetString("url", request.url);
        settings.SetString("md5", request.md5);
    }
    finish(true, "");
}

bool WallpaperManager::Impl::ApplyToDisplay(WallpaperSlot& slot, uint8_t* new_buffer,
                                            const WallpaperRequest& request) {
#if !WALLPAPER_HAS_LVGL_DISPLAY
    // Emote 风格构建没有壁纸渲染能力：释放缓冲并回 fail:no_display，屏幕不动
    ESP_LOGW(TAG, "wallpaper: display unsupported, drop version=%s",
             request.version.c_str());
    heap_caps_free(new_buffer);
    return false;
#else
    Display* display = Board::GetInstance().GetDisplay();
    if (display == nullptr) {
        ESP_LOGE(TAG, "wallpaper: no display, drop version=%s", request.version.c_str());
        heap_caps_free(new_buffer);
        return false;
    }
    // 按槽位分流显示接口：idle → 主界面背景；boot → splash 底图。
    // 两个接口共用同一套"先解绑旧引用、失败即放弃"的安全协议。
    const bool is_boot = (request.kind == WallpaperKind::Boot);
    auto unbind_old = [display, is_boot]() {
        return is_boot ? display->ClearBootWallpaper() : display->ClearWallpaper();
    };
    auto bind_new = [display, is_boot](const lv_img_dsc_t* image) {
        return is_boot ? display->SetBootWallpaper(image) : display->SetWallpaper(image);
    };

    lv_img_dsc_t new_dsc{};
    new_dsc.header.magic = LV_IMAGE_HEADER_MAGIC;
    new_dsc.header.cf = LV_COLOR_FORMAT_RGB565;
    new_dsc.header.w = kWidth;
    new_dsc.header.h = kHeight;
    new_dsc.header.stride = kWidth * 2;
    new_dsc.data_size = static_cast<uint32_t>(kImageBytes);
    new_dsc.data = new_buffer;

    // 持显示锁完成"解除旧引用 -> 换新图"的原子切换：
    // 1) Clear*Wallpaper 先让 LVGL 不再引用旧缓冲（FR-2.22，防悬空）；
    // 2) 释放旧缓冲；
    // 3) Set*Wallpaper 绑定新图。
    // lvgl_port_lock 是递归锁，Display 内部再次加锁是安全的。
    DisplayLockGuard lock(display);
    if (!unbind_old()) {
        // 没能让 LVGL 松开旧图。此时若继续换缓冲并释放旧 buffer，渲染线程可能
        // 正拿着一块已释放的 PSRAM 画 —— 直接放弃这次应用，回 fail 让下次重试。
        heap_caps_free(new_buffer);
        ESP_LOGW(TAG, "wallpaper: fail kind=%s version=%s reason=%s (cannot unbind old image)",
                 KindName(request.kind), request.version.c_str(), kReasonRender);
        return false;
    }

    lv_img_dsc_t old_dsc{};
    uint8_t* old_buffer = nullptr;
    {
        std::lock_guard<std::mutex> guard(mutex);
        old_buffer = slot.buffer;
        old_dsc = slot.dsc;
        slot.buffer = new_buffer;
        slot.dsc = new_dsc;
    }
    if (!bind_new(&slot.dsc)) {
        // ★ 显示层没接（拿不到锁 / bg_image_ 未建 / lv_image_set_src 被拒）。
        //   回滚到"换图之前"的完整状态：屏幕继续显示旧壁纸，applied_version 不动
        //   （它描述的正是屏幕上那张），新缓冲释放，dsc_valid 跟随旧图是否存在。
        //   —— 关键是绝不把这次失败记成"已应用"：以前无条件 return true，
        //   于是这次没画上去被记成成功，之后每次同版本下发都被 already applied
        //   挡回去，再也没有重试机会。
        heap_caps_free(new_buffer);
        {
            std::lock_guard<std::mutex> guard(mutex);
            slot.buffer = old_buffer;
            slot.dsc = old_dsc;
            slot.dsc_valid = (old_buffer != nullptr);
        }
        // 把旧图绑回去，避免"一次渲染失败把屏幕打回默认底纹"。
        // 回绑本身也可能失败，日志必须按实际结果写，否则排查时会被带偏
        // （dsc_valid 保持 true 是有意的：缓冲仍在，下次 duplicate 可直接重绑，
        //   比降级成 kNoState 重新下载 115KB 便宜）。
        const bool restored = (old_buffer != nullptr) && bind_new(&slot.dsc);
        ESP_LOGW(TAG, "wallpaper: fail kind=%s version=%s reason=%s (rolled back to %s)",
                 KindName(request.kind), request.version.c_str(), kReasonRender,
                 restored ? "previous wallpaper"
                          : (old_buffer != nullptr ? "default (restore failed)" : "default background"));
        return false;
    }
    if (old_buffer != nullptr) {
        heap_caps_free(old_buffer);
    }
    {
        std::lock_guard<std::mutex> guard(mutex);
        slot.dsc_valid = true;
        slot.applied_version = request.version;
        slot.applied_url = request.url;
        slot.applied_md5 = request.md5;
    }
    ESP_LOGI(TAG, "wallpaper: bound kind=%s version=%s buf=%p to display",
             KindName(request.kind), request.version.c_str(),
             static_cast<void*>(slot.buffer));
    return true;
#endif  // WALLPAPER_HAS_LVGL_DISPLAY
}

// 显式命令命中幂等时把已缓存的图重新绑一次并触发重绘（不重新下载）。
// 场景：开机时 device_config 已经把这张图应用过，屏幕上却因为 splash 还盖着 / 主题
// 重建 / 上次 SetWallpaper 撞上锁超时而没真正显示出来。此时操作员点"下发"，
// 旧行为只回一行 already applied + ok，屏幕毫无变化 —— 用户看到的就是"下发了没反应"。
WallpaperManager::Impl::RebindResult WallpaperManager::Impl::RebindCurrent(
    WallpaperSlot& slot, const std::string& expected_version) {
#if !WALLPAPER_HAS_LVGL_DISPLAY
    // 防御性返回。注意这个分支实际不可达：无显示构建下 ApplyToDisplay 恒失败，
    // dsc_valid 恒为 false，HandleSet 的 duplicate 判定永远不会成立。
    // 真正的止损在 ProcessSet 开头（不下载直接回 no_display）。
    return RebindResult::kRenderFail;
#else
    Display* display = Board::GetInstance().GetDisplay();
    if (display == nullptr) {
        // 图在、显示不在：回落重新下载只会再撞一次 no_display，如实报渲染失败
        return RebindResult::kRenderFail;
    }
    // ★ 锁序：display → mutex，与 ApplyToDisplay 一致（那里也是先 DisplayLockGuard
    //   再 lock(mutex)）。反过来写就是 ABBA。
    //   而且版本校验必须落在显示锁**之内**：若在锁外校验，从"校验通过 A"到"取显示锁"
    //   之间，另一条 ApplyToDisplay 可能已经把 B 应用完，你再重绑 &dsc（内容已是 B）
    //   却按 A 回 ok —— 窗口只是变小，并没有消除。
    DisplayLockGuard lock(display);
    if (!lock) { return RebindResult::kRenderFail; }  // 拿不到 LVGL 锁，别碰对象树
    std::string version;
    {
        std::lock_guard<std::mutex> guard(mutex);
        // 版本必须仍然对得上：并发下可能已被别的请求换掉，绑错版本比不绑更糟
        // （屏幕停在 A，回执却按 B 记成功）。
        if (!slot.dsc_valid || slot.applied_version != expected_version) {
            return RebindResult::kNoState;
        }
        version = slot.applied_version;
    }
    const bool is_boot = (slot.kind == WallpaperKind::Boot);
    ESP_LOGI(TAG, "wallpaper: rebind kind=%s version=%s (idempotent hit -> force repaint)",
             KindName(slot.kind), version.c_str());
    const bool bound = is_boot ? display->SetBootWallpaper(&slot.dsc)
                               : display->SetWallpaper(&slot.dsc);
    if (!bound) {
        ESP_LOGW(TAG, "wallpaper: rebind kind=%s version=%s failed (reason=%s)",
                 KindName(slot.kind), version.c_str(), kReasonRender);
        return RebindResult::kRenderFail;
    }
    return RebindResult::kOk;
#endif  // WALLPAPER_HAS_LVGL_DISPLAY
}

void WallpaperManager::Impl::ProcessClear(WallpaperSlot& slot, WallpaperKind kind,
                                          const WallpaperResultCallback& callback) {
    ESP_LOGI(TAG, "wallpaper: apply clear kind=%s", KindName(kind));

#if WALLPAPER_HAS_LVGL_DISPLAY
    Display* display = Board::GetInstance().GetDisplay();
    if (display != nullptr) {
        // 先解除 LVGL 对缓冲的引用，再释放（FR-2.22）。
        // 解除失败就整个放弃：宁可留着壁纸，也不能 free 一块还在用的 PSRAM。
        const bool unbound = (kind == WallpaperKind::Boot) ? display->ClearBootWallpaper()
                                                           : display->ClearWallpaper();
        if (!unbound) {
            ESP_LOGW(TAG, "wallpaper: fail kind=%s reason=%s (cannot unbind image, keep it)",
                     KindName(kind), kReasonRender);
            if (callback) {
                callback(false, kReasonRender);
            }
            return;
        }
    }
#endif

    uint8_t* old_buffer = nullptr;
    {
        std::lock_guard<std::mutex> guard(mutex);
        old_buffer = slot.buffer;
        slot.buffer = nullptr;
        slot.dsc = lv_img_dsc_t{};
        slot.dsc_valid = false;
        slot.applied_version.clear();
        slot.applied_url.clear();
        slot.applied_md5.clear();
        slot.restore_version.clear();
    }
    if (old_buffer != nullptr) {
        heap_caps_free(old_buffer);
    }

    {
        // boot 槽独立 NVS namespace（与写入侧 ProcessSet 对称）
        Settings settings(kind == WallpaperKind::Boot ? "wallpaper_boot" : "wallpaper", true);
        settings.EraseKey("version");
        settings.EraseKey("url");
        settings.EraseKey("md5");
    }
    if (callback) {
        callback(true, "");
    }
}

WallpaperManager& WallpaperManager::GetInstance() {
    static WallpaperManager instance;
    return instance;
}

WallpaperManager::WallpaperManager() : impl_(new Impl()) {}

WallpaperManager::~WallpaperManager() {
    // 单例与进程同生命周期：后台任务永不退出，这里不释放状态，避免退出期悬空。
}

void WallpaperManager::HandleSet(const WallpaperRequest& request,
                                 WallpaperResultCallback on_result) {
    // 参数级快速失败（在调用者任务上下文里回执，省一次任务调度）
    if (request.url.empty() || request.md5.empty()) {
        ESP_LOGW(TAG, "wallpaper: fail kind=%s version=%s reason=%s (missing url/md5)",
                 Impl::KindName(request.kind), request.version.c_str(), kReasonBadFormat);
        if (on_result) {
            on_result(false, kReasonBadFormat);
        }
        return;
    }
    if (!impl_->EnsureWorker()) {
        if (on_result) {
            on_result(false, kReasonNoMem);
        }
        return;
    }

    WallpaperSlot& slot = impl_->slots[Impl::SlotIndexOf(request.kind)];

    // 幂等判定先做一次快照：命中后要么重绑，要么（图已不在了）回落成重新下载
    bool duplicate = false;
    {
        std::lock_guard<std::mutex> lock(impl_->mutex);
        duplicate = slot.dsc_valid && !request.version.empty() &&
                    request.version == slot.applied_version;
    }

    if (duplicate) {
        ESP_LOGI(TAG, "wallpaper: skip kind=%s version=%s (already applied)",
                 Impl::KindName(request.kind), request.version.c_str());
        // device_config / NVS 恢复（无回执）：纯幂等跳过，什么都不用做
        if (!on_result) {
            return;
        }
        // ★ 显式命令（WS / 常连通道下发，带回执）不静默丢弃：
        //   老行为只打一行日志就回 ok，于是「操作员点下发 → 设备回 ok → 屏幕没变」
        //   成了无法自救的死角（applied_version 一旦被写脏，之后全被这一支挡回）。
        //   现在先尝试把 PSRAM 里缓存的图重绑一次并标脏重绘，不重新下载。
        const Impl::RebindResult rebind = impl_->RebindCurrent(slot, request.version);
        if (rebind == Impl::RebindResult::kOk) {
            on_result(true, "");
            return;
        }
        if (rebind == Impl::RebindResult::kRenderFail) {
            // 重绑失败绝不回 ok：否则服务端认为成功、后台显示已生效，屏幕却没变
            on_result(false, kReasonRender);
            return;
        }
        // kNoState：缓存的图已经被别的路径释放了。回 ok 是撒谎，回 render_failed
        // 又会诱导重试拿到同样结果 —— 正确答案是当普通请求重新下载一次。
        ESP_LOGW(TAG, "wallpaper: idempotent hit but no cached image, fall back to re-download");
    }

    WallpaperResultCallback superseded;
    {
        std::lock_guard<std::mutex> lock(impl_->mutex);
        // 单槽 pending：后到覆盖先到。若前一条还挂着一个没人取走的回执回调，
        // 说明它根本不会被执行 —— 必须当场给它一个结论，否则那条 command_id
        // 的结果回执永远不发，服务端只能干等到超时（日志里表现为"下发了没反应"）。
        // 双槽后"单槽"指本壁纸槽：boot 下发不再顶掉 idle 的回执（反之亦然）。
        if (slot.pending && slot.pending_callback) {
            superseded = std::move(slot.pending_callback);
            slot.pending_callback = nullptr;
        }
        slot.pending = true;
        slot.pending_clear = false;
        slot.pending_request = request;
        // device_config（无回执）后到时不要覆盖 WS 请求的回执回调，
        // 否则 WS 侧永远等不到 result。
        if (on_result || !slot.pending_callback) {
            slot.pending_callback = std::move(on_result);
        }
    }
    if (superseded) {
        ESP_LOGW(TAG, "wallpaper: fail kind=%s reason=%s (previous request dropped by a newer one)",
                 Impl::KindName(request.kind), kReasonSuperseded);
        superseded(false, kReasonSuperseded);
    }
    xSemaphoreGive(impl_->wake);
}

void WallpaperManager::HandleClear(WallpaperKind kind, WallpaperResultCallback on_result) {
    if (!impl_->EnsureWorker()) {
        if (on_result) {
            on_result(false, kReasonNoMem);
        }
        return;
    }
    WallpaperSlot& slot = impl_->slots[Impl::SlotIndexOf(kind)];
    {
        std::lock_guard<std::mutex> lock(impl_->mutex);
        if (slot.pending && slot.pending_callback) {
            // 与 HandleSet 同理：被顶掉的请求必须当场给结论
            if (on_result) {
                auto superseded = std::move(slot.pending_callback);
                slot.pending_callback = nullptr;
                superseded(false, kReasonSuperseded);
            } else {
                slot.pending_callback = nullptr;
            }
        }
        slot.pending = true;
        slot.pending_clear = true;
        slot.pending_request = WallpaperRequest{};
        slot.pending_request.kind = kind;
        slot.pending_callback = std::move(on_result);
    }
    xSemaphoreGive(impl_->wake);
}

void WallpaperManager::HandleClear(WallpaperResultCallback on_result) {
    // 旧签名（无 kind）：待机壁纸清除，兼容存量调用方
    HandleClear(WallpaperKind::Idle, std::move(on_result));
}

void WallpaperManager::RestoreFromNvsAsync() {
    // 双槽各自恢复：boot 槽读独立 namespace "wallpaper_boot"。
    // 任一槽失败不影响另一槽（boot 图拉不到只是 splash 回落默认底纹）。
    static const WallpaperKind kRestoreKinds[] = {WallpaperKind::Idle, WallpaperKind::Boot};
    for (WallpaperKind kind : kRestoreKinds) {
        WallpaperRequest request;
        {
            Settings settings(kind == WallpaperKind::Boot ? "wallpaper_boot" : "wallpaper", false);
            request.version = settings.GetString("version");
            request.url = settings.GetString("url");
            request.md5 = settings.GetString("md5");
        }
        request.kind = kind;
        request.from_config = true;
        if (request.url.empty() || request.md5.empty()) {
            continue;
        }

        WallpaperSlot& slot = impl_->slots[Impl::SlotIndexOf(kind)];
        {
            std::lock_guard<std::mutex> lock(impl_->mutex);
            if (slot.dsc_valid && !request.version.empty() &&
                request.version == slot.applied_version) {
                continue;
            }
            // 本次开机已尝试过该版本（失败也不再反复重拉，避免重连风暴）
            if (!request.version.empty() && slot.restore_version == request.version) {
                continue;
            }
            if (slot.pending && !slot.pending_clear &&
                slot.pending_request.version == request.version) {
                continue;
            }
            if (!request.version.empty()) {
                slot.restore_version = request.version;
            }
        }

        ESP_LOGI(TAG, "wallpaper: restore from nvs kind=%s version=%s url=%s",
                 Impl::KindName(kind), request.version.c_str(), request.url.c_str());
        HandleSet(request, nullptr);
    }
}

std::string WallpaperManager::applied_version(WallpaperKind kind) {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    return impl_->slots[Impl::SlotIndexOf(kind)].applied_version;
}
