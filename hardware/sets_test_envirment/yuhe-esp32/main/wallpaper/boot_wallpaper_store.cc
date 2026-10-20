#include "boot_wallpaper_store.h"

#include <esp_heap_caps.h>
#include <esp_log.h>
#include <esp_partition.h>
#include <esp_rom_md5.h>

#include <cstring>

#define TAG "YhBootWp"

namespace boot_wallpaper_store {
namespace {

constexpr char kMagic[4] = {'Y', 'B', 'W', '1'};
constexpr uint32_t kFormatVersion = 1;
constexpr size_t kHeaderSector = 4096;        // header 扇区（含数据区起始间隙）
constexpr size_t kRegionBytes = 128 * 1024;   // 整个自管区大小
constexpr size_t kHeaderSize = 64;            // 实际使用的 header 字节数

// assets 打包头 12B：files/checksum/len（见 assets.cc InitializePartition）
constexpr size_t kAssetsHeaderBytes = 12;
// 保险带：要求 assets 打包内容之外还有 ≥ 2 个 region 的余量
constexpr size_t kAssetsMargin = kRegionBytes * 2;

struct Header {
    char magic[4];
    uint32_t format_version;
    uint32_t image_size;
    uint8_t md5[16];
    uint8_t reserved[36];
};

static_assert(sizeof(Header) == 64, "header layout drifted");

// 找到 assets 分区并计算自管区地址。不适用（分区不存在 / 尾部余量不足）返回
// false —— 这不是错误：4m 板 assets=1MB，字体包 ~900KB，本来就不该启用本机制。
bool ResolveRegion(const esp_partition_t** out_part, size_t* out_region_offset) {
    const esp_partition_t* part = esp_partition_find_first(
        ESP_PARTITION_TYPE_ANY, ESP_PARTITION_SUBTYPE_ANY, "assets");
    if (part == nullptr) {
        return false;
    }
    if (part->size < kRegionBytes + kAssetsMargin) {
        return false;  // 小分区板（4m）：尾部余量不足，回落网络路径
    }
    // 读 assets 打包头算实际占用；读失败按"占满"处理（保守，不会误写）
    uint8_t assets_header[kAssetsHeaderBytes] = {};
    esp_err_t err = esp_partition_read(part, 0, assets_header, sizeof(assets_header));
    uint32_t stored_len = 0;
    if (err == ESP_OK) {
        memcpy(&stored_len, assets_header + 8, sizeof(stored_len));
    }
    const size_t used = (err == ESP_OK && stored_len != 0 &&
                         stored_len <= part->size - kAssetsHeaderBytes)
                            ? kAssetsHeaderBytes + static_cast<size_t>(stored_len)
                            : part->size;
    if (used + kAssetsMargin > part->size) {
        ESP_LOGW(TAG, "assets packed %u bytes, no room for boot wallpaper region",
                 static_cast<unsigned>(used));
        return false;
    }
    *out_part = part;
    *out_region_offset = part->size - kRegionBytes;
    return true;
}

bool HeaderIsValid(const Header& header) {
    return memcmp(header.magic, kMagic, sizeof(kMagic)) == 0 &&
           header.format_version == kFormatVersion &&
           header.image_size == kImageDataBytes;
}

void ComputeMd5(const uint8_t* data, size_t len, uint8_t out[16]) {
    md5_context_t ctx;
    esp_rom_md5_init(&ctx);
    esp_rom_md5_update(&ctx, data, static_cast<uint32_t>(len));
    esp_rom_md5_final(out, &ctx);
}

}  // namespace

uint8_t* Load(uint8_t out_md5[16]) {
    const esp_partition_t* part = nullptr;
    size_t region = 0;
    if (!ResolveRegion(&part, &region)) {
        return nullptr;
    }

    Header header{};
    if (esp_partition_read(part, region, &header, sizeof(header)) != ESP_OK ||
        !HeaderIsValid(header)) {
        return nullptr;  // 无图（首次开机/已清除/半写自愈）
    }

    uint8_t* buffer = static_cast<uint8_t*>(
        heap_caps_malloc(kImageDataBytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    if (buffer == nullptr) {
        ESP_LOGW(TAG, "no psram for boot wallpaper restore");
        return nullptr;
    }
    if (esp_partition_read(part, region + kHeaderSector, buffer, kImageDataBytes) != ESP_OK) {
        heap_caps_free(buffer);
        return nullptr;
    }

    uint8_t actual[16];
    ComputeMd5(buffer, kImageDataBytes, actual);
    if (memcmp(actual, header.md5, sizeof(actual)) != 0) {
        ESP_LOGW(TAG, "boot wallpaper md5 mismatch in flash, erase header");
        // 半写/位翻转的坏数据：抹掉 header 防止 Save 的"同图跳过"判据被骗过
        esp_partition_erase_range(part, region, kHeaderSector);
        heap_caps_free(buffer);
        return nullptr;
    }

    if (out_md5 != nullptr) {
        memcpy(out_md5, header.md5, 16);
    }
    ESP_LOGI(TAG, "boot wallpaper restored from flash (offset=0x%x md5 ok)",
             static_cast<unsigned>(region + kHeaderSector));
    return buffer;
}

void Save(const uint8_t* image, const uint8_t md5[16]) {
    const esp_partition_t* part = nullptr;
    size_t region = 0;
    if (!ResolveRegion(&part, &region)) {
        return;  // 分区不适用（4m 板）：静默，下次开机走网络重拉
    }
    if (image == nullptr || md5 == nullptr) {
        Erase();
        return;
    }

    // 同图跳过：header 完整且 md5 相同 → flash 里就是这张，不擦不写
    Header header{};
    if (esp_partition_read(part, region, &header, sizeof(header)) == ESP_OK &&
        HeaderIsValid(header) && memcmp(header.md5, md5, sizeof(header.md5)) == 0) {
        return;
    }

    ESP_LOGI(TAG, "saving boot wallpaper to flash (offset=0x%x)", static_cast<unsigned>(region));

    // 写序（掉电安全）：毁 header → 擦数据区 → 写数据 → 回读 → 落 header
    esp_err_t err = esp_partition_erase_range(part, region, kHeaderSector);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "erase header failed: %s", esp_err_to_name(err));
        return;
    }
    err = esp_partition_erase_range(part, region + kHeaderSector,
                                    (kImageDataBytes + kHeaderSector - 1) / kHeaderSector *
                                        kHeaderSector);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "erase image failed: %s", esp_err_to_name(err));
        return;
    }
    err = esp_partition_write(part, region + kHeaderSector, image, kImageDataBytes);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "write image failed: %s", esp_err_to_name(err));
        return;
    }

    // 回读校验：flash 写失败不总返回错误码，必须逐字节验证
    uint8_t* verify = static_cast<uint8_t*>(
        heap_caps_malloc(kImageDataBytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    if (verify == nullptr) {
        // 内存不足无法验证：不落 header（下次 Load 判无图），本次不重试
        ESP_LOGW(TAG, "no psram to verify, treat as unsaved");
        return;
    }
    const bool ok = esp_partition_read(part, region + kHeaderSector, verify,
                                       kImageDataBytes) == ESP_OK &&
                    memcmp(verify, image, kImageDataBytes) == 0;
    heap_caps_free(verify);
    if (!ok) {
        ESP_LOGE(TAG, "write verify failed, keep header erased");
        return;
    }

    Header fresh{};
    memcpy(fresh.magic, kMagic, sizeof(kMagic));
    fresh.format_version = kFormatVersion;
    fresh.image_size = kImageDataBytes;
    memcpy(fresh.md5, md5, sizeof(fresh.md5));
    err = esp_partition_write(part, region, &fresh, sizeof(fresh));
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "write header failed: %s", esp_err_to_name(err));
        return;
    }
    ESP_LOGI(TAG, "boot wallpaper saved (md5 ok, %u bytes)", static_cast<unsigned>(kImageDataBytes));
}

void Erase() {
    const esp_partition_t* part = nullptr;
    size_t region = 0;
    if (!ResolveRegion(&part, &region)) {
        return;
    }
    Header header{};
    if (esp_partition_read(part, region, &header, sizeof(header)) == ESP_OK &&
        HeaderIsValid(header)) {
        const esp_err_t err = esp_partition_erase_range(part, region, kHeaderSector);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "erase failed: %s", esp_err_to_name(err));
        } else {
            ESP_LOGI(TAG, "boot wallpaper erased from flash");
        }
    }
}

}  // namespace boot_wallpaper_store
