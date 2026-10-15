# ffmpeg 转码验证矩阵（修复方案数据支撑）

服务器：生产 sandyun.top，ffmpeg 6.1.1-3ubuntu5，libopus 已确认存在。
参数：`ffmpeg -y -v error -i <in> -ac 1 -ar 24000 -c:a libopus -b:a 32k <out>.ogg`

## 批量矩阵（真实损坏样本 41 个，全部带尾部 0xAA/0x55 垃圾）

| 指标 | 结果 |
|---|---|
| 转码成功 | **41/41 (100%)** |
| 声道 | 41/41 mono=1 |
| 时长偏差 | max **0.007s** / avg 0.007s（源 vs ogg） |
| 耗时 | avg 0.43s / max 0.77s（116KB 样本） |
| 尾部垃圾带入 | 无（垃圾在 LAME 结束标记后，转码自然丢弃） |

## 极端输入

| 输入 | ffmpeg 行为 | 结论 |
|---|---|---|
| ogg 尾部截断 100/500/2000B | ffprobe 仍出时长 18.0s | 截断不影响固件可播性判定（OggDemuxer 不要求 EOS）|
| 512B 纯 0xAA 垃圾 | rc=234 快速失败 | 正确拒绝 |
| 空文件 | rc=234 快速失败 | 正确拒绝 |

## 推荐参数（已用于补丁）

```
ffmpeg -y -v error -i IN -ac 1 -ar 24000 -c:a libopus -b:a 32k OUT.ogg
```

- 无需 `-fflags +discardcorrupt`：41 个真实损坏样本全部干净转码
- **校验前置有必要**：`ffprobe duration < 0.5s` 或 ffmpeg 探测 rc≠0 视为坏文件直接上抛（防止垃圾文件被转出空 ogg）
- 产物验证：OggS 页 + OpusHead + mono + 24kHz（固件支持档位：8k/12k/16k/24k/48k）

## 固件语义终验（模拟器）

| 对象 | 判定 |
|---|---|
| 6 个历史损坏 MP3 | NOT PLAYABLE ❌ NO_OGG_PAGE |
| /tmp/fix-test1.ogg（14.62s 转码产物） | PLAYABLE ✅ 17 页/732 包/14640ms |
| 线上新推送 topic-1792058396395-14c19fd13348.ogg | PLAYABLE ✅ 4 页/75 包/1500ms/24kHz |
