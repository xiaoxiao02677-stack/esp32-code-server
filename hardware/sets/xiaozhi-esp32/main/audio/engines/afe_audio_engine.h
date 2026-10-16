#ifndef AFE_AUDIO_ENGINE_H
#define AFE_AUDIO_ENGINE_H

#include "sdkconfig.h"

#include <atomic>
#include <condition_variable>
#include <deque>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include <esp_afe_sr_models.h>
#include <freertos/FreeRTOS.h>
#include <freertos/event_groups.h>
#include <freertos/task.h>

#include "audio_engine.h"
#include "wake_words/wake_word_audio_cache.h"

class CustomWakeWord;

class AfeAudioEngine : public AudioEngine {
public:
    AfeAudioEngine();
    ~AfeAudioEngine() override;

    bool Initialize(AudioCodec* codec, int frame_duration_ms, srmodel_list_t* models_list) override;
    void Feed(std::vector<int16_t>&& data) override;

    void EnableWakeWordDetection(bool enable) override;
    void EnableVoiceProcessing(bool enable) override;
    void EnableDeviceAec(bool enable) override;

    bool HasWakeWord() const override;
    bool IsWakeWordDetectionEnabled() const override;
    bool IsVoiceProcessingEnabled() const override;
    bool IsAfeWakeWord() const override { return HasWakeWord(); }
    size_t GetFeedSize() const override;

    void OnWakeWordDetected(std::function<void(const std::string& wake_word)> callback) override;
    void OnOutput(std::function<void(std::vector<int16_t>&& data)> callback) override;
    void OnVadStateChange(std::function<void(bool speaking)> callback) override;
    bool IsAecEffective() const override;

    void EncodeWakeWordData() override;
    bool GetWakeWordOpus(std::vector<uint8_t>& opus) override;
    const std::string& GetLastDetectedWakeWord() const override { return last_detected_wake_word_; }

    // 动态唤醒词（MultiNet）：仅当 custom_wake_word_（MultiNet 检测器）存在时支持
    bool UpdateWakeWordCommands(const std::vector<std::string>& pinyin_texts,
                                const std::vector<std::string>& display_texts) override;
    // 清空云端唤醒词并恢复默认命令表（MultiNet）
    bool ClearWakeWordCommands() override;
    bool SupportsDynamicWakeWords() const override { return custom_wake_word_ != nullptr; }

private:
    enum class WakeDetector {
        kNone,
        kWakeNet,
        kMultiNet,
    };

    static constexpr EventBits_t kWakeWordEnabled = 1 << 0;
    static constexpr EventBits_t kVoiceProcessingEnabled = 1 << 1;
    static constexpr EventBits_t kAfeActive = 1 << 2;
    static constexpr size_t kProcessingTaskStackSize = 4096;

    AudioCodec* codec_ = nullptr;
    srmodel_list_t* models_ = nullptr;
    bool owns_models_ = false;
    const esp_afe_sr_iface_t* afe_iface_ = nullptr;
    esp_afe_sr_data_t* afe_data_ = nullptr;
    EventGroupHandle_t event_group_ = nullptr;
    TaskHandle_t processing_task_ = nullptr;
    StaticTask_t* processing_task_buffer_ = nullptr;
    StackType_t* processing_task_stack_ = nullptr;
    int frame_samples_ = 0;
    bool is_speaking_ = false;
    // VAD 去抖：AFE 的 VAD 对残留回声极其敏感，TTS 播放时设备自己的声音会被判成
    // VAD_SPEECH，Application 随即触发"人声打断"把播报掐掉（表现为播到一半一声
    // "滴"后中断）。这里要求候选状态连续保持足够时长才真正翻转并上报，过滤掉
    // AEC 尚未收敛阶段与播放起停瞬态产生的几帧尖峰。
    bool vad_candidate_ = false;
    int64_t vad_candidate_since_us_ = 0;
    // 连续人声确认窗 / 连续静音确认窗，可通过 CONFIG_YH_VAD_*_CONFIRM_MS 调整。
    static constexpr int kVadSpeechConfirmMs = CONFIG_YH_VAD_SPEECH_CONFIRM_MS;
    static constexpr int kVadSilenceConfirmMs = CONFIG_YH_VAD_SILENCE_CONFIRM_MS;
    std::atomic<bool> device_aec_enabled_{false};
    // Deferred AFE buffer reset, performed by ProcessingTask (see UpdateActiveState)
    std::atomic<bool> reset_pending_{false};
    // Deferred WakeNet/AEC toggles, applied by ProcessingTask (see ApplyAfeControls)
    std::atomic<bool> afe_control_dirty_{false};
    // Deferred output_buffer_ clear, performed by the output-producing task
    std::atomic<bool> output_reset_pending_{false};
    // Incremented whenever an active AFE session is invalidated. ProcessingTask
    // uses it to reject a fetch result produced before a disable/re-enable cycle.
    std::atomic<uint32_t> control_generation_{0};
    WakeDetector wake_detector_ = WakeDetector::kNone;

    std::unique_ptr<CustomWakeWord> custom_wake_word_;
    std::vector<std::string> wake_words_;
    std::string last_detected_wake_word_;
    std::vector<int16_t> input_buffer_;
    std::vector<int16_t> output_buffer_;
    std::mutex input_buffer_mutex_;

    std::function<void(const std::string&)> wake_word_detected_callback_;
    std::function<void(std::vector<int16_t>&&)> output_callback_;
    std::function<void(bool)> vad_state_change_callback_;

    TaskHandle_t wake_word_encode_task_ = nullptr;
    StaticTask_t* wake_word_encode_task_buffer_ = nullptr;
    StackType_t* wake_word_encode_task_stack_ = nullptr;
    WakeWordAudioCache wake_word_audio_cache_;
    std::deque<std::vector<uint8_t>> wake_word_opus_;
    std::mutex wake_word_mutex_;
    std::condition_variable wake_word_cv_;

    void ProcessingTask();
    void UpdateActiveState();
    void UpdateAecState();
    void ApplyAfeControls();
    void ApplyPendingReset();
    void ResetVadState();
    void UpdateVadState(bool speech);
    void OutputRawAudio(const std::vector<int16_t>& data);
    void HandleWakeWordResult(const afe_fetch_result_t* result);
    void HandleVoiceResult(const afe_fetch_result_t* result);
};

#endif
