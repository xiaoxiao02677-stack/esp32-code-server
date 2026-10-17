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

// 回执失败原因（服务端按原值落库，见 yh/xiaozhi-server/core/utils/wallpaper_ack.py）
constexpr char kReasonBadFormat[] = "bad_format";
constexpr char kReasonSize[] = "size_mismatch";
constexpr char kReasonMd5[] = "md5_mismatch";
constexpr char kReasonDownload[] = "download_failed";
constexpr char kReasonNoMem[] = "no_mem";
constexpr char kReasonNoDisplay[] = "no_display";

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
struct WallpaperManager::Impl {
    std::mutex mutex;              // 保护下方全部状态
    SemaphoreHandle_t wake = nullptr;
    bool worker_started = false;

    // 待处理请求（单槽，后到覆盖先到）
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
    bool dsc_valid = false;

    // 本次开机已尝试过的 NVS 恢复版本（避免每次重连都重拉）
    std::string restore_version;

    static void TaskEntry(void* arg) { static_cast<Impl*>(arg)->Run(); }

    bool EnsureWorker();
    void Run();
    void ProcessSet(const WallpaperRequest& request, const WallpaperResultCallback& callback);
    void ProcessClear(const WallpaperResultCallback& callback);
    bool ApplyToDisplay(uint8_t* new_buffer, const WallpaperRequest& request);
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
            bool clear = false;
            WallpaperRequest request;
            WallpaperResultCallback callback;
            {
                std::lock_guard<std::mutex> lock(mutex);
                if (!pending) {
                    break;
                }
                clear = pending_clear;
                request = pending_request;
                callback = std::move(pending_callback);
                pending = false;
                pending_clear = false;
                pending_request = WallpaperRequest{};
                pending_callback = nullptr;
            }
            if (clear) {
                ProcessClear(callback);
            } else {
                ProcessSet(request, callback);
            }
        }
    }
}

