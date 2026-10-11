/*
 * server_link.h - 精简 WebSocket 客户端 + 服务器配置同步（预留扬声器/麦克风接口）
 *
 * 供 main 状态机对接：
 *   1. wifi 就绪后调用 server_link_start()（内部自动重试 3 次，间隔 5s）
 *   2. 轮询 server_link_get_state() 直到 SERVER_LINK_STATE_CONFIG_RECEIVED
 *      （或注册 on_config_received 回调）
 *   3. 用 server_link_get_config() 读取最新配置
 *   4. 退出时调用 server_link_stop()
 */
#ifndef SERVER_LINK_H
#define SERVER_LINK_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* 服务器 WebSocket 地址：可用 NVS 命名空间 "server"、key "url" 覆盖 */
#ifndef SERVER_WS_URL
#define SERVER_WS_URL "ws://sandyun.top:8001/xiaozhi/v1/"
#endif

/* 连接状态机 */
enum {
    SERVER_LINK_STATE_IDLE = 0,        /* 未启动 */
    SERVER_LINK_STATE_CONNECTING = 1,  /* 连接中（含自动重试期间） */
    SERVER_LINK_STATE_CONNECTED = 2,   /* TCP/WS 已连接，hello 已发出 */
    SERVER_LINK_STATE_CONFIG_RECEIVED = 3, /* 收到 device_config，握手+配置同步完成 */
    SERVER_LINK_STATE_FAILED = 4,      /* 重试 3 次仍失败，需上层介入（可再次 start） */
};

/* 接收缓冲区大小（精简：2KB） */
#ifndef SERVER_LINK_RX_BUF_SIZE
#define SERVER_LINK_RX_BUF_SIZE (2 * 1024)
#endif

/*
 * 服务器 device_config.payload 配置快照。
 * volume/brightness/wake_word 当前消费；speaker/microphone 相关为预留，
 * 解析到就填、上层暂不消费（上线后实现，见下方字段注释）。
 */
typedef struct {
    /* —— 当前消费字段 —— */
    int volume;             /* 0~100，缺省 -1 */
    int brightness;         /* 0~100，缺省 -1 */
    char wake_word[32];     /* 动态唤醒词（首个非空词），缺省空串 */

    /* —— 预留字段（上线后实现，暂不消费）—— */
    int speaker_volume;     /* 扬声器音量 0~100（server 下发 speaker.volume） */
    int mic_gain;           /* 麦克风增益 0~100（server 下发 microphone.gain） */
    char mic_type[16];      /* 麦克风类型，如 "pcm"/"opus" */
    char speaker_type[16];  /* 扬声器类型，如 "pcm"/"opus" */

    /* 服务器会话信息 */
    char session_id[40];    /* 服务器 hello 下发的 session_id */
} device_config_t;

/*
 * 启动连接（非阻塞，内部起 FreeRTOS 任务）。
 * URL 优先级：NVS("server","url") > SERVER_WS_URL 宏。
 * 已在运行则返回 -1；参数错误返回 -2；成功返回 0。
 */
int server_link_start(void);

/* 停止连接并释放资源（阻塞至任务退出） */
void server_link_stop(void);

/* 当前状态（enum，无锁读，仅用于轮询显示） */
int server_link_get_state(void);

/* 最新配置快照（线程安全拷贝）；未收到配置时返回 -1 */
int server_link_get_config(device_config_t *out_cfg);

/* 配置回调：收到完整 device_config 时在 server_link 任务上下文调用，
 * 亦会在握手后带 session_id（volume 等字段为缺省值）调用一次。
 * 注意：回调内不要做耗时/阻塞操作。*/
typedef void (*server_link_on_config_cb_t)(device_config_t *cfg);
void server_link_set_on_config(server_link_on_config_cb_t cb);

/*
 * —— 音频接口预留（上线后实现，当前为空实现）——
 * 本板无音频硬件；接入编解码器后：
 *   send_audio: 取麦克风帧（如 opus 60ms）二进制发送到服务器
 *   on_audio:   收到服务器二进制音频帧时回调（喂给扬声器解码播放）
 */
int server_link_send_audio(const uint8_t *data, size_t len);
typedef void (*server_link_on_audio_cb_t)(const uint8_t *data, size_t len);
void server_link_set_on_audio(server_link_on_audio_cb_t cb);

#ifdef __cplusplus
}
#endif

#endif /* SERVER_LINK_H */
