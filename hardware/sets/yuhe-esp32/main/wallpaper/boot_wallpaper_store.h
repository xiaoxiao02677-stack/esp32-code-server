#pragma once

// 开机壁纸 flash 持久化。
//
// 为什么需要它：开机壁纸的唯一展示面是 splash（品牌开机画面），而 splash 在
// SetupUI（联网前）就建好、时间同步后即收起。老方案图片只在 PSRAM（重启即丢）
// + NVS 只存 url/md5 元数据，每次开机都要"联网 → 下载 115KB → 和 splash 收起
// 赛跑"，下载几乎必输 —— 用户永远看不到自己设置的开机壁纸。
// 本模块把图片本体落 flash，下次开机 SetupUI 直接读，splash 首帧即用户图。
//
// 存哪里：复用 assets 分区**尾部** 128KB 作为自管区（16m 表 assets=8MB，当前
// 打包内容 ~4MB，尾部常年空闲）。不新增分区、不改分区表 —— OTA 只刷 app 分区，
// 本区域内容跨 OTA 保留。
//
// 与 assets 打包内容的互斥由数据判据保证（不依赖分区大小猜测）：读 assets 头
// （12B：files/checksum/len，见 assets.cc）算出 used = 12 + stored_len，Save/Load
// 都要求 used + 128KB <= 分区大小。4m 表（1MB assets）当前字体包 ~900KB，会被
// 此判据挡住 → 本机不适用 → 静默回落网络重拉路径（功能退化但不残废）。
//
// 布局（region = part->size - 128KB）：
//   [region + 0      ] header 扇区（4KB）：
//       [0..3]   magic "YBW1"
//       [4..7]   format version（=1）
//       [8..11]  image size（=115200）
//       [12..27] md5（16B 二进制）
//       [28..63] 保留（0xFF）
//   [region + 4096   ] image 数据（115200B，240x240 RGB565，与 WallpaperManager
//                       的 kImageBytes 严格一致 —— 改尺寸必须两边同步）
//
// 掉电安全：写序 = 擦 header（先毁 magic）→ 擦数据区 → 写数据 → 回读校验 →
// 写 header（最后落 magic）。任一步掉电，下次 Load 的 magic/MD5 校验都会把
// 半写状态判为"无图"，自愈回网络重拉路径（md5 坏数据还会顺手抹掉 header，
// 防止 Save 的"同图跳过"判据被坏数据骗过）。
//
// 擦写寿命：仅 boot 壁纸变更时写一次 128KB，天级频率远低于 flash 10 万次
// P/E 上限，不做磨损均衡。

#include <cstddef>
#include <cstdint>

namespace boot_wallpaper_store {

// 壁纸数据固定长度（240x240 RGB565）
constexpr size_t kImageDataBytes = 240 * 240 * 2;  // 115200

// 从 flash 读取并校验开机壁纸（同步，读 115KB + MD5 约 50ms，只应在开机
// SetupUI 早期调用一次）。
// 返回 PSRAM 缓冲（kImageDataBytes 字节，调用方接管：WallpaperManager boot 槽
// 把它当 slot.buffer 持有并负责释放）。out_md5 非 nullptr 时回填 16 字节二进制
// MD5（header 里记录的，即数据的真实摘要——已校验一致）。
// 无图 / 校验失败 / 分区不适用 / 内存不足 → nullptr（调用方静默回落网络路径）。
uint8_t* Load(uint8_t out_md5[16]);

// 把已通过 MD5 校验的壁纸数据持久化到 flash。同步执行（擦 30 扇区 + 写 +
// 回读，~百 ms 量级），设计上只在 WallpaperManager 后台任务调用，不卡 UI。
// 内部比对 flash 已有内容（header md5 相同即跳过，防无谓擦写）。失败仅打
// 日志：flash 只是下次开机的加速器，坏了回落网络重拉，不影响调用方本次
// "已应用"的状态记账。image/md5 为空指针等价 Erase。
void Save(const uint8_t* image, const uint8_t md5[16]);

// 抹掉 flash 中的开机壁纸（清除 boot 壁纸命令时调用）：只擦 header 扇区，
// magic 失效即无图；数据区留待下次 Save 覆盖。
void Erase();

}  // namespace boot_wallpaper_store