void WallpaperManager::Impl::ProcessSet(const WallpaperRequest& request,
                                        const WallpaperResultCallback& callback) {
    auto finish = [&callback](bool ok, const char* reason) {
        if (callback) {
            callback(ok, reason);
        }
    };

    // NFR-5：排队期间前一个请求可能已经应用了同一版本
    bool duplicate = false;
    {
        std::lock_guard<std::mutex> lock(mutex);
        duplicate = dsc_valid && !request.version.empty() && request.version == applied_version;
    }
    if (duplicate) {
        ESP_LOGI(TAG, "wallpaper: skip version=%s (already applied)", request.version.c_str());
        finish(true, "");
        return;
    }

    // 校验链（不做任何屏幕改动，FR-2.14）
    if (!request.format.empty() && !EqualsIgnoreCase(request.format, "rgb565")) {
        ESP_LOGW(TAG, "wallpaper: fail version=%s reason=%s format=%s", request.version.c_str(),
                 kReasonBadFormat, request.format.c_str());
        finish(false, kReasonBadFormat);
        return;
    }
    if ((request.width != 0 && request.width != kWidth) ||
        (request.height != 0 && request.height != kHeight) ||
        (request.size != 0 && request.size != static_cast<int>(kImageBytes))) {
        ESP_LOGW(TAG, "wallpaper: fail version=%s reason=%s size=%d %dx%d", request.version.c_str(),
                 kReasonSize, request.size, request.width, request.height);
        finish(false, kReasonSize);
        return;
    }
    uint8_t expected_md5[ESP_ROM_MD5_DIGEST_LEN];
    if (!ParseMd5(request.md5, expected_md5)) {
        ESP_LOGW(TAG, "wallpaper: fail version=%s reason=%s md5=%s", request.version.c_str(),
                 kReasonBadFormat, request.md5.c_str());
        finish(false, kReasonBadFormat);
        return;
    }

    uint8_t* buffer = static_cast<uint8_t*>(
        heap_caps_malloc(kImageBytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    if (buffer == nullptr) {
        ESP_LOGE(TAG, "wallpaper: fail version=%s reason=%s (psram free=%u)",
                 request.version.c_str(), kReasonNoMem,
                 static_cast<unsigned>(heap_caps_get_free_size(MALLOC_CAP_SPIRAM)));
        finish(false, kReasonNoMem);
        return;
    }

    ESP_LOGI(TAG, "wallpaper: download start version=%s url=%s bytes=%u", request.version.c_str(),
             request.url.c_str(), static_cast<unsigned>(kImageBytes));

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
    ESP_LOGI(TAG, "wallpaper: verify version=%s md5=%s expect=%s", request.version.c_str(),
             actual_hex, request.md5.c_str());
    if (memcmp(actual_md5, expected_md5, ESP_ROM_MD5_DIGEST_LEN) != 0) {
        heap_caps_free(buffer);
        ESP_LOGW(TAG, "wallpaper: fail version=%s reason=%s", request.version.c_str(), kReasonMd5);
        finish(false, kReasonMd5);
        return;
    }

    ESP_LOGI(TAG, "wallpaper: apply version=%s source=%s", request.version.c_str(),
             request.from_config ? "config" : "ws");
    if (!ApplyToDisplay(buffer, request)) {
        ESP_LOGW(TAG, "wallpaper: fail version=%s reason=%s", request.version.c_str(),
                 kReasonNoDisplay);
        finish(false, kReasonNoDisplay);
        return;
    }

    {
        Settings settings("wallpaper", true);
        settings.SetString("version", request.version);
        settings.SetString("url", request.url);
        settings.SetString("md5", request.md5);
    }
    finish(true, "");
}

bool WallpaperManager::Impl::ApplyToDisplay(uint8_t* new_buffer,
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

    lv_img_dsc_t new_dsc{};
    new_dsc.header.magic = LV_IMAGE_HEADER_MAGIC;
    new_dsc.header.cf = LV_COLOR_FORMAT_RGB565;
    new_dsc.header.w = kWidth;
    new_dsc.header.h = kHeight;
    new_dsc.header.stride = kWidth * 2;
    new_dsc.data_size = static_cast<uint32_t>(kImageBytes);
    new_dsc.data = new_buffer;

    // 持显示锁完成"解除旧引用 -> 换新图"的原子切换：
    // 1) ClearWallpaper 先让 LVGL 不再引用旧缓冲（FR-2.22，防悬空）；
    // 2) 释放旧缓冲；
    // 3) SetWallpaper 绑定新图。
    // lvgl_port_lock 是递归锁，Display 内部再次加锁是安全的。
    DisplayLockGuard lock(display);
    display->ClearWallpaper();

    uint8_t* old_buffer = nullptr;
    {
        std::lock_guard<std::mutex> guard(mutex);
        old_buffer = buffer;
        buffer = new_buffer;
        dsc = new_dsc;
        dsc_valid = true;
        applied_version = request.version;
        applied_url = request.url;
        applied_md5 = request.md5;
    }
    if (old_buffer != nullptr) {
        heap_caps_free(old_buffer);
    }
    display->SetWallpaper(&dsc);
    return true;
#endif  // WALLPAPER_HAS_LVGL_DISPLAY
}

void WallpaperManager::Impl::ProcessClear(const WallpaperResultCallback& callback) {
    ESP_LOGI(TAG, "wallpaper: apply clear");

#if WALLPAPER_HAS_LVGL_DISPLAY
    Display* display = Board::GetInstance().GetDisplay();
    if (display != nullptr) {
        // 先解除 LVGL 对缓冲的引用，再释放（FR-2.22）
        display->ClearWallpaper();
    }
#endif

    uint8_t* old_buffer = nullptr;
    {
        std::lock_guard<std::mutex> guard(mutex);
        old_buffer = buffer;
        buffer = nullptr;
        dsc = lv_img_dsc_t{};
        dsc_valid = false;
        applied_version.clear();
        applied_url.clear();
        applied_md5.clear();
        restore_version.clear();
    }
    if (old_buffer != nullptr) {
        heap_caps_free(old_buffer);
    }

    {
        Settings settings("wallpaper", true);
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
        ESP_LOGW(TAG, "wallpaper: fail version=%s reason=%s (missing url/md5)",
                 request.version.c_str(), kReasonBadFormat);
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

    bool duplicate = false;
    {
        std::lock_guard<std::mutex> lock(impl_->mutex);
        duplicate = impl_->dsc_valid && !request.version.empty() &&
                    request.version == impl_->applied_version;
        if (!duplicate) {
            impl_->pending = true;
            impl_->pending_clear = false;
            impl_->pending_request = request;
            // device_config（无回执）后到时不要覆盖 WS 请求的回执回调，
            // 否则 WS 侧永远等不到 result。
            if (on_result || !impl_->pending_callback) {
                impl_->pending_callback = std::move(on_result);
            }
        }
    }
    if (duplicate) {
        ESP_LOGI(TAG, "wallpaper: skip version=%s (already applied)", request.version.c_str());
        if (on_result) {
            on_result(true, "");
        }
        return;
    }
    xSemaphoreGive(impl_->wake);
}

void WallpaperManager::HandleClear(WallpaperResultCallback on_result) {
    if (!impl_->EnsureWorker()) {
        if (on_result) {
            on_result(false, kReasonNoMem);
        }
        return;
    }
    {
        std::lock_guard<std::mutex> lock(impl_->mutex);
        impl_->pending = true;
        impl_->pending_clear = true;
        impl_->pending_request = WallpaperRequest{};
        impl_->pending_callback = std::move(on_result);
    }
    xSemaphoreGive(impl_->wake);
}

void WallpaperManager::RestoreFromNvsAsync() {
    WallpaperRequest request;
    {
        Settings settings("wallpaper", false);
        request.version = settings.GetString("version");
        request.url = settings.GetString("url");
        request.md5 = settings.GetString("md5");
    }
    request.from_config = true;
    if (request.url.empty() || request.md5.empty()) {
        return;
    }

    {
        std::lock_guard<std::mutex> lock(impl_->mutex);
        if (impl_->dsc_valid && !request.version.empty() &&
            request.version == impl_->applied_version) {
            return;
        }
        // 本次开机已尝试过该版本（失败也不再反复重拉，避免重连风暴）
        if (!request.version.empty() && impl_->restore_version == request.version) {
            return;
        }
        if (impl_->pending && !impl_->pending_clear &&
            impl_->pending_request.version == request.version) {
            return;
        }
        if (!request.version.empty()) {
            impl_->restore_version = request.version;
        }
    }

    ESP_LOGI(TAG, "wallpaper: restore from nvs version=%s url=%s", request.version.c_str(),
             request.url.c_str());
    HandleSet(request, nullptr);
}

std::string WallpaperManager::applied_version() {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    return impl_->applied_version;
}
