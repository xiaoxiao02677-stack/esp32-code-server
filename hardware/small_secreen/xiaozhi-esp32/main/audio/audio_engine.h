#ifndef AUDIO_ENGINE_H
#define AUDIO_ENGINE_H

#include <cstddef>
#include <cstdint>
#include <functional>
#include <string>
#include <vector>

#include <model_path.h>

#include "audio_codec.h"

class AudioEngine {
public:
    virtual ~AudioEngine() = default;

    virtual bool Initialize(AudioCodec* codec, int frame_duration_ms, srmodel_list_t* models_list) = 0;
    virtual void Feed(std::vector<int16_t>&& data) = 0;

    virtual void EnableWakeWordDetection(bool enable) = 0;
    virtual void EnableVoiceProcessing(bool enable) = 0;
    virtual void EnableDeviceAec(bool enable) = 0;

    virtual bool HasWakeWord() const = 0;
    virtual bool IsWakeWordDetectionEnabled() const = 0;
    virtual bool IsVoiceProcessingEnabled() const = 0;
    virtual bool IsAfeWakeWord() const = 0;
    virtual size_t GetFeedSize() const = 0;

    virtual void OnWakeWordDetected(std::function<void(const std::string& wake_word)> callback) = 0;
    virtual void OnOutput(std::function<void(std::vector<int16_t>&& data)> callback) = 0;
    virtual void OnVadStateChange(std::function<void(bool speaking)> callback) = 0;

    virtual void EncodeWakeWordData() = 0;
    virtual bool GetWakeWordOpus(std::vector<uint8_t>& opus) = 0;
    virtual const std::string& GetLastDetectedWakeWord() const = 0;

    // 服务器下发动态唤醒词（MultiNet 拼音短语）。默认实现返回 false：
    // 不支持动态命令表的引擎（WakeNet 单词模型）安全忽略。
    virtual bool UpdateWakeWordCommands(const std::vector<std::string>& pinyin_texts,
                                        const std::vector<std::string>& display_texts) {
        (void)pinyin_texts;
        (void)display_texts;
        return false;
    }
    // 当前引擎是否支持动态唤醒命令（MultiNet）
    virtual bool SupportsDynamicWakeWords() const { return false; }

    // 清空云端下发的唤醒词并恢复默认命令表（MultiNet 引擎支持；
    // 其他引擎默认返回 false 安全忽略）。同时删除 NVS 中的云端缓存。
    virtual bool ClearWakeWordCommands() { return false; }

    // 服务器动态调整唤醒词参数（阈值 0.01-1.0，时长 500-5000ms）
    virtual void SetThreshold(float threshold) { (void)threshold; }
    virtual void SetDuration(int duration) { (void)duration; }
};

#endif
